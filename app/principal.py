"""Interfaz de escritorio (Tkinter): una ventana con las tres partes del Excel.

· Pestaña «Listado»: columnas A-G (A ITEM · B NIVEL · C DESCRIP · D CONTROLADOR · E FUNCION · F TAG (HMI) ·
  G DESC. HMI). El PDF del plano llena la tabla; todo se puede corregir a mano.
· Botón «Generar SCADA…»: completa las columnas H-O (tag, offset, descripción SCADA, estados, unidades) con el motor
  de scada/; las descripciones propuestas (amarillo) se confirman en «Propuestas SCADA…».
· Pestaña «Carátula»: datos de la obra, referencias, revisiones y logos.
«Exportar Excel…» junta lo que haya: carátula (si se completó) + listado A-G (+ SCADA H-O si se generó)."""
from __future__ import annotations

import queue
import re
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import excel_writer
import pdf_plano
import perfiles
from modelo import Campo, Funcion, Nivel, Proyecto, Senal

import catalogo
import scada

from .caratula_ui import PestanaCaratula
from .catalogo_ui import VentanaCatalogo
from .scada_ui import (DialogoOffsets, VentanaPropuestas, mostrar_texto, pendientes_de_confirmar,
                       resumen_informe)

# (clave, título, ancho, editable)
COLUMNAS = (
    ("item", "ITEM", 50, False), ("nivel", "NIVEL", 70, True), ("descrip", "DESCRIP", 170, True),
    ("controlador", "CONTROLADOR/DISPOSITIVO DE CAMPO", 215, True), ("funcion", "FUNCION", 100, True),
    ("tag_hmi", "TAG (HMI)", 260, True), ("desc_hmi", "DESC. HMI", 330, True),
)
ULTIMA_COLUMNA = "G"
# Columnas H-O (SCADA): aparecen cuando se genera el SCADA (botón «Generar SCADA…») o si el proyecto ya las trae.
COLUMNAS_SCADA = (
    ("tag_scada", "TAG (SCADA)", 95, True), ("offset", "OFFSET", 60, True), ("desc_scada", "DESC. SCADA", 170, True),
    ("s0", "S0 / MIN RAW", 80, True), ("s1", "S1 / MAX RAW", 80, True), ("s2", "S2 / MIN EU", 80, True),
    ("s3", "S3 / MAX EU", 80, True), ("unidad", "UNITS", 55, True),
)
CLAVES_SCADA = tuple(c[0] for c in COLUMNAS_SCADA)
ULTIMA_COLUMNA_SCADA = "O"


class DialogoCampo(tk.Toplevel):
    """Datos de un campo nuevo (para cargar filas a mano)."""

    def __init__(self, master, nivel: str = ""):
        super().__init__(master)
        self.title("Agregar campo")
        self.transient(master)
        self.resultado: tuple | None = None
        self.vars = {k: tk.StringVar() for k in ("nivel", "numero", "nombre", "descripcion", "controlador")}
        self.vars["nivel"].set(nivel)
        etiquetas = (("nivel", "Nivel (ej. 33KV)"), ("numero", "Campo (ej. 04)"), ("nombre", "Nombre (ej. LC)"),
                     ("descripcion", "Descripción"), ("controlador", "Controlador (vacío = por defecto)"))
        f = ttk.Frame(self, padding=10)
        f.pack()
        for i, (k, t) in enumerate(etiquetas):
            ttk.Label(f, text=t).grid(row=i, column=0, sticky="w", pady=2, padx=(0, 8))
            ttk.Entry(f, textvariable=self.vars[k], width=36).grid(row=i, column=1)
        b = ttk.Frame(f)
        b.grid(row=len(etiquetas), column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(b, text="Agregar", command=self._ok).pack(side="right")
        self.grab_set()

    def _ok(self) -> None:
        d = {k: v.get().strip() for k, v in self.vars.items()}
        if not d["nivel"] or not d["numero"]:
            messagebox.showwarning("Falta dato", "Completá al menos el nivel y el campo.", parent=self)
            return
        self.resultado = (d["nivel"], d["numero"], d["nombre"], d["descripcion"], d["controlador"])
        self.destroy()


class DialogoControlador(tk.Toplevel):
    """Elegir el controlador de una fila: se despliega el catálogo (SEL, Schneider y los propios) o se escribe otro.
    `resultado` = (controlador, alcance) con alcance "fila" o "campo"."""

    def __init__(self, master, actual: str, nivel: str, entradas: list[dict]):
        super().__init__(master)
        self.title("Controlador / dispositivo de campo")
        self.transient(master)
        self.nivel, self.entradas = nivel, entradas
        self.resultado: tuple[str, str] | None = None
        self.valor = tk.StringVar(value=actual)
        self.kv = pdf_plano.tension_texto(nivel)
        self.con_tension = tk.BooleanVar(value=False)
        self.alcance = tk.StringVar(value="fila")
        f = ttk.Frame(self, padding=10)
        f.pack()
        ttk.Label(f, text="Elegí del catálogo o escribí otro").grid(row=0, column=0, sticky="w")
        self.combo = ttk.Combobox(f, textvariable=self.valor, values=catalogo.valores_desplegable(entradas), width=46)
        self.combo.grid(row=1, column=0, sticky="w", pady=(2, 8))
        self.combo.bind("<<ComboboxSelected>>", lambda e: self._elegido())
        ttk.Checkbutton(f, text=f"Agregar la tensión del nivel ({self.kv or 'el nivel no tiene tensión'})",
                        variable=self.con_tension, state="normal" if self.kv else "disabled").grid(row=2, column=0, sticky="w")
        ttk.Radiobutton(f, text="Solo esta fila", variable=self.alcance, value="fila").grid(row=3, column=0, sticky="w", pady=(8, 0))
        ttk.Radiobutton(f, text="Todas las filas del campo", variable=self.alcance, value="campo").grid(row=4, column=0, sticky="w")
        b = ttk.Frame(f)
        b.grid(row=5, column=0, sticky="e", pady=(10, 0))
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(b, text="Aceptar", command=self._ok).pack(side="right")
        self.bind("<Return>", lambda e: self._ok())
        self.combo.focus_set()
        self.grab_set()

    def _elegido(self) -> None:
        """Al elegir un controlador (RTAC, CPU) de la lista se propone agregar la tensión del nivel."""
        self.con_tension.set(bool(self.kv) and catalogo.lleva_tension(self.valor.get(), self.entradas))

    def _ok(self) -> None:
        texto = self.valor.get().strip()
        if self.con_tension.get():
            texto = pdf_plano.controlador_con_tension(texto, self.nivel)
        self.resultado = (texto, self.alcance.get())
        self.destroy()


class DialogoPaginas(tk.Toplevel):
    """Páginas de bornes que encontró en el PDF: nivel, campo, nombre, descripción y controlador de cada una."""

    def __init__(self, master, paginas: list, cfg: dict, lugar: str):
        super().__init__(master)
        self.title("Páginas encontradas en el plano")
        self.transient(master)
        self.resultado: dict | None = None
        self.filas: list[tuple] = []
        self.entradas = catalogo.cargar()["entradas"]
        self.valores = catalogo.valores_desplegable(self.entradas)
        f = ttk.Frame(self, padding=10)
        f.pack()
        ttk.Label(f, text="Revisá los datos de cada campo. El NOMBRE (ej. LC, GTR01) forma el prefijo de DESC. HMI. "
                          "Las señales de protección (Prot. …) llevan el relé del campo. MEDICIONES: tildado si el plano "
                          "nombra un multimedidor en ese campo.",
                  foreground="#555").grid(row=0, column=0, columnspan=9, sticky="w", pady=(0, 6))
        for j, t in enumerate(("PÁG.", "NIVEL", "CAMPO", "NOMBRE", "DESCRIPCIÓN DEL CAMPO", "CONTROLADOR",
                               "RELÉ DE PROTECCIÓN", "MEDICIONES", "SEÑ.")):
            ttk.Label(f, text=t, font=("Segoe UI", 8, "bold")).grid(row=1, column=j, padx=2, sticky="w")
        for i, pg in enumerate(paginas, start=2):
            v = [tk.StringVar(value=pg.nivel), tk.StringVar(value=pg.campo), tk.StringVar(value=lugar),
                 tk.StringVar(value=pg.descripcion), tk.StringVar(value=pdf_plano.controlador_por_defecto(pg.nivel, cfg)),
                 tk.StringVar()]
            mide = tk.BooleanVar(value=pg.mediciones)  # el plano nombra un multimedidor: el campo mide
            ttk.Label(f, text=str(pg.pagina)).grid(row=i, column=0, padx=2)
            for j, (var, w) in enumerate(zip(v, (8, 6, 8, 28, 24, 24)), start=1):
                if j >= 5:  # controlador y relé: desplegable con el catálogo, o se escribe otro
                    cb = ttk.Combobox(f, textvariable=var, values=self.valores, width=w)
                    cb.bind("<<ComboboxSelected>>", lambda e, var=var, niv=v[0]: var.set(
                        pdf_plano.controlador_con_tension(var.get(), niv.get())
                        if catalogo.lleva_tension(var.get(), self.entradas) else var.get()))
                    cb.grid(row=i, column=j, padx=2, pady=1)
                else:
                    ttk.Entry(f, textvariable=var, width=w).grid(row=i, column=j, padx=2, pady=1)
            ttk.Checkbutton(f, variable=mide).grid(row=i, column=7, padx=2)
            ttk.Label(f, text=f"{len(pg.senales)} ({'relé' if pg.origen == 'rele' else 'E/S'})").grid(row=i, column=8, padx=2)
            self.filas.append((pg.pagina, *v, mide))
        b = ttk.Frame(f)
        b.grid(row=len(paginas) + 2, column=0, columnspan=9, sticky="e", pady=(8, 0))
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(b, text="Armar listado", command=self._ok).pack(side="right")
        self.grab_set()

    def _ok(self) -> None:
        destinos = {}
        for pagina, niv, cam, nom, des, ctl, rele, mide in self.filas:
            if not niv.get().strip() or not cam.get().strip():
                messagebox.showwarning("Falta dato", f"Completá nivel y campo en la página {pagina}.", parent=self)
                return
            destinos[pagina] = (niv.get().strip(), cam.get().strip(), des.get().strip(), ctl.get().strip(),
                                nom.get().strip(), rele.get().strip(), mide.get())
        self.resultado = destinos
        self.destroy()


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Listado de Señales")
        self.geometry("1180x620")
        self.minsize(900, 420)
        ids = perfiles.listar_perfiles()
        self.perfil = perfiles.cargar_perfil("EPEN" if "EPEN" in ids else ids[0])
        self.cfg = pdf_plano.cargar_config(self.perfil)
        # reglas SCADA del cliente (perfiles/<id>/scada.json); sin ellas el botón avisa y la app sigue en A-G
        self.perfil_scada = scada.cargar_perfil(self.perfil.id) if self.perfil.id in scada.listar_perfiles() else None
        self.offsets_iniciales: dict[str, int] = {}
        self._cols = COLUMNAS
        self.niveles: list[Nivel] = []
        self.item = tk.StringVar(value="1")
        self.lugar = tk.StringVar()
        self.filas: dict[str, tuple[Nivel, Campo, Senal]] = {}
        self.cola: queue.Queue = queue.Queue()
        self._editor: tk.Entry | None = None
        self._construir()
        self.refrescar()

    # ------------------------------------------------------------ ventana
    def _construir(self) -> None:
        self.pestanas = ttk.Notebook(self)
        self.pestanas.pack(fill="both", expand=True)
        raiz = ttk.Frame(self.pestanas, padding=8)
        self.pestanas.add(raiz, text="Listado")
        self.caratula_ui = PestanaCaratula(self.pestanas, self.perfil)
        self.pestanas.add(self.caratula_ui, text="Carátula")

        arriba = ttk.Frame(raiz)
        arriba.pack(fill="x")
        ttk.Button(arriba, text="Cargar PDF de plano…", command=self.cargar_pdf).pack(side="left")
        ttk.Label(arriba, text="ITEM inicial").pack(side="left", padx=(14, 3))
        ttk.Entry(arriba, textvariable=self.item, width=6).pack(side="left")
        ttk.Label(arriba, text="Nombre de campo por defecto (ej. LC)").pack(side="left", padx=(14, 3))
        ttk.Entry(arriba, textvariable=self.lugar, width=8).pack(side="left")
        for texto, cmd in (("Exportar Excel…", self.exportar), ("Guardar…", self.guardar), ("Abrir…", self.abrir)):
            ttk.Button(arriba, text=texto, command=cmd).pack(side="right", padx=2)
        self.item.trace_add("write", lambda *_: self.refrescar())

        barra = ttk.Frame(raiz)
        barra.pack(fill="x", pady=(8, 4))
        for texto, cmd in (("Agregar campo…", self.agregar_campo), ("Agregar fila", self.agregar_fila),
                           ("Agregar mediciones", self.agregar_mediciones), ("Catálogo de controladores…", self.abrir_catalogo),
                           ("Generar SCADA…", self.generar_scada), ("Propuestas SCADA…", self.revisar_propuestas),
                           ("Borrar", self.borrar), ("Subir", lambda: self.mover(-1)),
                           ("Bajar", lambda: self.mover(1))):
            ttk.Button(barra, text=texto, command=cmd).pack(side="left", padx=2)
        self.estado = ttk.Label(barra, text="", foreground="#666")
        self.estado.pack(side="left", padx=12)

        marco = ttk.Frame(raiz)
        marco.pack(fill="both", expand=True)
        self.arbol = ttk.Treeview(marco, columns=[c[0] for c in COLUMNAS], show="headings", selectmode="extended")
        self._configurar_columnas(COLUMNAS)
        self.arbol.tag_configure("grupo", background="#eef3fb")
        self.arbol.tag_configure("reserva", foreground="#777")
        self.arbol.tag_configure("propuesta", background="#fff3bf")  # DESC. SCADA propuesta, a confirmar
        sy = ttk.Scrollbar(marco, orient="vertical", command=self.arbol.yview)
        sx = ttk.Scrollbar(marco, orient="horizontal", command=self.arbol.xview)
        self.arbol.configure(yscrollcommand=sy.set, xscrollcommand=sx.set)
        self.arbol.grid(row=0, column=0, sticky="nsew")
        sy.grid(row=0, column=1, sticky="ns")
        sx.grid(row=1, column=0, sticky="ew")
        marco.rowconfigure(0, weight=1)
        marco.columnconfigure(0, weight=1)
        self.arbol.bind("<Double-1>", self._editar)

    # ------------------------------------------------------------ tabla
    def _item_inicial(self) -> int:
        t = self.item.get().strip()
        return int(t) if t.isdigit() else 1

    def _configurar_columnas(self, cols) -> None:
        self._cols = cols
        self.arbol.configure(columns=[c[0] for c in cols])
        for c, t, w, _ in cols:
            self.arbol.heading(c, text=t)
            self.arbol.column(c, width=w, anchor="w", stretch=c in ("tag_hmi", "desc_hmi"))

    def _hay_scada(self) -> bool:
        """¿Alguna fila ya tiene datos de las columnas H-O? (entonces se muestran y se exportan)."""
        return any(s.tag_scada or s.desc_scada or s.offset is not None
                   for n in self.niveles for c in n.campos for s in c.senales)

    @staticmethod
    def _valores_scada(s: Senal) -> tuple:
        return (s.tag_scada, "" if s.offset is None else s.offset, s.desc_scada, s.s0, s.s1, s.s2, s.s3, s.unidad)

    def refrescar(self) -> None:
        con_scada = self._hay_scada()
        if con_scada != (self._cols is not COLUMNAS):  # aparecen/desaparecen las columnas H-O
            self._configurar_columnas(COLUMNAS + COLUMNAS_SCADA if con_scada else COLUMNAS)
        self.arbol.delete(*self.arbol.get_children())
        self.filas.clear()
        n = self._item_inicial()
        for nivel in self.niveles:
            for k, campo in enumerate(nivel.campos):
                for i, s in enumerate(campo.senales):
                    # como las celdas combinadas del Excel: NIVEL y DESCRIP solo en la primera fila del grupo
                    primera_nivel, primera_campo = k == 0 and i == 0, i == 0
                    valores = (n, nivel.nombre if primera_nivel else "", campo.descripcion if primera_campo else "",
                               s.controlador, s.funcion.value, s.tag_hmi, s.desc_hmi)
                    if con_scada:
                        valores += self._valores_scada(s)
                    tags = (("grupo",) if primera_campo else ()) + (("reserva",) if s.funcion == Funcion.RESERVA else ()) \
                        + (("propuesta",) if s.desc_scada_origen == "propuesta" else ())
                    iid = self.arbol.insert("", "end", values=valores, tags=tags)
                    self.filas[iid] = (nivel, campo, s)
                    n += 1
        total = len(self.filas)
        self.estado.config(text=f"{total} filas. Doble clic en una celda para editarla." if total
                           else "Cargá un PDF de plano o agregá un campo para empezar.")

    def _seleccion(self) -> list[tuple[Nivel, Campo, Senal]]:
        return [self.filas[i] for i in self.arbol.selection() if i in self.filas]

    @staticmethod
    def _bloques(campo: Campo) -> list[list[Senal]]:
        """Una señal con su segunda fila (doble bit) forma un bloque: se mueve y se borra junta."""
        bloques: list[list[Senal]] = []
        for s in campo.senales:
            if s.segunda_fila and bloques:
                bloques[-1].append(s)
            else:
                bloques.append([s])
        return bloques

    def _seleccionar(self, senal: Senal) -> None:
        for iid, (_, _, s) in self.filas.items():
            if s is senal:
                self.arbol.selection_set(iid)
                self.arbol.see(iid)

    def agregar_campo(self) -> None:
        dlg = DialogoCampo(self, self.niveles[0].nombre if self.niveles else "")
        self.wait_window(dlg)
        if not dlg.resultado:
            return
        nombre_nivel, numero, nombre, descripcion, ctl = dlg.resultado
        nivel = next((n for n in self.niveles if n.nombre == nombre_nivel), None)
        if nivel is None:
            nivel = Nivel(nombre=nombre_nivel, codigo=pdf_plano.codigo_nivel(nombre_nivel, self.cfg))
            pos = next((i for i, n in enumerate(self.niveles) if n.nombre == "RESERVAS"), len(self.niveles))
            self.niveles.insert(pos, nivel)  # el bloque RESERVAS siempre va al final de la hoja
        campo = Campo(numero=numero, descripcion=descripcion, prefijo=f"{nivel.codigo}{numero}{nombre}",
                      controlador=ctl or pdf_plano.controlador_por_defecto(nombre_nivel, self.cfg))
        nivel.campos.append(campo)
        self.agregar_fila(campo)

    def agregar_fila(self, campo: Campo | None = None) -> None:
        sel = self._seleccion()
        if campo is None:
            if sel:
                campo = sel[-1][1]
            elif self.niveles and self.niveles[0].campos:
                campo = self.niveles[0].campos[-1]
            else:
                messagebox.showinfo("Falta un campo", "Primero agregá un campo o cargá un plano.")
                return
        nueva = Senal(funcion=Funcion.ALARMAS, controlador=campo.controlador)
        if sel and sel[-1][1] is campo:  # después de la fila seleccionada (y de su 2ª fila, si la tiene)
            idx = campo.senales.index(sel[-1][2]) + 1
            while idx < len(campo.senales) and campo.senales[idx].segunda_fila:
                idx += 1
            campo.senales.insert(idx, nueva)
        else:
            campo.senales.append(nueva)
        self.refrescar()
        self._seleccionar(nueva)

    def agregar_mediciones(self) -> None:
        """Agrega el juego de mediciones (ETAP: 13) al final del campo elegido; no repite si ya las tiene."""
        sel = self._seleccion()
        grupos = {id(c): (n, c) for n, c, _ in sel} or (
            {id(self.niveles[0].campos[0]): (self.niveles[0], self.niveles[0].campos[0])}
            if self.niveles and self.niveles[0].campos else {})
        if not grupos:
            messagebox.showinfo("Falta un campo", "Primero cargá un plano o agregá un campo.")
            return
        agregados = 0
        for nivel, campo in grupos.values():
            if any(s.funcion == Funcion.MEDICION for s in campo.senales):
                continue
            filas = pdf_plano.filas_mediciones(nivel.nombre, campo.numero,
                                               campo.prefijo or f"{nivel.codigo}{campo.numero}", self.cfg)
            campo.senales += filas
            agregados += len(filas)
        self.refrescar()
        if not agregados:
            messagebox.showinfo("Mediciones", "Ese campo ya tiene sus mediciones.")

    def abrir_catalogo(self) -> None:
        """Listado de controladores del mercado (SEL-2240 Axion/RTAC y Schneider Saitel DP)."""
        VentanaCatalogo(self, self._aplicar_controlador)

    def _aplicar_controlador(self, modelo: str, con_tension: bool, alcance: str) -> int:
        """Pone `modelo` como controlador de las filas elegidas (o de todo su campo). Devuelve cuántas cambió."""
        sel = self._seleccion()
        if not sel:
            return 0
        if alcance == "campo":
            vistos, objetivos = set(), []
            for nivel, campo, _ in sel:
                if id(campo) not in vistos:
                    vistos.add(id(campo))
                    objetivos += [(nivel, campo, x) for x in campo.senales]
        else:
            objetivos = sel
        for nivel, _campo, x in objetivos:
            x.controlador = pdf_plano.controlador_con_tension(modelo, nivel.nombre) if con_tension else modelo
        elegidas = [x for _, _, x in sel]
        self.refrescar()
        for iid, (_, _, x) in self.filas.items():  # mantiene la selección para probar otro modelo
            if any(x is e for e in elegidas):
                self.arbol.selection_add(iid)
        return len(objetivos)

    def borrar(self) -> None:
        sel = self._seleccion()
        if not sel or not messagebox.askyesno("Borrar", f"¿Borrar {len(sel)} fila(s)?"):
            return
        for _, campo, s in sel:
            if s not in campo.senales:
                continue
            i = campo.senales.index(s)
            fin = i + 1
            if not s.segunda_fila:  # una señal de doble bit se va con su segunda fila
                while fin < len(campo.senales) and campo.senales[fin].segunda_fila:
                    fin += 1
            del campo.senales[i:fin]
        for nivel in self.niveles:
            nivel.campos = [c for c in nivel.campos if c.senales]
        self.niveles[:] = [n for n in self.niveles if n.campos]
        self.refrescar()

    def mover(self, delta: int) -> None:
        sel = self._seleccion()
        if len(sel) != 1:
            messagebox.showinfo("Mover", "Seleccioná una sola fila.")
            return
        _, campo, s = sel[0]
        bloques = self._bloques(campo)
        k = next(i for i, b in enumerate(bloques) if s in b)
        j = k + delta
        if not 0 <= j < len(bloques):
            return
        bloques[k], bloques[j] = bloques[j], bloques[k]
        campo.senales[:] = [x for b in bloques for x in b]
        self.refrescar()
        self._seleccionar(s)

    # ------------------------------------------------------------ edición de celdas
    def _editar(self, ev) -> None:
        self._cerrar_editor()
        iid, col = self.arbol.identify_row(ev.y), self.arbol.identify_column(ev.x)
        if not iid or iid not in self.filas:
            return
        clave, _, _, editable = self._cols[int(col[1:]) - 1]
        if not editable:
            return
        nivel, campo, s = self.filas[iid]
        if clave == "controlador":  # se elige del catálogo (o se escribe otro)
            self._elegir_controlador(nivel, campo, s)
            return
        base = {"nivel": nivel.nombre, "descrip": campo.descripcion, "controlador": s.controlador,
                "funcion": s.funcion.value, "tag_hmi": s.tag_hmi, "desc_hmi": s.desc_hmi}
        actual = base[clave] if clave in base else ("" if getattr(s, clave) is None else str(getattr(s, clave)))
        x, y, w, h = self.arbol.bbox(iid, col)
        ent = tk.Entry(self.arbol)
        ent.insert(0, actual)
        ent.select_range(0, "end")
        ent.place(x=x, y=y, width=w, height=h)
        ent.focus_set()
        ent.bind("<Return>", lambda e: self._confirmar(iid, clave, ent))
        ent.bind("<Escape>", lambda e: self._cerrar_editor())
        ent.bind("<FocusOut>", lambda e: self._confirmar(iid, clave, ent))
        self._editor = ent

    def _elegir_controlador(self, nivel: Nivel, campo: Campo, s: Senal) -> None:
        dlg = DialogoControlador(self, s.controlador, nivel.nombre, catalogo.cargar()["entradas"])
        self.wait_window(dlg)
        if not dlg.resultado:
            return
        texto, alcance = dlg.resultado
        for x in (campo.senales if alcance == "campo" else [s]):
            x.controlador = texto
        self.refrescar()
        self._seleccionar(s)

    def _cerrar_editor(self) -> None:
        if self._editor is not None:
            ed, self._editor = self._editor, None
            ed.destroy()

    def _confirmar(self, iid: str, clave: str, ent: tk.Entry) -> None:
        if ent is not self._editor:
            return
        texto = ent.get().strip()
        self._cerrar_editor()
        try:
            self._asignar(*self.filas[iid], clave, texto)
        except ValueError as e:
            messagebox.showwarning("Valor no válido", str(e))
            return
        self.refrescar()

    def _asignar(self, nivel: Nivel, campo: Campo, s: Senal, clave: str, texto: str) -> None:
        if clave == "nivel":  # el nivel se comparte con todo su grupo (celda combinada)
            nivel.nombre = texto
            nivel.codigo = pdf_plano.codigo_nivel(texto, self.cfg)
            for c in nivel.campos:  # la tensión al final del controlador sigue al nivel (SEL-2241-33kV -> -132kV)
                c.controlador = pdf_plano.con_tension_del_nivel(c.controlador, texto)
                for x in c.senales:
                    x.controlador = pdf_plano.con_tension_del_nivel(x.controlador, texto)
        elif clave == "descrip":
            campo.descripcion = texto
        elif clave == "funcion":
            validas = {f.value: f for f in Funcion}
            f = validas.get(texto.upper())
            if f is None:
                raise ValueError("Función válida: " + ", ".join(validas))
            s.funcion = f
            s.es_reserva = f == Funcion.RESERVA
        elif clave in CLAVES_SCADA:  # lo editado a mano en H-O queda fijo: «Generar SCADA…» no lo pisa
            if clave == "offset":
                if texto and not texto.isdigit():
                    raise ValueError("El OFFSET debe ser un número entero (0 o mayor).")
                s.offset = int(texto) if texto else None
            else:
                if clave == "desc_scada" and self.perfil_scada and len(texto) > self.perfil_scada.maximo:
                    raise ValueError(f"DESC. SCADA: máximo {self.perfil_scada.maximo} caracteres.")
                setattr(s, clave, texto)
                if clave == "desc_scada":
                    s.desc_scada_origen = "usuario" if texto else ""
            if clave not in s.fijos:
                s.fijos.append(clave)
        else:
            setattr(s, clave, texto)

    # ------------------------------------------------------------ PDF
    def cargar_pdf(self) -> None:
        ruta = filedialog.askopenfilename(title="Plano de ingeniería", filetypes=[("PDF", "*.pdf")])
        if not ruta:
            return
        self.estado.config(text="Leyendo el PDF…")

        def trabajo():
            try:
                info: dict = {}
                res = pdf_plano.leer_plano(
                    ruta, self.perfil, avance=lambda n, t: self.cola.put(("avance", n, t)), info=info)
                self.cola.put(("ok", res, ruta, info))
            except (pdf_plano.PdfSinTexto, pdf_plano.PdfNoEsquema, pdf_plano.PdfNoDisponible) as e:
                self.cola.put(("error", str(e)))  # avisos propios: sin el nombre de la clase
            except Exception as e:  # PDF dañado, vocabulario del perfil roto…
                self.cola.put(("error", f"{type(e).__name__}: {e}"))

        threading.Thread(target=trabajo, daemon=True).start()
        self.after(150, self._sondear)

    def _sondear(self) -> None:
        try:
            while True:
                msg = self.cola.get_nowait()
                if msg[0] == "avance":
                    self.estado.config(text=f"Leyendo el PDF… página {msg[1]} de {msg[2]}")
                elif msg[0] == "error":
                    self.refrescar()
                    messagebox.showerror("No se pudo leer el PDF", msg[1])
                    return
                else:
                    self._paginas_leidas(msg[1], msg[2], msg[3])
                    return
        except queue.Empty:
            self.after(150, self._sondear)

    def _paginas_leidas(self, paginas: list, ruta: str = "", info: dict | None = None) -> None:
        self.refrescar()
        if not paginas:
            i = info or {}
            detalle = (f"\n\nArchivo: {Path(ruta).name}\nDetalle: {i.get('paginas', '?')} páginas, "
                       f"{i.get('caracteres', '?')} caracteres de rótulos, {i.get('con_rotulos', '?')} páginas con rótulos, "
                       f"{i.get('con_franja', '?')} con módulos de E/S, {i.get('con_tira', '?')} con tira de relé.")
            messagebox.showinfo(
                "Sin señales", "No encontré páginas con módulos de entradas/salidas ni tiras de señales de relé en ese "
                "PDF.\n\nLa app lee los ESQUEMAS FUNCIONALES (EF) de los tableros de control (TC) y de protección (TP). "
                "No lee los esquemas constructivos, de medición (TMA), de comunicaciones ni unifilares." + detalle)
            return
        dlg = DialogoPaginas(self, paginas, self.cfg, self.lugar.get().strip())
        self.wait_window(dlg)
        if not dlg.resultado:
            return
        if self.niveles and not messagebox.askyesno(
                "Reemplazar", "La tabla ya tiene filas. ¿Reemplazarlas por las del PDF?"):
            return
        self.niveles[:] = pdf_plano.a_niveles(paginas, self.perfil, dlg.resultado, self.lugar.get().strip())
        self.refrescar()

    # ------------------------------------------------------------ archivos
    def _proyecto(self) -> Proyecto:
        return Proyecto(perfil_id=self.perfil.id, caratula=self.caratula_ui.leer(), niveles=self.niveles,
                        item_inicial=self._item_inicial(), offsets_iniciales=dict(self.offsets_iniciales))

    def guardar(self) -> None:
        ruta = filedialog.asksaveasfilename(title="Guardar proyecto", defaultextension=".json",
                                            filetypes=[("Proyecto", "*.json")], initialfile="listado.json")
        if ruta:
            self._proyecto().guardar(ruta)
            self.estado.config(text=f"Guardado en {ruta}")

    def abrir(self) -> None:
        ruta = filedialog.askopenfilename(title="Abrir proyecto", filetypes=[("Proyecto", "*.json")])
        if not ruta:
            return
        try:
            p = Proyecto.cargar(ruta)
        except Exception as e:  # archivo ajeno o JSON roto
            messagebox.showerror("No se pudo abrir", f"{type(e).__name__}: {e}")
            return
        self.niveles[:] = p.niveles
        self.item.set(str(p.item_inicial))
        self.offsets_iniciales = dict(p.offsets_iniciales)
        self.caratula_ui.cargar(p.caratula)
        self.refrescar()

    def exportar(self) -> None:
        if not self.filas:
            messagebox.showinfo("Sin filas", "No hay filas para exportar.")
            return
        ruta = filedialog.asksaveasfilename(title="Exportar Excel", defaultextension=".xlsx",
                                            filetypes=[("Excel", "*.xlsx")], initialfile="listado.xlsx")
        if not ruta:
            return
        # Las tres partes en un solo Excel: la carátula (si se completó), el listado A-G y, si ya se generó, el SCADA H-O.
        con_caratula = self.caratula_ui.tiene_datos()
        problemas = self.caratula_ui.problemas() if con_caratula else []
        if problemas:
            self.pestanas.select(self.caratula_ui)
            messagebox.showerror("Revisá la carátula", "\n".join(problemas))
            return
        con_scada = self._hay_scada()
        try:
            excel_writer.escribir_xlsx(self._proyecto(), self.perfil, Path(ruta), incluir_caratula=con_caratula,
                                       hasta_columna=ULTIMA_COLUMNA_SCADA if con_scada else ULTIMA_COLUMNA)
        except (excel_writer.PlantillaNoEncontrada, ValueError, OSError) as e:
            messagebox.showerror("No se pudo exportar", str(e))
            return
        partes = (["carátula"] if con_caratula else []) + ["listado A-G"] + (["SCADA H-O"] if con_scada else [])
        messagebox.showinfo("Exportado", f"Excel generado ({', '.join(partes)}) en:\n{ruta}")

    # ------------------------------------------------------------ SCADA (columnas H-O)
    def generar_scada(self) -> None:
        """Completa tag, offset, descripción SCADA, estados y unidades de todas las filas (motor de scada/)."""
        if self.perfil_scada is None:
            messagebox.showinfo("SCADA", f"El perfil {self.perfil.id} no tiene reglas SCADA (perfiles/{self.perfil.id}/scada.json).")
            return
        if not self.filas:
            messagebox.showinfo("Sin filas", "Cargá un plano o agregá filas antes de generar el SCADA.")
            return
        dlg = DialogoOffsets(self, self.offsets_iniciales)
        self.wait_window(dlg)
        if not dlg.resultado:
            return
        self.offsets_iniciales = dlg.resultado
        glosario = scada.Glosario.cargar(self.perfil_scada.ruta_glosario)  # incluye lo que el usuario ya confirmó
        try:
            informe = scada.generar_scada(self._proyecto(), self.perfil_scada, glosario)
        except scada.ErrorGeneracion as e:
            messagebox.showerror("No se pudo generar el SCADA", str(e))
            return
        self.refrescar()
        total = len(self.filas)
        self.estado.config(text=f"SCADA generado en {total} filas.")
        mostrar_texto(self, "SCADA generado", resumen_informe(informe, total))

    def revisar_propuestas(self) -> None:
        """Ventana para corregir y confirmar las DESC. SCADA propuestas (amarillas); lo confirmado se recuerda."""
        if self.perfil_scada is None:
            messagebox.showinfo("SCADA", "Este perfil no tiene reglas SCADA.")
            return
        pend = pendientes_de_confirmar(self.niveles)
        if not pend:
            messagebox.showinfo("Propuestas SCADA", "No hay descripciones SCADA para confirmar. "
                                "Aparecen (en amarillo) después de «Generar SCADA…».")
            return
        todas = [s for n in self.niveles for c in n.campos for s in c.senales]
        glosario = scada.Glosario.cargar(self.perfil_scada.ruta_glosario)
        VentanaPropuestas(self, pend, todas, glosario, self.perfil_scada.ruta_glosario, self.perfil_scada.maximo,
                          self.refrescar)


def main() -> None:
    App().mainloop()
