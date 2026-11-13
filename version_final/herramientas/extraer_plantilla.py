"""Extrae la plantilla de formato de un listado de señales de ejemplo (solo lectura).

Uso:
    python herramientas/extraer_plantilla.py <ejemplo.xlsx> <salida.json> <hoja_listado> <filas_encabezado> [filas_muestra]

    Ejemplo (Excel oficial de Senillosa: 4 filas de encabezado, datos desde la fila 5):
    python herramientas/extraer_plantilla.py USRE-0119-...xlsx plantillas/USRE/USRE_listado.json EPEN 4 5,6,7

Guarda anchos, alturas, merges del encabezado, estilos, filtro, área de impresión, títulos, formato condicional y la
página de la hoja del listado. No guarda datos de señales: solo formato y rótulos fijos. (La carátula se sigue
tomando de plantillas/EPEN: ver `excel_writer`.)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from openpyxl import load_workbook
from openpyxl.utils import get_column_letter


def _color(c):
    if c is None:
        return None
    if c.type == "rgb":
        return c.rgb if isinstance(c.rgb, str) else None
    if c.type == "theme":
        return {"theme": c.theme, "tint": c.tint}
    if c.type == "indexed":
        return {"indexed": c.indexed}
    return None


def _lado(s):
    if s is None or s.style is None:
        return None
    return {"style": s.style, "color": _color(s.color)}


def estilo(cell) -> dict:
    f, fl, b, a = cell.font, cell.fill, cell.border, cell.alignment
    d = {
        "font": {"name": f.name, "sz": f.sz, "b": bool(f.b), "i": bool(f.i), "u": f.u, "color": _color(f.color)},
        "fill": None,
        "border": {k: _lado(getattr(b, k)) for k in ("left", "right", "top", "bottom")},
        "align": {"h": a.horizontal, "v": a.vertical, "wrap": bool(a.wrap_text), "rot": a.textRotation, "indent": a.indent},
        "fmt": cell.number_format,
    }
    if fl is not None and fl.fill_type:
        d["fill"] = {"type": fl.fill_type, "fg": _color(fl.fgColor)}
    return d


def _celda(cell) -> dict:
    d = estilo(cell)
    d["v"] = cell.value
    return d


def extraer_listado(ws, filas_encabezado: int, filas_muestra: tuple[int, ...]) -> dict:
    ult = ws.max_column
    columnas = {}
    for i in range(1, ult + 1):
        l = get_column_letter(i)
        dim = ws.column_dimensions.get(l)
        columnas[l] = {"ancho": dim.width if dim else None, "oculta": bool(dim.hidden) if dim else False}
    alturas = {str(r): ws.row_dimensions[r].height
               for r in list(range(1, filas_encabezado + 1)) + list(filas_muestra)
               if ws.row_dimensions[r].height is not None}
    encabezado = {str(r): {get_column_letter(c): _celda(ws.cell(r, c)) for c in range(1, ult + 1)}
                  for r in range(1, filas_encabezado + 1)}
    muestra = {str(r): {get_column_letter(c): estilo(ws.cell(r, c)) for c in range(1, ult + 1)} for r in filas_muestra}
    merges_enc = [str(m) for m in ws.merged_cells.ranges if m.min_row <= filas_encabezado]
    cf = []
    for rng, reglas in ws.conditional_formatting._cf_rules.items():
        for r in reglas:
            cf.append({"rango": str(rng.sqref), "tipo": r.type, "operador": r.operator, "formula": list(r.formula or []),
                       "dxf_fill": _color(r.dxf.fill.bgColor) if r.dxf and r.dxf.fill else None,
                       "dxf_font": _color(r.dxf.font.color) if r.dxf and r.dxf.font else None})
    return {
        "dimension": ws.dimensions,
        "columnas": columnas,
        "alturas_filas": alturas,
        "encabezado": encabezado,
        "merges_encabezado": merges_enc,
        "estilo_filas_datos": muestra,
        "autofiltro": ws.auto_filter.ref,
        "area_impresion": ws.print_area,
        "titulos_repetir_filas": ws.print_title_rows,
        "titulos_repetir_columnas": ws.print_title_cols,
        "congelar": ws.freeze_panes,
        "formato_condicional": cf,
        "pagina": {"orientacion": ws.page_setup.orientation, "papel": ws.page_setup.paperSize,
                   "escala": ws.page_setup.scale, "ajustar_ancho": ws.page_setup.fitToWidth,
                   "ajustar_alto": ws.page_setup.fitToHeight,
                   "fit_to_page": ws.sheet_properties.pageSetUpPr.fitToPage if ws.sheet_properties.pageSetUpPr else None},
        "margenes": {k: getattr(ws.page_margins, k) for k in ("left", "right", "top", "bottom", "header", "footer")},
    }


def extraer(ruta, hoja_listado: str, filas_encabezado: int, filas_muestra: tuple[int, ...]) -> dict:
    wb = load_workbook(ruta)  # sin data_only: no hacen falta valores calculados
    return {"fuente": Path(ruta).name, "hoja_listado": hoja_listado,
            "filas_encabezado": filas_encabezado, "primera_fila_datos": filas_encabezado + 1,
            "listado": extraer_listado(wb[hoja_listado], filas_encabezado, filas_muestra)}


def main(argv: list[str]) -> int:
    if len(argv) < 5:
        print(__doc__)
        return 1
    muestra = tuple(int(x) for x in argv[5].split(",")) if len(argv) > 5 else tuple(
        range(int(argv[4]) + 1, int(argv[4]) + 4))
    datos = extraer(argv[1], argv[3], int(argv[4]), muestra)
    out = Path(argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(datos, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"Plantilla guardada en {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
