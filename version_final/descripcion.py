"""DESC. SCADA (columna J): en mayúsculas, máximo 20 caracteres, a partir del texto del PDF y de abreviaturas.json.

Resultado: (texto, resuelta). `resuelta=False` -> el texto no entró en 20 caracteres con las abreviaturas conocidas y se
acortó a la fuerza: la fila se marca en amarillo para que la revise quien arma el listado.
"""
from __future__ import annotations

import json
import re
import unicodedata
from functools import lru_cache
from pathlib import Path

MAXIMO = 20


@lru_cache(maxsize=1)
def vocabulario() -> dict:
    return json.loads((Path(__file__).with_name("abreviaturas.json")).read_text(encoding="utf-8"))


def _sin_acentos(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _limpiar(texto: str) -> str:
    t = _sin_acentos(texto).replace("�", "").lower()
    t = re.sub(r"\bcampo\s*\d+\b", " ", t)                         # el campo ya va en el prefijo
    t = re.sub(r"\b\d+(?:[.,]\d+)?\s*kv\b", " ", t)                 # nivel de tensión
    t = re.sub(r"\b\d{4,5}\b", " ", t)                              # número de equipo (25204)
    t = re.sub(r"\b\d{2,3}[a-z]{0,2}/\d{2}\b", " ", t)              # código de equipo (152/01, 189t/03)
    t = re.sub(r"\.", " ", t).replace("-", " ")
    return re.sub(r"\s+", " ", t).strip()


def _equipo(m: re.Match, barras: dict) -> str:
    return barras.get(m.group(1), m.group(1)).upper()


def abreviar(texto: str) -> str:
    v = vocabulario()
    t = _limpiar(texto)
    # Seccionador 229SB04 -> "seccionador BB": el código SA/SB/SL dice qué seccionador es.
    t = re.sub(r"\b\d{3}(s[abl])\d{2}\b", lambda m: "@" + _equipo(m, v["barras"]), t)
    for frase in sorted(v["frases"], key=len, reverse=True):
        t = re.sub(rf"(?<![\w/]){re.escape(frase)}(?![\w/])", "#" + v["frases"][frase].replace(" ", "_") + "#", t)
    salida = []
    for palabra in t.split():
        if palabra.startswith("#"):
            salida.append(palabra.strip("#").replace("_", " "))
        elif palabra.startswith("@"):
            salida.append(palabra[1:])
        elif palabra in v["ignorar"]:
            continue
        else:
            salida.append(v["palabras"].get(palabra, palabra.upper() if len(palabra) <= 4 or re.search(r"\d", palabra) else palabra))
    return re.sub(r"F/ (?=\S)", "F/", " ".join(s for s in salida if s)).strip()


def _sin_vocales(palabra: str) -> str:
    if not palabra.isalpha() or len(palabra) < 6:  # códigos (F/Vca, 2TV04) no se tocan
        return palabra
    return palabra[0] + re.sub(r"[aeiouAEIOU]", "", palabra[1:])


def descripcion_scada(prefijo: str, texto: str) -> tuple[str, bool]:
    """Prefijo + texto abreviado, en MAYÚSCULAS y de máximo 20 caracteres."""
    cuerpo = abreviar(texto)
    completo = f"{prefijo} {cuerpo}".strip().upper()
    if len(completo) <= MAXIMO:
        return completo, True
    comprimido = " ".join(_sin_vocales(p) for p in cuerpo.split())
    completo = f"{prefijo} {comprimido}".strip().upper()
    if len(completo) <= MAXIMO:
        return completo, False
    return completo[:MAXIMO].rstrip(), False


def descripcion_medicion(prefijo: str, indice: int) -> tuple[str, bool]:
    return f"{prefijo} {vocabulario()['mediciones'][indice]}".upper()[:MAXIMO], True
