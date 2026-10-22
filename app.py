import os
import json
import webbrowser
import threading
from flask import Flask, render_template, request, jsonify, send_file
import io
import pymupdf as fitz
from converter import process_pdf_to_dxf, get_pdf_metadata_and_preview

template_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), 'templates'))
app = Flask(__name__, template_folder=template_dir)
app.config['MAX_CONTENT_LENGTH'] = 64 * 1024 * 1024  # Hasta 64 MB para planos de alta resolución


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/api/preview', methods=['POST'])
def preview_pdf():
    if 'pdf' not in request.files:
        return jsonify({'success': False, 'error': 'No se envió ningún archivo PDF'}), 400

    file = request.files['pdf']
    if not file.filename.lower().endswith('.pdf'):
        return jsonify({'success': False, 'error': 'El archivo debe ser un PDF'}), 400

    pdf_bytes = file.read()
    try:
        data = get_pdf_metadata_and_preview(pdf_bytes)
        return jsonify({'success': True, **data})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500


@app.route('/api/convert', methods=['POST'])
def convert_pdf():
    if 'pdf' not in request.files:
        return jsonify({'error': 'No se envió ningún archivo'}), 400

    file = request.files['pdf']
    units = request.form.get('units', 'm')
    scale_str = request.form.get('scale', 'auto')
    curve_mode = request.form.get('curve_mode', 'hybrid')
    force_raster = request.form.get('force_raster', 'false').lower() == 'true'

    manual_scale = None
    if scale_str != 'auto':
        try:
            parts = scale_str.replace("1:", "").replace("1/", "")
            manual_scale = float(parts)
        except ValueError:
            manual_scale = None

    pdf_bytes = file.read()
    try:
        dxf_bytes, stats = process_pdf_to_dxf(
            pdf_bytes=pdf_bytes,
            manual_scale=manual_scale,
            target_units=units,
            curve_mode=curve_mode,
            force_raster=force_raster
        )

        filename_base = os.path.splitext(file.filename)[0]
        dxf_filename = f"{filename_base}.dxf"

        response = send_file(
            io.BytesIO(dxf_bytes),
            mimetype='application/dxf',
            as_attachment=True,
            download_name=dxf_filename
        )
        response.headers['X-Stats'] = json.dumps(stats)
        response.headers['Access-Control-Expose-Headers'] = 'X-Stats'
        return response
    except Exception as e:
        return jsonify({'error': str(e)}), 500


def open_browser():
    webbrowser.open_new('http://127.0.0.1:5000')


if __name__ == '__main__':
    print("==========================================================")
    print(">> PDF to DWG / CAD Studio iniciado con exito")
    print(">> Servidor web disponible en: http://127.0.0.1:5000")
    print("==========================================================")
    # Abrir el navegador tras 1 segundo
    threading.Timer(1.0, open_browser).start()
    app.run(host='127.0.0.1', port=5000, debug=False)
