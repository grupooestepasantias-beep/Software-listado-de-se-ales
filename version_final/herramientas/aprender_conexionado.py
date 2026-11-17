"""Aprende el conexionado de equipos (BORNERA EQUIPO / N° DE BORNE EQUIPO) de un listado oficial en Excel.

    python herramientas/aprender_conexionado.py "USRE-0119-SET-C-T-LI-Ls-0744_rD_DV_2.xlsx" [--perfil EPEN] [--agregar]

Lee la hoja de datos del listado (la que tiene los encabezados NIVEL, DESCRIP, BORNERA EQUIPO y N* DE BORNE EQUIPO; las
columnas se buscan por su TÍTULO, no por la letra, así sirve para cualquier listado con ese formato) y arma una regla por
cada señal que tiene bornera y borne de equipo: rótulo normalizado + nivel + tipo de campo -> (bornera, borne).
Con `--agregar` suma a lo que ya había en `perfiles/<perfil>/conexionado_equipos.json` (las reglas repetidas no se duplican);
sin él, reemplaza. Imprime las reglas que difieren entre campos del mismo tipo (esas no se aplican solas)."""
from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import openpyxl  # noqa: E402

import conexionado  # noqa: E402
from conexionado import Regla  # noqa: E402


def _columnas(ws) -> tuple[int, dict[str, int]]:
    """(fila de encabezado, {nombre: columna}) buscando los títulos en las primeras filas."""
    nombres = {"NIVEL": "nivel", "DESCRIP": "descrip", "BORNERA EQUIPO": "bornera", "N* DE BORNE EQUIPO": "borne",
               "N° DE BORNE EQUIPO": "borne", "DESCRIPCION / OBSERVAC": "obs", "DESC. HMI SEL": "hmi"}
    for fila in range(1, 8):
        encontradas: dict[str, int] = {}
        for c in ws[fila]:
            v = str(c.value or "").replace("\n", " ").strip().upper()
            for titulo, clave in nombres.items():
                if v.startswith(titulo.upper()):
                    encontradas.setdefault(clave, c.column)
        if "bornera" in encontradas and "borne" in encontradas:
            return fila, encontradas
    raise ValueError(f"la hoja «{ws.title}» no tiene columnas BORNERA EQUIPO y N° DE BORNE EQUIPO")


def aprender(ruta_excel, fuente: str = "") -> tuple[list[Regla], list[str]]:
    wb = openpyxl.load_workbook(ruta_excel, data_only=True)
    ws = next((h for h in wb.worksheets if h.sheet_state == "visible" and _tiene(h)), None)
    if ws is None:
        raise ValueError("no encontré una hoja con BORNERA EQUIPO / N° DE BORNE EQUIPO")
    fila0, col = _columnas(ws)
    val = lambda r, k: str(ws.cell(r, col[k]).value or "").strip() if k in col else ""     # noqa: E731
    fuente = fuente or Path(ruta_excel).name
    nivel = campo = ""
    reglas: dict[tuple, Regla] = {}
    campos_de: dict[tuple, set] = defaultdict(set)         # regla -> números de campo donde se vio
    for r in range(fila0 + 3, ws.max_row + 1):
        if val(r, "nivel"):
            nivel = val(r, "nivel")
        if val(r, "descrip"):
            campo = val(r, "descrip")
        bornera, borne = val(r, "bornera"), val(r, "borne")
        etiqueta = val(r, "obs") or val(r, "hmi")
        if not (bornera and borne and etiqueta):
            continue
        regla = Regla(conexionado.clave_de(etiqueta), conexionado.nivel_normal(nivel), conexionado.tipo_de_campo(campo),
                      bornera, borne, fuente, etiqueta)
        reglas[(regla.clave, regla.nivel, regla.tipo_campo, regla.bornera, regla.borne)] = regla
        n_campo = re.findall(r"\d+", campo)
        campos_de[(regla.clave, regla.nivel, regla.tipo_campo, regla.bornera, regla.borne)].add(n_campo[-1] if n_campo else "")
    _plantillas(reglas, campos_de)
    por_ctx: dict[tuple, set] = defaultdict(set)
    for r in reglas.values():
        por_ctx[(r.clave, r.nivel, r.tipo_campo)].add((r.bornera, r.borne))
    conflictos = [f"{k[1]} / {k[2] or '(cualquier campo)'} / «{k[0]}»: {sorted(v)}" for k, v in sorted(por_ctx.items()) if len(v) > 1]
    return list(reglas.values()), conflictos


def _plantillas(reglas: dict, campos_de: dict) -> None:
    """Si en un mismo contexto la bornera cambia solo por el número de campo (campo 103 -> 1XP3, 104 -> 1XP4) y el borne es el
    mismo, se guarda UNA regla con plantilla «1XP{c}» en lugar de varias que se contradicen."""
    por_ctx: dict[tuple, list] = defaultdict(list)
    for k in reglas:
        por_ctx[k[:3]].append(k)
    for ctx, claves in por_ctx.items():
        if len(claves) < 2 or len({k[4] for k in claves}) != 1:
            continue
        bases = set()
        for k in claves:
            digitos = {c[-1] for c in campos_de[k] if c}
            if len(digitos) != 1 or not k[3].endswith(next(iter(digitos))):
                break
            bases.add(k[3][:-1])
        else:
            if len(bases) == 1:
                molde = reglas[claves[0]]
                for k in claves:
                    del reglas[k]
                nueva = Regla(molde.clave, molde.nivel, molde.tipo_campo, next(iter(bases)) + "{c}", molde.borne, molde.fuente)
                reglas[(nueva.clave, nueva.nivel, nueva.tipo_campo, nueva.bornera, nueva.borne)] = nueva


def _tiene(ws) -> bool:
    try:
        _columnas(ws)
        return True
    except ValueError:
        return False


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("excel")
    p.add_argument("--perfil", default="EPEN")
    p.add_argument("--agregar", action="store_true", help="suma a lo ya aprendido en vez de reemplazarlo")
    a = p.parse_args(argv)
    reglas, conflictos = aprender(a.excel)
    carpeta = RAIZ / "perfiles" / a.perfil
    previas = conexionado.Conexionado.cargar(carpeta).reglas if a.agregar else []
    unicas = {(r.clave, r.nivel, r.tipo_campo, r.bornera, r.borne): r for r in previas + reglas}
    ruta = conexionado.Conexionado(list(unicas.values())).guardar(carpeta)
    print(f"{len(reglas)} reglas leídas de {Path(a.excel).name}; {len(unicas)} en total -> {ruta}")
    if conflictos:
        print(f"\n{len(conflictos)} señales con borne distinto entre campos del mismo tipo (no se aplican solas):")
        for c in conflictos:
            print("  -", c)
    return 0


if __name__ == "__main__":
    sys.exit(main())
