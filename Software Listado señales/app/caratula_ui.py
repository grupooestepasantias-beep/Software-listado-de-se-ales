"""Pestaña "Carátula" de la app: datos de la obra, referencias, revisiones y los dos logos (imágenes elegibles).

La lógica que se puede probar sin pantalla (tablas como texto, datos <-> Caratula, validación) está en funciones
de módulo; la clase PestanaCaratula solo arma los controles."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, ttk

import excel_writer
from modelo import Caratula, Referencia, Revision

from . import validacion

SEPARADOR = "|"
LOGO_CLIENTE_ETAP = Path(__file__).resolve().parent.parent / "plantillas" / "EPEN" / "imagenes" / "logo_epen.jpeg"
LOGO_PROYECTISTA_ETAP = Path(__file__).resolve().parent.parent / "plantillas" / "EPEN" / "imagenes" / "logo_proyectista.png"

ETIQUETAS = [
    ("cliente", "Cliente"), ("obra", "Obra"), ("lugar", "Lugar"), ("departamento", "Departamento"),
    ("expediente", "Nro. expediente"), ("titulo", "Título"), ("numero_documento", "Nº de documento"),
    ("proyecto", "Proyectó"), ("dibujo", "Dibujó"), ("aprobo", "Aprobó"),
    ("archivo_magnetico", "Archivo magnético"), ("escala", "Escala"), ("revision", "Revisión"), ("fecha", "Fecha"),
]
LOGOS = [("logo_cliente", "Logo del cliente (arriba a la izquierda)"),
         ("logo_proyectista", "Logo del proyectista (abajo a la izquierda)")]


# ---------------------------------------------------------------- lógica sin pantalla
def referencias_a_texto(refs) -> str:
    return "\n".join(f"{r.codigo} {SEPARADOR} {r.descripcion}" for r in refs)


def texto_a_referencias(texto: str) -> list[Referencia]:
    out = []
    for linea in texto.splitlines():
        if linea.strip():
            c, _, t = linea.partition(SEPARADOR)
            out.append(Referencia(c.strip(), t.strip()))
    return out


def revisiones_a_texto(revs) -> str:
    return "\n".join(f" {SEPARADOR} ".join(getattr(r, k) for k in validacion.COLS_REVISION) for r in revs)


def texto_a_revisiones(texto: str) -> list[Revision]:
    out = []
    for linea in texto.splitlines():
        if linea.strip():
            partes = [p.strip() for p in linea.split(SEPARADOR)]
            partes += [""] * (len(validacion.COLS_REVISION) - len(partes))
            out.append(Revision(**dict(zip(validacion.COLS_REVISION, partes))))
    return out


def tiene_datos(car: Caratula) -> bool:
    """¿El usuario completó algo? (la escala N/A de fábrica no cuenta). Sin datos el Excel sale sin carátula."""
    texto = any(getattr(car, k).strip() for k, _ in ETIQUETAS if k != "escala")
    return bool(texto or car.referencias or car.revisiones)


def problemas(car: Caratula, limites: dict) -> list[str]:
    """Todo lo que impediría exportar la carátula (largos de la plantilla, revisiones sin letra, logos inválidos)."""
    datos = {k: getattr(car, k) for k, _ in ETIQUETAS}
    datos["referencias"] = [(r.codigo, r.descripcion) for r in car.referencias]
    datos["revisiones"] = [{k: getattr(r, k) for k in validacion.COLS_REVISION} for r in car.revisiones]
    p = validacion.validar(datos, limites["referencias"], limites["revisiones"], limites["documento"])
    for clave, nombre in (("logo_cliente", "Logo del cliente"), ("logo_proyectista", "Logo del proyectista")):
        p += excel_writer.validar_imagen(getattr(car, clave), nombre)
    return p


def limites_de(perfil) -> dict:
    """Capacidad de la carátula según la plantilla: referencias, revisiones y largo del nº de documento."""
    c = excel_writer.cargar_plantilla(perfil)["caratula_campos"]
    r0, r1 = c["referencias"]["filas"]
    v0, v1 = c["revisiones"]["filas"]
    return {"referencias": r1 - r0 + 1, "revisiones": v1 - v0 + 1, "documento": len(c["documento"]["celdas"])}


def caratula_nueva() -> Caratula:
    """Carátula de un proyecto nuevo: escala N/A y, si existen, los logos del ETAP preseleccionados."""
    return Caratula(
        logo_cliente=str(LOGO_CLIENTE_ETAP) if LOGO_CLIENTE_ETAP.is_file() else "",
        logo_proyectista=str(LOGO_PROYECTISTA_ETAP) if LOGO_PROYECTISTA_ETAP.is_file() else "")


# ---------------------------------------------------------------- controles
class PestanaCaratula(ttk.Frame):
    def __init__(self, master, perfil):
        super().__init__(master, padding=10)
        try:
            self.lim = limites_de(perfil)
        except (excel_writer.PlantillaNoEncontrada, KeyError):
            self.lim = {"referencias": 14, "revisiones": 4, "documento": 20}
        self.vars = {k: tk.StringVar() for k, _ in ETIQUETAS}
        self.logo_var = {k: tk.StringVar() for k, _ in LOGOS}
        self.logo_vista: dict[str, ttk.Label] = {}
        self._fotos: dict[str, object] = {}

        form = ttk.LabelFrame(self, text="Datos de la obra")
        form.pack(fill="x")
        for i, (k, texto) in enumerate(ETIQUETAS):
            col, fila = (0, i) if i < 7 else (2, i - 7)
            ttk.Label(form, text=texto).grid(row=fila, column=col, sticky="e", padx=4, pady=2)
            ttk.Entry(form, textvariable=self.vars[k], width=34).grid(row=fila, column=col + 1, padx=4, pady=2)
        ttk.Label(form, foreground="#666",
                  text=f"(Nº de documento: hasta {self.lim['documento']} caracteres, sin contar guiones)"
                  ).grid(row=7, column=0, columnspan=4, sticky="w", padx=4)

        logos = ttk.LabelFrame(self, text="Logos (imágenes: png, jpg, gif o bmp)")
        logos.pack(fill="x", pady=(8, 0))
        for fila, (k, texto) in enumerate(LOGOS):
            ttk.Label(logos, text=texto).grid(row=fila, column=0, sticky="e", padx=4, pady=3)
            ttk.Entry(logos, textvariable=self.logo_var[k], width=52, state="readonly").grid(row=fila, column=1, padx=4)
            ttk.Button(logos, text="Elegir imagen…", command=lambda k=k: self.elegir_logo(k)).grid(row=fila, column=2, padx=2)
            ttk.Button(logos, text="Quitar", command=lambda k=k: self.poner_logo(k, "")).grid(row=fila, column=3, padx=2)
            self.logo_vista[k] = ttk.Label(logos, text="(sin logo)", width=12, anchor="center")
            self.logo_vista[k].grid(row=fila, column=4, padx=6)

        tablas = ttk.Frame(self)
        tablas.pack(fill="both", expand=True, pady=8)
        izq = ttk.LabelFrame(tablas, text=f"Referencias (máx. {self.lim['referencias']})  —  código | título")
        izq.pack(side="left", fill="both", expand=True, padx=(0, 4))
        self.t_ref = tk.Text(izq, height=8, width=48, wrap="none")
        self.t_ref.pack(fill="both", expand=True)
        der = ttk.LabelFrame(
            tablas, text=f"Revisiones (máx. {self.lim['revisiones']}, de la más antigua a la más nueva)\n"
                         "rev | fecha | descripción | proyectó | revisó | aprobó")
        der.pack(side="left", fill="both", expand=True, padx=(4, 0))
        self.t_rev = tk.Text(der, height=8, width=48, wrap="none")
        self.t_rev.pack(fill="both", expand=True)
        self.cargar(caratula_nueva())

    # --- datos <-> controles
    def cargar(self, car: Caratula) -> None:
        for k, _ in ETIQUETAS:
            self.vars[k].set(getattr(car, k))
        for k, _ in LOGOS:
            self.poner_logo(k, getattr(car, k))
        self.t_ref.delete("1.0", "end")
        self.t_ref.insert("1.0", referencias_a_texto(car.referencias))
        self.t_rev.delete("1.0", "end")
        self.t_rev.insert("1.0", revisiones_a_texto(car.revisiones))

    def leer(self) -> Caratula:
        d = {k: self.vars[k].get().strip() for k, _ in ETIQUETAS}
        d.update({k: self.logo_var[k].get() for k, _ in LOGOS})
        return Caratula(**d, referencias=texto_a_referencias(self.t_ref.get("1.0", "end")),
                        revisiones=texto_a_revisiones(self.t_rev.get("1.0", "end")))

    def tiene_datos(self) -> bool:
        return tiene_datos(self.leer())

    def problemas(self) -> list[str]:
        return problemas(self.leer(), self.lim)

    # --- logos
    def poner_logo(self, clave: str, ruta: str) -> None:
        """Muestra el logo elegido (ruta vacía = sin logo) con una vista previa."""
        self.logo_var[clave].set(ruta)
        foto = None
        if ruta and Path(ruta).is_file():
            try:
                from PIL import Image, ImageTk
                with Image.open(ruta) as im:
                    im = im.convert("RGBA")
                    im.thumbnail((70, 50))
                    foto = ImageTk.PhotoImage(im)
            except Exception:
                foto = None
        self._fotos[clave] = foto
        self.logo_vista[clave].configure(image=foto or "", text="" if foto else ("(no se puede mostrar)" if ruta else "(sin logo)"))

    def elegir_logo(self, clave: str) -> None:
        ruta = filedialog.askopenfilename(
            title="Elegí la imagen", filetypes=[("Imágenes", "*.png *.jpg *.jpeg *.gif *.bmp"), ("Todos", "*.*")])
        if ruta:
            self.poner_logo(clave, ruta)
