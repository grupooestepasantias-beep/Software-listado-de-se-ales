"""Esqueleto de tags: construir, parsear y validar TAG SCADA y DESC. SCADA según el perfil.

Patrón EPEN confirmado contra el ejemplo ETAP (484 de 539 tags):
    {nivel}{campo}.{variable:02d}{bits}{C}      alarmas / señalización / comando   (303.632C)
    {nivel}{campo}.{variable:02d}{medicion}     mediciones                          (303.01AU)
    {campo_especial}.{variable:02d}{bits}...    TP1, TP2, RN1, RN2, SAA, SAC        (TP1.431)
Los tags fuera de patrón (SACC.01V48, UTR02T_132, 'N/A' en reservas) no se generan: el validador
los reporta como no estándar hasta que el usuario defina su regla (ver PREGUNTAS.md).
"""
from __future__ import annotations

import re
from typing import Optional

from modelo import Funcion, Senal
from perfiles import Perfil

NO_APLICA = "N/A"


def _codigos_medicion(perfil: Perfil) -> list[str]:
    codigos = {s["codigo"] for s in perfil.sufijos_medicion["sufijos"]}
    return sorted(codigos, key=lambda c: (-len(c), c))  # los largos primero (AFP antes que AF)


def _regex(perfil: Perfil) -> re.Pattern:
    cfg = perfil.datos["tag"]
    dv = cfg["digitos_variable"]
    bits = "".join(str(b) for b in cfg["bits_validos"])
    especiales = "|".join(re.escape(c) for c in sorted(cfg["campos_especiales"], key=lambda c: (-len(c), c)))
    med = "|".join(re.escape(c) for c in _codigos_medicion(perfil))
    return re.compile(
        rf"^(?:(?P<nivel>\d)(?P<campo>\d{{2}})|(?P<especial>{especiales}))"
        rf"\.(?P<variable>\d{{{dv}}})"
        rf"(?:(?P<bits>[{bits}])(?P<comando>{re.escape(cfg['sufijo_comando'])})?|(?P<medicion>{med}))$"
    )


def construir_tag(perfil: Perfil, *, campo: str, variable: int, nivel: Optional[str] = None,
                  bits: Optional[int] = None, comando: bool = False,
                  medicion: Optional[str] = None) -> str:
    """Arma un TAG SCADA. `nivel` es el dígito del nivel de tensión (obligatorio salvo campos especiales)."""
    cfg = perfil.datos["tag"]
    dv = cfg["digitos_variable"]
    if not 0 <= variable < 10 ** dv:
        raise ValueError(f"variable fuera de rango (0-{10 ** dv - 1}): {variable}")

    if campo in cfg["campos_especiales"]:
        base = campo if cfg.get("campos_especiales_sin_nivel", True) else f"{nivel}{campo}"
    else:
        if not (campo.isdigit() and len(campo) == 2):
            raise ValueError(f"campo debe ser de 2 dígitos o uno especial {list(cfg['campos_especiales'])}: '{campo}'")
        if not (nivel and nivel.isdigit() and len(nivel) == 1):
            raise ValueError(f"nivel debe ser un dígito: '{nivel}'")
        base = f"{nivel}{campo}"

    if medicion is not None:
        if bits is not None or comando:
            raise ValueError("una medición no lleva bits ni comando")
        if medicion not in _codigos_medicion(perfil):
            raise ValueError(f"código de medición desconocido: '{medicion}'")
        return f"{base}.{variable:0{dv}d}{medicion}"

    if bits not in cfg["bits_validos"]:
        raise ValueError(f"bits debe ser uno de {cfg['bits_validos']}: {bits}")
    return f"{base}.{variable:0{dv}d}{bits}{cfg['sufijo_comando'] if comando else ''}"


def parsear_tag(perfil: Perfil, tag: str) -> Optional[dict]:
    """Descompone un tag estándar; devuelve None si no respeta el patrón del perfil."""
    m = _regex(perfil).match((tag or "").strip())
    if not m:
        return None
    g = m.groupdict()
    return {
        "nivel": g["nivel"],
        "campo": g["campo"] or g["especial"],
        "variable": int(g["variable"]),
        "bits": int(g["bits"]) if g["bits"] else None,
        "comando": bool(g["comando"]),
        "medicion": g["medicion"],
    }


def proxima_variable(perfil: Perfil, usadas: set[int], desde: int = 0) -> int:
    """Primer número de variable libre >= `desde` dentro de un campo (00-99)."""
    tope = 10 ** perfil.datos["tag"]["digitos_variable"]
    for v in range(desde, tope):
        if v not in usadas:
            return v
    raise ValueError(f"el campo no tiene más variables libres desde {desde}")


def construir_desc_scada(perfil: Perfil, prefijo: str, texto: str) -> str:
    """Prefijo del campo + descripción (separados por espacio). Falla si supera el largo del perfil."""
    desc = f"{prefijo} {texto}".strip()
    maximo = perfil.largo_max("desc_scada")
    if maximo is not None and len(desc) > maximo:
        raise ValueError(f"DESC. SCADA de {len(desc)} caracteres (máx. {maximo}): '{desc}'")
    return desc


def validar_tag(perfil: Perfil, senal: Senal) -> list[str]:
    """Problemas del tag de una señal según su función. Lista vacía si está bien."""
    if senal.funcion == Funcion.RESERVA:
        return []
    tag = (senal.tag_scada or "").strip()
    if not tag:
        return ["tag SCADA vacío"]
    p = parsear_tag(perfil, tag)
    if p is None:
        return [f"tag no estándar '{tag}' (no respeta el patrón del perfil {perfil.id})"]
    f, problemas = senal.funcion, []
    if f == Funcion.MEDICION:
        if not p["medicion"]:
            problemas.append(f"'{tag}': una medición debe terminar en un código de medición")
    else:
        if p["medicion"]:
            problemas.append(f"'{tag}': {f.value} no puede llevar código de medición")
        if f == Funcion.COMANDO and not p["comando"]:
            problemas.append(f"'{tag}': un comando debe terminar en C")
        if f == Funcion.ALARMAS and p["comando"]:
            problemas.append(f"'{tag}': una alarma no lleva C")
        if f == Funcion.ALARMAS and p["bits"] == 2:
            problemas.append(f"'{tag}': una alarma es de 1 bit")
    maximo = perfil.largo_max("desc_scada")
    if maximo is not None and len(senal.desc_scada) > maximo:
        problemas.append(f"DESC. SCADA de {len(senal.desc_scada)} caracteres (máx. {maximo})")
    return problemas
