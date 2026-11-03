"""Ventana «Verificación de documentación»: se muestra ANTES de armar el listado.

Cruza lo leído de los esquemas funcionales (EF) con las hojas de LISTA DE SEÑALES de los mismos documentos y dice, por
señal, qué quedó verificado, qué tiene texto distinto, qué no tiene respaldo y qué figura solo en las listas. Cada dato
lleva su archivo y hoja. Se puede guardar como CSV."""
from __future__ import annotations

import csv
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import cruce

ESTADOS = {"verificada": "Verificada", "distinto": "Texto distinto", "ambigua": "Ambigua", "sin_respaldo": "Sin respaldo"}
COLORES = {"verificada": "#15803d", "distinto": "#c2410c", "ambigua": "#a16207", "sin_respaldo": "#b91c1c"}


def filas_ef(inf: cruce.Informe) -> list[tuple]:
    """(estado, campo, señal del EF, origen en el EF, texto en la lista, origen del respaldo, módulo/relé/borne, nota)."""
    out = []
    for v in inf.verificaciones:
        c = v.celda
        out.append((ESTADOS[v.estado], v.campo, v.rotulo, f"{v.archivo_ef} · pág. {v.pagina_ef}",
                    c.texto if c else "", c.origen if c else "",
                    " · ".join(x.strip() for x in (c.modulo, c.rele, c.borne) if x.strip()) if c else "", v.nota))
    return out


def filas_recuperadas(inf: cruce.Informe) -> list[tuple]:
    return [("Solo en la lista", c.campo, c.texto, "—", c.texto, c.origen,
             " · ".join(x.strip() for x in (c.modulo, c.rele, c.borne) if x.strip()),
             "figura en la lista de señales y no se leyó del EF: pendiente de confirmar") for c in inf.recuperadas]


def filas_tableros(inf: cruce.Informe) -> list[tuple]:
    return [("Solo en tablero", "", c.texto, "—", c.texto, c.origen,
             " · ".join(x.strip() for x in (c.modulo, c.borne) if x.strip()),
             "reserva" if c.texto.lower().startswith("reserva") else "nivel, campo y función por confirmar")
            for c in inf.tableros]


ENCABEZADO = ("Estado", "Campo", "Señal (EF)", "Origen en el EF", "Texto en la lista", "Respaldo", "Módulo · relé · borne", "Nota")


def guardar_csv(inf: cruce.Informe, ruta: str) -> None:
    with open(ruta, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f, delimiter=";")
        w.writerow(ENCABEZADO)
        w.writerows(filas_ef(inf) + filas_recuperadas(inf) + filas_tableros(inf))
        for d in inf.duplicados:
            w.writerow(("Posible duplicado", "", d, "", "", "", "", ""))
        for s in inf.sin_leer:
            w.writerow(("Página sin leer", "", s, "", "", "", "", "necesita OCR"))


class DialogoVerificacion(tk.Toplevel):
    def __init__(self, master, inf: cruce.Informe):
        super().__init__(master)
        self.title("Verificación de documentación")
        self.transient(master)
        self.inf = inf
        self.continuar = False
        ttk.Label(self, text=inf.resumen(), wraplength=1100, justify="left", padding=10).pack(fill="x")
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10)
        self._tabla(nb, f"Señales del EF ({len(inf.verificaciones)})", filas_ef(inf))
        self._tabla(nb, f"Solo en las listas ({len(inf.recuperadas)})", filas_recuperadas(inf))
        self._tabla(nb, f"Señales de tableros ({len(inf.tableros)})", filas_tableros(inf))
        avisos = ttk.Frame(nb, padding=8)
        nb.add(avisos, text="Avisos")
        txt = tk.Text(avisos, width=130, height=20, wrap="word")
        txt.pack(fill="both", expand=True)
        txt.insert("end", "Índices leídos:\n" + ("\n".join(" · " + i for i in inf.indices) or " · ninguno") + "\n\n")
        txt.insert("end", "Hojas de lista de señales leídas:\n" + ("\n".join(" · " + i for i in inf.listas) or " · ninguna") + "\n\n")
        txt.insert("end", "Posibles duplicados:\n" + ("\n".join(" · " + i for i in inf.duplicados) or " · ninguno") + "\n\n")
        txt.insert("end", "Páginas que no se pudieron leer:\n" + ("\n".join(" · " + i for i in inf.sin_leer) or " · ninguna") + "\n")
        txt.config(state="disabled")
        b = ttk.Frame(self, padding=10)
        b.pack(fill="x")
        ttk.Button(b, text="Continuar al listado", command=self._seguir).pack(side="right")
        ttk.Button(b, text="Cancelar", command=self.destroy).pack(side="right", padx=6)
        ttk.Button(b, text="Guardar informe (CSV)…", command=self._guardar).pack(side="left")
        self.grab_set()

    def _tabla(self, nb, titulo: str, filas: list[tuple]) -> None:
        marco = ttk.Frame(nb)
        nb.add(marco, text=titulo)
        cols = [f"c{i}" for i in range(len(ENCABEZADO))]
        arbol = ttk.Treeview(marco, columns=cols, show="headings", height=18)
        for c, t, ancho in zip(cols, ENCABEZADO, (95, 50, 230, 190, 230, 230, 200, 260)):
            arbol.heading(c, text=t)
            arbol.column(c, width=ancho, anchor="w")
        for est, col in ((ESTADOS[k], v) for k, v in COLORES.items()):
            arbol.tag_configure(est, foreground=col)
        arbol.tag_configure("Solo en la lista", foreground="#1d4ed8")
        arbol.tag_configure("Solo en tablero", foreground="#1d4ed8")
        sb = ttk.Scrollbar(marco, orient="vertical", command=arbol.yview)
        arbol.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        arbol.pack(side="left", fill="both", expand=True)
        for f in filas:
            arbol.insert("", "end", values=f, tags=(f[0],))

    def _guardar(self) -> None:
        ruta = filedialog.asksaveasfilename(title="Guardar informe", defaultextension=".csv",
                                            filetypes=[("CSV", "*.csv")], initialfile="verificacion.csv")
        if ruta:
            guardar_csv(self.inf, ruta)
            messagebox.showinfo("Informe guardado", ruta, parent=self)

    def _seguir(self) -> None:
        self.continuar = True
        self.destroy()
