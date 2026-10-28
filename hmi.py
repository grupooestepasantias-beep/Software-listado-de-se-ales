"""TAG HMI y DESC. HMI (columnas F y G) a partir del texto de la señal."""
from __future__ import annotations

import re
import unicodedata


def sin_acentos(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("ñ", "n").replace("Ñ", "N")


def tag_hmi_desde(texto: str) -> str:
    """Texto -> TAG HMI: sin acentos ni puntos; cada grupo de símbolos/espacios pasa a '_'."""
    return re.sub(r"[^0-9A-Za-z]+", "_", sin_acentos(texto).replace(".", "")).strip("_")


def desc_hmi_desde(prefijo: str, texto: str) -> str:
    """Prefijo del campo + texto sin tildes (ej. '204AP Interruptor 25204 Falta Fuerza Motriz')."""
    return f"{prefijo} {sin_acentos(texto)}".strip()
