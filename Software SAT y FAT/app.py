"""Generador de protocolos SAT / FAT (con Anexos 1 y 2) - Grupo Oeste."""
import datetime
import json
import os
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

import generador_sat as g
import gestion
import validador

TIPOS_TABLERO = ["Tablero de Control", "Tablero de Protección", "Tablero de Control y Protección",
                 "Tablero de Servicios Auxiliares", "Tablero de Comunicaciones", "Tablero de Medición"]
TENSIONES = ["33 KV", "66/13,2 KV", "132 KV", "13,2 KV"]
SET_TIPICO = [("RTAC SEL 2241", 1), ("POWER COUPLER SEL 2243", 2),
              ("MÓDULO DI SEL 2244-2", 7), ("MÓDULO DO SEL 2244-3", 2)]

CAMPOS = [  # clave, etiqueta, valor por defecto, opciones (None = campo de texto)
    ("CLIENTE", "Cliente", "EDESTE", None),
    ("NRO_OBRA", "Nº de obra", "205", None),
    ("OBRA", "Proyecto/Obra", "205-EDESTE_Reemplazo RTUs", None),
    ("UBICACION", "Ubicación", "", None),
    ("TIPO_TABLERO", "Tipo de tablero", "Tablero de Control", TIPOS_TABLERO),
    ("NOMBRE", "Nombre / estación", "", None),
    ("TENSION", "Tensión", "33 KV", TENSIONES),
    ("FECHA", "Fecha (dd/mm/aaaa)", "", None),
    ("REVISION", "Revisión", "A", None),
]
DOCUMENTOS = [("SAT", "Protocolo SAT (con sus anexos)"), ("FAT", "Protocolo FAT"), ("A1", "FAT Anexo 1 (energizado)"),
              ("A2", "FAT Anexo 2 (señales)")]
PRESETS = [("Solo SAT", ("SAT",)), ("FAT completo", ("FAT", "A1", "A2")),
           ("Paquete completo", ("SAT", "FAT", "A1", "A2"))]
COLORES = {validador.BLOQUEANTE: "#fde2e2", validador.ADVERTENCIA: "#fff3cd", validador.INFO: "#eef2f7"}


def archivo_config():
    return os.path.join(gestion.carpeta_programa_usuario(), "config.json")


class TablaEditable(ttk.Frame):
    """Treeview editable con doble clic."""

    def __init__(self, master, columnas, anchos, alto=6):
        super().__init__(master)
        self.tree = ttk.Treeview(self, columns=columnas, show="headings", height=alto, selectmode="extended")
        for col, ancho in zip(columnas, anchos):
            self.tree.heading(col, text=col)
            self.tree.column(col, width=ancho, stretch=True)
        barra = ttk.Scrollbar(self, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=barra.set)
        self.tree.grid(row=0, column=0, sticky="nsew")
        barra.grid(row=0, column=1, sticky="ns")
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self._editar)

    def agregar(self, valores):
        self.tree.insert("", "end", values=valores)

    def filas(self):
        return [tuple(self.tree.item(i, "values")) for i in self.tree.get_children()]

    def limpiar(self):
        self.tree.delete(*self.tree.get_children())

    def cargar(self, filas):
        self.limpiar()
        for fila in filas:
            self.agregar(fila)

    def quitar(self):
        for i in self.tree.selection():
            self.tree.delete(i)

    def duplicar(self):
        for i in self.tree.selection():
            nuevo = self.tree.insert("", self.tree.index(i) + 1, values=self.tree.item(i, "values"))
            self.tree.selection_set(nuevo)

    def insertar_vacia(self):
        sel = self.tree.selection()
        pos = self.tree.index(sel[-1]) + 1 if sel else "end"
        nuevo = self.tree.insert("", pos, values=[""] * len(self.tree["columns"]))
        self.tree.selection_set(nuevo)
        self.tree.see(nuevo)

    def mover(self, delta):
        for i in sorted(self.tree.selection(), key=self.tree.index, reverse=delta > 0):
            self.tree.move(i, "", max(0, self.tree.index(i) + delta))

    def _editar(self, evento):
        fila = self.tree.identify_row(evento.y)
        col = self.tree.identify_column(evento.x)
        if not fila or not col:
            return
        x, y, ancho, alto = self.tree.bbox(fila, col)
        idx = int(col[1:]) - 1
        valores = list(self.tree.item(fila, "values"))
        entrada = ttk.Entry(self.tree)
        entrada.insert(0, valores[idx])
        entrada.select_range(0, "end")
        entrada.place(x=x, y=y, width=ancho, height=alto)
        entrada.focus()

        def guardar(_=None):
            valores[idx] = entrada.get()
            self.tree.item(fila, values=valores)
            entrada.destroy()

        entrada.bind("<Return>", guardar)
        entrada.bind("<FocusOut>", guardar)
        entrada.bind("<Escape>", lambda _: entrada.destroy())


def panel_tabla(master, titulo, columnas, anchos, botones, alto=8):
    """Marco con una TablaEditable y una columna de botones [(texto, comando)]."""
    marco = ttk.LabelFrame(master, text=titulo, padding=8)
    marco.columnconfigure(0, weight=1)
    marco.rowconfigure(0, weight=1)
    tabla = TablaEditable(marco, columnas, anchos, alto=alto)
    tabla.grid(row=0, column=0, sticky="nsew")
    caja = ttk.Frame(marco)
    caja.grid(row=0, column=1, sticky="n", padx=(8, 0))
    for texto, cmd in botones(tabla):
        ttk.Button(caja, text=texto, command=cmd).pack(fill="x", pady=2)
    return marco, tabla


def botones_basicos(tabla):
    return [("Agregar fila", tabla.insertar_vacia), ("Duplicar", tabla.duplicar), ("Quitar", tabla.quitar),
            ("Subir", lambda: tabla.mover(-1)), ("Bajar", lambda: tabla.mover(1))]


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Generador de Protocolos SAT / FAT - Grupo Oeste")
        self.geometry("980x860")
        self.minsize(820, 700)
        self.vars = {}
        self.incluir = {k: tk.BooleanVar(value=k in ("FAT", "A1", "A2")) for k, _ in DOCUMENTOS}
        self.pdf = tk.BooleanVar(value=True)
        self.pdfs = {}            # nombre -> ruta de los planos cargados
        self.confirmados = set()  # (código, archivo) de hallazgos de los planos que el usuario confirmó
        self.protecciones = tk.BooleanVar(value=True)
        self.carpeta = tk.StringVar(value="")
        self.ruta_proyecto = ""
        self.ultima_carpeta = ""
        self.pdf_anexo = {"A1": [], "A2": []}
        self.cola = queue.Queue()
        self.ocupado = False
        self.informe = None
        self.report_callback_exception = lambda tipo, valor, tb: messagebox.showerror(
            "Error", f"{tipo.__name__}: {valor}")
        self._armar()
        self._menu()
        self._cargar_config()
        self.protocol("WM_DELETE_WINDOW", self._cerrar)

    # ---------- interfaz ----------
    def _menu(self):
        barra = tk.Menu(self)
        proyecto = tk.Menu(barra, tearoff=0)
        proyecto.add_command(label="Nuevo proyecto", command=self._nuevo)
        proyecto.add_command(label="Abrir proyecto…", command=self._abrir)
        proyecto.add_command(label="Guardar proyecto", command=self._guardar)
        proyecto.add_command(label="Guardar proyecto como…", command=lambda: self._guardar(True))
        barra.add_cascade(label="Proyecto", menu=proyecto)
        herramientas = tk.Menu(barra, tearoff=0)
        herramientas.add_command(label="Controlar documentos existentes…", command=self._validar_archivos)
        herramientas.add_command(label="Versiones anteriores de un documento…", command=self._versiones)
        herramientas.add_command(label="Ver registro de operaciones", command=self._ver_registro)
        barra.add_cascade(label="Herramientas", menu=herramientas)
        ayuda = tk.Menu(barra, tearoff=0)
        ayuda.add_command(label="Alcance del control de calidad", command=lambda: messagebox.showinfo(
            "Alcance", validador.AVISO_ALCANCE))
        barra.add_cascade(label="Ayuda", menu=ayuda)
        self.config(menu=barra)

    def _armar(self):
        raiz = ttk.Frame(self, padding=10)
        raiz.pack(fill="both", expand=True)
        raiz.columnconfigure(0, weight=1)
        raiz.rowconfigure(3, weight=1)

        self.lbl_proyecto = ttk.Label(raiz, text="Proyecto sin guardar", foreground="gray")
        self.lbl_proyecto.grid(row=0, column=0, sticky="w")

        datos = ttk.LabelFrame(raiz, text="Datos del protocolo", padding=8)
        datos.grid(row=1, column=0, sticky="ew", pady=(2, 0))
        for n, (clave, etiqueta, defecto, opciones) in enumerate(CAMPOS):
            fila, col = divmod(n, 2)
            ttk.Label(datos, text=etiqueta + ":").grid(row=fila, column=col * 2, sticky="w", padx=(0, 4), pady=3)
            var = tk.StringVar(value=defecto)
            w = ttk.Combobox(datos, textvariable=var, values=opciones) if opciones else ttk.Entry(datos, textvariable=var)
            w.grid(row=fila, column=col * 2 + 1, sticky="ew", padx=(0, 12), pady=3)
            self.vars[clave] = var
        datos.columnconfigure(1, weight=1)
        datos.columnconfigure(3, weight=1)
        self.vars["FECHA"].set(datetime.date.today().strftime("%d/%m/%Y"))

        sel = ttk.LabelFrame(raiz, text="Qué generar", padding=8)
        sel.grid(row=2, column=0, sticky="ew", pady=6)
        for i, (clave, etiqueta) in enumerate(DOCUMENTOS):
            ttk.Checkbutton(sel, text=etiqueta, variable=self.incluir[clave]).grid(row=0, column=i, sticky="w", padx=(0, 14))
        ttk.Checkbutton(sel, text="Incluir lectura de protecciones", variable=self.protecciones).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(4, 0))
        ttk.Checkbutton(sel, text="Exportar también PDF", variable=self.pdf).grid(
            row=1, column=2, columnspan=2, sticky="w", pady=(4, 0))
        presets = ttk.Frame(sel)
        presets.grid(row=0, column=5, rowspan=2, sticky="e", padx=(10, 0))
        sel.columnconfigure(4, weight=1)
        for texto, claves in PRESETS:
            ttk.Button(presets, text=texto, command=lambda c=claves: self._preset(c)).pack(side="left", padx=2)

        self.pestanas = ttk.Notebook(raiz)
        self.pestanas.grid(row=3, column=0, sticky="nsew")

        p1 = ttk.Frame(self.pestanas, padding=6)
        p1.columnconfigure(0, weight=1)
        p1.rowconfigure(0, weight=1)
        p1.rowconfigure(1, weight=2)
        self.pestanas.add(p1, text="Documentos y componentes")
        marco, self.t_refs = panel_tabla(
            p1, "Documentos de referencia (doble clic para editar)", ("Archivo", "Descripción"), (300, 420),
            lambda t: [("Leer planos (1 o 2 PDF)…", self._leer_planos), ("Agregar archivos…", self._agregar_docs),
                       ("Agregar a mano", t.insertar_vacia),
                       ("Recalcular descripción", self._recalcular), ("Quitar", t.quitar),
                       ("Subir", lambda: t.mover(-1)), ("Bajar", lambda: t.mover(1))], alto=5)
        marco.grid(row=0, column=0, sticky="nsew")
        marco, self.t_comp = panel_tabla(
            p1, "Componentes de hardware (doble clic para editar)", ("Componente", "Número de serie"), (420, 300),
            lambda t: [("Cargar set típico…", self._set_tipico)] + botones_basicos(t), alto=8)
        marco.grid(row=1, column=0, sticky="nsew", pady=(8, 0))

        p2 = ttk.Frame(self.pestanas, padding=6)
        p2.columnconfigure(0, weight=1)
        p2.rowconfigure(1, weight=1)
        self.pestanas.add(p2, text="Anexo 1 - Energizado")
        self.lbl_an1 = ttk.Label(p2, foreground="gray", text="Subí el PDF de planos (topográfico y/o funcional) para "
                                 "leer las térmicas. Grupo: 220 VCA o 110 VCC.")
        self.lbl_an1.grid(row=0, column=0, sticky="w")
        marco, self.t_term = panel_tabla(
            p2, "Térmicas del Anexo 1", ("Grupo", "Descripción", "Térmica"), (90, 460, 90),
            lambda t: [("Subir PDF…", self._leer_termicas), ("Sugerir descripciones…", self._sugerir)] + botones_basicos(t), alto=12)
        marco.grid(row=1, column=0, sticky="nsew")

        p3 = ttk.Frame(self.pestanas, padding=6)
        p3.columnconfigure(0, weight=1)
        p3.rowconfigure(1, weight=3)
        p3.rowconfigure(2, weight=1)
        self.pestanas.add(p3, text="Anexo 2 - Señales")
        self.lbl_an2 = ttk.Label(p3, foreground="gray", text="Subí el PDF del esquema funcional (EF). Las señales sin "
                                 "borne quedan como '(ver H3/C01)': completarlas.")
        self.lbl_an2.grid(row=0, column=0, sticky="w")
        marco, self.t_sen = panel_tabla(
            p3, "Señales", ("Borne / Elemento", "Señal"), (150, 520),
            lambda t: [("Subir PDF…", self._leer_senales)] + botones_basicos(t), alto=10)
        marco.grid(row=1, column=0, sticky="nsew")
        marco, self.t_cmd = panel_tabla(p3, "Comandos", ("Borne", "Comando"), (150, 520), botones_basicos, alto=5)
        marco.grid(row=2, column=0, sticky="nsew", pady=(8, 0))

        p4 = ttk.Frame(self.pestanas, padding=6)
        p4.columnconfigure(0, weight=1)
        p4.rowconfigure(1, weight=1)
        self.pestanas.add(p4, text="Control de calidad")
        self.lbl_calidad = ttk.Label(p4, text="Todavía no se controló ningún documento.", font=("Segoe UI", 10, "bold"))
        self.lbl_calidad.grid(row=0, column=0, sticky="w")
        cols = ("Gravedad", "Tipo", "Archivo", "Apartado", "Descripción", "Solución")
        self.t_cal = ttk.Treeview(p4, columns=cols, show="headings", height=14)
        for c, a in zip(cols, (90, 100, 190, 140, 330, 260)):
            self.t_cal.heading(c, text=c)
            self.t_cal.column(c, width=a, stretch=c in ("Descripción", "Solución"))
        for grav, color in COLORES.items():
            self.t_cal.tag_configure(grav, background=color)
        barra = ttk.Scrollbar(p4, orient="vertical", command=self.t_cal.yview)
        self.t_cal.configure(yscrollcommand=barra.set)
        self.t_cal.grid(row=1, column=0, sticky="nsew")
        barra.grid(row=1, column=1, sticky="ns")
        self.t_cal.bind("<Double-1>", self._detalle_hallazgo)
        pie_cal = ttk.Frame(p4)
        pie_cal.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Label(pie_cal, foreground="gray", text="Control documental y de formato; no valida criterios técnicos "
                  "de ingeniería. Doble clic en una fila para ver el detalle.").pack(side="left")
        ttk.Button(pie_cal, text="Exportar informe…", command=self._exportar_informe).pack(side="right")

        pie = ttk.Frame(raiz)
        pie.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        pie.columnconfigure(1, weight=1)
        ttk.Label(pie, text="Carpeta de salida:").grid(row=0, column=0, sticky="w")
        ttk.Entry(pie, textvariable=self.carpeta).grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(pie, text="Elegir…", command=self._elegir_carpeta).grid(row=0, column=2)
        ttk.Button(pie, text="Abrir carpeta", command=self._abrir_carpeta).grid(row=0, column=3, padx=(4, 0))
        self.progreso = ttk.Progressbar(pie, maximum=1.0)
        self.progreso.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self.estado = ttk.Label(pie, text="Listo.", foreground="gray")
        self.estado.grid(row=2, column=0, columnspan=3, sticky="w")
        self.btn_generar = ttk.Button(pie, text="Generar documentos", command=self._generar)
        self.btn_generar.grid(row=1, column=3, rowspan=2, sticky="e", padx=(4, 0), pady=(6, 0))

    def _preset(self, claves):
        claves = {{"FAT_A1": "A1", "FAT_A2": "A2"}.get(c, c) for c in claves}
        for k, v in self.incluir.items():
            v.set(k in claves)

    def _seleccion(self):
        marcadas = [k for k, _ in DOCUMENTOS if self.incluir[k].get()]
        if "SAT" in marcadas:
            marcadas += ["SAT_A1", "SAT_A2"]
        return g.normalizar_incluir(marcadas)

    # ---------- proyecto ----------
    def _estado_proyecto(self):
        return {"datos": self._datos(), "documentos": self.t_refs.filas(), "componentes": self.t_comp.filas(),
                "termicas": self.t_term.filas(), "senales": self.t_sen.filas(), "comandos": self.t_cmd.filas(),
                "opciones": {"incluir": list(self._seleccion()), "pdf": self.pdf.get(),
                             "protecciones": self.protecciones.get()},
                "carpeta_salida": self.carpeta.get(), "pdf_anexo": self.pdf_anexo, "pdfs": self.pdfs}

    def _cargar_estado(self, e):
        for k, v in e.get("datos", {}).items():
            if k in self.vars:
                self.vars[k].set(v)
        self.t_refs.cargar([tuple(f) for f in e.get("documentos", [])])
        self.t_comp.cargar([tuple(f) for f in e.get("componentes", [])])
        self.t_term.cargar([tuple(f) for f in e.get("termicas", [])])
        self.t_sen.cargar([tuple(f) for f in e.get("senales", [])])
        self.t_cmd.cargar([tuple(f) for f in e.get("comandos", [])])
        op = e.get("opciones", {})
        self._preset(tuple(op.get("incluir", ["FAT", "A1", "A2"])))
        self.pdf.set(bool(op.get("pdf", False)))
        self.protecciones.set(bool(op.get("protecciones", True)))
        self.carpeta.set(e.get("carpeta_salida", ""))
        self.pdf_anexo = e.get("pdf_anexo", {"A1": [], "A2": []})
        self.pdfs = dict(e.get("pdfs", {}))
        for lbl, clave, prefijo in ((self.lbl_an1, "A1", "Leído de: "), (self.lbl_an2, "A2", "Leído de: ")):
            if self.pdf_anexo.get(clave):
                lbl.config(text=prefijo + ", ".join(os.path.basename(r) for r in self.pdf_anexo[clave]))

    def _titulo_proyecto(self):
        nombre = os.path.basename(self.ruta_proyecto) if self.ruta_proyecto else "sin guardar"
        self.lbl_proyecto.config(text=f"Proyecto: {nombre}")

    def _nuevo(self):
        if not messagebox.askyesno("Nuevo proyecto", "Se vacían los datos cargados. ¿Continuar?"):
            return
        self._cargar_estado({"datos": {"NOMBRE": "", "FECHA": datetime.date.today().strftime("%d/%m/%Y"),
                                       "REVISION": "A"}, "carpeta_salida": self.carpeta.get()})
        self.ruta_proyecto = ""
        self._titulo_proyecto()

    def _abrir(self):
        ruta = filedialog.askopenfilename(title="Abrir proyecto", initialdir=gestion.carpeta_proyectos(),
                                          filetypes=[("Proyecto", "*.json")])
        if not ruta:
            return
        try:
            self._cargar_estado(gestion.cargar_proyecto(ruta))
        except (OSError, ValueError) as e:
            messagebox.showerror("No se pudo abrir el proyecto", str(e))
            return
        self.ruta_proyecto = ruta
        self._titulo_proyecto()
        self._estado_texto(f"Proyecto abierto: {os.path.basename(ruta)}")

    def _guardar(self, como=False):
        ruta = self.ruta_proyecto
        if como or not ruta:
            nombre = gestion.nombre_archivo_seguro(self.vars["NOMBRE"].get() or "proyecto")
            ruta = filedialog.asksaveasfilename(title="Guardar proyecto", defaultextension=".json",
                                                initialdir=gestion.carpeta_proyectos(),
                                                initialfile=f"{nombre}.json", filetypes=[("Proyecto", "*.json")])
            if not ruta:
                return False
        try:
            gestion.guardar_proyecto(ruta, self._estado_proyecto())
        except OSError as e:
            messagebox.showerror("No se pudo guardar el proyecto", str(e))
            return False
        self.ruta_proyecto = ruta
        self._titulo_proyecto()
        self._estado_texto(f"Proyecto guardado: {os.path.basename(ruta)}")
        return True

    # ---------- documentos y componentes ----------
    def _descripcion(self, archivo):
        return g.deducir_descripcion(archivo, self.vars["TIPO_TABLERO"].get(), self.vars["TENSION"].get())

    def _agregar_docs(self):
        rutas = filedialog.askopenfilenames(
            title="Elegir documentos de referencia", initialdir=self.ultima_carpeta or None,
            filetypes=[("Planos PDF", "*.pdf"), ("Todos los archivos", "*.*")])
        for ruta in rutas:
            nombre = os.path.basename(ruta)
            self.pdfs[nombre] = ruta
            self.t_refs.agregar((nombre, self._descripcion(nombre)))
        if rutas:
            self.ultima_carpeta = os.path.dirname(rutas[0])

    def _recalcular(self):
        tree = self.t_refs.tree
        for i in tree.selection() or tree.get_children():
            archivo, desc = tree.item(i, "values")
            tree.item(i, values=(archivo, self._descripcion(archivo) or desc))

    def _set_tipico(self):
        if self.t_comp.filas() and not messagebox.askyesno("Set típico", "¿Reemplazar la lista actual?"):
            return
        nuevas = []
        for nombre, cantidad in SET_TIPICO:
            n = simpledialog.askinteger("Set típico", f"Cantidad de {nombre}:", initialvalue=cantidad,
                                        minvalue=0, maxvalue=60, parent=self)
            if n is None:
                return
            nuevas += [(nombre, "")] * n
        self.t_comp.cargar(nuevas)

    # ---------- PDF subidos para los anexos ----------
    def _subir_pdf(self, titulo):
        rutas = list(filedialog.askopenfilenames(title=titulo, initialdir=self.ultima_carpeta or None,
                                                 filetypes=[("PDF", "*.pdf")]))
        for r in rutas:
            problema = gestion.validar_pdf(r)
            if problema:
                messagebox.showerror("PDF no válido", f"{os.path.basename(r)}: {problema}")
                return []
        for r_ in rutas:
            self.pdfs[os.path.basename(r_)] = r_
        if rutas:
            self.ultima_carpeta = os.path.dirname(rutas[0])
        return rutas

    def _sugerir(self):
        import extraer_pdf
        if not messagebox.askyesno("Sugerir descripciones", "Las sugerencias salen de los protocolos de referencia (La Paz), NO de los "
                                   "planos de esta obra. Solo se completan los campos vacíos y después hay que verificarlos. ¿Aplicarlas?"):
            return
        self.t_term.cargar(extraer_pdf.aplicar_sugerencias(self.t_term.filas()))

    def _confirmar_reemplazo(self, *tablas):
        return not any(t.filas() for t in tablas) or messagebox.askyesno("Subir PDF", "¿Reemplazar la lista actual?")

    def _leer_planos(self):
        """Un solo lugar para cargar los planos: uno (funcional con todo) o dos (funcional + constructivo).
        Alimenta documentos de referencia, Anexo 1 (térmicas) y Anexo 2 (señales); los botones de cada anexo siguen disponibles."""
        if not self._confirmar_reemplazo(self.t_term, self.t_sen, self.t_cmd):
            return
        rutas = self._subir_pdf("Planos de ingeniería: elegir 1 PDF (funcional con todo) o 2 (funcional y constructivo)")
        if not rutas:
            return
        existentes = {f[0] for f in self.t_refs.filas()}
        for r_ in rutas:
            nombre = os.path.basename(r_)
            if nombre not in existentes:
                self.t_refs.agregar((nombre, self._descripcion(nombre)))
        avisos = self._cargar_termicas(rutas, aviso=False) + self._cargar_senales(rutas, aviso=False)
        mensaje = (f"Planos leídos: {', '.join(os.path.basename(r) for r in rutas)}.\n"
                   f"Térmicas: {len(self.t_term.filas())}. Señales: {len(self.t_sen.filas())}. Comandos: {len(self.t_cmd.filas())}.")
        if not (self.t_sen.filas() or self.t_term.filas()):
            mensaje += ("\n\nNo se pudo leer ninguna señal ni térmica de estos planos (el lector no reconoce este formato de plano). "
                        "No se carga nada por suposición: completá las tablas a mano.")
        if avisos:
            mensaje += "\n\nRevisar:\n- " + "\n- ".join(dict.fromkeys(avisos))
        messagebox.showinfo("Leer planos", mensaje)

    def _leer_termicas(self):
        if not self._confirmar_reemplazo(self.t_term):
            return
        rutas = self._subir_pdf("Anexo 1: elegir PDF de planos (topográfico y/o funcional)")
        if rutas:
            self._cargar_termicas(rutas)

    def _cargar_termicas(self, rutas, aviso=True):
        import extraer_pdf
        self.config(cursor="watch")
        self.update()
        try:
            termicas = extraer_pdf.extraer_termicas(*rutas)
        except Exception as e:
            messagebox.showerror("Error al leer los PDF", str(e))
            return ["No se pudieron leer las térmicas: " + str(e)]
        finally:
            self.config(cursor="")
        # El plano da la térmica (y a veces la tensión); el grupo y la descripción se completan con las
        # habituales de los protocolos de referencia. Lo que no se pueda completar queda vacío y se pide.
        self.t_term.cargar(extraer_pdf.aplicar_sugerencias(termicas))
        self.pdf_anexo["A1"] = rutas
        self.lbl_an1.config(text="Leído de: " + ", ".join(os.path.basename(r) for r in rutas)
                            + ". Grupo y descripción: valores habituales de los protocolos de referencia; revisarlos.")
        avisos = []
        if not termicas:
            avisos.append("No se encontraron térmicas (-Q…) en el PDF. Cargarlas a mano.")
        elif any(not g_.strip() or not d.strip() for g_, d, _ in self.t_term.filas()):
            avisos.append("Hay térmicas sin descripción o grupo conocido: completalas en la tabla.")
        if aviso:
            for a in avisos:
                messagebox.showinfo("Subir PDF", a)
        return avisos

    def _leer_senales(self):
        if not self._confirmar_reemplazo(self.t_sen, self.t_cmd):
            return
        rutas = self._subir_pdf("Anexo 2: elegir el PDF del esquema funcional (EF)")
        if rutas:
            self._cargar_senales(rutas)

    def _cargar_senales(self, rutas, aviso=True):
        import extraer_pdf
        self.config(cursor="watch")
        self.update()
        try:
            senales, comandos, avisos = [], [], []
            for ruta in rutas:
                s, c, a = extraer_pdf.extraer_senales(ruta)
                senales += s
                comandos += c
                avisos += a
        except Exception as e:
            messagebox.showerror("Error al leer el PDF", str(e))
            return ["No se pudieron leer las señales: " + str(e)]
        finally:
            self.config(cursor="")
        self.t_sen.cargar(senales)
        self.t_cmd.cargar(comandos)
        di, do = (sum(v) for v in zip(*(extraer_pdf.contar_modulos(r_) for r_ in rutas)))
        # Hardware según el plano: los módulos DI/DO se rehacen con la cantidad que dibuja el plano funcional
        otros = [f for f in self.t_comp.filas() if not f[0].upper().startswith(("MÓDULO DI", "MODULO DI", "MÓDULO DO", "MODULO DO"))]
        self.t_comp.cargar(otros + [("MÓDULO DI SEL 2244-2", "")] * di + [("MÓDULO DO SEL 2244-3", "")] * do)
        self.pdf_anexo["A2"] = rutas
        self.lbl_an2.config(text="Leído de: " + ", ".join(os.path.basename(r) for r in rutas))
        if aviso:
            mensaje = f"Se leyeron {len(senales)} señales y {len(comandos)} comandos."
            if avisos:
                mensaje += "\n\nRevisar:\n- " + "\n- ".join(avisos)
            messagebox.showinfo("Leer del PDF", mensaje)
        return avisos

    # ---------- generación ----------
    def _datos(self):
        d = {k: v.get().strip() for k, v in self.vars.items()}
        d["PROTECCIONES"] = self.protecciones.get()
        return d

    def _estado_texto(self, texto, fraccion=None):
        self.estado.config(text=texto)
        if fraccion is not None:
            self.progreso["value"] = fraccion

    def _elegir_carpeta(self):
        ruta = filedialog.askdirectory(title="Carpeta donde guardar los documentos",
                                       initialdir=self.carpeta.get() or self.ultima_carpeta or None)
        if ruta:
            self.carpeta.set(ruta)

    def _abrir_carpeta(self):
        ruta = self.carpeta.get()
        if ruta and os.path.isdir(ruta):
            os.startfile(ruta)
        else:
            messagebox.showinfo("Carpeta", "Elegí primero una carpeta de salida que exista.")

    def _generar(self):
        if self.ocupado:
            return
        datos = self._datos()
        errores = gestion.validar_entradas(datos)
        if errores:
            messagebox.showwarning("Revisá los datos", "\n".join(m for _, m in errores))
            return
        incluir = self._seleccion()
        if not incluir:
            messagebox.showwarning("Qué generar", "Marcá al menos un documento para generar.")
            return
        carpeta = self.carpeta.get().strip()
        if not carpeta:
            self._elegir_carpeta()
            carpeta = self.carpeta.get().strip()
            if not carpeta:
                return
        if not os.path.isdir(carpeta):
            messagebox.showerror("Carpeta de salida", "La carpeta de salida no existe.")
            return
        existentes = [os.path.basename(r) for _, r in g.documentos_previstos(datos, carpeta, incluir) if os.path.exists(r)]
        if existentes and not messagebox.askyesno(
                "Ya existen documentos",
                "Ya existen:\n\n" + "\n".join(existentes) + "\n\nLas versiones actuales NO se pierden: se guardan en la "
                "carpeta 'versiones' y se pueden recuperar desde Herramientas. ¿Generar los nuevos?"):
            return
        self.ocupado = True
        self.btn_generar.state(["disabled"])
        args = (datos, self.t_refs.filas(), self.t_comp.filas(), self.t_term.filas(), self.t_sen.filas(),
                self.t_cmd.filas(), carpeta, incluir, self.pdf.get())

        def trabajo():
            try:
                r = g.generar_paquete(*args, progreso=lambda t, f: self.cola.put(("progreso", t, f)),
                                    pdfs=dict(self.pdfs), confirmados=set(self.confirmados))
                self.cola.put(("fin", r))
            except g.DatosIncompletos as e:
                self.cola.put(("incompleto", e))
            except Exception as e:
                self.cola.put(("error", e))

        threading.Thread(target=trabajo, daemon=True).start()
        self.after(150, self._revisar_cola)

    def _revisar_cola(self):
        try:
            while True:
                msg = self.cola.get_nowait()
                if msg[0] == "progreso":
                    self._estado_texto(msg[1], msg[2])
                else:
                    self._terminar(msg)
                    return
        except queue.Empty:
            pass
        self.after(150, self._revisar_cola)

    def _terminar(self, msg):
        self.ocupado = False
        self.btn_generar.state(["!disabled"])
        tipo = msg[0]
        if tipo == "incompleto":
            self._mostrar_informe(validador.Informe(hallazgos=msg[1].hallazgos))
            self._estado_texto("No se generó: faltan datos obligatorios.", 0)
            if msg[1].solo_confirmables:
                lista = "\n".join(f"- {h.descripcion}" for h in msg[1].hallazgos if h.confirmable)
                if messagebox.askyesno("Confirmar datos de los PDF", "Los planos tienen inconsistencias que solo vos podés resolver:\n\n" + lista +
                                       "\n\n¿Confirmás que son correctas para esta obra? Queda registrado a tu nombre."):
                    self.confirmados |= {(h.codigo, h.archivo) for h in msg[1].hallazgos if h.confirmable}
                    self._generar()
                return
            messagebox.showwarning("No se puede generar todavía", str(msg[1])[:1800])
            return
        if tipo == "error":
            self._estado_texto("Error al generar.", 0)
            if isinstance(msg[1], PermissionError):
                messagebox.showerror("No se pudo guardar", "¿Algún documento está abierto en Word? Cerralo y reintentá.")
            else:
                messagebox.showerror("Error al generar", str(msg[1]))
            return
        r = msg[1]
        self._mostrar_informe(r["informe"])
        self._estado_texto(f"{r['estado']}: {len(r['archivos'])} documento(s) generado(s).", 1.0)
        if self.ruta_proyecto:
            self._guardar()
        self._guardar_config()
        detalle = "\n".join(os.path.basename(a) for a in r["archivos"])
        if r["archivadas"]:
            detalle += f"\n\n{len(r['archivadas'])} versión(es) anterior(es) archivada(s) en 'versiones'."
        texto = f"{r['informe'].resumen()}\n\n{detalle}\n\n¿Abrir la carpeta?"
        if messagebox.askyesno("Documentos generados", texto):
            self._abrir_carpeta()

    # ---------- control de calidad ----------
    def _mostrar_informe(self, informe):
        self.informe = informe
        self.t_cal.delete(*self.t_cal.get_children())
        orden = {validador.BLOQUEANTE: 0, validador.ADVERTENCIA: 1, validador.INFO: 2}
        for h in sorted(informe.hallazgos, key=lambda h: (orden[h.gravedad], h.archivo)):
            self.t_cal.insert("", "end", values=(h.gravedad, h.tipo, h.archivo, h.apartado, h.descripcion, h.solucion),
                              tags=(h.gravedad,))
        self.lbl_calidad.config(text=informe.resumen(),
                                foreground="#b00020" if not informe.apto else "#1b5e20")
        self.pestanas.select(self.pestanas.tabs()[-1])

    def _detalle_hallazgo(self, _):
        sel = self.t_cal.selection()
        if sel:
            v = self.t_cal.item(sel[0], "values")
            messagebox.showinfo(f"{v[0]} - {v[1]}", f"Archivo: {v[2]}\nApartado: {v[3]}\n\n{v[4]}\n\nSolución: {v[5] or '-'}")

    def _validar_archivos(self):
        rutas = filedialog.askopenfilenames(title="Elegir los documentos a controlar (mismo proyecto)",
                                            initialdir=self.carpeta.get() or self.ultima_carpeta or None,
                                            filetypes=[("Documentos Word", "*.docx")])
        if not rutas:
            return
        self.config(cursor="watch")
        self.update()
        try:
            self._mostrar_informe(validador.validar_paquete(list(rutas), con_pdf=True))
        except Exception as e:
            messagebox.showerror("Error al controlar", str(e))
        finally:
            self.config(cursor="")

    def _exportar_informe(self):
        if not self.informe:
            messagebox.showinfo("Informe", "Todavía no hay un informe para exportar.")
            return
        ruta = filedialog.asksaveasfilename(title="Guardar informe", defaultextension=".txt",
                                            initialfile="informe_control_de_calidad.txt",
                                            initialdir=self.carpeta.get() or None, filetypes=[("Texto", "*.txt")])
        if ruta:
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(self.informe.a_texto())

    # ---------- versiones y registro ----------
    def _versiones(self):
        ruta = filedialog.askopenfilename(title="Elegir el documento actual",
                                          initialdir=self.carpeta.get() or None, filetypes=[("Word", "*.docx")])
        if not ruta:
            return
        versiones = gestion.listar_versiones(ruta)
        if not versiones:
            messagebox.showinfo("Versiones", "Este documento no tiene versiones anteriores archivadas.")
            return
        win = tk.Toplevel(self)
        win.title("Versiones anteriores - " + os.path.basename(ruta))
        win.geometry("560x320")
        lista = tk.Listbox(win, activestyle="dotbox")
        lista.pack(fill="both", expand=True, padx=8, pady=8)
        for _, fecha in versiones:
            lista.insert("end", fecha)

        def restaurar():
            if not lista.curselection():
                return
            ruta_v, fecha = versiones[lista.curselection()[0]]
            if messagebox.askyesno("Restaurar", f"Se vuelve a la versión del {fecha}. La versión actual se archiva "
                                   "(no se pierde). ¿Continuar?", parent=win):
                try:
                    gestion.restaurar_version(ruta_v, ruta)
                    gestion.registrar(os.path.dirname(ruta), "restaurar_version", archivo=os.path.basename(ruta), version=fecha)
                except OSError as e:
                    messagebox.showerror("No se pudo restaurar", str(e), parent=win)
                    return
                messagebox.showinfo("Restaurar", "Versión restaurada.", parent=win)
                win.destroy()

        ttk.Button(win, text="Restaurar la versión elegida", command=restaurar).pack(pady=(0, 8))

    def _ver_registro(self):
        carpeta = self.carpeta.get()
        lineas = gestion.leer_registro(carpeta) if carpeta else []
        if not lineas:
            messagebox.showinfo("Registro", "No hay operaciones registradas en la carpeta de salida.")
            return
        texto = "\n".join(f"{x['fecha']}  {x['usuario']}  {x['accion']}  {x.get('estado', '')}  "
                          f"{', '.join(a['archivo'] for a in x.get('archivos', []))}" for x in lineas[-30:])
        win = tk.Toplevel(self)
        win.title("Registro de operaciones (últimas 30)")
        t = tk.Text(win, width=140, height=24, wrap="none")
        t.insert("1.0", texto)
        t.config(state="disabled")
        t.pack(fill="both", expand=True)

    # ---------- configuración ----------
    def _cargar_config(self):
        try:
            with open(archivo_config(), encoding="utf-8") as f:
                cfg = json.load(f)
        except (OSError, ValueError):
            return
        for clave in ("CLIENTE", "NRO_OBRA", "OBRA", "TIPO_TABLERO", "TENSION", "REVISION"):
            if cfg.get(clave):
                self.vars[clave].set(cfg[clave])
        self.ultima_carpeta = cfg.get("ultima_carpeta", "")
        self.carpeta.set(cfg.get("carpeta_salida", ""))
        for fila in cfg.get("componentes", []):
            self.t_comp.agregar(tuple(fila[:1]) + ("",))

    def _guardar_config(self):
        cfg = {k: v for k, v in self._datos().items() if k not in ("NOMBRE", "FECHA", "PROTECCIONES")}
        cfg.update({"ultima_carpeta": self.ultima_carpeta, "carpeta_salida": self.carpeta.get(),
                    "componentes": [[c] for c, _ in self.t_comp.filas()]})
        try:
            gestion.escribir_json_atomico(archivo_config(), cfg)
        except OSError:
            pass

    def _cerrar(self):
        if self.ocupado and not messagebox.askyesno("Generación en curso",
                                                    "Se está generando un documento. ¿Cerrar igual?"):
            return
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
