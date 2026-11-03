"""Corpus documental: todas las páginas de todos los archivos, con su texto, su número de hoja y su sección del índice.

Una página sale con su texto nativo; si el texto está dibujado como vectores o es una imagen (poco texto y muchos
trazos), se lee con OCR (ocr.py). Todas las cajas de texto quedan en puntos PDF, en la orientación en que se ve la hoja,
así se pueden agrupar en filas y columnas igual venga del texto o del OCR.

El ÍNDICE de cada documento ("HOJA 74  LISTA DE SEÑALES Y ALARMAS") se detecta y se lee: dice qué es cada hoja, y con
eso se encuentran las hojas que traen la información de las señales (listas, tablas de bornes) sin reglas por cliente.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

import ocr
from hmi import sin_acentos

DPI_OCR = 200


@dataclass
class Caja:
    x: float
    y: float
    w: float
    h: float
    texto: str

    @property
    def cx(self) -> float:
        return self.x + self.w / 2

    @property
    def cy(self) -> float:
        return self.y + self.h / 2


@dataclass
class PaginaDoc:
    archivo: str
    n: int                       # página del PDF (desde 1)
    cajas: list[Caja]
    fuente: str                  # "texto" | "ocr" | "sin_texto" (necesita OCR y no está disponible)
    hoja: str = ""               # número de hoja del cajetín ("HOJA: 74 DE 92")
    titulo: str = ""             # título del cajetín
    seccion: str = ""            # descripción de la hoja según el índice
    es_indice: bool = False

    @property
    def texto(self) -> str:
        return " ".join(c.texto for c in sorted(self.cajas, key=lambda c: (round(c.cy / 6), c.x)))


@dataclass
class Documento:
    ruta: str
    nombre: str
    paginas: list[PaginaDoc] = field(default_factory=list)
    indice: dict[int, str] = field(default_factory=dict)      # hoja -> descripción
    paginas_indice: list[int] = field(default_factory=list)
    sin_leer: list[int] = field(default_factory=list)         # páginas que necesitaban OCR y no se pudieron leer
    error: str = ""


def filas(cajas: list[Caja], tol: float = 4.0) -> list[list[Caja]]:
    """Agrupa las cajas en renglones (mismo centro vertical ± tol) y los ordena de arriba abajo, de izquierda a derecha."""
    res: list[list[Caja]] = []
    for c in sorted(cajas, key=lambda c: c.cy):
        if res and abs(res[-1][-1].cy - c.cy) <= tol:
            res[-1].append(c)
        else:
            res.append([c])
    return [sorted(f, key=lambda c: c.x) for f in res]


def _cajas_nativas(page) -> list[Caja]:
    m = page.rotation_matrix   # el texto viene en la página sin girar: se lleva a como se ve la hoja
    cajas = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = " ".join("".join(s["text"] for s in l["spans"]).split())
            if t:
                r = _rect(l["bbox"]) * m
                cajas.append(Caja(r.x0, r.y0, r.width, r.height, t))
    return cajas


def _rect(bbox):
    import pymupdf
    return pymupdf.Rect(bbox)


def _cajas_ocr(datos: list[dict]) -> list[Caja]:
    k = 72 / DPI_OCR
    return [Caja(d["x"] * k, d["y"] * k, d["w"] * k, d["h"] * k, d["texto"]) for d in datos if d["texto"].strip()]


def _cajetin(cajas: list[Caja]) -> tuple[str, str]:
    """(hoja, título) del cajetín: 'HOJA: 74 DE 92' y el texto de 'TITULO:' (hasta 'DOCUMENTO')."""
    hoja = titulo = ""
    for fila in filas(cajas, tol=5):
        t = " ".join(c.texto for c in fila)
        if not hoja:
            m = re.search(r"HOJA\s*:?\s*(\d{1,3})\s*DE\s*\$?\s*\d{1,3}", t, re.I)
            hoja = m.group(1) if m else hoja
        if not titulo:
            m = re.search(r"T[IÍ]TULO\s*:\s*(.*?)(?:DOCUMENTO|$)", t, re.I)
            titulo = m.group(1).strip() if m else titulo
    return hoja, titulo


def pagina_doc(doc, n: int, ruta: Path, usar_ocr: bool = True, dpi: int = DPI_OCR) -> PaginaDoc:
    page = doc[n - 1]
    if ocr.necesita_ocr(page):
        datos = ocr.leer_pagina(ruta, n, dpi, doc) if usar_ocr else None
        if datos is None:
            return PaginaDoc(ruta.name, n, [], "sin_texto")
        cajas, fuente = _cajas_ocr(datos), "ocr"
    else:
        cajas, fuente = _cajas_nativas(page), "texto"
    hoja, titulo = _cajetin(cajas)
    return PaginaDoc(ruta.name, n, cajas, fuente, hoja=hoja, titulo=titulo,
                     es_indice=bool(re.search(r"[IÍ]NDICE", titulo, re.I)))


def leer_indice(paginas: list[PaginaDoc]) -> dict[int, str]:
    """Entradas 'HOJA NN  descripción' de las páginas de índice (varias columnas por renglón)."""
    indice: dict[int, str] = {}
    for pg in paginas:
        # columnas: cada una arranca donde hay un 'HOJA'; el resto de las cajas va a la columna a su izquierda más cercana
        inicios: list[float] = []
        for c in sorted((c for c in pg.cajas if re.match(r"(?i)^HOJA\b", c.texto)), key=lambda c: c.x):
            if not inicios or c.x - inicios[-1] > 150:
                inicios.append(c.x)
        if not inicios:
            continue
        antes = len(indice)
        columnas: list[list] = [[] for _ in inicios]
        for c in pg.cajas:
            k = max((i for i, x0 in enumerate(inicios) if x0 - 5 <= c.x), default=0)
            columnas[k].append(c)
        for cajas in columnas:
            for fila in filas(cajas, tol=6):
                texto = " ".join(c.texto for c in fila)
                m = re.match(r"(?i)^HOJA\s*:?\s*(\d{1,3})\s+(.*)$", texto)
                # 'HOJA: 2 DE 92' es el cajetín de la hoja, no una entrada del índice
                if m and m.group(2).strip() and not re.match(r"(?i)^DE\s+\d+\b", m.group(2)):
                    indice[int(m.group(1))] = " ".join(m.group(2).split())
        if len(indice) == antes:
            # otro formato: encabezado 'HOJA · DETALLE · REVISION' y renglones '01  PORTADA' (el número va solo)
            for cajas in columnas:
                x0 = min(c.x for c in cajas if re.match(r"(?i)^HOJA\b", c.texto))
                for fila in filas([c for c in cajas if c.x >= x0 - 5], tol=6):
                    if re.fullmatch(r"\d{1,3}", fila[0].texto) and len(fila) > 1 and abs(fila[0].x - x0) < 30:
                        resto = " ".join(c.texto for c in fila[1:] if not re.fullmatch(r"[A-Z0-9]|\d+", c.texto))
                        if resto.strip():
                            indice[int(fila[0].texto)] = " ".join(resto.split())
    return indice


def leer_documento(ruta, usar_ocr: bool = True, avance: Optional[Callable[[str, int, int], None]] = None) -> Documento:
    """Todas las páginas del PDF (sin límite), con OCR donde haga falta, y su índice."""
    import pymupdf
    ruta = Path(str(ruta))
    d = Documento(str(ruta), ruta.name)
    try:
        with pymupdf.open(str(ruta)) as doc:
            for n in range(1, len(doc) + 1):
                if avance:
                    avance(ruta.name, n, len(doc))
                pg = pagina_doc(doc, n, ruta, usar_ocr)
                d.paginas.append(pg)
                if pg.fuente == "sin_texto":
                    d.sin_leer.append(n)
    except Exception as e:   # PDF dañado, sin permiso…
        d.error = f"{type(e).__name__}: {e}"
        return d
    d.paginas_indice = [p.n for p in d.paginas if p.es_indice]
    d.indice = leer_indice([p for p in d.paginas if p.es_indice])
    for p in d.paginas:
        if p.hoja.isdigit():
            p.seccion = d.indice.get(int(p.hoja), "")
    return d


def normalizar(texto: str) -> str:
    """Para comparar rótulos entre documentos: sin tildes, mayúsculas, sin signos; en el OCR 0/O y 1/I/L se confunden."""
    t = sin_acentos(texto).upper()
    t = re.sub(r"[^A-Z0-9/ ]+", " ", t)
    return " ".join(t.split())


def clave_ocr(texto: str) -> str:
    """Forma comparable aunque el OCR haya cambiado O por 0 dentro de una palabra (CERRAD0, L0CAL)."""
    return re.sub(r"(?<=[A-Z])0|0(?=[A-Z])", "O", normalizar(texto))
