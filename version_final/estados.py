"""Estados de señales digitales (K-N) y rangos/unidad de mediciones (K-O). Valores por defecto en estados.json."""
from __future__ import annotations

import json
import re
import unicodedata
from pathlib import Path

import estilo
import numeracion as num

DATOS = json.loads(Path(__file__).with_name("estados.json").read_text(encoding="utf-8"))
NA = "N/A"


def _plano(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def tipo_estado(s: num.Senal) -> str:
    """Clave de DATOS['digitales'] para una señal."""
    if s.funcion == num.ALARMAS:
        return "alarma"
    if not s.doble:
        return "simple"
    t = _plano(" ".join(s.pares))
    for clave, pistas in (("abierto/cerrado", ("abierto", "apertura", "abrir")),
                          ("local/remoto", ("local",)),
                          ("distancia/tele", ("distancia", " en d", "tele"))):
        if any(p in t for p in pistas):
            return clave
    return "doble"


def _alarma_usre(texto: str) -> str:
    """Estado activo de una alarma: FALTA (falta de tensión/alimentación), FALLA o ACTUO."""
    t = _plano(texto)
    if re.search(r"\bfalta\b|\bf/u\b|\bsin tension\b", t):
        return "FALTA"
    if re.search(r"\bfalla\b|\bfalla\w*\b", t):
        return "FALLA"
    return "ACTUO"


def _estados_usre(s: num.Senal, comando: tuple[str, ...] | None = None) -> list:
    """Estados del estilo USRE: salen del nombre del propio estado (ver estilo.py)."""
    if comando is not None and len(comando) == 2:                       # comando de dos bornes: ABRIR / CERRAR
        _, e0, e1 = estilo.partir_par(*comando)
        return [estilo.nombre_estado(e0), estilo.nombre_estado(e1), NA, NA]
    if s.funcion == num.ALARMAS and len(s.pares) < 2:
        return ["NORMAL", _alarma_usre(s.texto), NA, NA]
    if len(s.pares) == 2:
        _, e0, e1 = estilo.partir_par(*s.pares)
        n0, n1 = estilo.nombre_estado(e0), estilo.nombre_estado(e1)
        return ["err_0", n0, n1, "err_1"] if s.doble else [n0, n1, NA, NA]
    return ["NORMAL", "OPERO", NA, NA]


def estados(s: num.Senal, elegidos: dict[str, list[str]] | None = None, modo: str = estilo.ETAP,
            comando: tuple[str, ...] | None = None) -> list:
    """[K, L, M, N, O] de una señal digital: S0, S1, S2, S3 y unidad (N/A). `modo`: estilo del listado (ETAP o USRE);
    `comando`: los dos rótulos del comando cuando se pide la fila del COMANDO."""
    if s.reserva:
        return DATOS["reserva"] + [NA]
    clave = tipo_estado(s)
    if elegidos and clave in elegidos:                                   # lo que eligió el usuario manda
        return list(elegidos[clave]) + [NA]
    if modo == estilo.USRE:
        return _estados_usre(s, comando) + [NA]
    return list(DATOS["digitales"][clave]) + [NA]


def rango(indice: int, elegidos: dict[int, dict] | None = None) -> list:
    """[MIN RAW, MAX RAW, MIN EU, MAX EU, unidad] de la medición número `indice` del juego."""
    r = (elegidos or {}).get(indice) or DATOS["medicion_defecto"]
    unidad = r.get("unidad") or DATOS["unidades"][indice]
    return [r["min_raw"], r["max_raw"], r["min_eu"], r["max_eu"], unidad]


def numero(texto: str):
    """'327,67' -> 327.67; '32767' -> 32767."""
    t = texto.strip().replace(",", ".")
    f = float(t)
    return int(f) if f == int(f) else f
