"""Escribe el Excel de un formato (ver `formatos/__init__.py`) desde la base central (`base.ProyectoDB`).

No tiene reglas de ningún cliente: columnas, títulos, combinaciones, anchos, estilos, filtro e impresión salen del formato
y de su plantilla. Reutiliza de `excel_writer` los estilos, la página y la carátula.
"""
from __future__ import annotations

import re
from pathlib import Path

from openpyxl import Workbook
from openpyxl.formatting.rule import Rule
from openpyxl.styles import PatternFill
from openpyxl.styles.differential import DifferentialStyle
from openpyxl.utils import column_index_from_string
from openpyxl.worksheet.cell_range import CellRange

import excel_writer as xw
from base import ProyectoDB, SenalBase
from modelo import Caratula, Proyecto

from . import Formato

AMARILLO = PatternFill("solid", fgColor="FFFF00")           # DESC. SCADA que no entró en 20 caracteres
_MEDICION = "MEDICION"


def valor(campo: str, b: SenalBase):
    """Valor de una columna para una señal. Vacío -> None (la celda queda en blanco)."""
    if b.es_hueco and campo in ("item", "offset", "indice_dnp"):
        v = None                         # fila libre: vacía (el contador de offsets la salta, pero no la numera)
    elif campo == "item":
        v = b.item
    elif campo == "descrip":
        v = b.descripcion_campo
    elif campo.startswith("estado"):
        n = int(campo[-1])
        v = getattr(b, ("min_raw", "max_raw", "min_eu", "max_eu")[n] if b.funcion == _MEDICION else f"s{n}")
    else:
        v = getattr(b, campo)
    return None if v == "" else v


def _estilo(plantilla: dict, primera: int) -> dict:
    return plantilla["estilo_filas_datos"][str(primera)]


def escribir(db: ProyectoDB, formato: Formato, ruta, perfil, caratula: Caratula | None = None) -> int:
    """Escribe el Excel y devuelve cuántas descripciones SCADA quedaron en amarillo (a revisar)."""
    t = formato.plantilla
    limite = column_index_from_string(formato.ultima_columna)
    dentro = lambda letra: column_index_from_string(letra) <= limite  # noqa: E731
    primera = formato.primera_fila_datos

    wb = Workbook()
    if caratula is not None:                                     # la carátula sale de la plantilla EPEN
        ws_car = wb.active
        ws_car.title = perfil.datos["hojas"]["caratula"]
        base = xw.cargar_plantilla(perfil)
        xw._escribir_caratula(ws_car, Proyecto(db.perfil_id, caratula=caratula), perfil, base["caratula"],
                              base["caratula_campos"])
        ws = wb.create_sheet(formato.hoja)
    else:
        ws = wb.active
        ws.title = formato.hoja

    # --- encabezado, anchos, alturas
    xw._anchos(ws, {k: v for k, v in t["columnas"].items() if dentro(k)})
    for r, h in t["alturas_filas"].items():
        ws.row_dimensions[int(r)].height = h
    for r, fila in t["encabezado"].items():
        for letra, cel in fila.items():
            if dentro(letra):
                c = ws[f"{letra}{r}"]
                c.value = cel["v"]
                xw.aplicar_estilo(c, cel)
    for m in t["merges_encabezado"]:
        if CellRange(m).max_col <= limite:
            ws.merge_cells(m)

    # --- datos
    estilo = _estilo(t, primera)
    alto = t["alturas_filas"].get(str(primera))
    letra_de = formato.letra_de
    columnas = [c for c in formato.columnas if dentro(c["letra"])]
    col_desc = letra_de.get("desc_scada")
    amarillas = 0
    merges: list[tuple[str, int, int]] = []

    def cerrar(letra: str | None, desde: int, hasta: int) -> None:
        if letra and hasta > desde:
            merges.append((letra, desde, hasta))

    fila = primera
    n_desde = c_desde = f_desde = fila
    grupo_n = grupo_c = funcion = None
    for b in db.senales:
        if grupo_n is None:
            grupo_n, grupo_c, funcion = b.grupo_nivel, b.grupo_campo, b.funcion
        else:
            if b.grupo_nivel != grupo_n:                          # cambia el nivel: se cierran los tres bloques
                cerrar(letra_de.get("funcion"), f_desde, fila - 1)
                cerrar(letra_de.get("descrip"), c_desde, fila - 1)
                cerrar(letra_de.get("nivel"), n_desde, fila - 1)
                n_desde = c_desde = f_desde = fila
                grupo_n, grupo_c, funcion = b.grupo_nivel, b.grupo_campo, b.funcion
            elif b.grupo_campo != grupo_c:                         # cambia el campo
                cerrar(letra_de.get("funcion"), f_desde, fila - 1)
                cerrar(letra_de.get("descrip"), c_desde, fila - 1)
                c_desde = f_desde = fila
                grupo_c, funcion = b.grupo_campo, b.funcion
            elif b.funcion != funcion:                             # cambia la función dentro del campo
                cerrar(letra_de.get("funcion"), f_desde, fila - 1)
                f_desde = fila
                funcion = b.funcion
        for col in columnas:
            cel = ws[f"{col['letra']}{fila}"]
            if col["campo"]:
                cel.value = valor(col["campo"], b)
            xw.aplicar_estilo(cel, estilo[col["letra"]])
        if col_desc and b.sin_resolver:
            ws[f"{col_desc}{fila}"].fill = AMARILLO
            amarillas += 1
        if alto:
            ws.row_dimensions[fila].height = alto
        fila += 1
    if grupo_n is not None:
        cerrar(letra_de.get("funcion"), f_desde, fila - 1)
        cerrar(letra_de.get("descrip"), c_desde, fila - 1)
        cerrar(letra_de.get("nivel"), n_desde, fila - 1)
    for letra, d, h in merges:
        ws.merge_cells(f"{letra}{d}:{letra}{h}")

    # --- filtro, impresión, página, duplicados de DESC. SCADA
    ultima = max(fila - 1, primera)
    ultima_letra = formato.ultima_columna
    if t["autofiltro"]:
        ws.auto_filter.ref = re.sub(r"[A-Z]+(\d+)$", rf"{ultima_letra}\1", xw._con_fila_final(t["autofiltro"], ultima))
    if t["area_impresion"]:
        area = xw._con_fila_final(t["area_impresion"].split("!")[-1].replace("$", ""), ultima)
        ws.print_area = re.sub(r"[A-Z]+(\d+)$", rf"{ultima_letra}\1", area)
    if t["titulos_repetir_filas"]:
        ws.print_title_rows = t["titulos_repetir_filas"].replace("$", "")
    xw._pagina(ws, t)
    if t["formato_condicional"] and col_desc and fila > primera:
        regla = t["formato_condicional"][0]
        dxf = DifferentialStyle(fill=PatternFill(bgColor=xw._color(regla["dxf_fill"])))
        ws.conditional_formatting.add(f"{col_desc}{primera}:{col_desc}{ultima}", Rule(type="duplicateValues", dxf=dxf))

    ruta = Path(ruta)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    wb.save(ruta)
    return amarillas
