"""Utilidades de texto para el motor SCADA."""
from __future__ import annotations

import re
import unicodedata


def norm(t: str) -> str:
    """Minúsculas, sin tildes ni ñ, espacios simples. 'Señalización  OK' -> 'senalizacion ok'."""
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(t.split())


def clave(t: str) -> str:
    """Clave de búsqueda: sin tildes, símbolos ni puntuación y con los números como '#'."""
    t = re.sub(r"\d+", "#", norm(t))
    return " ".join(re.sub(r"[^a-z0-9#/ ]", " ", t).split())


def clave_exacta(t: str) -> str:
    """Igual que clave() pero conserva los números (TC3-01 no es TC3-02, INT48 no es INT110)."""
    t = norm(t)
    return " ".join(re.sub(r"[^a-z0-9#/ ]", " ", t).split())


def separar_prefijo(desc_hmi: str) -> tuple[str, str]:
    """'303LC Seccionador 329SA03 Abierto' -> ('303LC', 'Seccionador 329SA03 Abierto')."""
    pre, _, resto = (desc_hmi or "").strip().partition(" ")
    return pre, resto.strip()


def prefijo_comun(descs: list[str]) -> str:
    """Prefijo más repetido (primera palabra de las DESC. HMI)."""
    cuenta: dict[str, int] = {}
    for d in descs:
        p = (d or "").strip().split(" ")[0]
        if p and p.upper() != "RESERVA":
            cuenta[p] = cuenta.get(p, 0) + 1
    return max(cuenta, key=cuenta.get) if cuenta else ""
