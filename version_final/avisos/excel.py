"""Verifica que el Excel generado coincida con la base: lee el .xlsx y compara cada celda con lo que debería salir.
Solo informa (celeste: el archivo contradice la base); no corrige nada."""
from __future__ import annotations

import openpyxl
from openpyxl.cell.cell import MergedCell

from base import ProyectoDB
from formatos import Formato
from formatos.escritor import valor

from . import CELESTE, Aviso

MAX_AVISOS = 30                                   # para no inundar la pantalla si falla algo grande


def _igual(a, b) -> bool:
    if a in (None, "") and b in (None, ""):
        return True
    try:
        return float(a) == float(b)
    except (TypeError, ValueError):
        return str(a).strip() == str(b).strip()


def verificar(db: ProyectoDB, formato: Formato, ruta) -> list[Aviso]:
    """Avisos por cada celda que no coincide con la base (más uno por si faltan o sobran filas)."""
    wb = openpyxl.load_workbook(ruta)
    ws = wb[formato.hoja]
    primera = formato.primera_fila_datos
    out: list[Aviso] = []
    esperadas = len(db.senales)
    if ws.max_row < primera + esperadas - 1:
        out.append(Aviso(CELESTE, "EXCEL_FILAS", f"El Excel tiene menos filas ({ws.max_row - primera + 1}) que la base "
                                                 f"({esperadas}).", ()))
    for i, b in enumerate(db.senales):
        fila = primera + i
        for col in formato.columnas:
            if not col["campo"]:
                continue
            celda = ws[f"{col['letra']}{fila}"]
            if isinstance(celda, MergedCell):               # nivel, descripción y función van combinadas
                continue
            if not _igual(celda.value, valor(col["campo"], b)):
                out.append(Aviso(CELESTE, "EXCEL_DISTINTO_DE_LA_BASE",
                                 f"En el Excel, {col['letra']}{fila} dice «{celda.value}» y la base dice "
                                 f"«{valor(col['campo'], b)}» ({col['campo']}).", (b.id,), b.campo, b.item, b.hoja, b.archivo))
                if len(out) >= MAX_AVISOS:
                    return out
    return out
