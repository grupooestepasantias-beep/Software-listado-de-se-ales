"""Encabezado y pie de pagina de la hoja del listado, como el ETAP (obra + titulo arriba; numero de documento
y revision a la izquierda; numeracion de hojas contando la caratula abajo). Solo completa lo que esta vacio."""
from __future__ import annotations

from dataclasses import dataclass

from .reglas import Reglas


@dataclass
class DatosPortada:
    obra: str = ""
    titulo: str = ""
    documento: str = ""
    revision: str = ""


def _v(ws, celda) -> str:
    v = ws[celda].value
    return "" if v is None else str(v).strip()


def leer_portada(ws_caratula, campos: dict) -> DatosPortada:
    """`campos` = plantilla['caratula_campos'] (celdas de cada dato en la caratula)."""
    s = campos["simples"]
    documento = _v(ws_caratula, s["archivo_magnetico"]["celda"])
    if not documento:  # el numero de documento puede estar en una celda por caracter
        letras = "".join(_v(ws_caratula, c) for c in campos["documento"]["celdas"])
        documento = "" if letras.startswith("=") else letras
    return DatosPortada(_v(ws_caratula, s["obra"]["celda"]), _v(ws_caratula, s["titulo"]["celda"]), documento,
                        _v(ws_caratula, s["revision"]["celda"]))


def completar(ws_listado, portada: DatosPortada, reglas: Reglas) -> list[str]:
    """Devuelve la lista de lo que se completo (para el registro de cambios)."""
    hecho = []
    if not reglas.datos.get("presentacion", {}).get("encabezado_pie", False):
        return hecho
    h, p = ws_listado.oddHeader, ws_listado.oddFooter
    if not (h.center.text or h.left.text or h.right.text) and (portada.obra or portada.titulo):
        h.center.text = "\n".join(x for x in (portada.obra, portada.titulo) if x)
        hecho.append("encabezado")
    if not (p.left.text or p.center.text or p.right.text) and portada.documento:
        p.left.text = portada.documento + (f"-r{portada.revision}" if portada.revision else "")
        p.center.text = reglas.datos["presentacion"].get("pie_pagina", "&P+1 de &N+1")
        hecho.append("pie de pagina")
    return hecho
