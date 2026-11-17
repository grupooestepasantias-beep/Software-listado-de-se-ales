"""Aspecto de la ventana: tema claro, tipografía legible, tablas con filas más altas y rayado, botón principal
resaltado. Se aplica una vez sobre la raíz (`aplicar(root)`) y vale para todos los diálogos."""
from __future__ import annotations

import tkinter as tk
from tkinter import font as tkfont
from tkinter import ttk

FONDO = "#f4f6f9"
PANEL = "#ffffff"
TEXTO = "#1f2933"
SUAVE = "#6b7785"
BORDE = "#d5dbe3"
ACENTO = "#1f5fbf"
ACENTO_OSCURO = "#174a95"
ENCABEZADO = "#e8edf4"
SELECCION = "#cfe0fb"
RAYA = "#f6f8fb"


def _fuente() -> str:
    familias = set(tkfont.families())
    for f in ("Segoe UI", "Calibri", "Helvetica Neue", "DejaVu Sans"):
        if f in familias:
            return f
    return "TkDefaultFont"


def aplicar(raiz: tk.Misc) -> dict:
    """Configura ttk y las fuentes por defecto. Devuelve las fuentes usadas (por si la ventana quiere reusarlas)."""
    fam = _fuente()
    base = tkfont.nametofont("TkDefaultFont")
    base.configure(family=fam, size=10)
    tkfont.nametofont("TkTextFont").configure(family=fam, size=10)
    tkfont.nametofont("TkHeadingFont").configure(family=fam, size=10, weight="bold")
    negrita = tkfont.Font(family=fam, size=10, weight="bold")
    raiz.configure(background=FONDO)
    raiz.option_add("*TCombobox*Listbox.font", base)

    st = ttk.Style(raiz)
    if "clam" in st.theme_names():
        st.theme_use("clam")
    st.configure(".", background=FONDO, foreground=TEXTO, fieldbackground=PANEL, bordercolor=BORDE,
                 lightcolor=FONDO, darkcolor=FONDO, troughcolor=ENCABEZADO, focuscolor=ACENTO)
    st.configure("TFrame", background=FONDO)
    st.configure("TLabel", background=FONDO, foreground=TEXTO)
    st.configure("Suave.TLabel", foreground=SUAVE)
    st.configure("Titulo.TLabel", font=(fam, 11, "bold"))
    st.configure("TCheckbutton", background=FONDO)
    st.configure("TRadiobutton", background=FONDO)
    st.configure("TLabelframe", background=FONDO, bordercolor=BORDE)
    st.configure("TLabelframe.Label", background=FONDO, foreground=SUAVE, font=(fam, 9, "bold"))
    st.configure("TEntry", padding=4, bordercolor=BORDE)
    st.configure("TCombobox", padding=4, bordercolor=BORDE)
    st.map("TEntry", bordercolor=[("focus", ACENTO)])
    st.map("TCombobox", bordercolor=[("focus", ACENTO)], fieldbackground=[("readonly", PANEL)])

    # botones
    st.configure("TButton", padding=(12, 6), background=ENCABEZADO, bordercolor=BORDE, relief="flat")
    st.map("TButton", background=[("active", "#dbe3ee"), ("pressed", BORDE)])
    st.configure("Accent.TButton", background=ACENTO, foreground="#ffffff", bordercolor=ACENTO, font=negrita)
    st.map("Accent.TButton", background=[("active", ACENTO_OSCURO), ("pressed", ACENTO_OSCURO)],
           foreground=[("disabled", "#cfd8e6")])

    # pestañas
    st.configure("TNotebook", background=FONDO, borderwidth=0, tabmargins=(2, 4, 2, 0))
    st.configure("TNotebook.Tab", padding=(16, 7), background=ENCABEZADO, foreground=SUAVE, bordercolor=BORDE)
    st.map("TNotebook.Tab", background=[("selected", PANEL)], foreground=[("selected", ACENTO)],
           expand=[("selected", (0, 0, 0, 2))])

    # tablas
    st.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXTO, rowheight=26,
                 bordercolor=BORDE, borderwidth=1)
    st.map("Treeview", background=[("selected", SELECCION)], foreground=[("selected", TEXTO)])
    st.configure("Treeview.Heading", background=ENCABEZADO, foreground=TEXTO, font=(fam, 9, "bold"), padding=(6, 6),
                 relief="flat", bordercolor=BORDE)
    st.map("Treeview.Heading", background=[("active", BORDE)])
    st.configure("TScrollbar", background=ENCABEZADO, troughcolor=FONDO, bordercolor=FONDO, arrowcolor=SUAVE)
    st.configure("TPanedwindow", background=FONDO)
    st.configure("Estado.TLabel", background=ENCABEZADO, foreground=SUAVE, padding=(10, 5))
    st.configure("Barra.TFrame", background=PANEL)
    st.configure("Barra.TSeparator", background=BORDE)
    st.configure("Barra.TCheckbutton", background=PANEL)
    return {"familia": fam, "negrita": negrita}


def rayar(arbol: ttk.Treeview) -> None:
    """Rayado suave en las filas pares. Llamar una vez después de configurar las demás marcas (`tag_configure`)."""
    arbol.tag_configure("raya", background=RAYA)
