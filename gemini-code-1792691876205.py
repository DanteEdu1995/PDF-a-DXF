import pymupdf as fitz
import ezdxf
from ezdxf.math import Vec3
from ezdxf import units
import cv2
import numpy as np
import re
import argparse

# 1 punto PDF = 25.4 / 72 mm
PT_TO_MM = 25.4 / 72.0
PT_TO_M = PT_TO_MM / 1000.0


def detect_scale_from_text(page) -> float | None:
    """Busca menciones de escala como '1:50', '1:100', 'ESC: 1/50' en la página."""
    full_text = page.get_text()
    # Coincide con 1:50, 1:100, 1/200, Escala 1:25, etc.
    match = re.search(r"(?:escala|esc\.?|scale)?\s*1\s*[:/]\s*(\d+)", full_text, re.IGNORECASE)
    if match:
        denominator = float(match.group(1))
        if denominator > 0:
            return denominator
    return None


def calculate_scale_factor(scale_ratio: float, target_units: str) -> float:
    """Calcula el multiplicador para pasar de puntos PDF a la unidad real CAD."""
    if target_units.lower() == "m":
        # Puntos -> Metros en el papel -> Metros reales en terreno
        return PT_TO_M * scale_ratio
    else:  # "mm"
        # Puntos -> Milímetros en el papel -> Milímetros reales en terreno
        return PT_TO_MM * scale_ratio


def setup_dxf_layers_and_units(doc: ezdxf.document.Drawing, target_units: str):
    """Configura las variables internas de unidad del DXF y crea las capas."""
    # Asignar $INSUNITS para que AutoCAD/LibreCAD reconozca la unidad base
    if target_units.lower() == "m":
        doc.header["$INSUNITS"] = units.M
    else:
        doc.header["$INSUNITS"] = units.MM

    layers = [
        {"name": "TEXT", "color": 7},
        {"name": "VECTORES_LINEAS", "color": 3},
        {"name": "VECTORES_AREAS", "color": 1},
        {"name": "RASTER_EJES", "color": 4},
    ]
    for layer in layers:
        if layer["name"] not in doc.layers:
            doc.layers.add(name=layer["name"], color=layer["color"])


def skeletonize_image(gray_img: np.ndarray) -> np.ndarray:
    """Binariza y adelgaza la imagen a 1 px (Zhang-Suen)."""
    blurred = cv2.GaussianBlur(gray_img, (3, 3), 0)
    _, thresh = cv2.threshold(blurred, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    return cv2.ximgproc.thinning(thresh, thinningType=cv2.ximgproc.THINNING_ZHANGSUEN)


def vectorize_skeleton_page(page, msp, x_offset: float, scale_factor: float, dpi: int = 300):
    """Extrae ejes de planos escaneados aplicando el factor de escala."""
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)
    pix = page.get_pixmap(matrix=mat, alpha=False)

    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) if pix.n == 3 else img

    skeleton = skeletonize_image(gray)
    contours, _ = cv2.findContours(skeleton, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)

    # Conversión: píxeles a puntos PDF -> multiplicados por scale_factor
    pixel_to_cad = (1.0 / zoom) * scale_factor
    page_height = page.rect.height

    for cnt in contours:
        if cv2.arcLength(cnt, False) < 6:
            continue

        epsilon = 0.0015 * cv2.arcLength(cnt, False)
        approx = cv2.approxPolyDP(cnt, epsilon, closed=False)

        if len(approx) < 2:
            continue

        pts_dxf = []
        for pt in approx:
            px, py = pt[0]
            # Convertir pixel a punto, invertir eje Y, escalar y desplazar
            pt_y = page_height - (py / zoom)
            cad_x = ((px / zoom) * scale_factor) + x_offset
            cad_y = pt_y * scale_factor
            pts_dxf.append((cad_x, cad_y))

        msp.add_lwpolyline(pts_dxf, close=False, dxfattribs={"layer": "RASTER_EJES"})


def pdf_to_cad_scaled(pdf_path: str, dxf_path: str, manual_scale: float = None, target_units: str = "m", force_raster: bool = False):
    doc = fitz.open(pdf_path)
    dxf = ezdxf.new("R2010")
    setup_dxf_layers_and_units(dxf, target_units)
    msp = dxf.modelspace()

    x_offset = 0.0

    for page_num, page in enumerate(doc):
        # 1. Determinar escala para la página
        if manual_scale:
            ratio = manual_scale
            print(f"Página {page_num + 1}: Usando escala manual 1:{ratio:g}")
        else:
            detected = detect_scale_from_text(page)
            if detected:
                ratio = detected
                print(f"Página {page_num + 1}: Escala detectada automáticamente en texto: 1:{ratio:g}")
            else:
                ratio = 1.0  # Sin escala (escala 1:1 sobre el papel)
                print(f"Página {page_num + 1}: No se detectó escala. Usando 1:1 relativo.")

        factor = calculate_scale_factor(ratio, target_units)
        page_height = page.rect.height
        page_width = page.rect.width

        drawings = page.get_drawings()
        has_native_vectors = len(drawings) > 0 and not force_raster

        if has_native_vectors:
            for draw in drawings:
                is_filled = draw.get("fill") is not None
                layer = "VECTORES_AREAS" if is_filled else "VECTORES_LINEAS"

                for item in draw.get("items", []):
                    cmd = item[0]

                    if cmd == "l":
                        p1, p2 = item[1], item[2]
                        msp.add_line(
                            (p1.x * factor + x_offset, (page_height - p1.y) * factor),
                            (p2.x * factor + x_offset, (page_height - p2.y) * factor),
                            dxfattribs={"layer": layer},
                        )

                    elif cmd == "re":
                        r = item[1]
                        pts = [
                            (r.x0 * factor + x_offset, (page_height - r.y0) * factor),
                            (r.x1 * factor + x_offset, (page_height - r.y0) * factor),
                            (r.x1 * factor + x_offset, (page_height - r.y1) * factor),
                            (r.x0 * factor + x_offset, (page_height - r.y1) * factor),
                        ]
                        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})

                    elif cmd == "c":
                        p1, p2, p3, p4 = item[1], item[2], item[3], item[4]
                        control_points = [
                            Vec3(p1.x * factor + x_offset, (page_height - p1.y) * factor, 0),
                            Vec3(p2.x * factor + x_offset, (page_height - p2.y) * factor, 0),
                            Vec3(p3.x * factor + x_offset, (page_height - p3.y) * factor, 0),
                            Vec3(p4.x * factor + x_offset, (page_height - p4.y) * factor, 0),
                        ]
                        try:
                            msp.add_open_spline(control_points, degree=3, dxfattribs={"layer": layer})
                        except Exception:
                            from ezdxf.math import Bezier4P, Vec2
                            b = Bezier4P([Vec2(p.x, p.y) for p in control_points])
                            pts = b.approximate(16)
                            msp.add_lwpolyline([(pt.x, pt.y) for pt in pts], dxfattribs={"layer": layer})

                    elif cmd == "qu":
                        q = item[1]
                        pts = [
                            (q.ul.x * factor + x_offset, (page_height - q.ul.y) * factor),
                            (q.ur.x * factor + x_offset, (page_height - q.ur.y) * factor),
                            (q.lr.x * factor + x_offset, (page_height - q.lr.y) * factor),
                            (q.ll.x * factor + x_offset, (page_height - q.ll.y) * factor),
                        ]
                        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer})

            # Textos
            for b in page.get_text("blocks"):
                if b[6] == 0 and b[4].strip():
                    text_h = max(6.0, (b[3] - b[1]) * 0.5) * factor
                    msp.add_text(
                        b[4].strip(),
                        dxfattribs={
                            "layer": "TEXT",
                            "insert": (b[0] * factor + x_offset, (page_height - b[3]) * factor),
                            "height": text_h,
                        },
                    )
        else:
            print(f"Página {page_num + 1}: Esqueletizando escaneo con factor {factor:.6f}...")
            vectorize_skeleton_page(page, msp, x_offset, factor, dpi=300)

        # Separar la siguiente página en el espacio de modelo
        x_offset += (page_width * factor) + (5.0 if target_units == "m" else 500.0)

    dxf.saveas(dxf_path)
    print(f"DXF generado con unidades en [{target_units.upper()}]: {dxf_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Conversor de PDF a DXF con calibración de escala.")
    parser.add_argument("input", help="Ruta al archivo PDF")
    parser.add_argument("output", help="Ruta al archivo DXF de salida")
    parser.add_argument("--units", choices=["m", "mm"], default="m", help="Unidad destino en CAD (m o mm). Por defecto: m")
    parser.add_argument("--scale", type=str, help="Forzar escala (ej. '1:50', '1:100', '100'). Si no se indica, se autodetecta.")
    parser.add_argument("--force-raster", action="store_true", help="Forzar modo escáner/esqueletizado")

    args = parser.parse_args()

    scale_val = None
    if args.scale:
        parts = args.scale.replace("1:", "").replace("1/", "")
        scale_val = float(parts)

    pdf_to_cad_scaled(args.input, args.output, manual_scale=scale_val, target_units=args.units, force_raster=args.force_raster)