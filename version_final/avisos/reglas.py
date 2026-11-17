"""Reglas de validación. Cada una recibe un `Contexto` (la base + la configuración del perfil) y devuelve avisos.
Ninguna modifica la base."""
from __future__ import annotations

import json
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from base import ProyectoDB, SenalBase

from . import CELESTE, ROSA, Aviso

DIGITALES = ("ALARMAS", "SEÑALIZACION", "COMANDO")


@dataclass
class Contexto:
    db: ProyectoDB
    cfg: dict                              # perfiles/<id>/avisos.json
    avisos_de_lectura: list[str]           # avisos que dejó la lectura del PDF (Libro.avisos)
    pide_conexionado: bool = False         # el formato elegido lleva tablero/bornera/borne (formato completo)

    def reales(self) -> list[SenalBase]:
        """Señales que tienen datos (no las filas libres)."""
        return [b for b in self.db.senales if not b.es_hueco]


def cargar_config(perfil) -> dict:
    ruta = Path(perfil.carpeta) / "avisos.json"
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else {}


def _aviso(gravedad, codigo, mensaje, bs: list[SenalBase]) -> Aviso:
    b = bs[0] if bs else None
    return Aviso(gravedad, codigo, mensaje, tuple(x.id for x in bs), b.campo if b else "", b.item if b else None,
                 b.hoja if b else None, b.archivo if b else "")


def _vacio(v) -> bool:
    return v is None or v == ""


# ---------------------------------------------------------------- celeste: contradice una regla
def tag_scada_duplicado(c: Contexto) -> list[Aviso]:
    """Un TAG SCADA no se repite. Única excepción: una señal y su comando comparten tag (el tag termina en C)."""
    por_tag: dict[str, list[SenalBase]] = defaultdict(list)
    for b in c.reales():
        if not _vacio(b.tag_scada) and b.tag_scada != "N/A":
            por_tag[b.tag_scada].append(b)
    out = []
    for tag, bs in por_tag.items():
        comandos = [b for b in bs if b.funcion == "COMANDO"]
        resto = [b for b in bs if b.funcion != "COMANDO"]
        if len(resto) > 1 or len(comandos) > 1:
            out.append(_aviso(CELESTE, "TAG_SCADA_DUPLICADO", f"El TAG SCADA {tag} está repetido en {len(bs)} señales.", bs))
    return out


def tag_hmi_duplicado(c: Contexto) -> list[Aviso]:
    """Un TAG HMI no se repite (regla del usuario)."""
    por_tag: dict[str, list[SenalBase]] = defaultdict(list)
    for b in c.reales():
        if not _vacio(b.tag_hmi) and b.tag_hmi != "N/A":
            por_tag[b.tag_hmi].append(b)
    return [_aviso(CELESTE, "TAG_HMI_DUPLICADO", f"El TAG HMI «{tag}» está repetido en {len(bs)} señales.", bs)
            for tag, bs in por_tag.items() if len(bs) > 1]


def offset_repetido(c: Contexto) -> list[Aviso]:
    """Un OFFSET puede repetirse entre una señal y su comando y entre una digital y una medición (contadores aparte).
    Dos digitales distintas, o dos mediciones, con el mismo offset: contradice la regla. Las filas libres no cuentan."""
    out = []
    for nombre, filtro in (("digitales", lambda b: b.funcion in ("ALARMAS", "SEÑALIZACION", "RESERVA")),
                           ("mediciones", lambda b: b.funcion == "MEDICION")):
        por_off: dict[int, list[SenalBase]] = defaultdict(list)
        for b in c.reales():
            if filtro(b) and b.offset is not None:
                por_off[b.offset].append(b)
        for off, bs in por_off.items():
            if len(bs) > 1:
                out.append(_aviso(CELESTE, "OFFSET_REPETIDO",
                                  f"El OFFSET {off} está repetido en {len(bs)} {nombre} distintas.", bs))
    return out


def item_repetido(c: Contexto) -> list[Aviso]:
    por_item: dict[int, list[SenalBase]] = defaultdict(list)
    for b in c.reales():
        if b.item is not None:
            por_item[b.item].append(b)
    return [_aviso(CELESTE, "ITEM_REPETIDO", f"El ITEM {i} está repetido en {len(bs)} filas.", bs)
            for i, bs in por_item.items() if len(bs) > 1]


def tag_fuera_de_formato(c: Contexto) -> list[Aviso]:
    """El TAG SCADA sigue el formato de las Reglas: {nivel+campo}.{variable}{bits}[C] o {nivel+campo}.{NN}{código}."""
    esp = "|".join(map(re.escape, c.cfg.get("campos_especiales", [])))
    cods = "|".join(sorted(map(re.escape, c.cfg.get("codigos_medicion", [])), key=len, reverse=True))
    prefijo = rf"(?:\d{{3}}|{esp})" if esp else r"\d{3}"
    digital = re.compile(rf"^{prefijo}\.\d{{2}}[12]C?$")
    medicion = re.compile(rf"^{prefijo}\.\d{{2}}(?:{cods})$") if cods else None
    out = []
    for b in c.reales():
        t = b.tag_scada
        if _vacio(t) or t == "N/A" or b.es_reserva:
            continue
        if b.funcion == "MEDICION":
            ok = bool(medicion and medicion.match(t))
        else:
            ok = bool(digital.match(t)) and (b.funcion != "COMANDO" or t.endswith("C"))
        if not ok:
            out.append(_aviso(CELESTE, "TAG_FUERA_DE_FORMATO", f"El TAG SCADA «{t}» no sigue el formato de las Reglas.", [b]))
    return out


def desc_scada_larga(c: Contexto) -> list[Aviso]:
    largo = c.cfg.get("largo_desc_scada", 20)
    return [_aviso(CELESTE, "DESC_SCADA_LARGA", f"La DESC. SCADA «{b.desc_scada}» tiene {len(b.desc_scada)} caracteres "
                   f"y el máximo es {largo}.", [b])
            for b in c.reales() if isinstance(b.desc_scada, str) and len(b.desc_scada) > largo]


def _kv(texto) -> float | None:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*kv", str(texto or ""), re.I)
    return float(m.group(1).replace(",", ".")) if m else None


def controlador_de_otra_tension(c: Contexto) -> list[Aviso]:
    """Un controlador que nombra una tensión (ej. SEL-2241-33kV) debe ser la del nivel de la señal."""
    out = []
    for b in c.reales():
        if b.es_reserva or _vacio(b.controlador):
            continue
        k_ctl, k_niv = _kv(b.controlador), _kv(b.nivel)
        if k_ctl is not None and k_niv is not None and abs(k_ctl - k_niv) > 1e-9:
            out.append(_aviso(CELESTE, "CONTROLADOR_OTRA_TENSION",
                              f"El controlador «{b.controlador}» es de otra tensión que el nivel {b.nivel}.", [b]))
    return out


def escala_invertida(c: Contexto) -> list[Aviso]:
    out = []
    for b in c.reales():
        if b.funcion != "MEDICION":
            continue
        for lo, hi, nombre in ((b.min_raw, b.max_raw, "RAW"), (b.min_eu, b.max_eu, "EU")):
            try:
                if not _vacio(lo) and not _vacio(hi) and float(lo) >= float(hi):
                    out.append(_aviso(CELESTE, "ESCALA_INVERTIDA", f"En «{b.tag_scada}» el MIN {nombre} ({lo}) no es menor "
                                      f"que el MAX {nombre} ({hi}).", [b]))
            except (TypeError, ValueError):
                out.append(_aviso(CELESTE, "ESCALA_NO_NUMERICA", f"En «{b.tag_scada}» la escala {nombre} no es un número.", [b]))
    return out


# ---------------------------------------------------------------- rosa: falta información / revisar
def desc_scada_sin_resolver(c: Contexto) -> list[Aviso]:
    return [_aviso(ROSA, "DESC_SCADA_SIN_RESOLVER", f"La DESC. SCADA «{b.desc_scada}» no se pudo abreviar a 20 caracteres "
                   "con el vocabulario conocido: revisala.", [b]) for b in c.reales() if b.sin_resolver]


def desc_scada_repetida(c: Contexto) -> list[Aviso]:
    """Dos señales distintas con la misma DESC. SCADA (el Excel de EPEN resalta los duplicados). El comando repite la de
    su señal: no cuenta."""
    por: dict[str, list[SenalBase]] = defaultdict(list)
    for b in c.reales():
        if b.es_reserva or b.segunda_fila or b.funcion == "COMANDO" or _vacio(b.desc_scada):
            continue
        por[b.desc_scada].append(b)
    return [_aviso(ROSA, "DESC_SCADA_REPETIDA", f"La DESC. SCADA «{d}» se repite en {len(bs)} señales.", bs)
            for d, bs in por.items() if len(bs) > 1]


def falta_informacion(c: Contexto) -> list[Aviso]:
    """Datos obligatorios que faltan en una señal (las reservas y la 2.ª fila de un doble bit llevan menos)."""
    out = []
    for b in c.reales():
        if b.es_reserva or b.segunda_fila:
            continue
        falta = [n for n in ("controlador", "tag_hmi", "desc_hmi", "tag_scada", "desc_scada", "offset") if _vacio(getattr(b, n))]
        if b.funcion == "MEDICION":
            falta += [n for n in ("min_raw", "max_raw", "min_eu", "max_eu", "unidad") if _vacio(getattr(b, n))]
        elif b.funcion in DIGITALES:
            falta += [n for n in ("s0", "s1") if _vacio(getattr(b, n))]
        if falta:
            out.append(_aviso(ROSA, "FALTA_INFORMACION", "Falta " + ", ".join(falta) + ".", [b]))
    return out


def tag_y_descripcion_hmi(c: Contexto) -> list[Aviso]:
    """El TAG HMI y la DESC. HMI nombran el mismo equipo (el código de equipo de uno debe estar en el otro)."""
    cod = re.compile(r"\b\d{5}\b|\b\d{3}S[A-Z]\d{2}\b")
    out = []
    for b in c.reales():
        if b.es_reserva or _vacio(b.tag_hmi) or _vacio(b.desc_hmi):
            continue
        a, d = set(cod.findall(b.tag_hmi.replace("_", " "))), set(cod.findall(b.desc_hmi))
        if a != d:
            out.append(_aviso(ROSA, "TAG_Y_DESC_HMI", f"El TAG HMI «{b.tag_hmi}» y la DESC. HMI «{b.desc_hmi}» no nombran "
                              "los mismos equipos.", [b]))
    return out


def conexionado_incompleto(c: Contexto) -> list[Aviso]:
    """Solo si el formato elegido lleva conexionado: señales que no tienen tablero, bornera y borne. Se resume en un
    único aviso (hoy esos datos todavía no se leen del PDF)."""
    if not c.pide_conexionado:
        return []
    sin = [b for b in c.reales() if not b.es_reserva and not b.segunda_fila and b.funcion in DIGITALES
           and any(_vacio(getattr(b, n)) for n in ("tablero", "bornera_tablero", "borne_tablero"))]
    if not sin:
        return []
    return [Aviso(ROSA, "CONEXIONADO_INCOMPLETO",
                  f"{len(sin)} señales no tienen tablero, bornera o borne de tablero (el formato completo los pide).",
                  tuple(b.id for b in sin), sin[0].campo, sin[0].item, sin[0].hoja, sin[0].archivo)]


def avisos_de_lectura(c: Contexto) -> list[Aviso]:
    """Lo que no se pudo interpretar al leer el PDF (campos deducidos, comandos sin señal…)."""
    return [Aviso(ROSA, "LECTURA", m) for m in c.avisos_de_lectura]


REGLAS = [tag_scada_duplicado, tag_hmi_duplicado, offset_repetido, item_repetido, tag_fuera_de_formato, desc_scada_larga,
          controlador_de_otra_tension, escala_invertida,
          desc_scada_sin_resolver, desc_scada_repetida, falta_informacion, tag_y_descripcion_hmi, conexionado_incompleto,
          avisos_de_lectura]


def validar(db: ProyectoDB, perfil=None, cfg: dict | None = None, avisos_de_lectura: list[str] | None = None,
            pide_conexionado: bool = False) -> list[Aviso]:
    """Corre todas las reglas sobre la base y devuelve los avisos (celestes primero). No modifica `db`."""
    cfg = cfg if cfg is not None else (cargar_config(perfil) if perfil is not None else {})
    ctx = Contexto(db, cfg, list(avisos_de_lectura or []), pide_conexionado)
    avisos: list[Aviso] = []
    for regla in REGLAS:
        avisos += regla(ctx)
    return sorted(avisos, key=lambda a: (a.gravedad != CELESTE, a.codigo, a.item if a.item is not None else 10 ** 9))
