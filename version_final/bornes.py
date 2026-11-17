"""Bornera y borne de tablero de cada señal, leídos de los planos de cableado dibujados (sin texto) con OCR.

Los PDF funcionales traen, hacia el final, una hoja por bornera con su tabla de bornes («X1.1 - DISTRIBUCIÓN DE 110 Vcc»):
cada fila dice el número de borne, el dispositivo y la descripción de la señal que llega a ese borne. Se leen así:
  1. `hojas_de_tablas`: entre las hojas sin texto, se reconocen las de tablas (por su encabezado «DISPOSITIVO … BORNE»).
  2. `leer_tabla`: de cada hoja, por mitades (cada hoja trae dos tablas), la bornera (título), el borne y la descripción.
  3. `asignar`: cada etiqueta de señal del plano (ej. «Interruptor 252 / 01 Resorte descargado») se empareja con la fila cuya
     descripción se le parece («Int. 252 / 01 Resorte Descarg.»): se comparan las palabras (con las abreviaturas del plano) y
     el código de equipo. Si hay dudas (varias filas igual de buenas o ninguna), la señal queda sin bornera: no se adivina.
La lectura es solo para informar: lo que no se puede leer queda vacío y se avisa.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

import ocr

# palabras del plano -> palabra completa, para poder comparar «Int.» con «Interruptor», «Descarg.» con «descargado»…
ABREVIATURAS = {
    "int": "interruptor", "inte": "interruptor", "interr": "interruptor", "secciona": "seccionador", "seccion": "seccionador",
    "secc": "seccionador", "termomag": "termomagnetica", "termo": "termomagnetica", "descarg": "descargado",
    "descar": "descargado", "abiert": "abierto", "tens": "tension", "imag": "imagen", "ventila": "ventilacion",
    "venti": "ventilacion", "transf": "transformador", "tpo1": "tp01", "prot": "proteccion", "ppal": "principal",
}
PALABRAS_VACIAS = {"de", "del", "la", "el", "los", "las", "en", "y", "a", "por", "con", "al", "un", "una"}
UMBRAL = 0.7                                   # parecido mínimo entre la etiqueta y la descripción de la fila
MARGEN = 0.12                                  # cuánto mejor tiene que ser la mejor fila que la siguiente (si no, es dudosa)


@dataclass(frozen=True)
class FilaBorne:
    bornera: str          # "X1.1"
    borne: int            # 71
    descripcion: str      # "Int. 252 / 01 Resorte Descarg."
    hoja: int             # hoja del PDF
    bobina: str = ""      # terminal de la bobina del relé al que llega ("A1" señal / "A2" común), si la fila lo trae


# ------------------------------------------------------------------ leer las hojas de tablas
def es_hoja_de_tabla(cajas: list[dict]) -> bool:
    textos = [c["texto"].upper() for c in cajas]
    return any("DISPOSITIVO" in t for t in textos) and any(t.strip() == "BORNE" for t in textos)


def hojas_de_tablas(ruta, avance: Optional[Callable[[int, int], None]] = None) -> list[int]:
    """Hojas del PDF que son tablas de bornera. Solo se miran las que no tienen texto, y de cada una solo la franja del
    encabezado de la mitad izquierda (rápido; el OCR no lee bien una franja muy ancha y angosta). [] si no hay OCR."""
    import pymupdf
    if not ocr.disponible():
        return []
    ruta = Path(ruta)
    candidatas, salida = [], []
    with pymupdf.open(str(ruta)) as doc:
        candidatas = [i + 1 for i, pg in enumerate(doc) if ocr.necesita_ocr(pg)]
        for k, n in enumerate(candidatas, 1):
            if avance:
                avance(k, len(candidatas))
            d = ocr.leer_hoja(ruta, n, dpi=150, doc=doc, recorte=(0.0, 0.04, 0.5, 0.2))
            if d and es_hoja_de_tabla(d["cajas"]):
                salida.append(n)
    return salida


def leer_tabla(d: dict) -> list[FilaBorne]:
    """Filas (bornera, borne, descripción) de una hoja ya leída con OCR (`ocr.leer_hoja`)."""
    cj, ancho = d["cajas"], d["ancho"]
    hdr = [c for c in cj if c["texto"].strip() == "BORNE"]
    desc = [c for c in cj if c["texto"].strip().upper().startswith("DESCRIPCI")]
    if not hdr or not desc:
        return []
    y_hdr = min(c["y"] for c in hdr)
    hdr = sorted((c for c in hdr if abs(c["y"] - y_hdr) < 25), key=lambda c: c["x"])
    desc = [c for c in desc if abs(c["y"] - y_hdr) < 25]
    cy = lambda c: c["y"] + c["h"] / 2  # noqa: E731
    titulos = [c for c in cj if 100 < c["y"] < y_hdr - 15 and c["w"] > 200]
    salida: list[FilaBorne] = []
    for i, h in enumerate(hdr):
        xd = min(desc, key=lambda c: abs(c["x"] - h["x"] - 800))["x"]
        ini = h["x"] - 340                                     # cada mitad empieza en su columna «TIPO DE CABLE A»
        fin = ancho if i == len(hdr) - 1 else hdr[i + 1]["x"] - 340
        titulo = next((t["texto"] for t in sorted(titulos, key=lambda t: t["x"]) if ini <= t["x"] < fin), "")
        m = re.match(r"\s*-?\s*([A-Z]{1,3}\d*(?:\.\d+)?)", titulo.upper())      # «X1.1 - …», «XDO.1 - …», «XT.1ALARMAS…»
        bornera = m.group(1) if m else ""
        nums = sorted((c for c in cj if abs(c["x"] - h["x"]) < 45 and c["y"] > y_hdr + 20
                       and re.fullmatch(r"\d{1,3}", c["texto"].strip())), key=cy)
        textos = [c for c in cj if xd - 40 <= c["x"] < min(xd + 520, fin) and c["y"] > y_hdr + 20
                  and not re.fullmatch(r"[\d.,]+\s?mm2", c["texto"].strip(), re.I) and not c["texto"].strip().startswith("-")
                  and c["texto"].strip().upper() not in ("SEPARADOR", "EXTREMO", "TAPA")]
        # la descripción ocupa dos renglones centrados en el borne: cada renglón es del borne con el centro más cercano
        lineas = {id(n): [] for n in nums}
        for t in textos:
            if not nums:
                break
            n = min(nums, key=lambda n: abs(cy(n) - cy(t)))
            if abs(cy(n) - cy(t)) <= 30:
                lineas[id(n)].append(t)
        for n in nums:
            ls = sorted(lineas[id(n)], key=lambda t: (round(cy(t) / 10), t["x"]))
            bob = next((t["texto"].strip().upper() for t in cj if abs(t["x"] - h["x"] - 505) < 40 and abs(cy(t) - cy(n)) < 14
                        and re.fullmatch(r"A[12]", t["texto"].strip().upper())), "")
            salida.append(FilaBorne(bornera, int(n["texto"]), " ".join(t["texto"].strip() for t in ls), d["hoja"], bob))
    return salida


def leer_tablas(ruta, hojas: list[int], avance: Optional[Callable[[int, int], None]] = None) -> list[FilaBorne]:
    import pymupdf
    filas: list[FilaBorne] = []
    ruta = Path(ruta)
    with pymupdf.open(str(ruta)) as doc:
        for k, n in enumerate(hojas, 1):
            if avance:
                avance(k, len(hojas))
            d = ocr.leer_hoja(ruta, n, dpi=200, doc=doc)
            if d:
                filas += leer_tabla(d)
    return filas


# ------------------------------------------------------------------ emparejar etiquetas y filas
def _plano(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def palabras(texto: str) -> list[str]:
    """Palabras comparables de una etiqueta: sin tildes, con el código de equipo unido (252 / 01 -> 25201) y las
    abreviaturas del plano expandidas."""
    t = _plano(texto)
    t = re.sub(r"(\d{3}[a-z]{0,2})\s*/\s*(\d{2})\b", r"\1\2", t)
    out = []
    for w in re.findall(r"[a-z0-9]+", t):
        w = ABREVIATURAS.get(w, w)
        if w not in PALABRAS_VACIAS:
            out.append(w)
    return out


def _igual(a: str, b: str) -> bool:
    if a == b:
        return True
    return min(len(a), len(b)) >= 4 and (a.startswith(b) or b.startswith(a))


def _codigo(ws: list[str]) -> set[str]:
    return {w for w in ws if re.fullmatch(r"\d{4,5}[a-z]{0,2}|\d{3}[a-z]{1,2}\d{2}", w)}


def parecido(etiqueta: str, descripcion: str) -> float:
    a, b = palabras(etiqueta), palabras(descripcion)
    if not a or not b:
        return 0.0
    ca, cb = _codigo(a), _codigo(b)
    if ca and cb and ca != cb:                                 # otro equipo: no es la misma señal
        return 0.0
    acierta = sum(1 for w in b if any(_igual(w, x) for x in a))
    return acierta / max(len(a), len(b))


@dataclass(frozen=True)
class Hallazgo:
    bornera: str
    borne: int
    alternativas: tuple = ()          # otras filas igual de parecidas ((bornera, borne), ...): si hay, conviene revisar

    @property
    def dudoso(self) -> bool:
        return bool(self.alternativas)


def buscar(etiqueta: str, filas: list[FilaBorne]) -> Optional[Hallazgo]:
    """La fila de bornes que describe a esta etiqueta, o None si no hay ninguna parecida. Si varias filas son igual de
    buenas, se toma la primera del plano y las otras quedan como `alternativas` (la señal queda «dudosa»)."""
    if not etiqueta or "reserva" in _plano(etiqueta):
        return None
    puntajes = [(parecido(etiqueta, f.descripcion), i, f) for i, f in enumerate(filas)
                if f.descripcion and "reserva" not in _plano(f.descripcion)]
    if not puntajes:
        return None
    mejor = max(p[0] for p in puntajes)
    if mejor < UMBRAL:
        return None
    empatadas = [p for p in puntajes if mejor - p[0] < 0.02]
    # una señal de campo llega a la bobina de un relé por su terminal A1; A2 es el común (alimentación): vale la A1
    empatadas = [p for p in empatadas if p[2].bobina == "A1"] or empatadas
    elegida = min(empatadas, key=lambda p: p[1])[2]
    otras = tuple(sorted({(p[2].bornera, p[2].borne) for p in empatadas} - {(elegida.bornera, elegida.borne)}))
    return Hallazgo(elegida.bornera, elegida.borne, otras)


def asignar(etiquetas: list[str], filas: list[FilaBorne]) -> dict[str, Hallazgo]:
    """{etiqueta: Hallazgo} de las etiquetas para las que hay una fila de bornes."""
    salida: dict[str, Hallazgo] = {}
    for e in etiquetas:
        if e not in salida and (h := buscar(e, filas)):
            salida[e] = h
    return salida


def a_dicts(filas: list[FilaBorne]) -> list[dict]:
    return [{"bornera": f.bornera, "borne": f.borne, "descripcion": f.descripcion, "hoja": f.hoja, "bobina": f.bobina}
            for f in filas]


def de_dicts(datos: list[dict]) -> list[FilaBorne]:
    return [FilaBorne(d["bornera"], int(d["borne"]), d["descripcion"], int(d["hoja"]), d.get("bobina", "")) for d in datos]


def leer_bornes(ruta, avance: Optional[Callable[[str, int, int], None]] = None) -> list[FilaBorne]:
    """Todas las filas de las tablas de bornera de un PDF ([] si no tiene o no hay OCR). `avance(etapa, n, total)` informa
    'buscando' (hojas miradas) y 'leyendo' (tablas leídas)."""
    hojas = hojas_de_tablas(ruta, (lambda n, t: avance("buscando", n, t)) if avance else None)
    return leer_tablas(ruta, hojas, (lambda n, t: avance("leyendo", n, t)) if avance else None)
