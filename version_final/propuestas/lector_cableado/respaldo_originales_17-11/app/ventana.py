"""Ventana del Listado de Señales: carga PDFs de ingeniería, pregunta los datos, muestra el listado (que se puede
corregir a mano), arma la carátula y exporta todo a un Excel con el formato de EPEN. Guarda y abre proyectos.

Uso:  python -m app        (desde la carpeta version_final)
"""
from __future__ import annotations

import json
import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import avisos
import desde_pdf
import descripcion
import estados as est
import estilo
import formatos
import libro as lib
import numeracion as num
from modelo import Caratula

from avisos import excel as aviso_excel

from . import avisos_ui, caratula_ui, tema

COLUMNAS = [("item", "ITEM", 45), ("nivel", "NIVEL", 55), ("descrip", "DESCRIP", 190), ("ctl", "CONTROLADOR", 110),
            ("funcion", "FUNCION", 95), ("taghmi", "TAG HMI", 200), ("deschmi", "DESC. HMI", 190),
            ("tag", "TAG SCADA", 100), ("offset", "OFFSET", 55), ("desc", "DESC. SCADA", 160), ("k", "S0 / MIN RAW", 80), ("l", "S1 / MAX RAW", 80),
            ("m", "S2 / MIN EU", 80), ("n", "S3 / MAX EU", 80), ("o", "UNIDAD", 60),
            ("tablero", "TABLERO", 60), ("bornera", "BORNERA", 65), ("borne", "BORNE", 50),
            ("tipo", "TIPO", 45), ("placa", "PLACA", 70), ("entrada", "ENTRADA", 60), ("obs", "DESCRIPCION / OBSERVACIONES", 260)]
if not desde_pdf.MOSTRAR_UTR:                  # el apartado UTR (P a W) no se muestra ni se exporta
    COLUMNAS = [c for c in COLUMNAS if c[0] not in desde_pdf.COLUMNAS_UTR]
AMARILLO = "#fff3a3"
VERDE = "#d6f0d2"             # fila con alguna celda corregida a mano
SIN_COLOR_EN_FILA = {"CONEXIONADO_INCOMPLETO"}   # avisos generales: no pintan las cientos de filas a las que aluden


FORMATO_EXCEL = "completo"       # el único formato que se exporta desde la pantalla (el reducido se quitó a pedido)


class DialogoDatos(tk.Toplevel):
    """Una sola ventana con todo lo que la app pregunta. Entra en cualquier pantalla: lo que no cabe se desplaza."""

    def __init__(self, padre, libro: lib.Libro, pestana: str | None = None):
        super().__init__(padre)
        self.title("Datos del listado")
        self.transient(padre)
        self.libro = libro
        self.resultado = False
        self._lienzos: list[tuple[tk.Canvas, ttk.Frame]] = []
        d = libro.datos
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=8, pady=(8, 4))
        self.nb = nb

        # --- Campos y offsets
        f = self._desplazable(nb, "Campos y offsets")
        ttk.Label(f, text="Offset inicial (alarmas y señales)").grid(row=0, column=0, sticky="w")
        self.off_di = ttk.Entry(f, width=8)
        self.off_di.insert(0, d.offset_digital)
        self.off_di.grid(row=0, column=1, sticky="w", pady=2)
        ttk.Label(f, text="Offset inicial (mediciones)").grid(row=1, column=0, sticky="w")
        self.off_ai = ttk.Entry(f, width=8)
        self.off_ai.insert(0, d.offset_medicion)
        self.off_ai.grid(row=1, column=1, sticky="w", pady=2)
        ttk.Label(f, text="ITEM inicial").grid(row=2, column=0, sticky="w")
        self.item = ttk.Entry(f, width=8)
        self.item.insert(0, d.item_inicial)
        self.item.grid(row=2, column=1, sticky="w", pady=2)
        ttk.Label(f, text="Estilo del listado").grid(row=0, column=3, sticky="e", padx=(16, 4))
        self.estilo = ttk.Combobox(f, values=list(estilo.ESTILOS), width=7, state="readonly")
        self.estilo.set(d.estilo or estilo.ETAP)
        self.estilo.grid(row=0, column=4, sticky="w")
        ttk.Label(f, wraplength=640, foreground="#555", text=(
            "Cada campo se numera aparte; el primer número del tag sale de su tensión (132/66 kV = 3, 33 kV = 2, "
            "13,2/6,6 kV = 1). Estilo ETAP: DESC. HMI con prefijo, un tag por estado. USRE (Senillosa): sin prefijo, "
            "un solo tag por señal doble.")).grid(row=3, column=0, columnspan=13, sticky="w", pady=(6, 0))
        titulos = ("Campo", "Tensión", "Tag", "Señ.", "Equip.", "Var. inicial", "Hasta", "Prefijo", "Controlador",
                   "Ctrl. medición", "Tablero", "Relé", "Descripción", "Med.")
        for j, t in enumerate(titulos):
            ttk.Label(f, text=t, font=("", 9, "bold")).grid(row=4, column=j, pady=(6, 2), padx=2)
        self.fila_campo: dict[str, dict] = {}
        for i, c in enumerate(libro.campos):
            hecho = c.clave in libro.hechos
            fila = 5 + i
            campo_e = ttk.Entry(f, width=6)
            campo_e.insert(0, d.numero.get(c.clave) or c.numero_pdf)
            campo_e.grid(row=fila, column=0, sticky="w", padx=2)
            nivel = ttk.Entry(f, width=7)
            nivel.insert(0, d.nivel.get(c.clave) or c.nivel_pdf)
            dig = ttk.Label(f, text="", width=8)
            llega = ttk.Label(f, text="", width=9)
            v, p, k, r = ttk.Entry(f, width=5), ttk.Entry(f, width=9), ttk.Entry(f, width=15), ttk.Entry(f, width=11)
            v.insert(0, d.variable_inicial.get(c.clave, 1))
            p.insert(0, d.prefijo_desc.get(c.clave, c.prefijo))
            k.insert(0, d.controlador.get(c.clave, c.controlador))
            r.insert(0, d.rele.get(c.clave, ""))
            tb = ttk.Entry(f, width=9)                       # tablero del campo (se deduce: campo 103 -> TC1-03)
            tb.insert(0, d.tablero.get(c.clave) or libro.tablero_defecto(c))
            km = ttk.Entry(f, width=17)                      # controlador de las mediciones del campo (ej. 15203_MED)
            km.insert(0, d.controlador_medicion.get(c.clave) or libro.controlador_medicion_defecto(c))
            cant = libro.cantidad(c)
            widgets = (nivel, dig, ttk.Label(f, text=str(cant)), ttk.Label(f, text=str(libro.equipos(c))), v, llega, p, k, km, tb, r)
            for j, w in enumerate(widgets):
                w.grid(row=fila, column=1 + j, pady=1, padx=2)
            desc_e = ttk.Entry(f, width=18)
            desc_e.insert(0, d.descripcion.get(c.clave) or c.descripcion_base)
            desc_e.grid(row=fila, column=12, pady=1, padx=2)
            med_v = tk.BooleanVar(value=d.mediciones.get(c.clave, bool(c.mediciones)))
            med_c = ttk.Checkbutton(f, variable=med_v)
            med_c.grid(row=fila, column=13, pady=1, padx=2)
            if hecho:
                for w in (campo_e, nivel, v, p, k, km, tb, r, desc_e):
                    w.configure(state="disabled")
                med_c.configure(state="disabled")
            self.fila_campo[c.clave] = {"campo_e": campo_e, "nivel": nivel, "dig": dig, "var": v, "llega": llega, "pref": p, "ctl": k,
                                        "ctl_med": km, "tablero": tb, "rele": r, "campo": c, "cant": cant, "desc": desc_e, "med": med_v}
            for e in (campo_e, nivel, v):
                e.bind("<KeyRelease>", lambda _e, clave=c.clave: self._refrescar(clave))
            self._refrescar(c.clave)

        # --- Placas de los módulos de entradas/salidas
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="Placas", state="normal" if desde_pdf.MOSTRAR_UTR else "hidden")
        ttk.Label(f, text="La placa sale del rótulo del módulo en el plano. Si el plano no la trae, escribila acá.",
                  foreground="#555").grid(row=0, column=0, columnspan=6, sticky="w")
        for j, t in enumerate(("Campo", "Hoja", "Tipo", "Señales", "Placa")):
            ttk.Label(f, text=t, font=("", 9, "bold")).grid(row=1, column=j, pady=(6, 2), padx=2)
        self.placa_entry: dict[str, ttk.Entry] = {}
        self.placa_pdf: dict[str, str] = {}
        mods = libro.modulos()
        for i, m in enumerate(mods):
            for j, v in enumerate((m["campo"], m["hoja"], m["tipo"], m["senales"])):
                ttk.Label(f, text=str(v)).grid(row=2 + i, column=j, padx=2, sticky="w" if j == 0 else "")
            e = ttk.Entry(f, width=12)
            e.insert(0, d.placas.get(m["clave"]) or m["placa_pdf"])
            e.grid(row=2 + i, column=4, padx=2, pady=1)
            self.placa_entry[m["clave"]] = e
            self.placa_pdf[m["clave"]] = m["placa_pdf"]
            if not m["placa_pdf"]:
                ttk.Label(f, text="el plano no la trae", foreground="#b00").grid(row=2 + i, column=5, padx=4, sticky="w")
        if not mods:
            ttk.Label(f, text="Este PDF no trae módulos de entradas/salidas.").grid(row=2, column=0, columnspan=5)
        else:
            fila = 3 + len(mods)
            ttk.Label(f, text="Completar las vacías desde:").grid(row=fila, column=0, columnspan=2, sticky="w", pady=(10, 0))
            self.placa_desde = ttk.Entry(f, width=10)
            self.placa_desde.grid(row=fila, column=2, columnspan=2, pady=(10, 0))
            ttk.Button(f, text="Numerar", command=self._numerar_placas).grid(row=fila, column=4, pady=(10, 0))

        # --- Servicios auxiliares: SAA (alterna) / SAC (continua). Solo aparece si el plano trae esas alarmas.
        self.sa_combos: dict[str, ttk.Combobox] = {}
        self.sa_actual: dict[str, str | None] = {}
        self.sa_recordar = tk.BooleanVar(value=True)
        sa = libro.servicios_auxiliares()
        self.pestana_sa = None
        if sa:
            sin = sum(1 for x in sa if x["campo"] is None)
            f = ttk.Frame(nb, padding=8)
            self.pestana_sa = f
            nb.add(f, text="Servicios auxiliares" + (f"  (¡{sin} sin asignar!)" if sin else ""))
            ttk.Label(f, wraplength=720, foreground="#555", text=(
                "Las alarmas de servicios auxiliares van en SAA (alterna) o en SAC (continua). Ya sé la mayoría por lo que "
                "contestaste antes o por el rótulo (Vca / Vcc). Las que no sé están marcadas en rosa: elegí a cuál va cada una.")
            ).pack(anchor="w")
            marco = ttk.Frame(f)
            marco.pack(fill="both", expand=True, pady=6)
            lienzo = tk.Canvas(marco, height=300, highlightthickness=0)
            barra = ttk.Scrollbar(marco, orient="vertical", command=lienzo.yview)
            interior = ttk.Frame(lienzo)
            interior.bind("<Configure>", lambda _e: lienzo.configure(scrollregion=lienzo.bbox("all")))
            lienzo.create_window((0, 0), window=interior, anchor="nw")
            lienzo.configure(yscrollcommand=barra.set)
            lienzo.pack(side="left", fill="both", expand=True)
            barra.pack(side="right", fill="y")
            for j, t in enumerate(("Alarma", "Hoja", "Campo", "De dónde sale")):
                ttk.Label(interior, text=t, font=("", 9, "bold")).grid(row=0, column=j, padx=4, sticky="w")
            etiqueta = {"SAA": "SAA (alterna)", "SAC": "SAC (continua)"}
            fondo = self.cget("bg")
            for i, x in enumerate(sa, start=1):
                tk.Label(interior, text=x["texto"], anchor="w", width=42,
                         bg="#f8c8dc" if x["campo"] is None else fondo).grid(row=i, column=0, padx=4, pady=1, sticky="w")
                ttk.Label(interior, text=str(x["hoja"] or "")).grid(row=i, column=1, padx=4)
                cb = ttk.Combobox(interior, values=list(etiqueta.values()), width=16, state="readonly")
                if x["campo"]:
                    cb.set(etiqueta[x["campo"]])
                cb.grid(row=i, column=2, padx=4)
                ttk.Label(interior, text={"usuario": "lo elegiste vos", "memoria": "lo contestaste antes",
                                          "rótulo": "lo dice el rótulo", "sin asignar": "no lo sé: ¿cuál es?"}[x["fuente"]]
                          ).grid(row=i, column=3, padx=4, sticky="w")
                self.sa_combos[x["clave"]] = cb
                self.sa_actual[x["clave"]] = x["campo"]
            ttk.Checkbutton(f, variable=self.sa_recordar,
                            text="Recordar mis respuestas para los próximos proyectos").pack(anchor="w")

        # --- Estados
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="Estados (señales digitales)")
        ttk.Label(f, text="S0, S1, S2, S3 separados por coma. Lo que no cambies queda en el valor por defecto.").grid(
            row=0, column=0, columnspan=2, sticky="w", pady=(0, 6))
        usados = sorted({est.tipo_estado(s) for c in libro.campos for s in c.senales if not s.reserva})
        self.est_entry: dict[str, ttk.Entry] = {}
        for i, clave in enumerate(usados):
            ttk.Label(f, text=clave).grid(row=1 + i, column=0, sticky="w")
            e = ttk.Entry(f, width=34)
            e.insert(0, ",".join(d.estados.get(clave, est.DATOS["digitales"][clave])))
            e.grid(row=1 + i, column=1, pady=1, padx=4)
            self.est_entry[clave] = e

        # --- Mediciones
        f = ttk.Frame(nb, padding=8)
        nb.add(f, text="Mediciones (rangos)")
        base = est.DATOS["medicion_defecto"]
        self.usar_default = tk.BooleanVar(value=not d.rangos)
        ttk.Checkbutton(
            f, variable=self.usar_default, command=self._cambia_default,
            text=f"Default en todas (RAW {base['min_raw']} a {base['max_raw']}, EU {base['min_eu']} a {base['max_eu']})"
        ).grid(row=0, column=0, columnspan=6, sticky="w", pady=(0, 6))
        for j, t in enumerate(("Medición", "MIN RAW", "MAX RAW", "MIN EU", "MAX EU", "Unidad")):
            ttk.Label(f, text=t, font=("", 9, "bold")).grid(row=1, column=j)
        self.rango_entry: list[list[ttk.Entry]] = []
        for i, nombre in enumerate(descripcion.vocabulario()["mediciones"]):
            ttk.Label(f, text=nombre).grid(row=2 + i, column=0, sticky="w")
            actual = d.rangos.get(i) or {**base, "unidad": est.DATOS["unidades"][i]}
            fila = []
            for j, clave in enumerate(("min_raw", "max_raw", "min_eu", "max_eu", "unidad")):
                e = ttk.Entry(f, width=10 if j < 4 else 8)
                e.insert(0, actual[clave])
                e.grid(row=2 + i, column=1 + j, padx=2, pady=1)
                fila.append(e)
            self.rango_entry.append(fila)
        self._cambia_default()

        b = ttk.Frame(self)
        b.pack(side="bottom", fill="x", padx=8, pady=(0, 8), before=nb)     # los botones siempre a la vista
        ttk.Button(b, text="Aceptar", command=self._aceptar).pack(side="right")
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right", padx=6)
        if pestana == "servicios_auxiliares" and self.pestana_sa is not None:
            nb.select(self.pestana_sa)
        self._ajustar_a_la_pantalla()
        self.grab_set()

    def _desplazable(self, nb: ttk.Notebook, texto: str) -> ttk.Frame:
        """Pestaña con barras de desplazamiento: si el contenido no entra en la pantalla, se recorre."""
        marco = ttk.Frame(nb)
        nb.add(marco, text=texto)
        lienzo = tk.Canvas(marco, highlightthickness=0, bg=tema.FONDO)
        sy = ttk.Scrollbar(marco, orient="vertical", command=lienzo.yview)
        sx = ttk.Scrollbar(marco, orient="horizontal", command=lienzo.xview)
        interior = ttk.Frame(lienzo, padding=8)
        lienzo.create_window((0, 0), window=interior, anchor="nw")
        lienzo.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        interior.bind("<Configure>", lambda _e: lienzo.configure(scrollregion=lienzo.bbox("all")))
        lienzo.bind("<MouseWheel>", lambda e: lienzo.yview_scroll(-1 * (e.delta // 120), "units"))
        lienzo.bind("<Shift-MouseWheel>", lambda e: lienzo.xview_scroll(-1 * (e.delta // 120), "units"))
        sy.pack(side="right", fill="y")
        sx.pack(side="bottom", fill="x")
        lienzo.pack(side="left", fill="both", expand=True)
        self._lienzos.append((lienzo, interior))
        return interior

    def _ajustar_a_la_pantalla(self) -> None:
        """Tamaño de la ventana: lo que pide el contenido, pero nunca más que el 90 % de la pantalla; centrada."""
        self.update_idletasks()
        pantalla_w, pantalla_h = self.winfo_screenwidth(), self.winfo_screenheight()
        tope_w, tope_h = int(pantalla_w * 0.9) - 40, int(pantalla_h * 0.8) - 110      # menos barras, título y botones
        for lienzo, interior in self._lienzos:
            lienzo.configure(width=min(interior.winfo_reqwidth(), tope_w), height=min(interior.winfo_reqheight(), tope_h))
        self.update_idletasks()
        ancho = min(self.winfo_reqwidth(), int(pantalla_w * 0.92))
        alto = min(self.winfo_reqheight(), int(pantalla_h * 0.85))
        self.geometry(f"{ancho}x{alto}+{max(0, (pantalla_w - ancho) // 2)}+{max(0, (pantalla_h - alto) // 2 - 20)}")

    def _numerar_placas(self) -> None:
        """Rellena las placas vacías de a una, sumando 1 al último número (A4.2 -> A4.3)."""
        actual = self.placa_desde.get().strip()
        if not actual:
            return
        for e in self.placa_entry.values():
            if not e.get().strip():
                e.insert(0, actual)
                m = re.match(r"^(.*?)(\d+)$", actual)
                actual = f"{m.group(1)}{int(m.group(2)) + 1}" if m else actual

    def _refrescar(self, clave: str) -> None:
        """Muestra con qué dígito empieza el tag del campo y hasta qué variable llega con el número inicial elegido."""
        w = self.fila_campo[clave]
        c = w["campo"]
        dig = self.libro.digito(w["nivel"].get())
        numero = w["campo_e"].get().strip()
        pref = desde_pdf.prefijo_de(dig, numero)
        ok = bool(numero) and (bool(dig) or not numero.isdigit())
        w["dig"].configure(text=f"{pref}.xx" if ok else ("¿campo?" if not numero else "¿tensión?"),
                           foreground="" if ok else "red")
        try:
            fin = int(w["var"].get()) + w["cant"] - 1
            w["llega"].configure(text=f"{fin:02d}" if fin <= 99 else f"{fin} (¡pasa de 99!)",
                                 foreground="red" if fin > 99 else "")
        except ValueError:
            w["llega"].configure(text="?", foreground="red")

    def _cambia_default(self):
        for fila in self.rango_entry:
            for e in fila:
                e.configure(state="disabled" if self.usar_default.get() else "normal")

    def _aceptar(self):
        d = self.libro.datos
        try:
            off_di, off_ai, item = int(self.off_di.get()), int(self.off_ai.get()), int(self.item.get())
            variables = {k: int(w["var"].get()) for k, w in self.fila_campo.items()}
            rangos = {}
            if not self.usar_default.get():
                for i, fila in enumerate(self.rango_entry):
                    mr, xr, me, xe = (est.numero(e.get()) for e in fila[:4])
                    rangos[i] = {"min_raw": mr, "max_raw": xr, "min_eu": me, "max_eu": xe, "unidad": fila[4].get().strip()}
        except ValueError:
            messagebox.showerror("Datos", "Hay un número mal escrito (offsets, variables o rangos).", parent=self)
            return
        if any(not 0 <= v <= 99 for v in variables.values()):
            messagebox.showerror("Datos", "La variable inicial va de 0 a 99.", parent=self)
            return
        for k, w in self.fila_campo.items():
            if w["campo"].clave in self.libro.hechos:
                continue
            numero = w["campo_e"].get().strip()
            if not numero:
                messagebox.showerror("Datos", "Falta el número de campo: el PDF no lo trae. Escribilo en la columna "
                                              "«Campo» (por ejemplo 04, o TP1 para el campo del transformador).", parent=self)
                return
            if numero.isdigit() and not self.libro.digito(w["nivel"].get()):
                messagebox.showerror("Datos", f"No reconozco la tensión «{w['nivel'].get()}» del campo {w['campo'].numero}. "
                                              "Escribila como 132KV, 66KV, 33KV, 13,2KV o 6,6KV.", parent=self)
                return
            if variables[k] + w["cant"] > 100:
                messagebox.showerror("Datos", f"El campo {w['campo'].numero} tiene {w['cant']} señales y cada una usa un "
                                              f"número de variable (00 a 99): poné una variable inicial de {100 - w['cant']} "
                                              "o menos.", parent=self)
                return
        d.offset_digital, d.offset_medicion, d.item_inicial = off_di, off_ai, item
        # solo se guardan las placas que el usuario escribió o cambió (las del plano se leen solas)
        d.placas = {k: e.get().strip() for k, e in self.placa_entry.items()
                    if e.get().strip() and e.get().strip() != self.placa_pdf[k]}
        d.variable_inicial.update(variables)
        d.rangos = rangos
        for k, w in self.fila_campo.items():
            if k in self.libro.hechos:
                continue
            d.numero[k] = w["campo_e"].get().strip()
            d.nivel[k] = w["nivel"].get().strip()
            d.prefijo_desc[k] = w["pref"].get().strip() or k
            d.controlador[k] = w["ctl"].get().strip()
            d.rele[k] = w["rele"].get().strip()
            med = w["ctl_med"].get().strip()                  # solo se guarda si el usuario lo cambió
            if med and med != self.libro.controlador_medicion_defecto(w["campo"]):
                d.controlador_medicion[k] = med
            else:
                d.controlador_medicion.pop(k, None)
            tab = w["tablero"].get().strip()                  # solo se guarda si el usuario lo cambió
            if tab and tab != self.libro.tablero_defecto(w["campo"]):
                d.tablero[k] = tab
            else:
                d.tablero.pop(k, None)
            texto = w["desc"].get().strip()
            if texto and texto != w["campo"].descripcion_base:
                d.descripcion[k] = texto
            else:
                d.descripcion.pop(k, None)
            d.mediciones[k] = bool(w["med"].get())
        d.estilo = self.estilo.get() or estilo.ETAP
        cambios = {}                                       # servicios auxiliares: solo lo que el usuario eligió o cambió
        for clave, cb in self.sa_combos.items():
            elegido = {"SAA (alterna)": "SAA", "SAC (continua)": "SAC"}.get(cb.get())
            if elegido and elegido != self.sa_actual[clave]:
                cambios[clave] = elegido
        if cambios:
            self.libro.asignar_sa(cambios, self.sa_recordar.get())
        d.estados = {}
        for clave, e in self.est_entry.items():
            partes = [p.strip() for p in e.get().split(",")]
            valores = (partes + [est.NA] * 4)[:4]
            if valores != est.DATOS["digitales"][clave]:
                d.estados[clave] = valores
        self.resultado = True
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Listado de señales")
        self.geometry("1300x600")
        self.libro = lib.Libro()
        self.cola: queue.Queue = queue.Queue()
        self.claves: dict[str, str] = {}            # fila de la tabla -> clave de fila (para guardar lo corregido a mano)
        self.editor: tk.Entry | None = None
        tema.aplicar(self)
        self.minsize(900, 480)
        # Barra de herramientas: pasos del trabajo a la izquierda (Calcular y Exportar resaltados), proyecto a la derecha.
        barra = ttk.Frame(self, style="Barra.TFrame", padding=(10, 8))
        barra.pack(fill="x")
        for texto, cmd, estilo_b in (("Agregar PDF…", self.agregar_pdf, "TButton"), ("Datos…", self.datos, "TButton"),
                                     ("Calcular", self.calcular, "Accent.TButton"),
                                     ("Exportar Excel…", self.exportar, "Accent.TButton")):
            ttk.Button(barra, text=texto, command=cmd, style=estilo_b).pack(side="left", padx=(0, 6))
        self.por_offset = tk.BooleanVar(value=False)
        ttk.Checkbutton(barra, text="Ver por offset (reservas en su lugar)", variable=self.por_offset,
                        command=self.mostrar, style="Barra.TCheckbutton").pack(side="left", padx=14)
        for texto, cmd in (("Limpiar", self.limpiar), ("Guardar proyecto…", self.guardar), ("Abrir proyecto…", self.abrir)):
            ttk.Button(barra, text=texto, command=cmd).pack(side="right", padx=(6, 0))
        ttk.Separator(self, style="Barra.TSeparator").pack(fill="x")
        self.estado = tk.StringVar(value="Cargá un PDF de ingeniería para empezar.")
        ttk.Label(self, textvariable=self.estado, style="Estado.TLabel", anchor="w").pack(side="bottom", fill="x")
        self.pestanas = ttk.Notebook(self)
        self.pestanas.pack(fill="both", expand=True, padx=10, pady=(8, 6))
        self._armar_vista_campos()
        marco = ttk.Frame(self.pestanas)
        self.pestanas.add(marco, text="Listado")
        self.tabla = ttk.Treeview(marco, columns=[c[0] for c in COLUMNAS], show="headings", selectmode="browse")
        for clave, titulo, ancho in COLUMNAS:
            self.tabla.heading(clave, text=titulo)
            self.tabla.column(clave, width=ancho, anchor="w")
        tema.rayar(self.tabla)
        tema.rayar(self.arbol_campos)
        tema.rayar(self.arbol_senales)
        self.tabla.tag_configure("amarillo", background=AMARILLO)
        self.tabla.tag_configure("editado", background=VERDE)
        for gravedad, color in avisos.COLORES.items():     # filas con avisos: celeste (contradice una regla) / rosa
            self.tabla.tag_configure(gravedad, background=color)
        self.tabla.tag_configure("hueco", foreground="#888")
        self.tabla.bind("<Double-1>", self._editar)
        sb = ttk.Scrollbar(marco, orient="vertical", command=self.tabla.yview)
        sh = ttk.Scrollbar(marco, orient="horizontal", command=self.tabla.xview)
        self.tabla.configure(yscrollcommand=sb.set, xscrollcommand=sh.set)
        sb.pack(side="right", fill="y")
        sh.pack(side="bottom", fill="x")
        self.tabla.pack(side="left", fill="both", expand=True)
        self.iid_de_id: dict[int, str] = {}                # id de la señal en la base -> fila de la tabla
        self.avisos_excel: list = []                       # lo que encontró la verificación del último Excel exportado
        self.formato_elegido: str = FORMATO_EXCEL          # el completo pide conexionado (tablero, bornera, borne)
        self.pestana_avisos = avisos_ui.PestanaAvisos(self.pestanas, self.ir_a_senal)
        self.pestanas.add(self.pestana_avisos, text="Avisos")
        self.pestana_caratula = caratula_ui.PestanaCaratula(self.pestanas, self.libro.perfil)
        self.pestanas.add(self.pestana_caratula, text="Carátula")
        self.after(100, self._cola)

    def ir_a_senal(self, ids: tuple[int, ...]) -> None:
        """Desde un aviso: muestra la fila de la primera señal a la que se refiere."""
        iid = next((self.iid_de_id[i] for i in ids if i in self.iid_de_id), None)
        if iid is None:
            return
        self.pestanas.select(1)
        self.tabla.selection_set(iid)
        self.tabla.focus(iid)
        self.tabla.see(iid)

    # ---------------------------------------------------------- vista previa de lo leído
    def _armar_vista_campos(self):
        """Pestaña «Campos leídos»: a la izquierda los campos que encontró en el PDF; a la derecha, las señales del
        campo elegido con la hoja del PDF de donde salió cada una, para comprobar que cada señal quedó en su campo."""
        marco = ttk.Frame(self.pestanas)
        self.pestanas.add(marco, text="Campos leídos")
        panel = ttk.PanedWindow(marco, orient="horizontal")
        panel.pack(fill="both", expand=True)
        izq = ttk.Frame(panel)
        panel.add(izq, weight=1)
        self.arbol_campos = ttk.Treeview(izq, columns=("campo", "nivel", "n", "res", "hojas"), show="headings",
                                         selectmode="browse")
        for clave, titulo, ancho in (("campo", "CAMPO", 70), ("nivel", "TENSIÓN", 85), ("n", "SEÑALES", 85),
                                     ("res", "RESERVAS", 90), ("hojas", "HOJAS DEL PDF", 130)):
            self.arbol_campos.heading(clave, text=titulo)
            self.arbol_campos.column(clave, width=ancho, anchor="w")
        self.arbol_campos.pack(fill="both", expand=True)
        self.info_campo = tk.StringVar(value="Cargá un PDF para ver qué campos encontró.")
        ttk.Label(izq, textvariable=self.info_campo, wraplength=380, padding=4).pack(fill="x")
        der = ttk.Frame(panel)
        panel.add(der, weight=3)
        cols = (("pag", "HOJA", 50), ("func", "FUNCION", 95), ("texto", "RÓTULO LEÍDO DEL PDF", 380),
                ("bits", "BITS", 45), ("cmd", "COMANDO", 70))
        self.arbol_senales = ttk.Treeview(der, columns=[c[0] for c in cols], show="headings", selectmode="browse")
        for clave, titulo, ancho in cols:
            self.arbol_senales.heading(clave, text=titulo)
            self.arbol_senales.column(clave, width=ancho, anchor="w")
        self.arbol_senales.tag_configure("reserva", foreground="#888")
        sb = ttk.Scrollbar(der, orient="vertical", command=self.arbol_senales.yview)
        self.arbol_senales.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.arbol_senales.pack(side="left", fill="both", expand=True)
        self.arbol_campos.bind("<<TreeviewSelect>>", lambda _e: self._senales_del_campo())

    def mostrar_campos(self):
        """Rellena «Campos leídos» con lo que hay en el libro."""
        sel = self.arbol_campos.selection()
        previo = self.arbol_campos.item(sel[0])["tags"][0] if sel and self.arbol_campos.item(sel[0])["tags"] else None
        self.arbol_campos.delete(*self.arbol_campos.get_children())
        for c in self.libro.campos:
            res = sum(1 for x in c.senales if x.reserva)
            hojas = ", ".join(str(p) for p in sorted(set(c.paginas)))
            self.arbol_campos.insert("", "end", iid=c.clave, tags=(c.clave,),
                                     values=(c.numero, c.nivel_pdf or "?", self.libro.cantidad(c), res, hojas))
        hijos = self.arbol_campos.get_children()
        if hijos:
            elegido = previo if previo in hijos else hijos[0]
            self.arbol_campos.selection_set(elegido)
        self._senales_del_campo()

    def _senales_del_campo(self):
        self.arbol_senales.delete(*self.arbol_senales.get_children())
        sel = self.arbol_campos.selection()
        if not sel:
            return
        c = next((x for x in self.libro.campos if x.clave == sel[0]), None)
        if c is None:
            return
        for s in c.senales:
            pag = getattr(s.origen, "pagina", "")
            texto = " / ".join(s.pares) if s.pares else ("Reserva" if s.reserva else s.texto)
            self.arbol_senales.insert("", "end", tags=("reserva",) if s.reserva else (), values=(
                pag, "RESERVA" if s.reserva else s.funcion, texto, 2 if s.doble else 1, "sí" if s.comando else ""))
        deducido = f" Deducido de la hoja (no está escrito en el cajetín): {', '.join(c.inferidos)}." if c.inferidos else \
            " Nivel y campo leídos del cajetín."
        self.info_campo.set(f"Campo {c.numero} · {c.nivel_pdf or 'tensión ?'} · {c.descripcion_base or 'sin descripción'}."
                            f" Archivo: {', '.join(c.archivos)}.{deducido}")

    # ---------------------------------------------------------- PDF
    def agregar_pdf(self):
        ruta = filedialog.askopenfilename(title="PDF de ingeniería", filetypes=[("PDF", "*.pdf")])
        if not ruta:
            return
        self.estado.set(f"Leyendo {Path(ruta).name}…")

        def trabajo():
            try:
                self.cola.put(("ok", ruta, self.libro.agregar_pdf(
                    ruta, avance=lambda n, t: self.cola.put(("avance", n, t)),
                    avance_copia=lambda n, t: self.cola.put(("copia", n, t)),
                    avance_bornes=lambda etapa, n, t: self.cola.put(("bornes", etapa, (n, t))))))
            except Exception as e:  # noqa: BLE001 - se muestra al usuario
                self.cola.put(("error", ruta, e))

        threading.Thread(target=trabajo, daemon=True).start()

    def _cola(self):
        try:
            while True:
                tipo, ruta, res = self.cola.get_nowait()
                if tipo == "bornes":                        # (etapa, (hoja, total)) de la lectura de tablas de bornes dibujadas
                    self.estado.set(("Buscando tablas de bornes en el plano" if ruta == "buscando" else "Leyendo las tablas de bornes")
                                    + f"… hoja {res[0]} de {res[1]}")
                    continue
                if tipo == "copia":                         # (bytes, total) copiados desde el servidor
                    self.estado.set(f"Copiando el PDF desde el servidor… {ruta // 2**20} de {max(res // 2**20, 1)} MB")
                    continue
                if tipo == "avance":                       # (n, total) de hojas leídas
                    self.estado.set(f"Leyendo el PDF… hoja {ruta} de {res}")
                    continue
                nombre = Path(ruta).name
                if tipo == "abierto":
                    self._proyecto_abierto(ruta, res)
                    continue
                if tipo == "error":
                    self.estado.set("No se pudo leer el PDF.")
                    messagebox.showerror("PDF", f"No pude leer {nombre}:\n{res}")
                    continue
                nuevos, repetidos = res
                if not nuevos and not repetidos:
                    i = self.libro.ultimo_info
                    messagebox.showinfo("PDF", (
                        f"No encontré señales en {nombre}.\n\n"
                        f"Revisé {i.get('paginas', '?')} hojas: {i.get('con_rotulos', 0)} con rótulos de texto, "
                        f"{i.get('con_franja', 0)} con módulos de entradas/salidas y {i.get('con_tira', 0)} con tiras de relé.\n\n"
                        + (("Las hojas del plano son:\n  • " + "\n  • ".join(i["titulos"][:8]) + "\n\n") if i.get("titulos") else "")
                        + "La app saca las señales de los módulos de entradas/salidas del tablero de control y de las tiras de "
                        "señales de los relés. Este archivo no trae ninguno de los dos: no hay hojas con alarmas, estados "
                        "ni comandos para el listado. Si alguna hoja debería dar señales, decime cuál."))
                    self.estado.set("Sin señales en ese PDF.")
                    continue
                self.mostrar_campos()
                self.pestanas.select(0)
                resumen = "\n".join(
                    f"• Campo {c.numero} ({c.nivel_pdf or 'tensión ?'}): {self.libro.cantidad(c)} señales, "
                    f"{sum(1 for x in c.senales if x.reserva)} reservas"
                    for c in self.libro.campos if c.clave in nuevos + repetidos)
                messagebox.showinfo("PDF leído", f"{nombre}\nCampos encontrados: {len(nuevos) + len(repetidos)}\n\n{resumen}")
                msg = f"{nombre}: campos nuevos {', '.join(nuevos) or '—'}."
                if repetidos:
                    msg += f" Ya estaban y se ignoraron: {', '.join(repetidos)}."
                self.estado.set(msg + " Completá «Datos…» y tocá «Calcular».")
                sin = [x for x in self.libro.servicios_auxiliares() if x["campo"] is None]
                if sin and messagebox.askyesno(          # solo pregunta si hay algo que no sabe
                        "Servicios auxiliares",
                        f"Hay {len(sin)} alarmas de servicios auxiliares que no sé si son de alterna (SAA) o de continua "
                        "(SAC). Hasta que las asignes quedan en SAA.\n\n¿Las asignás ahora?"):
                    self.datos("servicios_auxiliares")
        except queue.Empty:
            pass
        self.after(100, self._cola)

    # ---------------------------------------------------------- datos y cálculo
    def datos(self, pestana: str | None = None) -> bool:
        if not self.libro.campos:
            messagebox.showinfo("Datos", "Primero agregá un PDF.")
            return False
        d = DialogoDatos(self, self.libro, pestana)
        self.wait_window(d)
        return d.resultado

    def calcular(self):
        if not self.libro.campos:
            messagebox.showinfo("Calcular", "Primero agregá un PDF.")
            return
        agregar = False
        if self.libro.filas:
            if not self.libro.pendientes():
                if not messagebox.askyesno("Calcular", "No hay campos nuevos. ¿Recalcular todo con los datos actuales?"):
                    return
            else:
                r = messagebox.askyesnocancel(
                    "Calcular", "Ya hay un listado calculado.\n\nSí = recalcular todo desde cero.\n"
                                "No = agregar solo los campos nuevos a continuación de lo ya hecho.")
                if r is None:
                    return
                agregar = not r
        if not agregar and not self.datos():
            return
        try:
            self.libro.calcular(agregar)
        except num.ErrorNumeracion as e:
            messagebox.showerror("Calcular", str(e))
            return
        self.mostrar()
        self.pestanas.select(1)

    def mostrar(self):
        self._cerrar_editor()
        self.tabla.delete(*self.tabla.get_children())
        self.claves = {}
        proyecto, marcas, huecos = self.libro.proyecto()
        marcas = self.libro.marcas(proyecto, marcas)
        claves = desde_pdf.claves_de(proyecto)
        lista = self.calcular_avisos()                # validaciones sobre la base: solo informan
        gravedad_de: dict[int, str] = {}              # señal -> color de su fila (el celeste gana al rosa)
        for a in lista:
            if a.codigo in SIN_COLOR_EN_FILA:
                continue
            for n in a.ids:
                if gravedad_de.get(n) != avisos.CELESTE:
                    gravedad_de[n] = a.gravedad
        self.iid_de_id = {}
        i = 0
        filas = []                                   # [campo, nivel, descrip, senal, amarilla, libre, item, clave, posición]
        item = self.libro.datos.item_inicial
        for nivel in proyecto.niveles:
            for campo in nivel.campos:
                for s in campo.senales:
                    filas.append([campo.numero, nivel.nombre, campo.descripcion, s, marcas[i], huecos[i], None, claves[i], i])
                    if not huecos[i]:
                        filas[-1][6], item = item, item + 1
                    i += 1
        if self.por_offset.get():
            filas = self._por_offset(filas)
        editadas = self.libro.datos.ediciones
        for campo, nivel, descrip, s, amarilla, libre, nro, clave, pos in filas:
            vals = [nro, nivel, descrip, s.controlador, s.funcion.value, s.tag_hmi, s.desc_hmi, s.tag_scada,
                    None if libre else s.offset,                 # las filas libres van vacías (sin OFFSET)
                    s.desc_scada, s.s0, s.s1, s.s2, s.s3, s.unidad, s.tablero, s.bornera_tablero, s.borne_tablero,
                    s.tipo_punto.value if s.tipo_punto else "", s.placa, s.entrada, s.observaciones]
            vals = vals[:len(COLUMNAS)]
            tags = ()
            if gravedad_de.get(pos + 1):                      # celeste: contradice una regla / rosa: falta información
                tags = (gravedad_de[pos + 1],)
            elif clave in editadas:
                tags = ("editado",)
            elif libre or s.es_reserva:
                tags = ("hueco",)
            if not tags or tags == ("hueco",):
                tags += ("raya",) if len(self.claves) % 2 else ()
            iid = self.tabla.insert("", "end", values=["" if v is None else v for v in vals], tags=tags)
            self.claves[iid] = clave
            self.iid_de_id[pos + 1] = iid                     # la señal i de la base es la fila i + 1
        corregidas = sum(len(e) for e in editadas.values())
        celestes = sum(1 for a in lista if a.gravedad == avisos.CELESTE)
        self.estado.set(f"{len(filas)} filas · {celestes} avisos celestes y {len(lista) - celestes} rosas (pestaña Avisos) · "
                        f"{corregidas} celdas corregidas a mano (verde). Doble clic en una celda para corregirla.")

    def calcular_avisos(self) -> list:
        """Corre las validaciones sobre la base y las muestra en la pestaña «Avisos». No modifica nada."""
        db = self.libro.base()
        lista = avisos.validar(db, self.libro.perfil, avisos_de_lectura=self.libro.avisos,
                               pide_conexionado=self.formato_elegido == "completo") + self.avisos_excel
        self.pestana_avisos.mostrar(lista)
        return lista

    # ---------------------------------------------------------- corrección a mano
    def _cerrar_editor(self):
        if self.editor is not None:
            self.editor.destroy()
            self.editor = None

    def _editar(self, ev):
        """Doble clic en una celda: se corrige a mano. Vacío = volver al valor calculado. Lo corregido queda guardado
        con el proyecto y no se pierde al recalcular."""
        self._cerrar_editor()
        iid = self.tabla.identify_row(ev.y)
        col = self.tabla.identify_column(ev.x)
        if not iid or not col:
            return
        clave_col = COLUMNAS[int(col[1:]) - 1][0]
        if clave_col not in desde_pdf.EDITABLES:
            self.estado.set("Esa columna sale del plano o de la numeración; las corregibles son las de controlador, tags, "
                            "descripciones, estados, unidad, tipo, placa, entrada y observaciones.")
            return
        x, y, w, h = self.tabla.bbox(iid, col)
        actual = self.tabla.set(iid, clave_col)
        e = tk.Entry(self.tabla)
        e.insert(0, actual)
        e.select_range(0, "end")
        e.place(x=x, y=y, width=max(w, 80), height=h)
        e.focus_set()
        e.bind("<Return>", lambda _e: self._confirmar(iid, clave_col, e))
        e.bind("<Escape>", lambda _e: self._cerrar_editor())
        self.editor = e

    def _confirmar(self, iid, clave_col, e):
        texto = e.get().strip()
        clave = self.claves.get(iid)
        self._cerrar_editor()
        if clave is None:
            return
        if not texto:                                   # vacío = deshacer la corrección
            self.libro.deshacer_edicion(clave, clave_col)
        else:
            if clave_col == "tipo" and texto.upper() not in ("DI", "DO", "AI", "AO"):
                messagebox.showerror("Tipo", "El tipo de señal es DI, DO, AI o AO.")
                return
            if clave_col == "offset" and not texto.isdigit():
                messagebox.showerror("Offset", "El offset es un número entero.")
                return
            if clave_col == "desc":
                largo = self.libro.perfil.largo_max("desc_scada")
                if largo and len(texto) > largo and not messagebox.askyesno(
                        "DESC. SCADA", f"Tiene {len(texto)} caracteres y el máximo es {largo}. ¿Dejarla igual?"):
                    return
            self.libro.editar(clave, clave_col, texto.upper() if clave_col in ("desc", "tipo") else texto)
        self.mostrar()

    @staticmethod
    def _por_offset(filas):
        """Vista: por campo, lo digital (incl. reservas) en orden de offset; después comandos y mediciones.
        Las reservas del bloque final vuelven a su lugar según su offset."""
        digital = lambda f: f[3].funcion.value in ("ALARMAS", "SEÑALIZACION", "RESERVA")  # noqa: E731
        orden = list(dict.fromkeys(f[0] for f in filas if not f[3].es_reserva))
        reservas = [f for f in filas if f[3].es_reserva]
        salida = []
        for n, campo in enumerate(orden):
            propias = [f for f in filas if f[0] == campo and not f[3].es_reserva]
            dig = [f for f in propias if digital(f)]
            otras = [f for f in propias if not digital(f)]
            if dig:
                lo = min(f[3].offset for f in dig)
                siguiente = min((f[3].offset for c2 in orden[n + 1:] for f in filas if f[0] == c2 and digital(f)),
                                default=10 ** 9)
                dig += [r for r in reservas if lo <= r[3].offset < siguiente]
            salida += sorted(dig, key=lambda f: f[3].offset) + otras
        return salida

    # ---------------------------------------------------------- salida
    def exportar(self):
        if not self.libro.filas:
            messagebox.showinfo("Exportar", "Todavía no hay nada calculado.")
            return
        car = self.pestana_caratula.leer() if self.pestana_caratula.tiene_datos() else None
        if car is not None:
            problemas = self.pestana_caratula.problemas()
            if problemas:
                messagebox.showerror("Carátula", "La carátula tiene datos que no entran en la plantilla:\n\n• "
                                     + "\n• ".join(problemas) + "\n\nCorregilos en la pestaña «Carátula».")
                self.pestanas.select(self.pestana_caratula)
                return
        ruta = filedialog.asksaveasfilename(title="Guardar Excel", defaultextension=".xlsx", filetypes=[("Excel", "*.xlsx")])
        if not ruta:
            return
        db = self.libro.base(car)
        try:
            n = self.libro.exportar_formato(FORMATO_EXCEL, ruta, car, db=db)
        except PermissionError:
            messagebox.showerror("Exportar", "No pude escribir el archivo. ¿Está abierto en Excel?")
            return
        # verificación: el Excel recién escrito se lee de nuevo y se compara con la base (solo informa)
        self.avisos_excel = aviso_excel.verificar(db, formatos.cargar(FORMATO_EXCEL), ruta)
        self.mostrar()                                    # refresca colores y la pestaña Avisos
        texto = f"Listo: {ruta}\n{'Con' if car else 'Sin'} carátula.\nDescripciones a revisar: {n}"
        if self.avisos_excel:
            messagebox.showwarning("Exportar", texto + f"\n\nOjo: el Excel no coincide con la base en "
                                   f"{len(self.avisos_excel)} celdas. Mirá la pestaña «Avisos».")
            self.pestanas.select(self.pestana_avisos)
        else:
            messagebox.showinfo("Exportar", texto + "\n\nVerificado: el Excel coincide con la base.")

    def guardar(self):
        """Guarda el proyecto (.json): PDFs, datos, celdas corregidas y carátula."""
        if not self.libro.rutas:
            messagebox.showinfo("Guardar proyecto", "Todavía no hay nada para guardar.")
            return
        ruta = filedialog.asksaveasfilename(title="Guardar proyecto", defaultextension=".json",
                                            filetypes=[("Proyecto", "*.json")])
        if not ruta:
            return
        self.libro.guardar(ruta, self.pestana_caratula.leer())
        self.estado.set(f"Proyecto guardado en {ruta}.")

    def abrir(self):
        """Abre un proyecto guardado: vuelve a leer sus PDFs (tarda) y restituye datos, correcciones y carátula."""
        ruta = filedialog.askopenfilename(title="Abrir proyecto", filetypes=[("Proyecto", "*.json")])
        if not ruta:
            return
        if self.libro.campos and not messagebox.askyesno("Abrir proyecto", "Se descarta lo que hay cargado. ¿Seguir?"):
            return
        self.estado.set("Abriendo el proyecto…")

        def trabajo():
            try:
                self.cola.put(("abierto", ruta, self.libro.abrir(
                    ruta, avance=lambda n, t: self.cola.put(("avance", n, t)),
                    avance_copia=lambda n, t: self.cola.put(("copia", n, t)))))
            except Exception as e:  # noqa: BLE001 - se muestra al usuario
                self.cola.put(("error", ruta, e))

        threading.Thread(target=trabajo, daemon=True).start()

    def _proyecto_abierto(self, ruta, resultado):
        caratula, faltan = resultado
        self.pestana_caratula.cargar(Caratula.from_dict(caratula) if caratula else caratula_ui.caratula_nueva())
        self.mostrar_campos()
        if self.libro.filas:
            self.mostrar()
            self.pestanas.select(1)
        else:
            self.pestanas.select(0)
        if faltan:
            messagebox.showwarning("Abrir proyecto", "No encontré estos PDFs y no se cargaron:\n\n• " + "\n• ".join(faltan))
        self.estado.set(f"Proyecto abierto: {Path(ruta).name}.")

    def limpiar(self):
        if self.libro.campos and not messagebox.askyesno("Limpiar", "¿Descartar todo lo cargado?"):
            return
        self.libro.vaciar()
        self._cerrar_editor()
        self.tabla.delete(*self.tabla.get_children())
        self.pestana_caratula.cargar(caratula_ui.caratula_nueva())
        self.mostrar_campos()
        self.estado.set("Cargá un PDF de ingeniería para empezar.")


def main() -> None:
    App().mainloop()
