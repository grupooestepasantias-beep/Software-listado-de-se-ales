"""Interfaz de escritorio (Tkinter): pantalla de inicio y formulario de proyecto/carátula."""
from __future__ import annotations

import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

import descripciones
import excel_writer
import generador
import pdf_plano
import perfiles
from modelo import Proyecto, TipoPunto

from . import validacion

ETIQUETAS = {
    "cliente": "Cliente", "obra": "Obra", "lugar": "Lugar", "departamento": "Departamento",
    "expediente": "Nro. expediente", "titulo": "Título", "numero_documento": "Documento N°",
    "proyecto": "Proyectó", "dibujo": "Dibujó", "aprobo": "Aprobó",
    "archivo_magnetico": "Archivo magnético", "escala": "Escala", "revision": "Revisión", "fecha": "Fecha",
}
TITULOS_REV = {"rev": "REV", "fecha": "FECHA", "descripcion": "DESCRIPCIÓN", "proyecto": "PROY.",
               "revisor": "REV.", "aprobador": "APR."}
GRUPOS = (  # (columna, título del grupo, campos)
    (0, "Obra", ("cliente", "obra", "lugar", "departamento", "expediente", "titulo")),
    (1, "Documento", ("numero_documento", "archivo_magnetico", "escala", "revision", "fecha")),
    (1, "Firmas", ("proyecto", "dibujo", "aprobo")),
)


class TablaEditable(ttk.Frame):
    """Tabla de Entry que crece solo al agregar filas (empieza vacía, sin espacio reservado).

    Encabezados y filas comparten la misma grilla, así que quedan alineados y pegados."""

    def __init__(self, master, columnas: list[tuple[str, str, int]], max_filas: int):
        super().__init__(master)
        self.columnas, self.max_filas = columnas, max_filas
        self.filas: list[list[tk.StringVar]] = []
        self.cuerpo = ttk.Frame(self)
        self.cuerpo.pack(anchor="w")
        for j, (_, titulo, _) in enumerate(columnas):
            ttk.Label(self.cuerpo, text=titulo, font=("Segoe UI", 8, "bold")).grid(row=0, column=j, sticky="w", padx=1)
        barra = ttk.Frame(self)
        barra.pack(anchor="w", pady=(3, 0))
        ttk.Button(barra, text="+ Agregar", width=10, command=self.agregar).pack(side="left")
        ttk.Button(barra, text="− Quitar", width=9, command=self.quitar).pack(side="left", padx=3)
        self.contador = ttk.Label(barra, foreground="#666")
        self.contador.pack(side="left", padx=6)
        self._contar()

    def agregar(self, valores=None) -> None:
        if len(self.filas) >= self.max_filas:
            messagebox.showinfo("Límite", f"La carátula admite hasta {self.max_filas} filas.")
            return
        vars_ = []
        for j, (_, _, ancho) in enumerate(self.columnas):
            v = tk.StringVar(value="" if valores is None else str(valores[j]))
            ttk.Entry(self.cuerpo, textvariable=v, width=ancho).grid(row=len(self.filas) + 1, column=j, padx=1, pady=0)
            vars_.append(v)
        self.filas.append(vars_)
        self._contar()

    def quitar(self) -> None:
        if not self.filas:
            return
        self.filas.pop()
        for h in self.cuerpo.grid_slaves(row=len(self.filas) + 1):
            h.destroy()
        self._contar()

    def _contar(self) -> None:
        self.contador.config(text=f"{len(self.filas)} de {self.max_filas}")

    def cargar(self, filas: list) -> None:
        while self.filas:
            self.quitar()
        for f in filas:
            self.agregar(f)

    def valores(self) -> list[list[str]]:
        return [[v.get() for v in fila] for fila in self.filas]


class DialogoAbreviaturas(tk.Toplevel):
    """Pregunta las abreviaturas que las reglas no definen. Cada respuesta se guarda y no se repite."""

    ORDEN = {"equipo": 0, "frase": 1, "estado": 2, "texto": 3, "largo": 4}

    def __init__(self, master, pendientes: list, maximo: int):
        super().__init__(master)
        self.title("Abreviaturas que faltan")
        self.geometry("720x460")
        self.transient(master)
        self.pendientes = sorted(pendientes, key=lambda p: self.ORDEN[p.tipo])
        self.vars: list[tk.StringVar] = []
        ttk.Label(self, text=f"Los lineamientos no definen estas abreviaturas. DESC. SCADA admite hasta {maximo} "
                             f"caracteres contando el prefijo del campo. Lo que dejes vacío queda para completar "
                             f"a mano.", wraplength=680, padding=8).pack(anchor="w")
        marco = ttk.Frame(self)
        marco.pack(fill="both", expand=True, padx=8)
        lienzo = tk.Canvas(marco, highlightthickness=0)
        barra = ttk.Scrollbar(marco, orient="vertical", command=lienzo.yview)
        cuerpo = ttk.Frame(lienzo)
        cuerpo.bind("<Configure>", lambda e: lienzo.configure(scrollregion=lienzo.bbox("all")))
        lienzo.create_window((0, 0), window=cuerpo, anchor="nw")
        lienzo.configure(yscrollcommand=barra.set)
        lienzo.pack(side="left", fill="both", expand=True)
        barra.pack(side="right", fill="y")
        for i, p in enumerate(self.pendientes):
            v = tk.StringVar(value=p.borrador)
            ttk.Label(cuerpo, text=p.pregunta, wraplength=470).grid(row=i, column=0, sticky="w", pady=3, padx=(0, 8))
            ttk.Entry(cuerpo, textvariable=v, width=22).grid(row=i, column=1, pady=3)
            cont = ttk.Label(cuerpo, width=6, foreground="#666")
            cont.grid(row=i, column=2, padx=4)
            v.trace_add("write", lambda *_, v=v, c=cont, m=p.maximo: c.config(
                text=f"{len(v.get())}/{m}", foreground="#b00020" if len(v.get()) > m else "#666"))
            v.set(p.borrador)
            self.vars.append(v)
        pie = ttk.Frame(self)
        pie.pack(fill="x", padx=8, pady=8)
        ttk.Button(pie, text="Guardar y continuar", command=self._aceptar).pack(side="right")
        ttk.Button(pie, text="Omitir", command=self.destroy).pack(side="right", padx=6)
        self.grab_set()

    def _aceptar(self) -> None:
        for p, v in zip(self.pendientes, self.vars):
            p.respuesta = v.get().strip()
        self.destroy()


class Inicio(ttk.Frame):
    def __init__(self, app: "App"):
        super().__init__(app, padding=20)
        self.app = app
        ttk.Label(self, text="Listado de Señales", font=("Segoe UI", 16, "bold")).pack(anchor="w")
        f = ttk.LabelFrame(self, text="Nuevo proyecto", padding=8)
        f.pack(anchor="w", fill="x", pady=(10, 6))
        ttk.Label(f, text="Cliente").grid(row=0, column=0, sticky="w", pady=2)
        self.cliente = tk.StringVar()
        ttk.Entry(f, textvariable=self.cliente, width=48).grid(row=0, column=1, sticky="w", padx=6)
        ttk.Label(f, text="Reglas (perfil)").grid(row=1, column=0, sticky="w", pady=2)
        self.perfil = tk.StringVar()
        ids = perfiles.listar_perfiles()
        self.combo = ttk.Combobox(f, textvariable=self.perfil, values=ids, state="readonly", width=20)
        self.combo.grid(row=1, column=1, sticky="w", padx=6)
        if ids:
            self.combo.current(0)
        ttk.Button(f, text="Empezar desde cero", command=self.nuevo).grid(row=2, column=1, sticky="w", padx=6, pady=(8, 0))
        g = ttk.LabelFrame(self, text="Proyecto existente", padding=8)
        g.pack(anchor="w", fill="x")
        ttk.Button(g, text="Abrir proyecto guardado (.json)", command=self.abrir).pack(side="left")
        ttk.Button(g, text="Cargar Excel existente (próximamente)", state="disabled").pack(side="left", padx=6)

    def _perfil(self):
        if not self.perfil.get():
            messagebox.showerror("Perfil", "No hay perfiles de cliente disponibles en perfiles/.")
            return None
        try:
            return perfiles.cargar_perfil(self.perfil.get())
        except perfiles.PerfilInvalido as e:
            messagebox.showerror("Perfil inválido", str(e))
            return None

    def nuevo(self) -> None:
        p = self._perfil()
        if p:
            self.app.mostrar_formulario(p, None, self.cliente.get().strip())

    def abrir(self) -> None:
        ruta = filedialog.askopenfilename(title="Abrir proyecto", filetypes=[("Proyecto", "*.json")])
        if not ruta:
            return
        try:
            proyecto = Proyecto.cargar(ruta)
            perfil = perfiles.cargar_perfil(proyecto.perfil_id)
        except Exception as e:  # archivo ajeno, JSON roto o perfil inexistente
            messagebox.showerror("No se pudo abrir", f"{type(e).__name__}: {e}")
            return
        self.app.mostrar_formulario(perfil, proyecto)


class Formulario(ttk.Frame):
    def __init__(self, app: "App", perfil: perfiles.Perfil, proyecto: Proyecto | None,
                 cliente: str = ""):
        super().__init__(app, padding=8)
        self.app, self.perfil, self.proyecto = app, perfil, proyecto
        try:
            self.campos = excel_writer.cargar_plantilla(perfil)["caratula_campos"]
        except excel_writer.PlantillaNoEncontrada as e:
            messagebox.showerror("Plantilla", str(e))
            self.campos = {"referencias": {"filas": [3, 16]}, "revisiones": {"filas": [25, 28]},
                           "documento": {"celdas": []}}
        r0, r1 = self.campos["referencias"]["filas"]
        v0, v1 = self.campos["revisiones"]["filas"]
        self.max_ref, self.max_rev = r1 - r0 + 1, v1 - v0 + 1
        self.largo_doc = len(self.campos["documento"]["celdas"]) or None

        ttk.Label(self, text=f"Proyecto — perfil {perfil.id}", font=("Segoe UI", 12, "bold")).pack(anchor="w")
        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, pady=4)
        self.vars = {k: tk.StringVar() for k in validacion.CAMPOS_TEXTO}
        self.item = tk.StringVar()
        self.offsets = {t.value: tk.StringVar() for t in TipoPunto}

        self.niveles = list(proyecto.niveles) if proyecto else []
        self.lugar = tk.StringVar()
        self.con_caratula = tk.BooleanVar(value=False)  # por ahora se trabaja solo el listado
        self._pestana_senales()
        self._pestana_numeracion()
        self._pestana_caratula()
        self._pestana_tablas()

        pie = ttk.Frame(self)
        pie.pack(fill="x")
        ttk.Button(pie, text="← Inicio", command=app.mostrar_inicio).pack(side="left")
        ttk.Button(pie, text="Exportar Excel…", command=self.exportar).pack(side="right", padx=3)
        ttk.Checkbutton(pie, text="Incluir carátula", variable=self.con_caratula).pack(side="right", padx=8)
        ttk.Button(pie, text="Guardar proyecto…", command=self.guardar).pack(side="right", padx=3)

        if proyecto:
            self._cargar(validacion.desde_proyecto(proyecto))
        else:
            d = validacion.datos_vacios()
            d["cliente"] = cliente
            self._cargar(d)

    # ------------------------------------------------------------ pestañas
    def _pestana(self, titulo: str) -> ttk.Frame:
        f = ttk.Frame(self.nb, padding=6)
        self.nb.add(f, text=titulo)
        return f

    def _grupo(self, master, titulo: str, claves, fila: int, columna: int, ancho: int = 34) -> None:
        g = ttk.LabelFrame(master, text=titulo, padding=6)
        g.grid(row=fila, column=columna, sticky="nsew", padx=3, pady=3)
        for i, k in enumerate(claves):
            ttk.Label(g, text=ETIQUETAS[k]).grid(row=i, column=0, sticky="w", pady=1, padx=(0, 8))
            ttk.Entry(g, textvariable=self.vars[k], width=ancho).grid(row=i, column=1, sticky="w")

    def _pestana_caratula(self) -> None:
        f = self._pestana("Carátula")
        self._grupo(f, "Obra", GRUPOS[0][2], 0, 0, ancho=44)
        self._grupo(f, "Documento", GRUPOS[1][2], 0, 1)
        self._grupo(f, "Firmas", GRUPOS[2][2], 1, 1)
        f.columnconfigure(0, weight=1)
        ttk.Label(f, text=f"Obligatorios: cliente, obra, título y documento. El documento admite hasta "
                          f"{self.largo_doc or '—'} caracteres sin contar guiones (puede tener menos).",
                  foreground="#555", wraplength=760).grid(row=2, column=0, columnspan=2, sticky="w", padx=3, pady=4)

    def _pestana_tablas(self) -> None:
        f = self._pestana("Referencias y revisiones")
        g1 = ttk.LabelFrame(f, text="Referencias (planos)", padding=6)
        g1.pack(fill="x", padx=3, pady=3)
        self.refs = TablaEditable(g1, [("c", "CÓDIGO", 28), ("t", "TÍTULO DEL PLANO", 70)], self.max_ref)
        self.refs.pack(anchor="w")
        g2 = ttk.LabelFrame(f, text="Revisiones (de la más antigua a la más nueva)", padding=6)
        g2.pack(fill="x", padx=3, pady=3)
        self.revs = TablaEditable(g2, [(k, TITULOS_REV[k], w) for k, w in
                                       zip(validacion.COLS_REVISION, (5, 11, 34, 7, 7, 7))], self.max_rev)
        self.revs.pack(anchor="w")

    def _pestana_numeracion(self) -> None:
        f = self._pestana("Numeración")
        g = ttk.LabelFrame(f, text="Desde qué número arrancar (obra intervenida: continuar la anterior)", padding=6)
        g.pack(fill="x", padx=3, pady=3)
        ttk.Label(g, text="ITEM").grid(row=0, column=0, sticky="w")
        ttk.Entry(g, textvariable=self.item, width=7).grid(row=0, column=1, padx=(3, 14))
        for j, (tipo, v) in enumerate(self.offsets.items()):
            ttk.Label(g, text=f"OFFSET {tipo}").grid(row=0, column=2 + 2 * j, sticky="w")
            ttk.Entry(g, textvariable=v, width=7).grid(row=0, column=3 + 2 * j, padx=(3, 14))

    # ---------------------------------------------------------- señales desde PDF
    def _pestana_senales(self) -> None:
        f = self._pestana("Señales (PDF)")
        self.pdf_paginas: list = []
        self.pdf_destinos: list[tuple] = []
        self.cola: queue.Queue = queue.Queue()
        arriba = ttk.Frame(f)
        arriba.pack(fill="x")
        ttk.Button(arriba, text="Cargar PDF de plano…", command=self.cargar_pdf).pack(side="left")
        self.btn_aplicar = ttk.Button(arriba, text="Aplicar al proyecto", command=self.aplicar_pdf, state="disabled")
        self.btn_aplicar.pack(side="left", padx=4)
        ttk.Button(arriba, text="Generar tags, offsets y descripciones", command=self.generar).pack(side="left", padx=4)
        ttk.Label(arriba, text="Nombre de campo por defecto (ej. LC)").pack(side="left", padx=(10, 2))
        ttk.Entry(arriba, textvariable=self.lugar, width=6).pack(side="left")
        self.estado_pdf = ttk.Label(arriba, text="", foreground="#555")
        self.estado_pdf.pack(side="left", padx=8)
        self.marco_paginas = ttk.LabelFrame(
            f, text="Páginas de bornes detectadas (revisá nivel, campo y controlador)", padding=4)
        cols = (("nivel", "NIVEL", 55), ("campo", "CAMPO", 50), ("funcion", "FUNCION", 90), ("tipo", "TIPO", 35),
                ("tag", "TAG", 70), ("offset", "OFFSET", 50), ("scada", "DESC. SCADA", 130),
                ("texto", "DESCRIPCIÓN / OBSERVACIONES", 330))
        self.arbol = ttk.Treeview(f, columns=[c[0] for c in cols], show="headings", height=9)
        for c, t, w in cols:
            self.arbol.heading(c, text=t)
            self.arbol.column(c, width=w, anchor="w")
        self.arbol.pack(fill="both", expand=True, pady=(6, 0))
        self._refrescar_arbol()

    def cargar_pdf(self) -> None:
        ruta = filedialog.askopenfilename(title="Plano de ingeniería", filetypes=[("PDF", "*.pdf")])
        if not ruta:
            return
        self.estado_pdf.config(text="Leyendo el PDF…")
        self.btn_aplicar.config(state="disabled")

        def trabajo():
            try:
                res = pdf_plano.leer_plano(
                    ruta, self.perfil, avance=lambda n, t: self.cola.put(("avance", n, t)))
                self.cola.put(("ok", res))
            except Exception as e:  # PDF dañado, sin pymupdf, sin vocabulario del perfil…
                self.cola.put(("error", f"{type(e).__name__}: {e}"))

        threading.Thread(target=trabajo, daemon=True).start()
        self.after(150, self._sondear)

    def _sondear(self) -> None:
        try:
            while True:
                msg = self.cola.get_nowait()
                if msg[0] == "avance":
                    self.estado_pdf.config(text=f"Leyendo el PDF… página {msg[1]} de {msg[2]}")
                elif msg[0] == "error":
                    self.estado_pdf.config(text="")
                    messagebox.showerror("No se pudo leer el PDF", msg[1])
                    return
                else:
                    self._mostrar_paginas(msg[1])
                    return
        except queue.Empty:
            self.after(150, self._sondear)

    def _mostrar_paginas(self, paginas: list) -> None:
        for w in self.marco_paginas.winfo_children():
            w.destroy()
        self.pdf_paginas, self.pdf_destinos = paginas, []
        if not paginas:
            self.marco_paginas.pack_forget()
            self.estado_pdf.config(text="No se encontraron páginas de bornes en ese PDF.")
            return
        total = sum(len(p.senales) for p in paginas)
        self.estado_pdf.config(text=f"{len(paginas)} páginas de bornes, {total} señales.")
        self.marco_paginas.pack(fill="x", pady=(6, 0), before=self.arbol)
        for j, t in enumerate(("PÁG.", "NIVEL", "CAMPO", "NOMBRE", "DESCRIPCIÓN DEL CAMPO", "CONTROLADOR", "SEÑ.")):
            ttk.Label(self.marco_paginas, text=t, font=("Segoe UI", 8, "bold")).grid(row=0, column=j, padx=2, sticky="w")
        for i, pg in enumerate(paginas, start=1):
            niv, cam, nom = tk.StringVar(value=pg.nivel), tk.StringVar(value=pg.campo), tk.StringVar()
            des, ctl = tk.StringVar(), tk.StringVar()
            ttk.Label(self.marco_paginas, text=str(pg.pagina)).grid(row=i, column=0, padx=2)
            ttk.Entry(self.marco_paginas, textvariable=niv, width=7).grid(row=i, column=1, padx=2)
            ttk.Entry(self.marco_paginas, textvariable=cam, width=6).grid(row=i, column=2, padx=2)
            ttk.Entry(self.marco_paginas, textvariable=nom, width=8).grid(row=i, column=3, padx=2)
            ttk.Entry(self.marco_paginas, textvariable=des, width=26).grid(row=i, column=4, padx=2)
            ttk.Entry(self.marco_paginas, textvariable=ctl, width=20).grid(row=i, column=5, padx=2)
            ttk.Label(self.marco_paginas, text=str(len(pg.senales))).grid(row=i, column=6, padx=2)
            self.pdf_destinos.append((pg.pagina, niv, cam, des, ctl, nom))
        self.btn_aplicar.config(state="normal")

    def aplicar_pdf(self) -> None:
        destinos = {p: (n.get().strip(), c.get().strip(), d.get().strip(), k.get().strip(), m.get().strip())
                    for p, n, c, d, k, m in self.pdf_destinos}
        faltan = [p for p, (n, c, *_) in destinos.items() if not n or not c]
        if faltan:
            messagebox.showwarning("Falta nivel o campo", f"Completá nivel y campo en las páginas: {faltan}")
            return
        if self.niveles and not messagebox.askyesno(
                "Reemplazar señales", "El proyecto ya tiene señales cargadas. ¿Reemplazarlas por las del PDF?"):
            return
        self.niveles = pdf_plano.a_niveles(self.pdf_paginas, self.perfil, destinos, self.lugar.get().strip())
        self._refrescar_arbol()
        self.btn_aplicar.config(state="disabled")

    def _descripciones(self) -> tuple[int, int, int]:
        """DESC. SCADA por reglas; lo que falte se le pregunta al usuario (hasta 3 rondas).
        Devuelve (por reglas, por lo que el usuario ya respondió, sin resolver)."""
        reglas, informe, por_reglas, por_memoria = None, None, 0, 0
        for _ in range(3):
            informe, reglas = descripciones.aplicar(self.proyecto, self.perfil, reglas)
            por_reglas += informe.por_reglas
            por_memoria += informe.por_memoria
            if not informe.pendientes:
                break
            dlg = DialogoAbreviaturas(self, informe.pendientes, reglas.maximo)
            self.wait_window(dlg)
            respondidas = [p for p in informe.pendientes if p.respuesta.strip()]
            for p in respondidas:
                reglas.recordar(p)
            if respondidas:
                reglas.guardar_memoria()
            if not respondidas:
                break
        return por_reglas, por_memoria, len(informe.pendientes) if informe else 0

    def generar(self) -> None:
        """Completa tags, offsets, estados y descripciones con las reglas del perfil (generador.py)."""
        if not self.niveles:
            messagebox.showinfo("Sin señales", "Primero cargá un PDF de plano y aplicalo al proyecto.")
            return
        d = self.datos()
        problemas = [p for p in validacion.validar(d, self.max_ref, self.max_rev, self.largo_doc)
                     if "ITEM" in p or "OFFSET" in p]
        if problemas:
            messagebox.showwarning("Numeración", "Completá la pestaña Numeración:\n" +
                                   "\n".join(f"• {x}" for x in problemas))
            self.nb.select(1)
            return
        self.proyecto = validacion.a_proyecto(d, self.perfil.id, self.proyecto)
        self.proyecto.niveles = self.niveles
        try:
            reglas_n, memoria_n, sin_resolver = self._descripciones()
            avisos = generador.generar(self.proyecto, self.perfil)
        except (ValueError, OSError) as e:
            messagebox.showerror("No se pudo generar", str(e))
            return
        self._refrescar_arbol()
        texto = (f"Listo: {len(self.proyecto.todas_las_senales())} filas.\n\nDESC. SCADA: {reglas_n} por las reglas "
                 f"de los lineamientos, {memoria_n} con abreviaturas que ya habías respondido, {sin_resolver} "
                 f"sin resolver (quedan para completar a mano).")
        avisos = [a for a in avisos if "DESC. SCADA a definir" not in a] + \
                 ([f"{sum('DESC. SCADA a definir' in a for a in avisos)} señales con DESC. SCADA a definir a mano "
                   f"(más de 20 caracteres)"] if any("DESC. SCADA a definir" in a for a in avisos) else [])
        if avisos:
            texto += f"\n\n{len(avisos)} avisos:\n" + "\n".join(f"• {a}" for a in avisos[:15])
            if len(avisos) > 15:
                texto += f"\n… y {len(avisos) - 15} más"
        messagebox.showinfo("Generado", texto)

    def _refrescar_arbol(self) -> None:
        self.arbol.delete(*self.arbol.get_children())
        for n in self.niveles:
            for c in n.campos:
                for s in c.senales:
                    self.arbol.insert("", "end", values=(
                        n.nombre, c.numero or "—", s.funcion.value,
                        s.tipo_punto.value if s.tipo_punto else "", s.tag_scada,
                        "" if s.offset is None else s.offset, s.desc_scada, s.observaciones))

    # ------------------------------------------------------------ datos
    def _cargar(self, d: dict) -> None:
        for k in validacion.CAMPOS_TEXTO:
            self.vars[k].set(d[k])
        self.item.set(d["item_inicial"])
        for t, v in self.offsets.items():
            v.set(d["offsets"].get(t, ""))
        self.refs.cargar([list(r) for r in d["referencias"]])
        self.revs.cargar([[r[k] for k in validacion.COLS_REVISION] for r in d["revisiones"]])

    def datos(self) -> dict:
        d = {k: v.get() for k, v in self.vars.items()}
        d["item_inicial"] = self.item.get()
        d["offsets"] = {t: v.get() for t, v in self.offsets.items()}
        d["referencias"] = self.refs.valores()
        d["revisiones"] = [dict(zip(validacion.COLS_REVISION, fila)) for fila in self.revs.valores()]
        return d

    def _validado(self) -> Proyecto | None:
        d = self.datos()
        problemas = validacion.validar(d, self.max_ref, self.max_rev, self.largo_doc)
        if problemas:
            messagebox.showwarning("Revisá el formulario", "\n".join(f"• {x}" for x in problemas))
            return None
        self.proyecto = validacion.a_proyecto(d, self.perfil.id, self.proyecto)
        self.proyecto.niveles = self.niveles
        return self.proyecto

    def guardar(self) -> None:
        p = self._validado()
        if not p:
            return
        ruta = filedialog.asksaveasfilename(title="Guardar proyecto", defaultextension=".json",
                                            filetypes=[("Proyecto", "*.json")],
                                            initialfile=f"{p.caratula.archivo_magnetico or 'proyecto'}.json")
        if ruta:
            p.guardar(ruta)
            messagebox.showinfo("Guardado", f"Proyecto guardado en:\n{ruta}")

    def exportar(self) -> None:
        p = self._validado()
        if not p:
            return
        ruta = filedialog.asksaveasfilename(title="Exportar Excel", defaultextension=".xlsx",
                                            filetypes=[("Excel", "*.xlsx")],
                                            initialfile=f"{p.caratula.archivo_magnetico or 'listado'}.xlsx")
        if not ruta:
            return
        try:
            excel_writer.escribir_xlsx(p, self.perfil, Path(ruta), incluir_caratula=self.con_caratula.get())
        except (excel_writer.DocumentoInvalido, excel_writer.PlantillaNoEncontrada, ValueError, OSError) as e:
            messagebox.showerror("No se pudo exportar", str(e))
            return
        n = len(p.todas_las_senales())
        aviso = "" if n else "\n\nAviso: todavía no hay señales; el Excel tiene solo la carátula y el encabezado."
        messagebox.showinfo("Exportado", f"Excel generado en:\n{ruta}{aviso}")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Listado de Señales")
        self.geometry("860x520")
        self.minsize(720, 440)
        self._actual: ttk.Frame | None = None
        self.mostrar_inicio()

    def _poner(self, frame: ttk.Frame) -> None:
        if self._actual is not None:
            self._actual.destroy()
        self._actual = frame
        frame.pack(fill="both", expand=True)

    def mostrar_inicio(self) -> None:
        self._poner(Inicio(self))

    def mostrar_formulario(self, perfil, proyecto, cliente: str = "") -> None:
        self._poner(Formulario(self, perfil, proyecto, cliente))


def main() -> None:
    App().mainloop()
