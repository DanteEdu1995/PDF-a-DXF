import io
import re
import math
import sys
sys.modules['pymupdf.layout'] = None
import pymupdf as fitz
import ezdxf
from ezdxf.math import Vec2, Vec3, Bezier4P
from ezdxf import units
import cv2
import numpy as np

# 1 punto PDF = 25.4 / 72 mm
PT_TO_MM = 25.4 / 72.0
PT_TO_M = PT_TO_MM / 1000.0


def detect_scale_from_text(page) -> float | None:
    """Busca menciones de escala como '1:50', '1:100', 'ESC: 1/50' en la página."""
    full_text = page.get_text()
    match = re.search(r"(?:escala|esc\.?|scale)?\s*1\s*[:/]\s*(\d+)", full_text, re.IGNORECASE)
    if match:
        denominator = float(match.group(1))
        if denominator > 0:
            return denominator
    return None


def calculate_scale_factor(scale_ratio: float, target_units: str) -> float:
    """Calcula el multiplicador para pasar de puntos PDF a la unidad real CAD."""
    if target_units.lower() == "m":
        return PT_TO_M * scale_ratio
    else:  # "mm"
        return PT_TO_MM * scale_ratio


def setup_dxf_layers_and_units(doc: ezdxf.document.Drawing, target_units: str):
    """Configura las variables internas de unidad del DXF y crea las capas."""
    if target_units.lower() == "m":
        doc.header["$INSUNITS"] = units.M
    else:
        doc.header["$INSUNITS"] = units.MM

    layers = [
        {"name": "TEXT", "color": 7},
        {"name": "VECTORES_LINEAS", "color": 3},
        {"name": "VECTORES_CURVAS", "color": 2},  # Amarillo para curvas y arcos
        {"name": "VECTORES_AREAS", "color": 1},
        {"name": "RASTER_EJES", "color": 4},
    ]
    for layer in layers:
        if layer["name"] not in doc.layers:
            doc.layers.add(name=layer["name"], color=layer["color"])


def try_fit_arc(p1: Vec2, p2: Vec2, p3: Vec2, p4: Vec2, tolerance: float = 0.02):
    """
    Intenta ajustar una curva Bézier cúbica a un arco circular.
    Retorna (center, radius, start_angle, end_angle) o None si no es circular.
    """
    bezier = Bezier4P([p1, p2, p3, p4])
    p_mid = bezier.point(0.5)

    # Centro de circunferencia que pasa por 3 puntos: p1, p_mid, p4
    d = 2 * (p1.x * (p_mid.y - p4.y) + p_mid.x * (p4.y - p1.y) + p4.x * (p1.y - p_mid.y))
    if abs(d) < 1e-6:
        return None  # Casi colineales (recta)

    p1_sq = p1.x**2 + p1.y**2
    pm_sq = p_mid.x**2 + p_mid.y**2
    p4_sq = p4.x**2 + p4.y**2

    cx = (p1_sq * (p_mid.y - p4.y) + pm_sq * (p4.y - p1.y) + p4_sq * (p1.y - p_mid.y)) / d
    cy = (p1_sq * (p4.x - p_mid.x) + pm_sq * (p1.x - p4.x) + p4_sq * (p_mid.x - p1.x)) / d
    center = Vec2(cx, cy)
    radius = (p1 - center).magnitude

    if radius < 1e-4:
        return None

    # Verificar error radial en puntos intermedios
    pt_25 = bezier.point(0.25)
    pt_75 = bezier.point(0.75)

    err1 = abs((pt_25 - center).magnitude - radius) / radius
    err2 = abs((pt_75 - center).magnitude - radius) / radius

    if max(err1, err2) <= tolerance:
        # Calcular ángulos en grados (0 a 360)
        a1 = math.degrees(math.atan2(p1.y - cy, p1.x - cx)) % 360
        a4 = math.degrees(math.atan2(p4.y - cy, p4.x - cx)) % 360

        # Determinar si el arco va en sentido antihorario (CCW) o horario (CW)
        vt = p2 - p1
        if vt.magnitude < 1e-6:
            vt = p4 - p1
        vr = p1 - center
        cross = vr.x * vt.y - vr.y * vt.x

        if cross >= 0:
            start_angle, end_angle = a1, a4
        else:
            start_angle, end_angle = a4, a1

        return center, radius, start_angle, end_angle

    return None


def add_curve_to_cad(msp, p1: Vec2, p2: Vec2, p3: Vec2, p4: Vec2, layer: str, curve_mode: str = "hybrid", stats: dict = None):
    """
    Agrega una curva Bézier al modelo CAD según el modo seleccionado:
    - 'hybrid': Arcos nativos si es circular, si no SPLINE o polilínea suavizada
    - 'spline': Siempre SPLINE nativa de AutoCAD
    - 'polyline': Polilínea suavizada con múltiples vértices (LWPOLYLINE)
    """
    # Si los 4 puntos están muy cerca o alineados como recta
    if (p4 - p1).magnitude < 1e-5:
        return

    bezier = Bezier4P([p1, p2, p3, p4])

    if curve_mode in ("hybrid", "arc"):
        arc_fit = try_fit_arc(p1, p2, p3, p4)
        if arc_fit:
            center, radius, start_ang, end_ang = arc_fit
            msp.add_arc(
                center=(center.x, center.y),
                radius=radius,
                start_angle=start_ang,
                end_angle=end_ang,
                dxfattribs={"layer": layer}
            )
            if stats:
                stats["arcs"] += 1
            return

    if curve_mode == "polyline":
        # Muestreo suave de 16 segmentos
        pts = bezier.approximate(segments=16)
        msp.add_lwpolyline([(pt.x, pt.y) for pt in pts], dxfattribs={"layer": layer})
        if stats:
            stats["polylines"] += 1
    else:
        # Modo SPLINE nativa CAD (degree 3)
        control_points = [
            Vec3(p1.x, p1.y, 0),
            Vec3(p2.x, p2.y, 0),
            Vec3(p3.x, p3.y, 0),
            Vec3(p4.x, p4.y, 0)
        ]
        try:
            msp.add_open_spline(control_points, degree=3, dxfattribs={"layer": layer})
            if stats:
                stats["splines"] += 1
        except Exception:
            # Fallback seguro a polilínea suavizada
            pts = bezier.approximate(segments=16)
            msp.add_lwpolyline([(pt.x, pt.y) for pt in pts], dxfattribs={"layer": layer})
            if stats:
                stats["polylines"] += 1


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
            pt_y = page_height - (py / zoom)
            cad_x = ((px / zoom) * scale_factor) + x_offset
            cad_y = pt_y * scale_factor
            pts_dxf.append((cad_x, cad_y))

        msp.add_lwpolyline(pts_dxf, close=False, dxfattribs={"layer": "RASTER_EJES"})


def process_pdf_to_dxf(
    pdf_bytes: bytes,
    manual_scale: float = None,
    target_units: str = "m",
    curve_mode: str = "hybrid",
    force_raster: bool = False,
    log_callback=None
):
    """
    Convierte bytes de PDF a bytes de DXF procesando líneas, rectángulos,
    curvas Bézier, arcos, splines y textos con calibración de escala precisa.
    """
    def log(msg):
        if log_callback:
            log_callback(msg)

    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    dxf = ezdxf.new("R2010")
    setup_dxf_layers_and_units(dxf, target_units)
    msp = dxf.modelspace()

    x_offset = 0.0
    stats = {
        "pages": len(doc),
        "lines": 0,
        "polylines": 0,
        "arcs": 0,
        "splines": 0,
        "texts": 0,
        "raster_lines": 0,
        "scales": []
    }

    def to_cad(pt, ph, sc, x_off):
        """Convierte punto PDF a coordenadas CAD (con inversión de eje Y)."""
        return Vec2(pt.x * sc + x_off, (ph - pt.y) * sc)

    for page_num, page in enumerate(doc):
        log(f"Procesando página {page_num + 1} de {len(doc)}...")
        if manual_scale:
            ratio = manual_scale
            log(f"Página {page_num + 1}: Usando escala personalizada 1:{ratio:g}")
        else:
            detected = detect_scale_from_text(page)
            if detected:
                ratio = detected
                log(f"Página {page_num + 1}: Escala detectada automáticamente: 1:{ratio:g}")
            else:
                ratio = 1.0
                log(f"Página {page_num + 1}: Sin escala explícita detectada (1:1 relativo).")

        stats["scales"].append(ratio)
        factor = calculate_scale_factor(ratio, target_units)
        page_height = page.rect.height
        page_width = page.rect.width

        drawings = page.get_drawings()
        has_native_vectors = len(drawings) > 0 and not force_raster

        if has_native_vectors:
            log(f"Página {page_num + 1}: Extrayendo {len(drawings)} paths vectoriales nativos...")
            for draw in drawings:
                is_filled = draw.get("fill") is not None
                layer_base = "VECTORES_AREAS" if is_filled else "VECTORES_LINEAS"

                for item in draw.get("items", []):
                    cmd = item[0]

                    if cmd == "l":
                        p1_cad = to_cad(item[1], page_height, factor, x_offset)
                        p2_cad = to_cad(item[2], page_height, factor, x_offset)
                        msp.add_line(
                            (p1_cad.x, p1_cad.y),
                            (p2_cad.x, p2_cad.y),
                            dxfattribs={"layer": layer_base},
                        )
                        stats["lines"] += 1

                    elif cmd == "c":
                        # Curva de Bézier cúbica: p1, p2, p3, p4
                        p1_cad = to_cad(item[1], page_height, factor, x_offset)
                        p2_cad = to_cad(item[2], page_height, factor, x_offset)
                        p3_cad = to_cad(item[3], page_height, factor, x_offset)
                        p4_cad = to_cad(item[4], page_height, factor, x_offset)

                        layer_curve = "VECTORES_AREAS" if is_filled else "VECTORES_CURVAS"
                        add_curve_to_cad(msp, p1_cad, p2_cad, p3_cad, p4_cad, layer_curve, curve_mode, stats)

                    elif cmd == "re":
                        r = item[1]
                        pts = [
                            (r.x0 * factor + x_offset, (page_height - r.y0) * factor),
                            (r.x1 * factor + x_offset, (page_height - r.y0) * factor),
                            (r.x1 * factor + x_offset, (page_height - r.y1) * factor),
                            (r.x0 * factor + x_offset, (page_height - r.y1) * factor),
                        ]
                        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer_base})
                        stats["polylines"] += 1

                    elif cmd == "qu":
                        q = item[1]
                        pts = [
                            (q.ul.x * factor + x_offset, (page_height - q.ul.y) * factor),
                            (q.ur.x * factor + x_offset, (page_height - q.ur.y) * factor),
                            (q.lr.x * factor + x_offset, (page_height - q.lr.y) * factor),
                            (q.ll.x * factor + x_offset, (page_height - q.ll.y) * factor),
                        ]
                        msp.add_lwpolyline(pts, close=True, dxfattribs={"layer": layer_base})
                        stats["polylines"] += 1

            # Textos
            for b in page.get_text("blocks"):
                if b[6] == 0 and b[4].strip():
                    text_h = max(4.0, (b[3] - b[1]) * 0.5) * factor
                    msp.add_text(
                        b[4].strip(),
                        dxfattribs={
                            "layer": "TEXT",
                            "insert": (b[0] * factor + x_offset, (page_height - b[3]) * factor),
                            "height": text_h,
                        },
                    )
                    stats["texts"] += 1
        else:
            log(f"Página {page_num + 1}: Esqueletizando imagen escaneada / ráster (OpenCV)...")
            initial_count = len(list(msp))
            vectorize_skeleton_page(page, msp, x_offset, factor, dpi=300)
            final_count = len(list(msp))
            stats["raster_lines"] += (final_count - initial_count)

        x_offset += (page_width * factor) + (5.0 if target_units == "m" else 500.0)

    # Exportar a stream
    out_stream = io.StringIO()
    dxf.write(out_stream)
    dxf_content = out_stream.getvalue().encode("utf-8")
    log("¡Conversión completada con éxito!")

    return dxf_content, stats


def get_pdf_metadata_and_preview(pdf_bytes: bytes):
    """Obtiene metadatos y primera página como imagen PNG en Base64 para previsualizar."""
    import base64
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_info = []

    total_curves = 0
    total_lines = 0

    for i, page in enumerate(doc):
        detected_scale = detect_scale_from_text(page)
        pages_info.append({
            "page": i + 1,
            "width_pt": round(page.rect.width, 2),
            "height_pt": round(page.rect.height, 2),
            "detected_scale": f"1:{detected_scale:g}" if detected_scale else "No detectada (1:1)"
        })

        for draw in page.get_drawings():
            for item in draw.get("items", []):
                if item[0] == "c":
                    total_curves += 1
                elif item[0] == "l":
                    total_lines += 1

    preview_base64 = None
    if len(doc) > 0:
        pix = doc[0].get_pixmap(dpi=150)
        img_bytes = pix.tobytes("png")
        preview_base64 = base64.b64encode(img_bytes).decode("ascii")

    return {
        "num_pages": len(doc),
        "pages": pages_info,
        "preview_img": preview_base64,
        "curve_count": total_curves,
        "line_count": total_lines
    }
