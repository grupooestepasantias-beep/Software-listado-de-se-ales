"""Lectura de las filas del listado y aplicacion de la normalizacion celda por celda sobre una hoja."""
from __future__ import annotations

from dataclasses import dataclass

from .reglas import Reglas
from .texto import normalizar


@dataclass
class Fila:
    fila: int
    nivel: str
    funcion: str
    tag: str          # TAG SCADA (o TAG HMI si no tiene)
    tag_scada: str
    prefijo: str      # primer termino de DESC. HMI (ej. "204te"): identifica el campo
    desc_hmi: str
    desc_scada: str


@dataclass
class Cambio:
    hoja: str
    celda: str
    tag: str
    columna: str
    original: str     # texto de la celda antes de todo
    final: str        # texto de la celda despues de todo
    tipo: str
    regla: str
    antes: str        # texto antes de esta regla
    despues: str      # texto despues de esta regla
    confianza: str
    motivo: str


@dataclass
class Pendiente:
    hoja: str
    celda: str
    tag: str
    texto: str
    tipo: str
    detalle: str
    propuesta: str = ""


def _txt(v) -> str:
    return v.strip() if isinstance(v, str) else ("" if v is None else str(v))


def leer_filas(ws, reglas: Reglas) -> list[Fila]:
    """Filas con datos. NIVEL y FUNCION estan combinadas en el Excel: se arrastran hacia abajo."""
    c = reglas.col
    out: list[Fila] = []
    nivel = funcion = ""
    for r in range(reglas.primera_fila, ws.max_row + 1):
        n, f = ws[f"{c['nivel']}{r}"].value, ws[f"{c['funcion']}{r}"].value
        nivel = _txt(n) or nivel
        funcion = _txt(f) or funcion
        tag_s, tag_h = _txt(ws[f"{c['tag_scada']}{r}"].value), _txt(ws[f"{c['tag_hmi']}{r}"].value)
        g, j = _txt(ws[f"{c['desc_hmi']}{r}"].value), _txt(ws[f"{c['desc_scada']}{r}"].value)
        if not (tag_s or tag_h or g or j):
            continue
        out.append(Fila(r, nivel, funcion, tag_s or tag_h, tag_s, g.split(" ", 1)[0] if g else "", g, j))
    return out


def corregir(ws, reglas: Reglas, filas: list[Fila]) -> tuple[list[Cambio], list[Pendiente], int]:
    """Aplica `normalizar` a las columnas de texto. Devuelve (cambios, pendientes, celdas examinadas)."""
    cambios: list[Cambio] = []
    pendientes: list[Pendiente] = []
    examinadas = 0
    por_fila = {f.fila: f for f in filas}
    for r in range(reglas.primera_fila, ws.max_row + 1):
        f = por_fila.get(r)
        nivel = f.nivel if f else ""
        tag = f.tag if f else ""
        for letra in reglas.columnas_texto:
            celda = ws[f"{letra}{r}"]
            if not isinstance(celda.value, str) or not celda.value.strip():
                continue
            examinadas += 1
            res = normalizar(celda.value, letra, reglas, nivel)
            for p in res.pasos:
                cambios.append(Cambio(ws.title, celda.coordinate, tag, letra, res.original, res.final, p.tipo,
                                      p.regla, p.antes, p.despues, p.confianza, p.motivo))
            for d in res.dudas:
                pendientes.append(Pendiente(ws.title, celda.coordinate, tag, res.final, d.tipo, d.detalle, d.propuesta))
            if res.final != celda.value:
                celda.value = res.final
    return cambios, pendientes, examinadas
