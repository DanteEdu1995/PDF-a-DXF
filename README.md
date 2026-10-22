# PDF a DXF / CAD Studio 📐🏛️

Conversor profesional de planos arquitectónicos e ingenieriles en formato **PDF a DXF (AutoCAD / LibreCAD)** con calibración de escala real, reconocimiento avanzado de curvas y una moderna interfaz gráfica web interactiva.

---

## ✨ Características Principales

- **Interfaz Gráfica Web Interactiva**: Carga planos mediante arrastrar y soltar (Drag & Drop), previsualización en tiempo real y descarga directa del archivo `.dxf`.
- **Extracción Vectorial Nativa**: Convierte líneas, rectángulos, cuadriláteros y áreas rellenas a capas CAD estandarizadas (`VECTORES_LINEAS`, `VECTORES_AREAS`, `TEXT`).
- **Reconocimiento Inteligente de Curvas**:
  - **Ajuste de Arcos (`ARC`)**: Detecta arcos circulares (puertas, vanos, chaflanes, radios de giro) y calcula su centro y radio exactos.
  - **Splines Nativas (`SPLINE`)**: Exporta curvas Bézier orgánicas a entidades SPLINE de grado 3 para AutoCAD.
  - **Polilíneas Suavizadas (`LWPOLYLINE`)**: Modo de alta compatibilidad para cortadoras láser, centros de mecanizado CNC y programas CAD antiguos.
- **Calibración y Detección de Escala**:
  - Detección automática en el texto del plano (ej. `1:50`, `1:100`, `1:200`, `1:25`, `1:500`).
  - Selección de escala manual y unidades base en **metros (`m`)** o **milímetros (`mm`)** con `$INSUNITS` configurado en el archivo DXF.
- **Vectorización de Planos Escaneados (Ráster a Vector)**:
  - Algoritmo de esqueletizado Zhang-Suen mediante OpenCV para extraer ejes en PDFs con imágenes físicas o escaneos a la capa `RASTER_EJES`.
- **Extracción de Textos**: Preserva rótulos, cotas y anotaciones de texto en su propia capa `TEXT`.

---

## 🚀 Instalación y Requisitos

### 1. Clonar el repositorio
```bash
git clone https://github.com/DanteEdu1995/PDF-a-DXF.git
cd PDF-a-DXF
```

### 2. Instalar dependencias
```bash
pip install -r requirements.txt
```

---

## 💻 Uso

### Opción 1: Interfaz Gráfica Web (Recomendado)

Ejecuta el servidor web local con:
```bash
python app.py
```
*O en Windows simplemente haz doble clic en `iniciar_interfaz.bat`.*

Abre tu navegador en:
👉 **http://127.0.0.1:5000**

1. Arrastra tu plano en formato `.pdf`.
2. Configura las unidades (`m` o `mm`), escala y el modo de curvas.
3. Haz clic en **"Convertir a DXF / CAD"** y descarga el archivo resultante.

---

### Opción 2: Línea de Comandos (CLI)

También puedes convertir archivos directamente por consola:

```bash
python gemini-code-1792691876205.py plano.pdf salida.dxf --units m --scale 1:50
```

#### Opciones CLI:
- `--units`: Unidad destino en CAD (`m` o `mm`). Por defecto: `m`.
- `--scale`: Forzar escala manual (ej. `1:50`, `1:100`, `100`). Si se omite, se autodetecta.
- `--force-raster`: Forzar vectorizado ráster / esqueletizado para escaneos.

---

## 📂 Estructura del Proyecto

```text
├── app.py                      # Servidor backend web Flask
├── converter.py                # Motor de conversión y análisis de curvas
├── templates/
│   └── index.html              # Interfaz web con drag & drop y vista previa
├── gemini-code-1792691876205.py# Script CLI original optimizado
├── iniciar_interfaz.bat        # Lanzador rápido en Windows
├── requirements.txt            # Dependencias del proyecto
└── README.md                   # Documentación
```

---

## 🛠️ Tecnologías Utilizadas

- **Python 3.11+**
- **PyMuPDF (`fitz`)**: Extracción de primitivas vectoriales, paths y rasterizado.
- **ezdxf**: Generación de documentos CAD DXF R2010 con soporte de Splines, Arcos y Polilíneas.
- **OpenCV & NumPy**: Procesamiento digital de imágenes y esqueletizado.
- **Flask**: Servidor web local ligero y responsivo.

---

## 📄 Licencia
Este proyecto está bajo la Licencia MIT.
