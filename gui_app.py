import os
import sys
# Bloquear layout de PyMuPDF para evitar errores de archivos ONNX ausentes
sys.modules['pymupdf.layout'] = None

import threading
import tkinter as tk
from tkinter import filedialog, messagebox
import customtkinter as ctk
from converter import process_pdf_to_dxf

# Configuración visual de CustomTkinter
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


class PdfToCadApp(ctk.CTk):
    def __init__(self):
        super().__init__()

        self.title("PDF a CAD (DXF) Studio - Desktop Edition")
        self.geometry("780x640")
        self.minsize(700, 580)

        # Variables de estado
        self.input_pdf_path = tk.StringVar(value="")
        self.output_dxf_path = tk.StringVar(value="")
        self.unit_var = tk.StringVar(value="m")
        self.scale_var = tk.StringVar(value="auto")
        self.curve_var = tk.StringVar(value="hybrid")
        self.force_raster_var = tk.BooleanVar(value=False)
        self.is_converting = False

        self.setup_ui()

    def setup_ui(self):
        # Header
        header_frame = ctk.CTkFrame(self, corner_radius=12, fg_color="#111827")
        header_frame.pack(fill="x", padx=20, pady=(16, 12))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="📐 PDF a CAD (DXF) Studio",
            font=ctk.CTkFont(size=20, weight="bold"),
            text_color="#38bdf8"
        )
        title_lbl.pack(anchor="w", padx=16, pady=(12, 2))

        sub_lbl = ctk.CTkLabel(
            header_frame,
            text="Conversor de planos pesados sin límites de tiempo | Soporte de Arcos, Splines y Escalas",
            font=ctk.CTkFont(size=12),
            text_color="#94a3b8"
        )
        sub_lbl.pack(anchor="w", padx=16, pady=(0, 12))

        # Main Content
        main_frame = ctk.CTkFrame(self, corner_radius=12)
        main_frame.pack(fill="both", expand=True, padx=20, pady=(0, 16))

        # 1. Selección de archivos
        files_box = ctk.CTkFrame(main_frame, fg_color="transparent")
        files_box.pack(fill="x", padx=16, pady=(14, 8))

        # PDF Entrada
        ctk.CTkLabel(files_box, text="Archivo PDF de entrada:", font=ctk.CTkFont(weight="bold")).grid(row=0, column=0, sticky="w", pady=(0, 4))
        self.entry_pdf = ctk.CTkEntry(files_box, textvariable=self.input_pdf_path, placeholder_text="Selecciona tu plano PDF...")
        self.entry_pdf.grid(row=1, column=0, sticky="ew", padx=(0, 10))
        btn_browse_pdf = ctk.CTkButton(files_box, text="Examinar...", width=110, command=self.browse_pdf)
        btn_browse_pdf.grid(row=1, column=1)

        # DXF Salida
        ctk.CTkLabel(files_box, text="Ruta del archivo DXF de salida:", font=ctk.CTkFont(weight="bold")).grid(row=2, column=0, sticky="w", pady=(10, 4))
        self.entry_dxf = ctk.CTkEntry(files_box, textvariable=self.output_dxf_path, placeholder_text="Ubicación de guardado...")
        self.entry_dxf.grid(row=3, column=0, sticky="ew", padx=(0, 10))
        btn_browse_dxf = ctk.CTkButton(files_box, text="Guardar como...", width=110, fg_color="#374151", command=self.browse_dxf)
        btn_browse_dxf.grid(row=3, column=1)

        files_box.columnconfigure(0, weight=1)

        # 2. Configuración de parámetros
        config_box = ctk.CTkFrame(main_frame, fg_color="#1e293b", corner_radius=10)
        config_box.pack(fill="x", padx=16, pady=8)

        grid_cfg = ctk.CTkFrame(config_box, fg_color="transparent")
        grid_cfg.pack(fill="x", padx=12, pady=12)

        # Unidad
        ctk.CTkLabel(grid_cfg, text="Unidad CAD:").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        ctk.CTkOptionMenu(
            grid_cfg,
            values=["m (Metros - Arquitectura)", "mm (Milímetros - Detalle)"],
            command=self.on_unit_change,
            width=180
        ).grid(row=0, column=1, sticky="w", padx=6, pady=4)

        # Escala
        ctk.CTkLabel(grid_cfg, text="Escala:").grid(row=0, column=2, sticky="w", padx=6, pady=4)
        self.scale_menu = ctk.CTkOptionMenu(
            grid_cfg,
            values=["auto (Detectar automáticamente)", "1:20", "1:25", "1:50", "1:75", "1:100", "1:200", "1:500", "1:1"],
            command=self.on_scale_change,
            width=180
        )
        self.scale_menu.grid(row=0, column=3, sticky="w", padx=6, pady=4)

        # Motor de Curvas
        ctk.CTkLabel(grid_cfg, text="Motor de Curvas:").grid(row=1, column=0, sticky="w", padx=6, pady=4)
        ctk.CTkOptionMenu(
            grid_cfg,
            values=["Híbrido (Arcos ARC + Splines)", "Polilínea Suavizada (LWPOLYLINE)", "Splines AutoCAD (SPLINE)"],
            command=self.on_curve_change,
            width=180
        ).grid(row=1, column=1, sticky="w", padx=6, pady=4)

        # Modo Escáner
        self.chk_raster = ctk.CTkSwitch(
            grid_cfg,
            text="Modo Escáner / Ráster (OpenCV)",
            variable=self.force_raster_var
        )
        self.chk_raster.grid(row=1, column=2, columnspan=2, sticky="w", padx=6, pady=4)

        # 3. Botón de Acción y Barra de Progreso
        action_frame = ctk.CTkFrame(main_frame, fg_color="transparent")
        action_frame.pack(fill="x", padx=16, pady=10)

        self.btn_convert = ctk.CTkButton(
            action_frame,
            text="⚡ Convertir Plano a DXF",
            font=ctk.CTkFont(size=14, weight="bold"),
            height=42,
            fg_color="#0284c7",
            hover_color="#0369a1",
            command=self.start_conversion
        )
        self.btn_convert.pack(fill="x", pady=(0, 8))

        self.progress_bar = ctk.CTkProgressBar(action_frame)
        self.progress_bar.set(0)
        self.progress_bar.pack(fill="x")

        # 4. Consola de registros (Logs en tiempo real)
        ctk.CTkLabel(main_frame, text="Registro de proceso:", font=ctk.CTkFont(size=11, weight="bold")).pack(anchor="w", padx=16, pady=(8, 2))
        self.txt_log = ctk.CTkTextbox(main_frame, height=130, font=ctk.CTkFont(family="Consolas", size=11))
        self.txt_log.pack(fill="both", expand=True, padx=16, pady=(0, 14))
        self.log("Listo. Selecciona un plano PDF para comenzar.")

    def log(self, text):
        self.txt_log.insert("end", f"> {text}\n")
        self.txt_log.see("end")

    def browse_pdf(self):
        path = filedialog.askopenfilename(
            title="Seleccionar Plano PDF",
            filetypes=[("Archivos PDF", "*.pdf"), ("Todos los archivos", "*.*")]
        )
        if path:
            self.input_pdf_path.set(path)
            # Sugerir ruta DXF en la misma carpeta
            default_dxf = os.path.splitext(path)[0] + ".dxf"
            self.output_dxf_path.set(default_dxf)
            size_mb = os.path.getsize(path) / (1024 * 1024)
            self.log(f"Plano cargado: {os.path.basename(path)} ({size_mb:.2f} MB)")

    def browse_dxf(self):
        path = filedialog.asksaveasfilename(
            title="Guardar archivo DXF",
            defaultextension=".dxf",
            filetypes=[("Archivo AutoCAD DXF", "*.dxf")]
        )
        if path:
            self.output_dxf_path.set(path)

    def on_unit_change(self, val):
        self.unit_var.set("m" if "m (" in val else "mm")

    def on_scale_change(self, val):
        self.scale_var.set("auto" if "auto" in val else val)

    def on_curve_change(self, val):
        if "Híbrido" in val:
            self.curve_var.set("hybrid")
        elif "Polilínea" in val:
            self.curve_var.set("polyline")
        else:
            self.curve_var.set("spline")

    def start_conversion(self):
        pdf_path = self.input_pdf_path.get().strip()
        dxf_path = self.output_dxf_path.get().strip()

        if not pdf_path or not os.path.exists(pdf_path):
            messagebox.showerror("Error", "Por favor selecciona un archivo PDF válido.")
            return

        if not dxf_path:
            messagebox.showerror("Error", "Por favor indica la ruta de guardado para el archivo DXF.")
            return

        if self.is_converting:
            return

        self.is_converting = True
        self.btn_convert.configure(state="disabled", text="Procesando plano...")
        self.progress_bar.set(0)
        self.progress_bar.start()

        # Ejecutar en segundo plano para no congelar la ventana
        threading.Thread(target=self._run_conversion, daemon=True).start()

    def _run_conversion(self):
        pdf_path = self.input_pdf_path.get()
        dxf_path = self.output_dxf_path.get()
        units = self.unit_var.get()
        scale_val = self.scale_var.get()
        curve_mode = self.curve_var.get()
        force_raster = self.force_raster_var.get()

        manual_scale = None
        if scale_val != "auto":
            try:
                parts = scale_val.replace("1:", "").replace("1/", "")
                manual_scale = float(parts)
            except ValueError:
                manual_scale = None

        try:
            self.log(f"Iniciando conversión de: {os.path.basename(pdf_path)}")
            with open(pdf_path, "rb") as f:
                pdf_bytes = f.read()

            res = process_pdf_to_dxf(
                pdf_bytes=pdf_bytes,
                manual_scale=manual_scale,
                target_units=units,
                curve_mode=curve_mode,
                force_raster=force_raster,
                log_callback=self.log
            )
            dxf_content = res[0]
            stats = res[1]

            with open(dxf_path, "wb") as f:
                f.write(dxf_content)

            total_v = (stats.get("lines", 0) + stats.get("arcs", 0) + stats.get("splines", 0) + stats.get("polylines", 0) + stats.get("raster_lines", 0))

            self.log(f"✅ ¡Conversión completada con éxito!")
            self.log(f"Resumen: {total_v} vectores generados | {stats.get('texts', 0)} textos extraídos.")
            self.log(f"Archivo guardado en: {dxf_path}")

            self.after(0, lambda: self._on_success(dxf_path))
        except Exception as e:
            self.log(f"❌ Error durante el proceso: {str(e)}")
            self.after(0, lambda: messagebox.showerror("Error", f"Ocurrió un error al convertir el plano:\n{str(e)}"))
        finally:
            self.is_converting = False
            self.after(0, self._reset_ui)

    def _on_success(self, dxf_path):
        resp = messagebox.askyesno(
            "Conversión Exitosa",
            f"El plano se ha convertido a DXF correctamente.\n\n¿Deseas abrir la carpeta contenedora?"
        )
        if resp:
            folder = os.path.dirname(os.path.abspath(dxf_path))
            os.startfile(folder)

    def _reset_ui(self):
        self.progress_bar.stop()
        self.progress_bar.set(1.0)
        self.btn_convert.configure(state="normal", text="⚡ Convertir Plano a DXF")


if __name__ == "__main__":
    import traceback
    try:
        app = PdfToCadApp()
        app.mainloop()
    except Exception as e:
        with open("error_startup.log", "w", encoding="utf-8") as f:
            traceback.print_exc(file=f)
        try:
            messagebox.showerror("Error de Inicio", f"Error al iniciar la aplicación:\n{str(e)}")
        except Exception:
            pass
