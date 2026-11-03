"""Paso de calidad del listado: normaliza redaccion, contrasta con una referencia, completa la presentacion,
valida el resultado y deja un informe + un registro de cambios.

    from calidad import mejorar_archivo
    informe = mejorar_archivo("listado.xlsx")            # -> listado_final.xlsx + informe + cambios.csv
    python -m calidad listado.xlsx [-o salida.xlsx] [--ref referencia.xlsx] [--perfil EPEN]

Las reglas son de cada cliente (perfiles/<cliente>/redaccion.json); aca no hay textos de ningun cliente."""
from __future__ import annotations

import shutil
from pathlib import Path
from typing import Optional

import openpyxl

import excel_writer
import perfiles
from . import presentacion, referencia, reglas as _reglas
from .informe import Informe
from .libro import Cambio, corregir, leer_filas
from .validar import validar

__all__ = ["mejorar_archivo", "Informe"]


def _respaldo(ruta: Path) -> Path:
    n, destino = 0, ruta.with_name(ruta.stem + "_original.xlsx")
    while destino.exists():
        n += 1
        destino = ruta.with_name(f"{ruta.stem}_original{n}.xlsx")
    shutil.copy2(ruta, destino)
    return destino


def mejorar_archivo(entrada, salida=None, perfil_id: str = "EPEN", ref: Optional[str] = "auto",
                    respaldar: bool = True, escribir_informe: bool = True) -> Informe:
    """Mejora `entrada` (nunca la modifica salvo que salida == entrada, y entonces deja `_original`)."""
    entrada = Path(entrada)
    salida = Path(salida) if salida else entrada.with_name(entrada.stem + "_final.xlsx")
    perfil = perfiles.cargar_perfil(perfil_id)
    reglas = _reglas.cargar(perfil.carpeta)
    try:
        campos = excel_writer.cargar_plantilla(perfil)["caratula_campos"]
    except excel_writer.PlantillaNoEncontrada:
        campos = None

    fuente = entrada
    if salida.resolve() == entrada.resolve():
        fuente = _respaldo(entrada) if respaldar else entrada
        if not respaldar:  # sin copia no se puede comparar: se usa una temporal junto al archivo
            fuente = entrada.with_name(entrada.stem + "_tmp_original.xlsx")
            shutil.copy2(entrada, fuente)

    wb = openpyxl.load_workbook(fuente)
    if reglas.hoja not in wb.sheetnames:
        raise ValueError(f"{entrada.name} no tiene la hoja '{reglas.hoja}' (hojas: {wb.sheetnames})")
    ws = wb[reglas.hoja]

    cambios, pendientes, examinadas = corregir(ws, reglas, leer_filas(ws, reglas))
    informe = Informe(str(entrada), str(salida), examinadas=examinadas, cambios=cambios, pendientes=pendientes,
                      modo_tildes=reglas.modo_tildes)

    # referencia
    ruta_ref = None
    if ref == "auto":
        rel = reglas.datos.get("referencia", {}).get("archivo")
        ruta_ref = perfil.carpeta.parents[2] / rel if rel else None
    elif ref:
        ruta_ref = Path(ref)
    if ruta_ref and ruta_ref.is_file() and ruta_ref.resolve() != entrada.resolve():
        wb_ref = openpyxl.load_workbook(ruta_ref)
        nombre_ref = reglas.datos.get("referencia", {}).get("hoja", reglas.hoja)
        if nombre_ref in wb_ref.sheetnames:
            informe.referencia = str(ruta_ref)
            resumen, extra, pend = referencia.comparar(ws, leer_filas(ws, reglas), referencia.indexar(wb_ref[nombre_ref], reglas), reglas)
            informe.resumen_ref = resumen
            informe.cambios += extra
            informe.pendientes += pend
            informe.hallazgos_ref = referencia.auditar(wb_ref[nombre_ref], reglas)

    # presentacion (encabezado y pie)
    if campos:
        nombre_car = next((n for n in wb.sheetnames if n != reglas.hoja), None)
        if nombre_car:
            hecho = presentacion.completar(ws, presentacion.leer_portada(wb[nombre_car], campos), reglas)
            informe.presentacion = hecho
            for h in hecho:
                informe.cambios.append(Cambio(ws.title, h, "", "-", "", "(completado)", "presentacion", "encabezado_pie", "", "",
                                              "alta", "se completa como el ETAP con los datos de la caratula"))

    salida.parent.mkdir(parents=True, exist_ok=True)
    wb.save(salida)
    informe.chequeos = validar(fuente, salida, informe.cambios, reglas, campos)
    if fuente != entrada and fuente.name.endswith("_tmp_original.xlsx"):
        fuente.unlink()
    if escribir_informe:
        informe.escribir(salida)
    return informe
