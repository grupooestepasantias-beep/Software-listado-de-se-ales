"""Validaciones automaticas del archivo resultante contra el de entrada.

Tres niveles: BLOQUEANTE (el archivo no se puede entregar), ADVERTENCIA (hay que mirarlo) y RECOMENDACION
(editorial). Cada chequeo dice si paso; nada se declara validado si el codigo no pudo comprobarlo."""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

import openpyxl

from .libro import Cambio, leer_filas
from .reglas import Reglas
from .texto import RE_KV, normalizar, numero_de_nivel, sin_tildes

BLOQUEANTE, ADVERTENCIA, RECOMENDACION = "bloqueante", "advertencia", "recomendacion"


@dataclass
class Chequeo:
    nivel: str
    codigo: str
    ok: bool
    detalle: str


def _hoja_config(ws) -> dict:
    return {
        "dimension": ws.dimensions, "merges": sorted(map(str, ws.merged_cells.ranges)),
        "area_impresion": ws.print_area, "titulos": ws.print_title_rows, "congelar": ws.freeze_panes,
        "filtro": ws.auto_filter.ref, "orientacion": ws.page_setup.orientation, "papel": ws.page_setup.paperSize,
        "escala": ws.page_setup.scale, "ajustar": (ws.page_setup.fitToWidth, ws.page_setup.fitToHeight),
        "margenes": (ws.page_margins.left, ws.page_margins.right, ws.page_margins.top, ws.page_margins.bottom),
        "anchos": {k: round(v.width or 0, 2) for k, v in ws.column_dimensions.items()},
        "alturas": {k: v.height for k, v in ws.row_dimensions.items() if v.height},
        "formato_condicional": sorted((str(r.sqref), x.type) for r, xs in ws.conditional_formatting._cf_rules.items() for x in xs),
        "imagenes": len(getattr(ws, "_images", [])),
    }


def validar(ruta_entrada, ruta_salida, cambios: list[Cambio], reglas: Reglas, campos_caratula: dict | None = None,
            permitidas_extra: set | None = None) -> list[Chequeo]:
    out: list[Chequeo] = []

    def chk(nivel, codigo, ok, detalle):
        out.append(Chequeo(nivel, codigo, bool(ok), detalle))

    try:
        antes = openpyxl.load_workbook(ruta_entrada)
        despues = openpyxl.load_workbook(ruta_salida)
    except Exception as e:  # el libro guardado debe poder abrirse
        chk(BLOQUEANTE, "libro_abre", False, f"no se pudo abrir: {e}")
        return out
    chk(BLOQUEANTE, "libro_abre", True, "el libro guardado se reabre sin errores")
    chk(BLOQUEANTE, "hojas_presentes", antes.sheetnames == despues.sheetnames and reglas.hoja in despues.sheetnames,
        f"hojas: {despues.sheetnames}")

    cambiadas = {(c.hoja, c.celda): c for c in cambios}
    cambiadas_celdas = {k for k in cambiadas}
    # celda por celda: nada cambia fuera del registro
    fuera, ident = [], []
    protegidas = {reglas.col[k] for k in ("nivel", "funcion", "tag_hmi", "tag_scada", "offset")}
    for nombre in antes.sheetnames:
        a, d = antes[nombre], despues[nombre]
        for fila in range(1, max(a.max_row, d.max_row) + 1):
            for col in range(1, max(a.max_column, d.max_column) + 1):
                va, vd = a.cell(fila, col).value, d.cell(fila, col).value
                if va != vd and not (va in ("", None) and vd in ("", None)):  # openpyxl guarda '' como celda vacia
                    cel = d.cell(fila, col).coordinate
                    if (nombre, cel) not in cambiadas_celdas:
                        fuera.append(f"{nombre}!{cel}")
                    elif nombre == reglas.hoja and d.cell(fila, col).column_letter in protegidas:
                        ident.append(f"{nombre}!{cel}")
    chk(BLOQUEANTE, "sin_cambios_fuera_del_registro", not fuera,
        "todas las celdas modificadas estan en el registro de cambios" if not fuera else f"{len(fuera)} celdas cambiaron sin registro: {fuera[:5]}")
    chk(BLOQUEANTE, "identificadores_intactos", not ident,
        "TAG HMI, TAG SCADA, OFFSET, NIVEL y FUNCION identicos" if not ident else f"cambiaron: {ident[:5]}")

    a, d = antes[reglas.hoja], despues[reglas.hoja]
    fa, fd = leer_filas(a, reglas), leer_filas(d, reglas)
    chk(BLOQUEANTE, "filas_conservadas", len(fa) == len(fd), f"{len(fa)} filas con datos antes, {len(fd)} despues")
    chk(BLOQUEANTE, "tags_conservados", [(f.tag_scada, f.funcion) for f in fa] == [(f.tag_scada, f.funcion) for f in fd],
        "TAG SCADA y FUNCION de cada fila, en el mismo orden")

    # descripciones no vacias ni truncadas, largos
    vacias = [f.fila for f, g in zip(fa, fd) if (f.desc_hmi and not g.desc_hmi) or (f.desc_scada and not g.desc_scada)]
    chk(BLOQUEANTE, "descripciones_no_vaciadas", not vacias, "ninguna descripcion quedo vacia" if not vacias else f"filas {vacias[:8]}")
    lim = reglas.largo(reglas.col["desc_scada"])
    if lim:
        previas = {f.fila for f in fa if len(f.desc_scada) > lim}
        nuevas = [g.fila for g in fd if len(g.desc_scada) > lim and g.fila not in previas]
        chk(BLOQUEANTE, "largo_desc_scada_no_empeora", not nuevas, f"ninguna DESC. SCADA supera {lim} por la correccion" if not nuevas else f"filas {nuevas[:8]}")
        chk(ADVERTENCIA, "largo_desc_scada_total", not previas, f"DESC. SCADA de mas de {lim} caracteres que ya venian asi: filas {sorted(previas)[:10]}" if previas else f"todas las DESC. SCADA miden {lim} o menos")
    # duplicados
    dup = lambda fs, attr: Counter(getattr(f, attr) for f in fs if getattr(f, attr))
    da, dd = dup(fa, "desc_scada"), dup(fd, "desc_scada")
    nuevos = [g.desc_scada for f, g in zip(fa, fd) if g.desc_scada and dd[g.desc_scada] > 1 and da[f.desc_scada] <= 1]
    chk(BLOQUEANTE, "sin_duplicados_nuevos", not nuevos, "la correccion no creo DESC. SCADA repetidas" if not nuevos else f"nuevas repetidas: {nuevos[:5]}")
    previos = {t: n for t, n in dd.items() if n > 1}
    chk(ADVERTENCIA, "desc_scada_repetidas", not previos,
        "no hay DESC. SCADA repetidas" if not previos else
        f"{len(previos)} DESC. SCADA repetidas entre senales distintas (el Excel las resalta); ej. " + "; ".join(f"{t!r} x{n}" for t, n in list(previos.items())[:3]))
    tg = Counter((f.tag_scada, f.funcion) for f in fd if f.tag_scada and f.tag_scada != "N/A")
    rep = [k for k, n in tg.items() if n > 1]
    chk(ADVERTENCIA, "tags_repetidos", not rep, "no hay TAG SCADA repetidos dentro de una funcion" if not rep else f"{len(rep)} repetidos, ej. {rep[:3]}")

    # ortografia / nomenclatura residual
    resid = []
    for f in fd:
        for letra, texto in ((reglas.col["desc_hmi"], f.desc_hmi), (reglas.col["desc_scada"], f.desc_scada)):
            if not texto:
                continue
            if reglas.modo_tildes == "quitar" and texto != sin_tildes(texto):
                resid.append((f.fila, "tilde", texto))
            for mal in reglas.datos.get("errores_conocidos", {}):
                if re.search(rf"\b{re.escape(mal)}\b", texto, re.IGNORECASE) and mal.lower() != reglas.datos["errores_conocidos"][mal].lower():
                    resid.append((f.fila, mal, texto))
            tension = reglas.datos.get("tension")
            for m in RE_KV.finditer(texto) if tension else ():
                canonica = m.group(1) + (tension["decimal"] + m.group(2) if m.group(2) else "") + tension["unidad"]
                if m.group(0) != canonica:
                    resid.append((f.fila, "unidad_tension", texto))
    chk(ADVERTENCIA, "ortografia_residual", not resid,
        "sin errores detectables con el diccionario configurado (no hay corrector ortografico general)" if not resid else f"{len(resid)} casos, ej. {resid[:3]}")
    # estabilidad: una segunda pasada no debe cambiar nada
    inestables = [f.fila for f in fd if any(normalizar(t, l, reglas, f.nivel).pasos for l, t in
                  ((reglas.col["desc_hmi"], f.desc_hmi), (reglas.col["desc_scada"], f.desc_scada)) if t)]
    chk(ADVERTENCIA, "segunda_pasada_estable", not inestables, "volver a normalizar no produce cambios" if not inestables else f"filas {inestables[:8]}")

    # formato, impresion, imagenes: lo que la libreria pudo perder
    for nombre in antes.sheetnames:
        ca, cd = _hoja_config(antes[nombre]), _hoja_config(despues[nombre])
        difs = [k for k in ca if ca[k] != cd[k]]
        chk(BLOQUEANTE, f"formato_conservado[{nombre}]", not difs,
            "celdas combinadas, anchos, alturas, filtro, paneles, impresion, formato condicional e imagenes iguales" if not difs else f"cambiaron: {difs}")

    # coherencia de impresion
    ws = despues[reglas.hoja]
    chk(ADVERTENCIA, "impresion_coherente", bool(ws.print_area and ws.print_title_rows and ws.page_setup.orientation == "landscape"),
        f"area {ws.print_area}, titulos {ws.print_title_rows}, orientacion {ws.page_setup.orientation}")
    chk(ADVERTENCIA, "encabezado_pie", bool(ws.oddHeader.center.text and ws.oddFooter.left.text),
        "la hoja del listado tiene encabezado (obra + titulo) y pie (documento, hoja X de Y)" if (ws.oddHeader.center.text and ws.oddFooter.left.text) else "falta encabezado o pie (faltan datos en la caratula)")

    # portada
    if campos_caratula:
        from .presentacion import leer_portada
        nombre_car = next((n for n in despues.sheetnames if n != reglas.hoja), None)
        if nombre_car:
            p = leer_portada(despues[nombre_car], campos_caratula)
            faltan = [k for k, v in (("obra", p.obra), ("titulo", p.titulo), ("numero de documento", p.documento), ("revision", p.revision)) if not v]
            chk(ADVERTENCIA, "caratula_completa", not faltan, "obra, titulo, documento y revision completos" if not faltan else f"faltan en la caratula: {', '.join(faltan)}")
    else:
        chk(RECOMENDACION, "caratula_completa", False, "no se verifico la caratula (no hay hoja de caratula o plantilla)")

    raros = sorted({f.nivel for f in fd if numero_de_nivel(f.nivel) and f.nivel != numero_de_nivel(f.nivel) + "KV"})
    chk(RECOMENDACION, "formato_nivel", not raros,
        "NIVEL escrito como en el ETAP (ej. 6,6KV)" if not raros else
        f"NIVEL con otro formato que el ETAP (coma decimal y KV en mayusculas): {raros}; viene de la lectura del plano y no se corrige aca")
    chk(RECOMENDACION, "largo_desc_hmi", reglas.largo(reglas.col["desc_hmi"]) is not None,
        "no se conoce un limite para DESC. HMI: no se pudo comprobar su largo (ver PREGUNTAS.md)" if reglas.largo(reglas.col["desc_hmi"]) is None else "largo DESC. HMI configurado")
    return out
