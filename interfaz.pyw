# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import filedialog, messagebox, scrolledtext
from tkinter import ttk
from PIL import Image, ImageTk, ImageSequence
import threading
import sys
import os
import pandas as pd
from tkinterdnd2 import TkinterDnD, DND_FILES

import main_sinergias_updated

APP_VERSION = "1.4"
# =====================================================================
# CLASES DE APOYO UI, CONSOLA Y VISOR DE IMAGENES
# =====================================================================
class RedireccionConsola(object):
    def __init__(self, text_widget):
        self.text_widget = text_widget
        
    def write(self, string):
        partes = string.split('**')
        for i, parte in enumerate(partes):
            if i % 2 == 1: 
                self.text_widget.insert(tk.END, parte, "bold")
            else:
                self.text_widget.insert(tk.END, parte)
        self.text_widget.see(tk.END)
        
    def flush(self): pass

class RoundedButton(tk.Canvas):
    def __init__(self, parent, text, color, width=200, height=45, command=None, bg_color="white"):
        super().__init__(parent, width=width, height=height, bg=bg_color, highlightthickness=0)
        self.command = command
        self.color = color
        self.text = text
        # --- MEJORA: Fórmula para curva de píldora perfecta ---
        self.radius = (height - 10) // 2 
        
        self.create_rounded_rectangle(7, 7, width - 3, height - 3, radius=self.radius, fill="#151b2b", outline="")
        self.rounded_rectangles = self.create_rounded_rectangle(5, 5, width - 5, height - 5, radius=self.radius, fill=color, outline=color)
        
        self.text_id_small = self.create_text(width // 2, height // 2, text=text, fill="white", font=("Segoe UI", 10, "bold"))
        self.text_id_large = self.create_text(width // 2, height // 2, text=text, fill="white", font=("Segoe UI", 11, "bold"))
        self.itemconfig(self.text_id_large, state="hidden")

        self.bind("<Button-1>", self.on_click)
        self.bind("<Enter>", self.on_enter)
        self.bind("<Leave>", self.on_leave)
        self.disabled = False

    def create_rounded_rectangle(self, x1, y1, x2, y2, radius=25, **kwargs):
        elements = []
        elements.append(self.create_arc(x1, y1, x1 + radius, y1 + radius, start=90, extent=90, **kwargs))
        elements.append(self.create_arc(x2 - radius, y1, x2, y1 + radius, start=0, extent=90, **kwargs))
        elements.append(self.create_arc(x1, y2 - radius, x1 + radius, y2, start=180, extent=90, **kwargs))
        elements.append(self.create_arc(x2 - radius, y2 - radius, x2, y2, start=270, extent=90, **kwargs))
        elements.append(self.create_rectangle(x1 + radius / 2, y1, x2 - radius / 2, y2, **kwargs))
        elements.append(self.create_rectangle(x1, y1 + radius / 2, x2, y2 - radius / 2, **kwargs))
        return elements

    def on_click(self, event):
        if self.command and not self.disabled: self.command()

    def on_enter(self, event):
        if not self.disabled:
            self.itemconfig(self.text_id_small, state="hidden")
            self.itemconfig(self.text_id_large, state="normal")
            self.config(cursor="hand2")

    def on_leave(self, event):
        if not self.disabled:
            self.itemconfig(self.text_id_small, state="normal")
            self.itemconfig(self.text_id_large, state="hidden")
            self.config(cursor="")

    def change_button_color(self, new_color):
        for element in self.rounded_rectangles: self.itemconfig(element, fill=new_color, outline=new_color)

    def disable_button(self):
        if not self.disabled:
            self.disabled = True
            self.change_button_color("#7E807E")

    def enable_button(self):
        if self.disabled:
            self.disabled = False
            self.change_button_color(self.color)

class AnimatedGifLabel(tk.Label):
    def __init__(self, master, path, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self.path = path
        self.frames = []
        self.delay = 100
        self.current_frame = 0
        self.is_running = False
        self.load_frames()

    def load_frames(self):
        try:
            if os.path.exists(self.path):
                img = Image.open(self.path)
                for frame in ImageSequence.Iterator(img):
                    self.frames.append(ImageTk.PhotoImage(frame.copy().convert('RGBA')))
                if 'duration' in img.info: self.delay = int(img.info['duration'] * 2.5)
                else: self.delay = 150 
        except Exception as e:
            pass

    def start(self):
        if not self.frames: return
        self.is_running = True
        self.update_frame()

    def stop(self): self.is_running = False

    def update_frame(self):
        if not self.is_running: return
        self.config(image=self.frames[self.current_frame])
        self.current_frame = (self.current_frame + 1) % len(self.frames)
        self.after(self.delay, self.update_frame)

class VisorDiagramasPanZoom(tk.Frame):
    def __init__(self, master):
        super().__init__(master, bg="#ffffff")
        self.canvas = tk.Canvas(self, bg="#e6e4e1", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.orig_img = None
        self.tk_img = None
        self.img_id = None
        self.scale = 1.0
        
        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<MouseWheel>", self.on_zoom)
        self.canvas.bind("<Button-4>", self.on_zoom) 
        self.canvas.bind("<Button-5>", self.on_zoom) 
        self.canvas.bind("<Configure>", lambda e: self.redraw_debounced())
        
        self.offset_x = 0
        self.offset_y = 0
        self.last_x = 0
        self.last_y = 0
        self._after_id = None

    def load_image(self, path):
        if not os.path.exists(path):
            self.canvas.delete("all")
            self.canvas.create_text(400, 300, text=f"Imagen no encontrada:\n{path}\nPor favor, guarde la imagen en la carpeta 'resources'.", font=("Segoe UI", 12), justify="center")
            self.orig_img = None
            return
            
        self.orig_img = Image.open(path)
        self.scale = 1.0
        self.offset_x = 0
        self.offset_y = 0
        
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w > 10 and self.orig_img.width > canvas_w:
            self.scale = canvas_w / self.orig_img.width
            
        self.redraw()

    def redraw_debounced(self):
        if self._after_id: self.after_cancel(self._after_id)
        self._after_id = self.after(50, self.redraw)

    def redraw(self):
        if not self.orig_img: return
        canvas_w = self.canvas.winfo_width()
        canvas_h = self.canvas.winfo_height()
        if canvas_w <= 1 or canvas_h <= 1: return

        x0 = -self.offset_x / self.scale
        y0 = -self.offset_y / self.scale
        x1 = x0 + canvas_w / self.scale
        y1 = y0 + canvas_h / self.scale
        
        orig_w, orig_h = self.orig_img.size
        crop_x0, crop_y0 = max(0, int(x0)), max(0, int(y0))
        crop_x1, crop_y1 = min(orig_w, int(x1)), min(orig_h, int(y1))
        
        if crop_x1 <= crop_x0 or crop_y1 <= crop_y0:
            self.canvas.delete("all")
            return

        cropped = self.orig_img.crop((crop_x0, crop_y0, crop_x1, crop_y1))
        disp_w = int((crop_x1 - crop_x0) * self.scale)
        disp_h = int((crop_y1 - crop_y0) * self.scale)
        
        if disp_w <= 0 or disp_h <= 0: return

        resized = cropped.resize((disp_w, disp_h), Image.LANCZOS if self.scale < 1 else Image.NEAREST)
        self.tk_img = ImageTk.PhotoImage(resized)
        
        self.canvas.delete("all")
        draw_x = crop_x0 * self.scale + self.offset_x
        draw_y = crop_y0 * self.scale + self.offset_y
        self.img_id = self.canvas.create_image(draw_x, draw_y, anchor="nw", image=self.tk_img)

    def on_press(self, event):
        self.last_x = event.x
        self.last_y = event.y

    def on_drag(self, event):
        dx = event.x - self.last_x
        dy = event.y - self.last_y
        self.offset_x += dx
        self.offset_y += dy
        self.last_x = event.x
        self.last_y = event.y
        self.redraw_debounced()

    def on_zoom(self, event):
        if getattr(event, 'num', 0) == 4 or getattr(event, 'delta', 0) > 0: factor = 1.15
        elif getattr(event, 'num', 0) == 5 or getattr(event, 'delta', 0) < 0: factor = 0.85
        else: return

        new_scale = self.scale * factor
        if new_scale > 10.0 or new_scale < 0.05: return
        
        rel_x = (event.x - self.offset_x) / self.scale
        rel_y = (event.y - self.offset_y) / self.scale
        
        self.scale = new_scale
        self.offset_x = event.x - rel_x * self.scale
        self.offset_y = event.y - rel_y * self.scale
        
        self.redraw_debounced()


# =====================================================================
# APLICACION PRINCIPAL
# =====================================================================
class AppSinergias:
    def __init__(self, root):
        self.root = root
        self.root.title("Validador de Sinergias")
        
        try: self.root.state('zoomed')
        except: self.root.geometry("1400x850")
        self.root.resizable(True, True)
        # --- MEJORA ESTÉTICA: Fondo más suave ---
        self.root.configure(bg="#F3F4F6")
        
        self.directorio_base = os.path.dirname(os.path.abspath(__file__))
        self.directorio_datos = os.path.join(self.directorio_base, "data")
        self.carpeta_outputs = os.path.join(self.directorio_base, "outputs")
        
        self.archivos_esperados = {
            "Análisis de PD": "plantilla_analisis_PD.xlsx",
            "PD": "plantilla_PD.xlsx",
            "Operaciones": "plantilla_extracto_operaciones.xlsx",
            "Prioridades": "WP y SOURCES A400.xlsx",
            "Smart_Kits": "SMART_KITS.xlsx",
            "Add Works": "Add-Works Catalogue Data.xlsx",
            "Catalogo OCCAR": "Referencias de Catálogo OCCAR.xlsx"
        }
        
        self.rutas_archivos = {}
        self.entradas_ui = {}
        self.labels_popup = {}
        
        self.datos_cargados = False
        self.categoria_actual = "Todas"
        
        self.decisiones = {
            "aprobadas": set(),        
            "rechazadas": set(),       
            "forzadas_estacion": set() 
        }
        
        self.listas_orig = {"Todas": [], "Cumplimentadas": [], "Sin Sinergia": [], "Descartadas": [], "DistintaEstacion": []}
        self.listas_dinamicas = {
            "Todas": [], "Cumplimentadas": [], "Definitivas": [], "Cotizaciones": [], "Logica": [],
            "Sin_Sinergia": [], "Sinergiadas_DistintaEst": [], 
            "Descartadas_Fase0": [], "Descartadas_Usuario": []
        }
        
        self.simulador_data = {}
        self.mapa_padre_hijas = {}
        self.mapa_hija_padre = {}
        self.mapa_ignoradas = {}
        self.raw_data = {"ops": None, "lanz": None, "quot": None}
        self.datos_cotizaciones = {} 

        # [INSERCIÓN]: Variables en memoria para exportación en red y gestión del botón masivo
        self.df_resultados_finales = None
        self.btn_cump_todas = None

        self.crear_interfaz()
        self.autodetectar_archivos()
        self.root.after(500, self.mostrar_splash_screen)

    def centrar_ventana(self, ventana, ancho, alto):
        ventana.update_idletasks()
        ancho_pantalla = ventana.winfo_screenwidth()
        alto_pantalla = ventana.winfo_screenheight()
        x = (ancho_pantalla // 2) - (ancho // 2)
        y = (alto_pantalla // 2) - (alto // 2)
        ventana.geometry(f"{ancho}x{alto}+{x}+{y}")

    def crear_interfaz(self):

    # --- MEJORA VISUAL: MOTOR DE ESTILO MODERNO (FLAT DESIGN) ---
        style = ttk.Style()
        if "clam" in style.theme_names():
            style.theme_use("clam")
        
        # Suavizamos el menú desplegable (Combobox)
        style.configure("TCombobox", padding=5, relief="flat")
        style.map("TCombobox", fieldbackground=[("readonly", "#f8f9fa")], bordercolor=[("focus", "#0078D4")])
        # ------------------------------------------------------------

        self.root.grid_columnconfigure(1, weight=1)
        self.root.grid_rowconfigure(0, weight=1)

        sidebar = tk.Frame(self.root, bg="#00205b", width=360)
        sidebar.grid(row=0, column=0, sticky="nesw")
        sidebar.grid_propagate(False)

        title_label = tk.Label(sidebar, text="PROGRAMA\nCUMPLIMENTADAS", fg="white", bg="#00205b", font=("Segoe UI", 20, "bold"))
        title_label.pack(pady=30)

        frame_archivos = tk.LabelFrame(sidebar, text=" ARCHIVOS DETECTADOS ", fg="#d4d4d4", bg="#00205b", font=("Segoe UI", 11, "bold"), bd=2, relief="groove")
        frame_archivos.pack(fill="x", padx=15, pady=10, ipadx=5, ipady=10)

        # --- ACTUALIZACIÓN DE SELECTORES PARA QUE COINCIDAN CON LAS NUEVAS CLAVES ---
        self.crear_selector(frame_archivos, "Análisis de PD:", "Análisis de PD")
        self.crear_selector(frame_archivos, "PD:", "PD")
        self.crear_selector(frame_archivos, "Operaciones:", "Operaciones")
        self.crear_selector(frame_archivos, "Prioridades:", "Prioridades")
        self.crear_selector(frame_archivos, "Smart Kits:", "Smart_Kits")
        self.crear_selector(frame_archivos, "Add Works:", "Add Works")
        self.crear_selector(frame_archivos, "Cat. OCCAR:", "Catalogo OCCAR")

        lbl_ejecutar_info = tk.Label(sidebar, text="Pulse para procesar las sinergias\ndel evento actual:", fg="#d4d4d4", bg="#00205b", font=("Segoe UI", 10), justify="center")
        lbl_ejecutar_info.pack(pady=(40, 5))

        frame_boton_centro = tk.Frame(sidebar, bg="#00205b")
        frame_boton_centro.pack(fill="x")
        # --- MEJORA ESTÉTICA: Color de botón vibrante ---
        self.btn_ejecutar = RoundedButton(frame_boton_centro, "🚀 Ejecutar Análisis", "#0078D4", width=240, height=50, bg_color="#00205b", command=self.iniciar_ejecucion)
        self.btn_ejecutar.pack(anchor="center")

        main_frame = tk.Frame(self.root, bg="#F3F4F6")
        main_frame.grid(row=0, column=1, sticky="nsew", padx=20, pady=15)
        main_frame.grid_columnconfigure(0, weight=1)
        main_frame.grid_rowconfigure(3, weight=1)

        top_frame = tk.Frame(main_frame, bg="#F3F4F6")
        top_frame.grid(row=0, column=0, sticky="we", pady=(0, 5))
        top_frame.grid_columnconfigure(8, weight=1) 

        btn_font = ("Segoe UI", 9, "bold")
        
        def on_enter_btn(e, hover_color): e.widget.config(bg=hover_color)
        def on_leave_btn(e, normal_color): e.widget.config(bg=normal_color)

        # --- MEJORA ESTÉTICA: Paleta de colores moderna corporativa ---
        color_todas = "#34495E"
        color_pendientes = "#D35400"
        color_definitivas = "#27AE60"
        color_cotizaciones = "#8E44AD"
        color_sin_sinergia = "#7F8C8D"
        color_descartadas = "#C0392B"
        color_logica = "#2980B9"

        self.btn_t = tk.Button(top_frame, text="Todas (0)", width=10, command=lambda: self.mostrar_lista("Todas"), bg=color_todas, fg="white", font=btn_font, relief="flat", cursor="hand2")
        self.btn_c = tk.Button(top_frame, text="Pendientes (0)", width=12, command=lambda: self.mostrar_lista("Cumplimentadas"), bg=color_pendientes, fg="white", font=btn_font, relief="flat", cursor="hand2")
        self.btn_def = tk.Button(top_frame, text="Definitivas (0)", width=12, command=lambda: self.mostrar_lista("Definitivas"), bg=color_definitivas, fg="white", font=btn_font, relief="flat", cursor="hand2")
        self.btn_cot = tk.Button(top_frame, text="Cotizaciones (0)", width=14, command=lambda: self.mostrar_lista("Cotizaciones"), bg=color_cotizaciones, fg="white", font=btn_font, relief="flat", cursor="hand2")
        self.btn_e = tk.Button(top_frame, text="Sin Sinergia (0)", width=14, command=lambda: self.mostrar_lista("Sin Sinergia"), bg=color_sin_sinergia, fg="white", font=btn_font, relief="flat", cursor="hand2")
        self.btn_d = tk.Button(top_frame, text="Descartadas (0)", width=14, command=lambda: self.mostrar_lista("Descartadas"), bg=color_descartadas, fg="white", font=btn_font, relief="flat", cursor="hand2")
        self.btn_log = tk.Button(top_frame, text="Lógica del Programa", width=18, command=lambda: self.mostrar_lista("Logica"), bg=color_logica, fg="white", font=btn_font, relief="flat", cursor="hand2")

        self.btn_t.bind("<Enter>", lambda e: on_enter_btn(e, "#2C3E50"))
        self.btn_t.bind("<Leave>", lambda e: on_leave_btn(e, color_todas))
        self.btn_c.bind("<Enter>", lambda e: on_enter_btn(e, "#E67E22"))
        self.btn_c.bind("<Leave>", lambda e: on_leave_btn(e, color_pendientes))
        self.btn_def.bind("<Enter>", lambda e: on_enter_btn(e, "#2ECC71"))
        self.btn_def.bind("<Leave>", lambda e: on_leave_btn(e, color_definitivas))
        self.btn_cot.bind("<Enter>", lambda e: on_enter_btn(e, "#9B59B6"))
        self.btn_cot.bind("<Leave>", lambda e: on_leave_btn(e, color_cotizaciones))
        self.btn_e.bind("<Enter>", lambda e: on_enter_btn(e, "#95A5A6"))
        self.btn_e.bind("<Leave>", lambda e: on_leave_btn(e, color_sin_sinergia))
        self.btn_d.bind("<Enter>", lambda e: on_enter_btn(e, "#E74C3C"))
        self.btn_d.bind("<Leave>", lambda e: on_leave_btn(e, color_descartadas))
        self.btn_log.bind("<Enter>", lambda e: on_enter_btn(e, "#3498DB"))
        self.btn_log.bind("<Leave>", lambda e: on_leave_btn(e, color_logica))

        self.btn_t.grid(row=0, column=0, padx=2, pady=5)
        self.btn_c.grid(row=0, column=1, padx=2, pady=5)
        self.btn_def.grid(row=0, column=2, padx=2, pady=5)
        self.btn_cot.grid(row=0, column=3, padx=2, pady=5)
        self.btn_e.grid(row=0, column=4, padx=2, pady=5)
        self.btn_d.grid(row=0, column=5, padx=2, pady=5)
        self.btn_log.grid(row=0, column=6, padx=2, pady=5)

        try:
            ruta_logo = os.path.join(self.directorio_base, "resources", "Airbus_logo.png")
            img_logo = Image.open(ruta_logo)
            img_resized = img_logo.resize((150, 55), Image.LANCZOS) 
            self.bg_airbus = ImageTk.PhotoImage(img_resized)
            bg_airbus_label = tk.Label(top_frame, image=self.bg_airbus, bg="#F3F4F6")
            bg_airbus_label.grid(row=0, column=8, sticky="e")
        except Exception: pass

        frame_cabecera_lista = tk.Frame(main_frame, bg="#F3F4F6")
        frame_cabecera_lista.grid(row=1, column=0, sticky="we", pady=(5, 10))
        frame_cabecera_lista.grid_columnconfigure(1, weight=1)

        self.lbl_gran_titulo = tk.Label(frame_cabecera_lista, text="", font=("Segoe UI", 18, "bold"), fg="#00205b", bg="#F3F4F6")
        self.lbl_gran_titulo.grid(row=0, column=0, sticky="w", padx=5)

        self.frame_filtros = tk.Frame(frame_cabecera_lista, bg="#F3F4F6")
        tk.Label(self.frame_filtros, text="Filtrar Vista:", font=("Segoe UI", 10, "bold"), bg="#F3F4F6").pack(side="left")
        self.combo_filtros = ttk.Combobox(self.frame_filtros, state="readonly", width=50, font=("Segoe UI", 10))
        self.combo_filtros.pack(side="left", padx=10)
        self.combo_filtros.bind("<<ComboboxSelected>>", lambda e: self.mostrar_lista(self.categoria_actual, forzar_recarga=True))

        self.lbl_descripcion = tk.Label(main_frame, text="Ejecuta el torneo o selecciona una categoria para comenzar.", font=("Segoe UI", 11, "italic"), bg="#F3F4F6", fg="#4a4a4a")
        self.lbl_descripcion.grid(row=2, column=0, sticky="w", pady=(0, 10), padx=5)

        paned_window = tk.PanedWindow(main_frame, orient=tk.HORIZONTAL, bg="#F3F4F6", sashwidth=8, bd=0)
        paned_window.grid(row=3, column=0, sticky="nsew")

        # --- MEJORA ESTÉTICA: Frame con borde sutil ---
        frame_izquierdo = tk.Frame(paned_window, bg="white", bd=0, highlightthickness=1, highlightbackground="#D1D5DB")
        paned_window.add(frame_izquierdo, minsize=380)
        
        frame_buscador = tk.Frame(frame_izquierdo, bg="#f8f9fa")
        frame_buscador.pack(fill="x", padx=10, pady=10)
        tk.Label(frame_buscador, text="🔍 Buscar:", font=("Segoe UI", 10, "bold"), bg="#f8f9fa", fg="#333").pack(side="left")
        self.ent_buscar = tk.Entry(frame_buscador, font=("Segoe UI", 10), relief="solid", bd=1, highlightcolor="#0078D4", highlightthickness=1)
        self.ent_buscar.pack(side="left", padx=8, fill="x", expand=True)
        self.ent_buscar.bind("<Return>", lambda event: self.buscar_manual())
        tk.Button(frame_buscador, text="Ir", command=self.buscar_manual, bg="#00205b", fg="white", font=("Segoe UI", 9, "bold"), relief="flat", cursor="hand2").pack(side="right")
        
        # --- MEJORA VISUAL: SCROLLBARS MODERNOS Y LISTA LIMPIA ---
        # Usamos ttk.Scrollbar en lugar de tk.Scrollbar
        scroll_y = ttk.Scrollbar(frame_izquierdo, orient=tk.VERTICAL)
        scroll_y.pack(side="right", fill="y")
        
        scroll_x = ttk.Scrollbar(frame_izquierdo, orient=tk.HORIZONTAL)
        
        # Añadido activestyle="none" para quitar la fea caja de puntos al hacer clic
        self.listbox_ops = tk.Listbox(frame_izquierdo, yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set, font=("Consolas", 10) if os.name == 'nt' else ("Courier", 10), bg="white", fg="#000000", selectbackground="#0078D4", selectforeground="#ffffff", relief="flat", bd=0, highlightthickness=0, activestyle="none")
        
        self.listbox_ops.pack(side="top", fill="both", expand=True, padx=10, pady=(5, 0))
        scroll_x.pack(side="top", fill="x", padx=10, pady=(0, 5))
        
        scroll_y.config(command=self.listbox_ops.yview)
        scroll_x.config(command=self.listbox_ops.xview)
        self.listbox_ops.bind("<<ListboxSelect>>", self.on_operacion_click)
        # ---------------------------------------------------------

        # --- NUEVA LÓGICA DE BOTONES SIMÉTRICOS (4 BOTONES) ---
        # --- NUEVA LÓGICA DE BOTONES APILADOS (2x2) PARA REDUCIR ANCHO ---
        frame_botones_izq = tk.Frame(frame_izquierdo, bg="white")
        frame_botones_izq.pack(side="bottom", fill="x", padx=5, pady=15)
        
        frame_botones_izq.columnconfigure(0, weight=1)
        frame_botones_izq.columnconfigure(1, weight=1)
        
        # -- Fila Superior (row=0) --
        btn_exp = RoundedButton(frame_botones_izq, "📊 Exportar Vista", "#107C41", width=140, height=38, bg_color="white", command=self.exportar_vista)
        btn_exp.grid(row=0, column=0, pady=5, padx=2)
        
        btn_raw = RoundedButton(frame_botones_izq, "🔍 Auditar Info", "#0078D4", width=140, height=38, bg_color="white", command=self.consultar_raw_data)
        btn_raw.grid(row=0, column=1, pady=5, padx=2)

        # -- Fila Inferior (row=1) --
        # Botón para Cumplimentar Todas (arranca oculto por defecto)
        self.btn_cump_todas = RoundedButton(frame_botones_izq, "⚡ Cumplimentar", "#E67E22", width=140, height=38, bg_color="white", command=self.aprobar_todas_las_pendientes)
        self.btn_cump_todas.grid(row=1, column=0, pady=5, padx=2)
        self.btn_cump_todas.grid_remove()

        # Botón para descargar archivo global (Red/Local)
        self.btn_descargar_excel_final = RoundedButton(frame_botones_izq, "📥 Descargar Todo", "#8E44AD", width=140, height=38, bg_color="white", command=self.descargar_excel_final_red)
        self.btn_descargar_excel_final.grid(row=1, column=1, pady=5, padx=2)
        self.btn_descargar_excel_final.disable_button()

        self.frame_derecho = tk.Frame(paned_window, bg="#F3F4F6", bd=0)
        paned_window.add(self.frame_derecho, minsize=600)
        self.frame_derecho.grid_rowconfigure(0, weight=1)
        self.frame_derecho.grid_columnconfigure(0, weight=1)

        self.frame_consola = tk.Frame(self.frame_derecho, bg="#ffffff", bd=0, highlightthickness=1, highlightbackground="#D1D5DB")
        self.frame_consola.grid(row=0, column=0, sticky="nsew")
        
        tk.Label(self.frame_consola, text="Reporte de Auditoria", font=("Segoe UI", 12, "bold"), bg="#ffffff", fg="#00205b").pack(anchor="w", padx=15, pady=(15, 5))

        # --- MEJORA VISUAL: Color de selección corporativo ---
        self.consola = scrolledtext.ScrolledText(self.frame_consola, wrap=tk.WORD, bg="#ffffff", fg="#333333", relief="flat", padx=15, pady=10, bd=0, highlightthickness=0, selectbackground="#0078D4", selectforeground="#ffffff")        
        self.consola.pack(fill="both", expand=True, padx=5, pady=5)
        
        # --- SISTEMA DE ESTILOS (TAGS) PARA LA CONSOLA ---
        self.consola.tag_config("bold", font=("Segoe UI", 11, "bold"))
        self.consola.tag_config("h1", font=("Segoe UI", 12, "bold"), foreground="white", background="#00205b", spacing1=10, spacing3=10, justify="center")
        self.consola.tag_config("h2", font=("Segoe UI", 11, "bold"), foreground="#005A9E", spacing1=15, spacing3=5)
        self.consola.tag_config("h3", font=("Segoe UI", 10, "bold"), foreground="#4a4a4a", background="#e6e4e1", spacing1=10, spacing3=5)
        self.consola.tag_config("bullet", font=("Segoe UI", 10), lmargin1=10, lmargin2=30, spacing1=3)
        self.consola.tag_config("bullet_foco", font=("Segoe UI", 10, "bold"), foreground="#000000", background="#FFF4CE", lmargin1=10, lmargin2=30, spacing1=3)
        self.consola.tag_config("motivo_error", foreground="#D83B01", font=("Segoe UI", 9, "italic"), lmargin1=30, spacing3=8)
        self.consola.tag_config("motivo_ok", foreground="#107C41", font=("Segoe UI", 9, "italic"), lmargin1=30, spacing3=8)
        self.consola.tag_config("info", foreground="#666666", font=("Segoe UI", 10, "italic"), spacing3=10)
        # -------------------------------------------------

        self.visor_imagenes = VisorDiagramasPanZoom(self.frame_derecho)
        
        self.frame_acciones = tk.Frame(self.frame_derecho, bg="#e6e4e1", bd=1, relief="solid")

        self.frame_loading = tk.Frame(self.frame_consola, bg="#ffffff")
        tk.Label(self.frame_loading, text="Procesando Sinergias...", font=("Segoe UI", 14, "bold"), bg="#ffffff", fg="#00205b").pack(pady=10)
        ruta_gif = os.path.join(self.directorio_base, "resources", "avion.gif")
        self.lbl_gif = AnimatedGifLabel(self.frame_loading, ruta_gif, bg="#ffffff")
        self.lbl_gif.pack()

        #sys.stdout = RedireccionConsola(self.consola)
        #sys.stderr = RedireccionConsola(self.consola)

    def _escribir_reporte(self, texto, tag="normal"):
        """Inserta texto en la consola de Tkinter de forma estética y segura contra hilos."""
        def safe_insert():
            self.consola.insert(tk.END, texto + "\n", tag)
            self.consola.see(tk.END)
        self.root.after(0, safe_insert)

    def crear_selector(self, parent, label_text, clave_dict):
        frame = tk.Frame(parent, bg="#00205b")
        frame.pack(fill="x", pady=4)
        tk.Label(frame, text=label_text, width=12, anchor="w", font=("Segoe UI", 10, "underline"), bg="#00205b", fg="white").pack(side="left")
        ent = tk.Entry(frame, width=25, relief="flat", bd=0, bg="#00205b", fg="#d4d4d4", font=("Segoe UI", 10))
        ent.pack(side="left", padx=5, fill="x", expand=True)
        ent.config(state="readonly")
        tk.Button(frame, text="...", command=lambda: self.seleccionar_archivo(clave_dict), relief="flat", bg="#e6e4e1", width=3, bd=0, cursor="hand2").pack(side="right")
        self.entradas_ui[clave_dict] = ent
        

        # --- NUEVO: Habilitar arrastrar y soltar ---
        ent.drop_target_register(DND_FILES)
        ent.dnd_bind('<<Drop>>', lambda e, key=clave_dict: self.on_drop(e, key))

    def on_drop(self, event, clave_dict):
        # Limpiamos la ruta (Windows añade llaves {} si la ruta tiene espacios)
        ruta = event.data.strip('{}')
        
        # Verificamos que sea un Excel para evitar errores
        if ruta.lower().endswith(('.xlsx', '.xlsm')):
            self.actualizar_entrada(clave_dict, ruta)
        else:
            messagebox.showwarning("Formato incorrecto", "Por favor, arrastra un archivo Excel (.xlsx o .xlsm).")
    # =================================================================
    # VENTANAS EMERGENTES (SPLASH Y CARGA)
    # =================================================================
    def mostrar_splash_screen(self):
        self.splash = tk.Toplevel(self.root)
        self.splash.title("Bienvenido")
        self.centrar_ventana(self.splash, 600, 400)
        self.splash.configure(bg="#ffffff")
        self.splash.resizable(False, False)
        self.splash.transient(self.root)
        self.splash.grab_set()

        try:
            ruta_logo = os.path.join(self.directorio_base, "resources", "Airbus_logo.png")
            img_logo = Image.open(ruta_logo)
            img_resized = img_logo.resize((260, 96), Image.LANCZOS)
            self.img_splash_logo = ImageTk.PhotoImage(img_resized)
            tk.Label(self.splash, image=self.img_splash_logo, bg="#ffffff").pack(pady=(40, 20))
        except: pass

        tk.Label(self.splash, text="Bienvenido al programa diseñado\npara validar y aprobar sinergias", font=("Segoe UI", 16, "bold"), bg="#ffffff", fg="#00205b", justify="center").pack(pady=20)
        tk.Button(self.splash, text="Continuar", font=("Segoe UI", 11, "bold"), bg="#005A9E", fg="white", relief="flat", bd=0, cursor="hand2", command=self.cerrar_splash_y_continuar).pack(pady=30, ipadx=30, ipady=8)

    def cerrar_splash_y_continuar(self):
        self.splash.destroy()
        self.mostrar_popup_inicial()

    def mostrar_popup_inicial(self):
        popup = tk.Toplevel(self.root)
        popup.title("Carga de Archivos")
        self.centrar_ventana(popup, 650, 450)
        popup.configure(bg="#ffffff")
        popup.resizable(False, False)
        popup.transient(self.root)
        popup.grab_set()

        tk.Label(popup, text="Archivos Detectados", font=("Segoe UI", 16, "bold"), bg="#ffffff", fg="#00205b").pack(pady=(20, 5))
        tk.Label(popup, text="Revise los archivos detectados en 'data'.", font=("Segoe UI", 10), bg="#ffffff", fg="gray").pack(pady=(0, 15))

        frame_arch = tk.Frame(popup, bg="#ffffff")
        frame_arch.pack(fill="both", expand=True, padx=40)

        for clave, entry in self.entradas_ui.items():
            f_item = tk.Frame(frame_arch, bg="#ffffff")
            f_item.pack(fill="x", pady=8)
            tk.Label(f_item, text=f"{clave}:", width=12, anchor="w", font=("Segoe UI", 10, "bold"), bg="#ffffff").pack(side="left")
            val = entry.get()
            color = "#008000" if val else "#e60000"
            texto = val if val else "Archivo no detectado. Seleccione o arrastre manualmente."
            lbl_val = tk.Label(f_item, text=texto, fg=color, font=("Segoe UI", 10), bg="#ffffff", anchor="w")
            lbl_val.pack(side="left", fill="x", expand=True, padx=10)
            self.labels_popup[clave] = lbl_val
            tk.Button(f_item, text="Cambiar", font=("Segoe UI", 9, "bold"), bg="#e1dfdd", fg="#333333", relief="flat", bd=0, padx=10, cursor="hand2", command=lambda k=clave: self.cambiar_desde_popup(k)).pack(side="right")
            
            f_item.drop_target_register(DND_FILES)
            f_item.dnd_bind('<<Drop>>', lambda e, k=clave: self.on_drop_popup(e, k))
            lbl_val.drop_target_register(DND_FILES)
            lbl_val.dnd_bind('<<Drop>>', lambda e, k=clave: self.on_drop_popup(e, k))


        tk.Button(popup, text="Aceptar y Continuar", font=("Segoe UI", 11, "bold"), bg="#005A9E", fg="white", relief="flat", bd=0, cursor="hand2", command=popup.destroy).pack(pady=25, ipadx=20, ipady=8)

    def on_drop_popup(self, event, clave):
        self.on_drop(event, clave)  # Hace la misma magia del arrastre principal
        # Y actualizamos el texto del popup para que se ponga en verde
        val = self.entradas_ui[clave].get()
        if val: self.labels_popup[clave].config(text=val, fg="#008000")
        
    def cambiar_desde_popup(self, clave):
        self.seleccionar_archivo(clave)
        val = self.entradas_ui[clave].get()
        if val: self.labels_popup[clave].config(text=val, fg="#008000")

    # =================================================================
    # FUNCIONES DE CARGA Y EJECUCION
    # =================================================================
    def autodetectar_archivos(self):
        for clave, nombre_archivo in self.archivos_esperados.items():
            ruta_posible = os.path.join(self.directorio_datos, nombre_archivo)
            if os.path.exists(ruta_posible): self.actualizar_entrada(clave, ruta_posible)

    def actualizar_entrada(self, clave_dict, ruta):
        self.rutas_archivos[clave_dict] = ruta
        self.entradas_ui[clave_dict].config(state="normal")
        self.entradas_ui[clave_dict].delete(0, tk.END)
        self.entradas_ui[clave_dict].insert(0, os.path.basename(ruta)) 
        self.entradas_ui[clave_dict].config(state="readonly")

    def seleccionar_archivo(self, clave_dict):
        ruta_inicial = self.directorio_datos if os.path.exists(self.directorio_datos) else self.directorio_base
        ruta = filedialog.askopenfilename(initialdir=ruta_inicial, title=f"Selecciona {clave_dict}", filetypes=[("Excel", "*.xlsx *.xlsm")])
        if ruta: self.actualizar_entrada(clave_dict, ruta)

    def iniciar_ejecucion(self):
        for clave, ruta in self.rutas_archivos.items():
            if not ruta:
                messagebox.showwarning("Aviso", f"Falta el archivo correspondiente a: {clave}")
                return
        
        self.btn_ejecutar.disable_button()
        self.consola.delete(1.0, tk.END)
        self.lbl_descripcion.config(text="Procesando datos, por favor espere...")
        
        self.frame_consola.grid(row=0, column=0, sticky="nsew")
        self.visor_imagenes.grid_remove()
        
        self.consola.pack_forget()
        self.frame_loading.pack(fill="both", expand=True, padx=5, pady=5)
        self.lbl_gif.start()
        
        self.decisiones = {"aprobadas": set(), "rechazadas": set(), "forzadas_estacion": set()}
        threading.Thread(target=self.proceso_pesado).start()

    def proceso_pesado(self):
        try:
            if not os.path.exists(self.carpeta_outputs): os.makedirs(self.carpeta_outputs)
            
            # --- TRADUCCIÓN DE CLAVES UI A CLAVES QUE ESPERA EL BACKEND ---
            rutas_backend = {
                "Lanzamiento": self.rutas_archivos.get("Análisis de PD"),
                "TASAR": self.rutas_archivos.get("PD"),
                "Operaciones": self.rutas_archivos.get("Operaciones"),
                "Prioridades": self.rutas_archivos.get("Prioridades"),
                "Smart_Kits": self.rutas_archivos.get("Smart_Kits"),
                "Add_Works": self.rutas_archivos.get("Add Works"),
                "Catalogo_OCCAR": self.rutas_archivos.get("Catalogo OCCAR")
            }
            # -------------------------------------------------------------
            
            main_sinergias_updated.ejecutar_pipeline_completo(rutas_backend, self.carpeta_outputs)
            self.cargar_datos_auditoria()
            self.root.after(0, lambda: self.lbl_descripcion.config(text="Proceso completado exitosamente. Seleccione una categoria."))
        except Exception as e:
            print(f"\n**ERROR CRITICO:**\n{e}")
        finally:
            self.root.after(0, self.restaurar_ui_post_ejecucion)

    def restaurar_ui_post_ejecucion(self):
        self.lbl_gif.stop()
        self.frame_loading.pack_forget()
        self.consola.pack(fill="both", expand=True, padx=5, pady=5)
        self.btn_ejecutar.enable_button()
        print("\n------------------------------------------------------------")
        print("**PROCESO FINALIZADO**. PREPARANDO ENTORNO DE AUDITORIA...")
        print("**LISTO**. Utilice los filtros para validar operaciones.")
        print("------------------------------------------------------------")

    def _limpiar(self, v):
        if pd.isna(v): return ""
        t = str(v).replace('\xa0', ' ').replace('\n', '').strip().upper()
        if t.endswith('.0'): t = t[:-2]
        return t
        
    def _limpiar_rev(self, v):
        t = self._limpiar(v).lstrip('0')
        if t == "": return "00"
        return t.zfill(2)

    # =================================================================
    # LOGICA DE AUDITORIA Y ESTADO
    # =================================================================
    def cargar_datos_auditoria(self):
        df_res_norm = pd.read_excel(os.path.join(self.carpeta_outputs, "Resultados_Sinergias_Final.xlsx"), dtype=str) if os.path.exists(os.path.join(self.carpeta_outputs, "Resultados_Sinergias_Final.xlsx")) else pd.DataFrame()
        df_aw = pd.read_excel(os.path.join(self.carpeta_outputs, "Resultados_AddWorks_Trazabilidad.xlsx"), dtype=str) if os.path.exists(os.path.join(self.carpeta_outputs, "Resultados_AddWorks_Trazabilidad.xlsx")) else pd.DataFrame()
        
        lista_dfs = [df for df in [df_res_norm, df_aw] if not df.empty]
        df_res = pd.concat(lista_dfs, ignore_index=True) if lista_dfs else pd.DataFrame()
        
        df_ign = pd.read_excel(os.path.join(self.carpeta_outputs, "Operaciones_Ignoradas_Fase0.xlsx"), dtype=str) if os.path.exists(os.path.join(self.carpeta_outputs, "Operaciones_Ignoradas_Fase0.xlsx")) else pd.DataFrame()
        
        l_todas, l_cump, l_sin_sinergia, l_desc, l_dist_estacion = set(), set(), set(), set(), set()
        self.mapa_padre_hijas = {}
        self.mapa_hija_padre = {}
        self.mapa_ignoradas = {}
        self.mapa_warnings_mat = {}

        if not df_ign.empty:
            cols = df_ign.columns.str.strip().str.upper()
            pr = [i for i, c in enumerate(cols) if 'RUTA LOCAL' in c][0]
            col_op_ign = 'Operación' if 'Operación' in df_ign.columns else ('Operacion' if 'Operacion' in df_ign.columns else 'OPERACION')
            df_ign['ID'] = df_ign.iloc[:, pr].apply(self._limpiar) + "-" + df_ign.iloc[:, pr+1].apply(self._limpiar_rev) + "-" + df_ign.get(col_op_ign, pd.Series()).apply(self._limpiar)
            
            for _, r in df_ign.iterrows():
                id_ign = r['ID']
                l_todas.add(id_ign)
                self.mapa_ignoradas[id_ign] = str(r.get('MOTIVO_RECHAZO', 'Descartada por filtro')).strip()

        if not df_res.empty:
            for _, r in df_res.iterrows():
                res = str(r.get('Resultado_Final', '')).upper()
                if "SIN SINERGIA" in res or "EJECUTABLE" in res:
                    id_a = f"{self._limpiar(r.get('Op_A_Ruta'))}-{self._limpiar_rev(r.get('Op_A_Rev'))}-{self._limpiar(r.get('Op_A_Op'))}"
                    l_sin_sinergia.add(id_a)
                    l_todas.add(id_a)
                elif "PADRE" in res:
                    id_a = f"{self._limpiar(r.get('Op_A_Ruta'))}-{self._limpiar_rev(r.get('Op_A_Rev'))}-{self._limpiar(r.get('Op_A_Op'))}"
                    id_b = f"{self._limpiar(r.get('Op_B_Ruta'))}-{self._limpiar_rev(r.get('Op_B_Rev'))}-{self._limpiar(r.get('Op_B_Op'))}"
                    
                    est_a = str(r.get('Op_A_Estacion', '')).strip().upper()
                    est_b = str(r.get('Op_B_Estacion', '')).strip().upper()
                    llave_par = f"{id_a} -> {id_b}"
                    
                    # --- NUEVA LÓGICA: Captura del Warning de Materiales ---
                    warn_text = str(r.get('Warning_Materiales', '')).upper()
                    if "NO ESTÁN INCLUIDOS" in warn_text or "PERO EL HIJO SI" in warn_text:
                        self.mapa_warnings_mat[llave_par] = True
                    else:
                        self.mapa_warnings_mat[llave_par] = False
                    # -------------------------------------------------------
                    
                    if est_a != est_b and est_a != "" and est_b != "": l_dist_estacion.add(llave_par)
                    else: l_cump.add(llave_par)
                        
                    l_todas.add(id_a); l_todas.add(id_b)
                    
                    if id_a not in self.mapa_padre_hijas: self.mapa_padre_hijas[id_a] = []
                    self.mapa_padre_hijas[id_a].append(id_b)
                    self.mapa_hija_padre[id_b] = id_a

        self.listas_orig = {
            "Todas": sorted(list(l_todas)), "Cumplimentadas": sorted(list(l_cump)),
            "Sin Sinergia": sorted(list(l_sin_sinergia)), "Descartadas": sorted(list(l_desc)),
            "DistintaEstacion": sorted(list(l_dist_estacion))
        }
        
        self.simulador_data = {'df_res': df_res, 'df_ign': df_ign}
        self.datos_cargados = True
        
        self.df_resultados_finales = df_res.copy() if not df_res.empty else pd.DataFrame()
        if self.btn_descargar_excel_final and not self.df_resultados_finales.empty:
            self.btn_descargar_excel_final.enable_button()
        
        self.listas_dinamicas["Logica"] = [
            "Flujo Completo", 
            "Fase 1: Carga y Extracción", 
            "Fase 2: Agrupacion Documental", 
            "Fase 3: Arbol de Decisión", 
            "Fase 4: Jerarquía"
        ]
        
        self.actualizar_vista_dinamica()

    def actualizar_vista_dinamica(self):
        if not self.datos_cargados: return
        
        definitivas = list(self.decisiones["aprobadas"]) + list(self.decisiones["forzadas_estacion"])
        self.listas_dinamicas["Definitivas"] = [f"{op} ⚠️ [FALTA MATERIAL]" if getattr(self, 'mapa_warnings_mat', {}).get(op, False) else op for op in sorted(definitivas)]
        
        pendientes_cump = [op for op in self.listas_orig["Cumplimentadas"] if op not in self.decisiones["aprobadas"] and op not in self.decisiones["rechazadas"]]
        self.listas_dinamicas["Cumplimentadas"] = [f"{op} ⚠️ [FALTA MATERIAL]" if getattr(self, 'mapa_warnings_mat', {}).get(op, False) else op for op in sorted(pendientes_cump)]
        
        self.listas_dinamicas["Descartadas_Fase0"] = sorted(list(self.mapa_ignoradas.keys()))
        self.listas_dinamicas["Descartadas_Usuario"] = sorted(list(self.decisiones["rechazadas"]))
        
        self.listas_dinamicas["Sin_Sinergia"] = self.listas_orig["Sin Sinergia"]
        pendientes_dist_est = [op for op in self.listas_orig["DistintaEstacion"] if op not in self.decisiones["forzadas_estacion"] and op not in self.decisiones["rechazadas"]]
        self.listas_dinamicas["Sinergiadas_DistintaEst"] = [f"{op} ⚠️ [FALTA MATERIAL]" if getattr(self, 'mapa_warnings_mat', {}).get(op, False) else op for op in sorted(pendientes_dist_est)]

        lista_todas_anotada = []
        for op in self.listas_orig["Todas"]:
            if op in self.mapa_padre_hijas:
                hijas_str = ", ".join(self.mapa_padre_hijas[op])
                lista_todas_anotada.append(f"{op} (Es PADRE de: {hijas_str})")
            elif op in self.mapa_hija_padre:
                padre_str = self.mapa_hija_padre[op]
                lista_todas_anotada.append(f"{op} (Es HIJA de: {padre_str})")
            elif op in self.mapa_ignoradas:
                lista_todas_anotada.append(f"{op} (Ignorada: {self.mapa_ignoradas[op]})")
            else:
                lista_todas_anotada.append(op)
        self.listas_dinamicas["Todas"] = lista_todas_anotada

        df_res = self.simulador_data.get('df_res', pd.DataFrame())
        tiempos_ops = {}
        if not df_res.empty:
            for _, r in df_res.iterrows():
                id_a = f"{self._limpiar(r.get('Op_A_Ruta'))}-{self._limpiar_rev(r.get('Op_A_Rev'))}-{self._limpiar(r.get('Op_A_Op'))}"
                id_b = f"{self._limpiar(r.get('Op_B_Ruta'))}-{self._limpiar_rev(r.get('Op_B_Rev'))}-{self._limpiar(r.get('Op_B_Op'))}"
                try: t_a = float(str(r.get('Op_A_Tiempo', '0')).replace(',', '.'))
                except: t_a = 0.0
                try: t_b = float(str(r.get('Op_B_Tiempo', '0')).replace(',', '.'))
                except: t_b = 0.0
                tiempos_ops[id_a] = t_a
                tiempos_ops[id_b] = t_b

        self.datos_cotizaciones = {}
        for par in definitivas:
            if " -> " in par:
                padre, hija = par.split(" -> ")
                padre = padre.strip(); hija = hija.strip()
                if padre not in self.datos_cotizaciones:
                    self.datos_cotizaciones[padre] = {"hijas": [], "t_padre": tiempos_ops.get(padre, 0.0)}
                self.datos_cotizaciones[padre]["hijas"].append({"id": hija, "t_hija": tiempos_ops.get(hija, 0.0)})

        self.listas_dinamicas["Cotizaciones"] = sorted(list(self.datos_cotizaciones.keys()))

        self.btn_t.config(text=f"Todas ({len(self.listas_dinamicas['Todas'])})")
        self.btn_c.config(text=f"Pendientes ({len(self.listas_dinamicas['Cumplimentadas']) + len(self.listas_dinamicas['Sinergiadas_DistintaEst'])})")
        self.btn_def.config(text=f"Definitivas ({len(self.listas_dinamicas['Definitivas'])})")
        self.btn_cot.config(text=f"Cotizaciones ({len(self.datos_cotizaciones)} Grp)")
        self.btn_e.config(text=f"Sin Sinergia ({len(self.listas_dinamicas['Sin_Sinergia'])})")
        self.btn_d.config(text=f"Descartadas ({len(self.listas_dinamicas['Descartadas_Fase0']) + len(self.listas_dinamicas['Descartadas_Usuario'])})")

        if self.categoria_actual:
            idx_filtro_guardado = self.combo_filtros.current() if hasattr(self, "combo_filtros") and self.combo_filtros else -1
            self.mostrar_lista(self.categoria_actual, forzar_recarga=True, idx_filtro=idx_filtro_guardado)

    def mostrar_lista(self, categoria, forzar_recarga=False, idx_filtro=-1):
        if not self.datos_cargados and categoria != "Logica":
            self.cargar_datos_auditoria()
            if not self.datos_cargados:
                messagebox.showinfo("Aviso", "No hay datos generados. Ejecute el torneo primero.")
                return

        if categoria != self.categoria_actual and not forzar_recarga:
            self.combo_filtros.set('')
            self.categoria_actual = categoria

        # --- CONTROL DE VISIBILIDAD DEL BOTÓN "CUMPLIMENTAR TODAS" ---
        # --- CONTROL DE VISIBILIDAD DEL BOTÓN "CUMPLIMENTAR TODAS" ---
        if hasattr(self, "btn_cump_todas") and self.btn_cump_todas:
            if categoria == "Cumplimentadas":
                self.btn_cump_todas.grid(row=1, column=0, pady=5, padx=2)
            else:
                self.btn_cump_todas.grid_remove()

        titulos = {
            "Todas": "TODAS LAS OPERACIONES", 
            "Cumplimentadas": "CUMPLIMENTADAS (PENDIENTES DE VALIDACIÓN)", 
            "Definitivas": "LISTA DEFINITIVA DE SINERGIADAS", 
            "Cotizaciones": "COTIZACIONES Y AHORRO REAL",
            "Sin Sinergia": "OPERACIONES SIN SINERGIA", 
            "Descartadas": "DESCARTADAS",
            "Logica": "DIAGRAMAS DE LÓGICA Y FLUJO"
        }
        self.lbl_gran_titulo.config(text=f"  {titulos.get(categoria, categoria.upper())}  ")

        if categoria == "Logica":
            self.frame_consola.grid_remove()
            self.visor_imagenes.grid(row=0, column=0, sticky="nsew")
        else:
            self.visor_imagenes.grid_remove()
            self.frame_consola.grid(row=0, column=0, sticky="nsew")

        lista_a_mostrar = []
        if categoria == "Descartadas":
            self.frame_filtros.grid(row=0, column=1, sticky="e", padx=15)
            self.combo_filtros.config(values=[
                f"1. Ignoradas (Fase 0) - {len(self.listas_dinamicas['Descartadas_Fase0'])} ops", 
                f"2. Descartadas Manuales - {len(self.listas_dinamicas['Descartadas_Usuario'])} ops"
            ])
            if idx_filtro >= 0:
                self.combo_filtros.current(idx_filtro)
            elif self.combo_filtros.current() == -1:
                self.combo_filtros.current(0)
            
            idx = self.combo_filtros.current()
            if idx == 0: 
                lista_a_mostrar = self.listas_dinamicas["Descartadas_Fase0"]
                self.lbl_descripcion.config(text="FASE 0: Operaciones descartadas inicialmente por ser ejecutables directos o no tener patron valido.")
            else: 
                lista_a_mostrar = self.listas_dinamicas["Descartadas_Usuario"]
                self.lbl_descripcion.config(text="RECHAZO MANUAL: Operaciones que tu has decidido descartar desde otras pestañas.")

        elif categoria == "Cumplimentadas":
            self.frame_filtros.grid(row=0, column=1, sticky="e", padx=15)
            self.combo_filtros.config(values=[
                f"1. Sinergias (Misma Estación) - {len(self.listas_dinamicas['Cumplimentadas'])} ops", 
                f"2. Sinergias (Distinta Estación) - {len(self.listas_dinamicas['Sinergiadas_DistintaEst'])} ops"
            ])
            if idx_filtro >= 0:
                self.combo_filtros.current(idx_filtro)
            elif self.combo_filtros.current() == -1:
                self.combo_filtros.current(0)
            
            idx = self.combo_filtros.current()
            if idx == 0: 
                lista_a_mostrar = self.listas_dinamicas["Cumplimentadas"]
                self.lbl_descripcion.config(text="Las 'cumplimentadas' son los emparejamientos exitosos y óptimos. Pulsa 'Aprobar' para enviarlas a Definitivas.")
            else: 
                lista_a_mostrar = self.listas_dinamicas["Sinergiadas_DistintaEst"]
                self.lbl_descripcion.config(text="ATENCIÓN: Sinergiables entre si, pero de distinta estación. Requieren validación manual para forzarse.")

        elif categoria == "Sin Sinergia":
            self.frame_filtros.grid_remove() # Ya no necesita desplegable
            lista_a_mostrar = self.listas_dinamicas["Sin_Sinergia"]
            self.lbl_descripcion.config(text="Sin Sinergia: Operaciones independientes sin pareja o descartadas por reglas del algoritmo.")

        else:
            self.frame_filtros.grid_remove()
            lista_a_mostrar = self.listas_dinamicas[categoria]
            if categoria == "Todas":
                self.lbl_descripcion.config(text="Visor Global: Muestra absolutamente todas las operaciones del evento y su estado final.")
            elif categoria == "Definitivas":
                self.lbl_descripcion.config(text="TU LISTA FINAL: Emparejamientos validados.")
            elif categoria == "Cotizaciones":
                self.lbl_descripcion.config(text="Selecciona un Padre en la lista para visualizar las hijas absorbidas y el impacto de tiempo.")
            elif categoria == "Logica":
                self.lbl_descripcion.config(text="Selecciona un diagrama de la lista. (Click y arrastrar para mover, Rueda del raton para Zoom).")

        self.listbox_ops.delete(0, tk.END)
        for op in lista_a_mostrar:
            self.listbox_ops.insert(tk.END, op)
            
        for widget in self.frame_acciones.winfo_children(): widget.destroy()
        self.frame_acciones.grid_remove()
        self.consola.delete(1.0, tk.END)

    def exportar_vista(self):
        if not self.datos_cargados or self.categoria_actual == "Logica": return
        categoria = self.categoria_actual
        
        if categoria == "Descartadas":
            idx = self.combo_filtros.current()
            if idx == 0: datos = self.listas_dinamicas["Descartadas_Fase0"]
            else: datos = self.listas_dinamicas["Descartadas_Usuario"]
        elif categoria == "Cumplimentadas":
            datos = self.listas_dinamicas["Sinergiadas_DistintaEst"] if self.combo_filtros.current() == 1 else self.listas_dinamicas["Cumplimentadas"]
        elif categoria == "Sin Sinergia":
            datos = self.listas_dinamicas["Sin_Sinergia"]
        else:
            datos = self.listas_dinamicas[categoria]
        
        if not datos:
            messagebox.showinfo("Exportar", "No hay datos para exportar en esta vista.")
            return
            
        ruta_guardado = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile=f"Exportacion_{categoria}.xlsx", filetypes=[("Excel", "*.xlsx"), ("Text file", "*.txt")], title="Guardar exportacion")
        if not ruta_guardado: return
        
        try:
            if ruta_guardado.endswith(".xlsx"): pd.DataFrame({"Resultados": datos}).to_excel(ruta_guardado, index=False)
            else:
                with open(ruta_guardado, 'w', encoding='utf-8') as f:
                    for d in datos: f.write(f"{d}\n")
            messagebox.showinfo("Exportacion exitosa", f"Vista exportada correctamente en:\n{ruta_guardado}")
        except Exception as e:
            messagebox.showerror("Error", f"Fallo al exportar: {e}")

    # =====================================================================
    # [ INSERCIÓN ]: EXPORTACIÓN GLOBAL PARA CARPETAS DE RED
    # =====================================================================
    def descargar_excel_final_red(self):
        """
        Permite al usuario descargar y guardar explícitamente el archivo
        'Resultados_Sinergias_Final.xlsx' en una ruta de su elección (ej. Escritorio).
        """
        if self.df_resultados_finales is None or self.df_resultados_finales.empty:
            messagebox.showwarning("Sin datos", "No hay resultados calculados disponibles para descargar. Ejecute el análisis primero.")
            return

        ruta_destino = filedialog.asksaveasfilename(
            title="Guardar Excel Completo de Sinergias",
            initialfile="Resultados_Sinergias_Final.xlsx",
            defaultextension=".xlsx",
            filetypes=[("Archivos de Excel", "*.xlsx"), ("Todos los archivos", "*.*")]
        )

        if not ruta_destino:
            return

        def _guardar_en_background():
            try:
                self.df_resultados_finales.to_excel(ruta_destino, index=False)
                self.root.after(0, lambda: messagebox.showinfo(
                    "Exportación Exitosa", 
                    f"El archivo completo de sinergias se ha guardado en:\n{ruta_destino}"
                ))
            except Exception as e:
                err_msg = str(e)
                self.root.after(0, lambda: messagebox.showerror(
                    "Error de Escritura", 
                    f"No se pudo guardar el Excel en la ruta seleccionada:\n{err_msg}"
                ))

        threading.Thread(target=_guardar_en_background, daemon=True).start()

    # =====================================================================
    # [ INSERCIÓN ]: MÉTODO PARA APROBAR TODAS LAS PENDIENTES DE GOLPE
    # =====================================================================
    def aprobar_todas_las_pendientes(self):
        """
        Pasa masivamente todas las sinergias pendientes (Cumplimentadas de misma estación)
        directamente a la lista de Definitivas sin necesidad de ir 1 a 1.
        """
        if not self.datos_cargados:
            messagebox.showwarning("Atención", "No hay datos cargados. Ejecute el análisis primero.")
            return

        pendientes_actuales = [
            op for op in self.listas_orig["Cumplimentadas"] 
            if op not in self.decisiones["aprobadas"] and op not in self.decisiones["rechazadas"]
        ]

        if not pendientes_actuales:
            messagebox.showinfo("Sin Pendientes", "No quedan sinergias pendientes por aprobar en la lista principal.")
            return

        confirmar = messagebox.askyesno(
            "Confirmar Cumplimentación Masiva",
            f"¿Desea aprobar masivamente las {len(pendientes_actuales)} sinergias pendientes y enviarlas a Definitivas?"
        )
        if not confirmar:
            return

        self.decisiones["aprobadas"].update(pendientes_actuales)
        self.actualizar_vista_dinamica()
        messagebox.showinfo("Éxito", f"Se han añadido {len(pendientes_actuales)} sinergias a la lista Definitiva.")

    def on_operacion_click(self, event):
        seleccion = self.listbox_ops.curselection()
        if not seleccion: return
        
        llave_op = self.listbox_ops.get(seleccion[0])
        self.consola.delete(1.0, tk.END)
        
        # --- LOGICA DE CLICK EN PESTAÑA LOGICA ---
        if self.categoria_actual == "Logica":
            mapa_archivos = {
                "Flujo Completo": "Flujo_Completo.jpg",
                "Fase 1: Carga y Extraccion": "Fase 1_ Carga.jpg",
                "Fase 2: Agrupacion Documental": "Fase 2_ Agrupación de Docs.jpg",
                "Fase 3: Arbol de Decision": "Fase 3_ Árbol de Decisión.jpg",
                "Fase 4: Jerarquia": "Fase 4_ Jerarquía.jpg"
            }
            ruta_imagen = os.path.join(self.directorio_base, "resources", mapa_archivos.get(llave_op, ""))
            self.visor_imagenes.load_image(ruta_imagen)
            return

        # --- LOGICA DE CLICK EN COTIZACIONES CON NUEVO ESTILO ---
        if self.categoria_actual == "Cotizaciones":
            datos = self.datos_cotizaciones.get(llave_op)
            if not datos: return
            
            t_padre = datos["t_padre"]
            hijas = datos["hijas"]
            t_hijas_total = sum(h["t_hija"] for h in hijas)
            
            self._escribir_reporte(f" 💰 DETALLE DE COTIZACIÓN Y AHORRO ", "h1")
            
            self._escribir_reporte("OPERACIÓN PADRE (Definitiva en Taller)", "h2")
            self._escribir_reporte(f"🏆 {llave_op}  |  Tiempo de ejecución: {t_padre}h", "bullet_foco")
            
            self._escribir_reporte(f"OPERACIONES HIJAS ABSORBIDAS ({len(hijas)})", "h2")
            for h in hijas:
                self._escribir_reporte(f"└─ {h['id']}  |  Tiempo aportado al ahorro: {h['t_hija']}h", "bullet")
                
            self._escribir_reporte("RESUMEN DE IMPACTO TEMPORAL", "h3")
            self._escribir_reporte(f"• Tiempo Total Sin Sinergiar (Padre + Hijas): {round(t_padre + t_hijas_total, 2)}h", "bullet")
            self._escribir_reporte(f"• Tiempo Final en Taller (Solo Padre): {round(t_padre, 2)}h", "bullet")
            self._escribir_reporte(f"➔ HORAS PRODUCTIVAS AHORRADAS EN ESTE GRUPO: {round(t_hijas_total, 2)}h", "motivo_ok")
            
            for widget in self.frame_acciones.winfo_children(): widget.destroy()
            self.frame_acciones.grid_remove()
            return

        # --- MEJORA: Aislamos y limpiamos el texto de posibles Warnings para la búsqueda lógica ---
        llave_busqueda = llave_op.split(" (Es PADRE")[0].split(" (Es HIJA")[0].split(" (Ignorada")[0].split(" ⚠️")[0].strip()
        if " -> " in llave_busqueda: llave_base = llave_busqueda.split(" -> ")[0].strip()
        else: llave_base = llave_busqueda
            
        partes = llave_base.split('-')
        ruta_rev_prefijo = f"{partes[0]}-{partes[1]}-"
        
        threading.Thread(target=self.simular_trayectoria_ruta, args=(ruta_rev_prefijo, llave_busqueda)).start()
        
        for widget in self.frame_acciones.winfo_children(): widget.destroy()
        self.frame_acciones.grid_remove()
        
        if self.categoria_actual == "Cumplimentadas":
            self.frame_acciones.grid(row=1, column=0, sticky="we", padx=5, pady=5, ipadx=5, ipady=5)
            
            # --- CRÍTICO: Mandamos `llave_busqueda` (limpia) a tomar_decision, nunca llave_op (sucia con warning)
            if self.combo_filtros.current() == 0:
                tk.Label(self.frame_acciones, text="¿Desea incluir la sinergia en su lista definitiva?", font=("Segoe UI", 10, "bold"), bg="#e6e4e1").pack(side="left", padx=10)
                tk.Button(self.frame_acciones, text="SI (Aprobar)", bg="#107C41", fg="white", font=("Segoe UI", 10, "bold"), cursor="hand2", command=lambda: self.tomar_decision("aprobar", llave_busqueda)).pack(side="right", padx=5)
                tk.Button(self.frame_acciones, text="NO (Descartar)", bg="#D83B01", fg="white", font=("Segoe UI", 10, "bold"), cursor="hand2", command=lambda: self.tomar_decision("rechazar", llave_busqueda)).pack(side="right", padx=5)
            else:
                tk.Label(self.frame_acciones, text="¿Desea forzar esta sinergia de distinta estacion a su lista definitiva?", font=("Segoe UI", 10, "bold"), bg="#e6e4e1").pack(side="left", padx=10)
                tk.Button(self.frame_acciones, text="SI (Forzar a definitiva)", bg="#0078D4", fg="white", font=("Segoe UI", 10, "bold"), cursor="hand2", command=lambda: self.tomar_decision("forzar", llave_busqueda)).pack(side="right", padx=5)
                tk.Button(self.frame_acciones, text="NO (Descartar)", bg="#D83B01", fg="white", font=("Segoe UI", 10, "bold"), cursor="hand2", command=lambda: self.tomar_decision("rechazar", llave_busqueda)).pack(side="right", padx=5)

    def tomar_decision(self, accion, llave_op):
        if accion == "aprobar": self.decisiones["aprobadas"].add(llave_op)
        elif accion == "rechazar": self.decisiones["rechazadas"].add(llave_op)
        elif accion == "forzar": self.decisiones["forzadas_estacion"].add(llave_op)
        self.actualizar_vista_dinamica()

    def simular_trayectoria_ruta(self, prefijo_ruta, op_destacada):
        titulo = f" 🔎 ANÁLISIS DE LA RUTA: {prefijo_ruta[:-1]} "
        if op_destacada: titulo += f"\n 📌 FOCO EN OPERACIÓN: {op_destacada} "
        
        self._escribir_reporte(titulo, "h1")
        
        df_res = self.simulador_data.get('df_res', pd.DataFrame())
        df_ign = self.simulador_data.get('df_ign', pd.DataFrame())

        ops_ignoradas = df_ign[df_ign['ID'].str.startswith(prefijo_ruta)]['ID'].tolist() if not df_ign.empty and 'ID' in df_ign.columns else []
        if ops_ignoradas:
            self._escribir_reporte("Fase 0: OPERACIONES DESCARTADAS (Aduana Inicial)", "h2")
            for op in ops_ignoradas:
                tag_linea = "bullet_foco" if op == op_destacada else "bullet"
                marca = "➤ " if op == op_destacada else "• "
                fila_i = df_ign[df_ign['ID'] == op].iloc[0]
                motivo = fila_i.get('MOTIVO_RECHAZO', 'Descartada por patron')
                col_n = 'Nombre Operación' if 'Nombre Operación' in df_ign.columns else 'Nombre Operacion'
                
                self._escribir_reporte(f"{marca}{op}  |  {fila_i.get(col_n, '')}", tag_linea)
                self._escribir_reporte(f"   ↳ Motivo de purga: {motivo}", "motivo_error")

        res_ruta = df_res[df_res['Resultado_Final'].str.contains(prefijo_ruta)] if not df_res.empty else pd.DataFrame()
        
        if not res_ruta.empty:
            self._escribir_reporte("Fase 1 y 2: COMBATES Y RESOLUCIÓN DE LIGAS", "h2")
            self._escribir_reporte("Operaciones que superaron la aduana y su destino final:\n", "info")
            
            # --- Ajuste para leer "SIN SINERGIA" o "EJECUTABLE" según lo que devuelva el backend
            independientes = res_ruta[res_ruta['Resultado_Final'].str.contains("SIN SINERGIA") | res_ruta['Resultado_Final'].str.contains("EJECUTABLE")]
            combates = res_ruta[~res_ruta['Resultado_Final'].str.contains("SIN SINERGIA") & ~res_ruta['Resultado_Final'].str.contains("EJECUTABLE")]

            if not independientes.empty:
                self._escribir_reporte("  OPERACIONES SIN SINERGIAS  ", "h3")
                for _, r in independientes.iterrows():
                    id_a = f"{self._limpiar(r.get('Op_A_Ruta'))}-{self._limpiar_rev(r.get('Op_A_Rev'))}-{self._limpiar(r.get('Op_A_Op'))}"
                    tag_linea = "bullet_foco" if id_a == op_destacada else "bullet"
                    marca = "➤ " if id_a == op_destacada else "• "
                    self._escribir_reporte(f"{marca}{id_a}  |  Estación: {r.get('Op_A_Estacion')}", tag_linea)
                    self._escribir_reporte(f"   ↳ Estado: {r.get('Motivo', 'Independiente')}", "motivo_ok")

            if not combates.empty:
                grupos_combate = combates.groupby('Grupo')
                for nombre_grupo, combates_grupo in grupos_combate:
                    self._escribir_reporte(f"  GRUPO ANALIZADO: {nombre_grupo}  ", "h3")
                    for _, r in combates_grupo.iterrows():
                        id_a = f"{self._limpiar(r.get('Op_A_Ruta'))}-{self._limpiar_rev(r.get('Op_A_Rev'))}-{self._limpiar(r.get('Op_A_Op'))}"
                        id_b = f"{self._limpiar(r.get('Op_B_Ruta'))}-{self._limpiar_rev(r.get('Op_B_Rev'))}-{self._limpiar(r.get('Op_B_Op'))}"
                        
                        # --- EVALUAMOS SI ESTA PAREJA ES LA SELECCIONADA PARA RESALTARLA ---
                        es_foco_a = False
                        es_foco_b = False
                        if op_destacada:
                            if " -> " in op_destacada:
                                es_foco_a = (f"{id_a} -> {id_b}" == op_destacada)
                                es_foco_b = (f"{id_a} -> {id_b}" == op_destacada)
                            else:
                                es_foco_a = (id_a == op_destacada)
                                es_foco_b = (id_b == op_destacada)
                        
                        texto_padre = f"🏆 [PADRE] {id_a} (Est: {r.get('Op_A_Estacion')} | {r.get('Op_A_Tiempo')}h | PEP: {r.get('Op_A_Prioridad_Source')})"
                        texto_hija  = f"└─ [HIJA]  {id_b} (Est: {r.get('Op_B_Estacion')} | {r.get('Op_B_Tiempo')}h | PEP: {r.get('Op_B_Prioridad_Source')})"
                        
                        # --- AHORA IMPRIMIMOS SIEMPRE TODAS LAS DE LA RUTA ---
                        self._escribir_reporte(texto_padre, "bullet_foco" if es_foco_a else "bullet")
                        self._escribir_reporte(texto_hija, "bullet_foco" if es_foco_b else "bullet")
                        self._escribir_reporte(f"    ↳ Resolución: {r.get('Motivo')}", "motivo_ok")
                        
                        # --- MEJORA: AVISO DE MATERIALES DETALLADO EN CONSOLA DERECHA ---
                        warn_text_consola = str(r.get('Warning_Materiales', ''))
                        if "NO EST" in warn_text_consola.upper() or "PERO EL HIJO" in warn_text_consola.upper():
                            self._escribir_reporte(f"    ⚠️ AVISO: {warn_text_consola}", "motivo_error")
                            
                            
                        # ----------------------------------------------------------------
                        
                        # --- MEJORA: AVISO DE MATERIALES DETALLADO EN CONSOLA DERECHA ---
                        warn_text_consola = str(r.get('Warning_Materiales', ''))
                        if "NO EST" in warn_text_consola.upper() or "PERO EL HIJO" in warn_text_consola.upper():
                            self._escribir_reporte(f"    ⚠️ AVISO: {warn_text_consola}", "motivo_error")
                        # ----------------------------------------------------------------
        else:
            self._escribir_reporte("Fase 1 y 2: COMBATES Y RESOLUCION", "h2")
            if op_destacada:
                self._escribir_reporte(f"La operación seleccionada ({op_destacada}) no llegó a combatir.", "motivo_error")
            else:
                self._escribir_reporte("El registro fue descartado por la aduana de aplicabilidad (Flag 'Y') o por no coincidir con el Lanzamiento.", "motivo_error")

    def buscar_manual(self):
        consulta = self.ent_buscar.get().strip().upper()
        if not consulta: return
        self.consola.delete(1.0, tk.END)
        partes = consulta.split('-')
        if len(partes) == 1:
            prefijo = f"{self._limpiar(partes[0])}-"; op_destacada = ""
        elif len(partes) == 2:
            prefijo = f"{self._limpiar(partes[0])}-{self._limpiar_rev(partes[1])}-"; op_destacada = ""
        else:
            prefijo = f"{self._limpiar(partes[0])}-{self._limpiar_rev(partes[1])}-"
            op_destacada = f"{self._limpiar(partes[0])}-{self._limpiar_rev(partes[1])}-{self._limpiar(partes[2])}"
        threading.Thread(target=self.simular_trayectoria_ruta, args=(prefijo, op_destacada)).start()

    def consultar_raw_data(self):
        if self.categoria_actual == "Logica": return
        seleccion = self.listbox_ops.curselection()
        if not seleccion:
            messagebox.showwarning("Atencion", "Seleccione primero una operacion de la lista izquierda.")
            return
        llave_op = self.listbox_ops.get(seleccion[0])
        
        # --- MEJORA: Aislar el warning si existe para no estropear la búsqueda en el dataframe original ---
        llave_limpia = llave_op.split(" (Es PADRE")[0].split(" (Es HIJA")[0].split(" (Ignorada")[0].split(" ⚠️")[0].strip()
        llaves_a_buscar = [llave_limpia.split(" -> ")[0].strip(), llave_limpia.split(" -> ")[1].strip()] if " -> " in llave_limpia else [llave_limpia]
        
        self.consola.delete(1.0, tk.END)
        threading.Thread(target=self._cargar_y_mostrar_raw_multiple, args=(llaves_a_buscar, llave_limpia)).start()

        
    def _cargar_y_mostrar_raw_multiple(self, llaves_list, llave_limpia):
        try:
            # 1. --- SECCIÓN DE DOCUMENTACIÓN (Basada en los resultados finales del algoritmo) ---
            df_res = self.simulador_data.get('df_res', pd.DataFrame())
            if not df_res.empty:
                self._escribir_reporte(" 📚 DOCUMENTACIÓN REQUERIDA (Data Calculada) ", "h1")
                if " -> " in llave_limpia:
                    padre, hija = llave_limpia.split(" -> ")
                    padre, hija = padre.strip(), hija.strip()
                    match = df_res[df_res['Resultado_Final'].str.contains(padre) & df_res['Resultado_Final'].str.contains(hija)]
                    
                    if not match.empty:
                        fila = match.iloc[0]
                        self._escribir_reporte(f"OPERACIÓN PADRE: {padre}", "h2")
                        self._escribir_reporte(f"• Documentos: {fila.get('Docs_A', 'Sin documentos')}", "bullet_foco")
                        self._escribir_reporte(f"\nOPERACIÓN HIJA: {hija}", "h2")
                        self._escribir_reporte(f"• Documentos: {fila.get('Docs_B', 'Sin documentos')}", "bullet_foco")
                        
                        if str(fila.get('Evidencia_Docs', '')) == "Empate Documental":
                            self._escribir_reporte("\nℹ️ Nota: Ambas operaciones comparten exactamente la misma documentación.", "info")
                        elif str(fila.get('Evidencia_Docs', '')) == "Padre engloba a Hija":
                            self._escribir_reporte("\nℹ️ Nota: Los documentos del padre engloban completamente a los de la hija.", "info")
                else:
                    match = df_res[df_res['Resultado_Final'].str.contains(llave_limpia)]
                    if not match.empty:
                        fila = match.iloc[0]
                        if llave_limpia in str(fila.get('Op_A_Op', '')): docs = fila.get('Docs_A', 'Sin documentos')
                        else: docs = fila.get('Docs_B', 'Sin documentos')
                        
                        self._escribir_reporte(f"OPERACIÓN: {llave_limpia}", "h2")
                        self._escribir_reporte(f"• Documentos: {docs}", "bullet_foco")
                    else:
                        self._escribir_reporte(f"OPERACIÓN: {llave_limpia}", "h2")
                        self._escribir_reporte("No se encontró documentación pre-calculada. (Posible descarte inicial).", "motivo_error")

            # 2. --- SECCIÓN DE DATA CRUDA (Lectura directa de los Excels originales) ---
            self._escribir_reporte("\n 🗄️ INFORMACIÓN ORIGINAL EN EXCEL (Data Cruda) ", "h1")
            
            if self.raw_data["lanz"] is None:
                df_l = pd.read_excel(self.rutas_archivos["Lanzamiento"], sheet_name=0, dtype=str)
                df_l.columns = df_l.columns.str.strip().str.upper()
                c_r = [c for c in df_l.columns if 'RUTA LOCAL' in c][0]
                df_l['KEY'] = df_l[c_r].apply(self._limpiar) + "-" + df_l.iloc[:, df_l.columns.get_loc(c_r)+1].apply(self._limpiar_rev)
                self.raw_data["lanz"] = df_l

            if self.raw_data["ops"] is None:
                df_o = pd.read_excel(self.rutas_archivos["Operaciones"], sheet_name='Operaciones', dtype=str)
                df_o.columns = df_o.columns.str.strip().str.upper()
                c_ro = [c for c in df_o.columns if 'RUTA LOCAL' in c][0]
                col_op = 'OPERACION' if 'OPERACION' in df_o.columns else 'OPERACIÓN'
                df_o['KEY'] = df_o[c_ro].apply(self._limpiar) + "-" + df_o.iloc[:, df_o.columns.get_loc(c_ro)+1].apply(self._limpiar_rev) + "-" + df_o[col_op].apply(self._limpiar)
                self.raw_data["ops"] = df_o

            for llave_busqueda in llaves_list:
                partes = llave_busqueda.split('-')
                ruta, rev, op = self._limpiar(partes[0]), self._limpiar_rev(partes[1]), self._limpiar(partes[2])
                llave_rr = f"{ruta}-{rev}"
                
                self._escribir_reporte(f"  REGISTRO ANALIZADO: {llave_busqueda}  ", "h3")
                
                self._escribir_reporte("ARCHIVO DE ORIGEN: 'LANZAMIENTO MSN'", "h2")
                fila_lanz = self.raw_data["lanz"][self.raw_data["lanz"]['KEY'] == llave_rr]
                if not fila_lanz.empty:
                    for col in fila_lanz.columns:
                        if col != 'KEY' and pd.notna(fila_lanz.iloc[0][col]): 
                            self._escribir_reporte(f"• {col}: {fila_lanz.iloc[0][col]}", "bullet")
                else: 
                    self._escribir_reporte("Aviso: No se encontró esta Ruta-Rev en el archivo de Lanzamiento.", "motivo_error")

                self._escribir_reporte("\nARCHIVO DE ORIGEN: 'EXTRACTO OPERACIONES'", "h2")
                fila_ops = self.raw_data["ops"][self.raw_data["ops"]['KEY'] == f"{llave_rr}-{op}"]
                if not fila_ops.empty:
                    for col in fila_ops.columns:
                        if col != 'KEY' and pd.notna(fila_ops.iloc[0][col]): 
                            self._escribir_reporte(f"• {col}: {str(fila_ops.iloc[0][col]).replace(chr(10), ' ')}", "bullet")
                else: 
                    self._escribir_reporte("Aviso: No se encontró esta Operación exacta en el Extracto.", "motivo_error")
                    
        except Exception as e: 
            self._escribir_reporte(f"Error accediendo a los archivos originales: {e}", "motivo_error")

# =====================================================================
# EJECUCIÓN PRINCIPAL
# =====================================================================
if __name__ == "__main__":
    root = TkinterDnD.Tk()
    app = AppSinergias(root)
    root.mainloop()