"""Ventana del catálogo de controladores: listado filtrable de SEL (Axion/RTAC) y Schneider (Saitel DP)."""
from __future__ import annotations

import tkinter as tk
import webbrowser
from tkinter import messagebox, ttk
from typing import Callable

import catalogo

TODAS = "Todas"


class DialogoModeloPropio(tk.Toplevel):
    def __init__(self, master):
        super().__init__(master)
        self.title("Agregar modelo propio")
        self.transient(master)
        self.resultado: dict | None = None
        self.vars = {k: tk.StringVar() for k in ("marca", "familia", "categoria", "modelo", "descripcion")}
        f = ttk.Frame(self, padding=10)
        f.pack()
        for i, (k, t) in enumerate((("modelo", "Modelo *"), ("marca", "Marca"), ("familia", "Familia"),
                                    ("categoria", "Categoría"), ("descripcion", "Descripción"))):
            ttk.Label(f, text=t).grid(row=i, column=0, sticky="w", pady=2, padx=(0, 8))
            ttk.Entry(f, textvariable=self.vars[k], width=40).grid(row=i, column=1)
        b = ttk.Frame(f)
        b.grid(row=5, column=0, columnspan=2, sticky="e", pady=(8, 0))
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right", padx=4)
        ttk.Button(b, text="Guardar", command=self._ok).pack(side="right")
        self.grab_set()

    def _ok(self) -> None:
        d = {k: v.get().strip() for k, v in self.vars.items()}
        if not d["modelo"]:
            messagebox.showwarning("Falta el modelo", "Escribí el modelo.", parent=self)
            return
        self.resultado = d
        self.destroy()


class VentanaCatalogo(tk.Toplevel):
    """`usar(modelo, con_tension, alcance)` aplica el modelo elegido en la tabla; devuelve cuántas filas cambió.
    alcance = "filas" (las seleccionadas de la tabla) o "campo" (todo el campo de esas filas)."""

    def __init__(self, master, usar: Callable[[str, bool, str], int]):
        super().__init__(master)
        self.title("Catálogo de controladores")
        self.geometry("1000x540")
        self.minsize(800, 380)
        self.usar = usar
        self.doc = catalogo.cargar()
        self.marca, self.categoria, self.texto = tk.StringVar(value=TODAS), tk.StringVar(value=TODAS), tk.StringVar()
        self.con_tension = tk.BooleanVar(value=True)
        self.alcance = tk.StringVar(value="filas")
        self._armar()
        self._llenar()

    def _armar(self) -> None:
        raiz = ttk.Frame(self, padding=8)
        raiz.pack(fill="both", expand=True)
        filtros = ttk.Frame(raiz)
        filtros.pack(fill="x")
        ttk.Label(filtros, text="Marca").pack(side="left")
        self.cb_marca = ttk.Combobox(filtros, textvariable=self.marca, state="readonly", width=34)
        self.cb_marca.pack(side="left", padx=(4, 12))
        ttk.Label(filtros, text="Categoría").pack(side="left")
        self.cb_cat = ttk.Combobox(filtros, textvariable=self.categoria, state="readonly", width=26)
        self.cb_cat.pack(side="left", padx=(4, 12))
        ttk.Label(filtros, text="Buscar").pack(side="left")
        ttk.Entry(filtros, textvariable=self.texto, width=22).pack(side="left", padx=4)
        self.cb_marca.bind("<<ComboboxSelected>>", lambda e: self._cambio_marca())
        self.cb_cat.bind("<<ComboboxSelected>>", lambda e: self._llenar())
        self.texto.trace_add("write", lambda *_: self._llenar())

        marco = ttk.Frame(raiz)
        marco.pack(fill="both", expand=True, pady=6)
        cols = (("marca", "MARCA", 170), ("familia", "FAMILIA", 110), ("categoria", "CATEGORÍA", 150),
                ("modelo", "MODELO", 100), ("descripcion", "DESCRIPCIÓN", 420))
        self.arbol = ttk.Treeview(marco, columns=[c[0] for c in cols], show="headings", selectmode="browse")
        for c, t, w in cols:
            self.arbol.heading(c, text=t)
            self.arbol.column(c, width=w, anchor="w", stretch=c == "descripcion")
        sy = ttk.Scrollbar(marco, orient="vertical", command=self.arbol.yview)
        self.arbol.configure(yscrollcommand=sy.set)
        self.arbol.pack(side="left", fill="both", expand=True)
        sy.pack(side="right", fill="y")
        self.arbol.bind("<Double-1>", lambda e: self._usar())

        opciones = ttk.LabelFrame(raiz, text="Al usar el modelo elegido", padding=6)
        opciones.pack(fill="x")
        ttk.Checkbutton(opciones, text="Agregar la tensión del nivel al final (ej. SEL-2241-33kV)",
                        variable=self.con_tension).pack(side="left")
        ttk.Radiobutton(opciones, text="Filas seleccionadas", variable=self.alcance, value="filas").pack(side="left", padx=(16, 4))
        ttk.Radiobutton(opciones, text="Todo el campo de esas filas", variable=self.alcance, value="campo").pack(side="left")

        pie = ttk.Frame(raiz)
        pie.pack(fill="x", pady=(8, 0))
        ttk.Button(pie, text="Usar como controlador", command=self._usar).pack(side="left")
        ttk.Button(pie, text="Agregar modelo propio…", command=self._propio).pack(side="left", padx=6)
        for nombre, url in self.doc["sitios"].items():
            ttk.Button(pie, text=f"Abrir sitio: {nombre.split(' (')[0]}",
                       command=lambda u=url: webbrowser.open(u)).pack(side="left", padx=2)
        ttk.Button(pie, text="Cerrar", command=self.destroy).pack(side="right")
        self.info = ttk.Label(raiz, foreground="#666", wraplength=960)
        self.info.pack(anchor="w", pady=(6, 0))

    def _cambio_marca(self) -> None:
        self.categoria.set(TODAS)
        self._llenar()

    def _llenar(self) -> None:
        entradas = self.doc["entradas"]
        marca = "" if self.marca.get() == TODAS else self.marca.get()
        self.cb_marca["values"] = [TODAS] + catalogo.marcas(entradas)
        self.cb_cat["values"] = [TODAS] + catalogo.categorias(entradas, marca)
        cat = "" if self.categoria.get() == TODAS else self.categoria.get()
        self.arbol.delete(*self.arbol.get_children())
        visibles = catalogo.filtrar(entradas, marca, cat, self.texto.get())
        for e in visibles:
            self.arbol.insert("", "end", values=(e["marca"], e["familia"], e["categoria"], e["modelo"], e["descripcion"]))
        self.info.config(text=f"{len(visibles)} de {len(entradas)} modelos. Consultado el {self.doc['consultado']}. "
                              f"{self.doc['nota']}")

    def _modelo(self) -> str:
        sel = self.arbol.selection()
        return str(self.arbol.item(sel[0], "values")[3]) if sel else ""

    def _usar(self) -> None:
        modelo = self._modelo()
        if not modelo:
            messagebox.showinfo("Elegí un modelo", "Seleccioná un modelo de la lista.", parent=self)
            return
        n = self.usar(modelo, self.con_tension.get(), self.alcance.get())
        if n:
            self.info.config(text=f"'{modelo}' aplicado a {n} fila(s) de la tabla.")
        else:
            messagebox.showinfo("Sin filas", "Seleccioná primero las filas de la tabla que van a llevar ese controlador.",
                                parent=self)

    def _propio(self) -> None:
        dlg = DialogoModeloPropio(self)
        self.wait_window(dlg)
        if not dlg.resultado:
            return
        d = dlg.resultado
        try:
            catalogo.agregar_propio(d["modelo"], d["descripcion"], d["marca"] or catalogo.MARCA_PROPIA,
                                    d["familia"], d["categoria"])
        except (ValueError, OSError) as e:
            messagebox.showwarning("No se pudo guardar", str(e), parent=self)
            return
        self.doc = catalogo.cargar()
        self._llenar()
