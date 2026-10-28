"""TAG HMI y DESC. HMI (columnas F y G) a partir del texto de la señal.

DESC. HMI = prefijo del campo + descripción lo más completa posible (se expanden las abreviaturas del
plano: Secc. -> Seccionador, Ten. -> Tension…), sin tildes.
TAG HMI  = esa misma descripción (sin el prefijo) abreviada para que un humano la lea rápido:
           palabras largas conocidas acortadas (Falta -> F, Auxiliar -> Aux…), unidas con '_'.
El vocabulario sale de plantillas/<id>/lectura_plano.json ("expansiones" y "abreviaturas_tag").
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional


def sin_acentos(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("ñ", "n").replace("Ñ", "N")


def completar(texto: str, vocab: Optional[dict] = None) -> str:
    """Expande las abreviaturas del plano ('Secc. 229SL04 Falta Ten. de Comando' -> 'Seccionador 229SL04
    Falta Tension de Comando'). Primero las frases (F Motriz), después las palabras."""
    t = " ".join(texto.split())
    exp = (vocab or {}).get("expansiones", {})
    for k in sorted(exp, key=len, reverse=True):
        t = re.sub(rf"(?<![A-Za-z0-9]){re.escape(k)}\.?(?![A-Za-z0-9])", exp[k], t, flags=re.I)
    return t


def desc_hmi_desde(prefijo: str, texto: str, vocab: Optional[dict] = None) -> str:
    """Prefijo del campo + descripción completa sin tildes (ej. '204AP Seccionador 229SL04 Falta Tension')."""
    return f"{prefijo} {sin_acentos(completar(texto, vocab))}".strip()


def tag_hmi_desde(texto: str, vocab: Optional[dict] = None) -> str:
    """Descripción abreviada con '_' (ej. 'Seccionador_229SL04_F_Tension_Aux_Fza_Motriz')."""
    abrev = {k.lower(): v for k, v in (vocab or {}).get("abreviaturas_tag", {}).items()}
    palabras = re.findall(r"[0-9A-Za-z]+", sin_acentos(completar(texto, vocab)).replace(".", ""))
    return "_".join(abrev.get(p.lower(), p) for p in palabras)
