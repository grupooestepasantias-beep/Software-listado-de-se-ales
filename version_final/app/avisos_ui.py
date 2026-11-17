"""Pestaña «Avisos»: lo que las validaciones encontraron en el listado. Celeste = contradice una regla; rosa = falta
información o hay algo para revisar. Solo informa: nunca cambia un dato. Doble clic en un aviso lleva a su fila."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import Callable

from avisos import COLORES, CELESTE, NOMBRES, ROSA, Aviso


class PestanaAvisos(ttk.Frame):
    def __init__(self, master, ir_a: Callable[[tuple[int, ...]], None]):
        super().__init__(master, padding=6)
        self.ir_a = ir_a
        self.lista: list[Aviso] = []
        self.ver = {CELESTE: tk.BooleanVar(value=True), ROSA: tk.BooleanVar(value=True)}

        barra = ttk.Frame(self)
        barra.pack(fill="x")
        self.resumen = tk.StringVar(value="Todavía no hay un listado calculado.")
        ttk.Label(barra, textvariable=self.resumen, style="Titulo.TLabel").pack(side="left")
        for gravedad in (ROSA, CELESTE):
            tk.Checkbutton(barra, text=f"Ver {NOMBRES[gravedad].lower()}", variable=self.ver[gravedad], command=self.refrescar,
                           bg=COLORES[gravedad], activebackground=COLORES[gravedad], bd=0, padx=8).pack(side="right", padx=3)

        ttk.Label(self, style="Suave.TLabel", text=(
            "Los avisos no cambian ningún dato: solo avisan. Doble clic en uno para ir a su fila del listado.")
        ).pack(anchor="w", pady=(4, 6))

        cols = (("gravedad", "", 80), ("codigo", "Qué", 190), ("mensaje", "Aviso", 520), ("donde", "Dónde", 330))
        self.arbol = ttk.Treeview(self, columns=[c[0] for c in cols], show="headings", selectmode="browse")
        for clave, titulo, ancho in cols:
            self.arbol.heading(clave, text=titulo)
            self.arbol.column(clave, width=ancho, anchor="w")
        for gravedad, color in COLORES.items():
            self.arbol.tag_configure(gravedad, background=color)
        sb = ttk.Scrollbar(self, orient="vertical", command=self.arbol.yview)
        self.arbol.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.arbol.pack(side="left", fill="both", expand=True)
        self.arbol.bind("<Double-1>", self._ir)
        self.arbol.bind("<Return>", self._ir)

    def mostrar(self, lista: list[Aviso]) -> None:
        self.lista = list(lista)
        self.refrescar()

    def refrescar(self) -> None:
        self.arbol.delete(*self.arbol.get_children())
        n = {CELESTE: 0, ROSA: 0}
        for i, a in enumerate(self.lista):
            n[a.gravedad] += 1
            if self.ver[a.gravedad].get():
                self.arbol.insert("", "end", iid=str(i), tags=(a.gravedad,), values=(
                    "Celeste" if a.gravedad == CELESTE else "Rosa", a.codigo.replace("_", " ").capitalize(), a.mensaje, a.donde))
        if not self.lista:
            self.resumen.set("Sin avisos: el listado no contradice ninguna regla y no le falta información.")
        else:
            self.resumen.set(f"{n[CELESTE]} celestes (contradicen una regla) · {n[ROSA]} rosas (falta información o revisar)")

    def _ir(self, _ev=None) -> None:
        sel = self.arbol.selection()
        if sel:
            a = self.lista[int(sel[0])]
            if a.ids:
                self.ir_a(a.ids)
