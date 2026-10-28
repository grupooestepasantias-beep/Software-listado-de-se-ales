"""Generador de señales (tarea 2.1).

Recibe un Proyecto con las señales ya cargadas (función, tipo, estado_id, observaciones, par...) y completa:
orden por función, TAG SCADA, OFFSET, estados S0-S3 / rangos, UNITS, TAG/DESC. HMI y DESC. SCADA.
PLACA/ENTRADA son de la tarea 3.1. ITEM lo numera el escritor de Excel.

Reglas (todas leídas del perfil; las marcadas PENDIENTE están en PREGUNTAS.md):
- Orden dentro de cada campo: el del perfil (ALARMAS, SEÑALIZACION, COMANDO, MEDICION); RESERVA al final.
- Variable del tag: contador por campo, +1 por alarma/señalización; la medición lleva su propio contador.
  PENDIENTE: valor inicial (00 o 10) y saltos.
- OFFSET: un contador por tipo de punto (DI, AI...) desde Proyecto.offsets_iniciales, continuo entre campos.
  Una señalización de doble bit consume 2 offsets y ocupa 2 filas. Un comando enlazado (misma `par`) copia
  tag y offset de su señalización, y esa señalización lleva C en el tag.
- Lo que está en Senal.fijos (editado a mano) no se pisa.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional, Union

import tags
from modelo import NA, Campo, Funcion, Nivel, Proyecto, Senal, TipoPunto
from perfiles import Perfil

ESTADOS = ("s0", "s1", "s2", "s3")
TIPO_POR_FUNCION = {
    Funcion.ALARMAS: TipoPunto.DI,
    Funcion.SENALIZACION: TipoPunto.DI,
    Funcion.COMANDO: TipoPunto.DO,
    Funcion.MEDICION: TipoPunto.AI,
    Funcion.RESERVA: TipoPunto.DI,
}


class ErrorGeneracion(ValueError):
    """Falta un dato que el software tiene que pedir al usuario."""


def sin_acentos(texto: str) -> str:
    t = unicodedata.normalize("NFD", texto)
    return "".join(c for c in t if unicodedata.category(c) != "Mn").replace("ñ", "n").replace("Ñ", "N")


def tag_hmi_desde(texto: str) -> str:
    """Observaciones -> TAG HMI: sin acentos ni puntos; cada grupo de símbolos/espacios pasa a '_'."""
    return re.sub(r"[^0-9A-Za-z]+", "_", sin_acentos(texto).replace(".", "")).strip("_")


def desc_hmi_desde(prefijo: str, texto: str) -> str:
    return f"{prefijo} {sin_acentos(texto)}".strip()


class _Offsets:
    def __init__(self, iniciales: dict[str, int]):
        self.sig = {k: int(v) for k, v in iniciales.items()}

    def tomar(self, tipo: str, n: int = 1) -> int:
        if tipo not in self.sig:
            raise ErrorGeneracion(f"falta el OFFSET inicial de {tipo}: hay que preguntarlo al usuario")
        v = self.sig[tipo]
        self.sig[tipo] += n
        return v

    def reservar(self, tipo: str, hasta: int) -> None:
        self.sig[tipo] = max(self.sig.get(tipo, hasta), hasta)


def _sufijo(perfil: Perfil, codigo: str, unidad: str) -> Optional[dict]:
    candidatos = perfil.sufijos(codigo)
    for c in candidatos:
        if unidad and unidad != NA and c["unidad"] == unidad:
            return c
    return candidatos[0] if candidatos else None


def _inicial(valor: Union[int, dict, None], campo: Campo, defecto: int) -> int:
    if isinstance(valor, dict):
        return int(valor.get(campo.numero, defecto))
    return defecto if valor is None else int(valor)


def generar(proyecto: Proyecto, perfil: Perfil, *,
            variable_inicial: Union[int, dict, None] = None,
            variable_inicial_medicion: Union[int, dict, None] = None) -> list[str]:
    """Completa las señales del proyecto (en el lugar). Devuelve avisos para mostrar al usuario."""
    avisos: list[str] = []
    cfg = perfil.datos["tag"]
    offsets = _Offsets(proyecto.offsets_iniciales)
    for nivel in proyecto.niveles:
        for campo in nivel.campos:
            v0 = _inicial(variable_inicial, campo, cfg.get("variable_inicial", 0))
            m0 = _inicial(variable_inicial_medicion, campo, cfg.get("variable_inicial_medicion", 1))
            _generar_campo(perfil, nivel, campo, offsets, v0, m0, avisos)
    return avisos


def _generar_campo(perfil: Perfil, nivel: Nivel, campo: Campo, offsets: _Offsets,
                   v0: int, m0: int, avisos: list[str]) -> None:
    prefijo = campo.prefijo or f"{nivel.codigo}{campo.numero}"
    orden = {f: i for i, f in enumerate(perfil.orden_funciones)}
    originales = [s for s in campo.senales if not s.segunda_fila]
    ordenadas = sorted(originales, key=lambda s: orden.get(s.funcion.value, len(orden)))

    def parse(s: Senal) -> Optional[dict]:
        return tags.parsear_tag(perfil, s.tag_scada) if "tag_scada" in s.fijos else None

    usadas = {p["variable"] for s in ordenadas if (p := parse(s)) and not p["medicion"]}
    usadas_med = {p["variable"] for s in ordenadas if (p := parse(s)) and p["medicion"]}
    pares_con_comando = {s.par for s in ordenadas if s.funcion == Funcion.COMANDO and s.par}
    senal_por_par: dict[str, Senal] = {}
    v, m = v0, m0
    resultado: list[Senal] = []

    for n, s in enumerate(ordenadas, 1):
        ref = f"{nivel.nombre} / campo {campo.numero} / señal {n} ({s.observaciones or s.funcion.value})"
        aviso = lambda msg, ref=ref: avisos.append(f"{ref}: {msg}")  # noqa: E731
        _comunes(perfil, campo, prefijo, s, aviso)
        fija = lambda nombre, s=s: nombre in s.fijos  # noqa: E731
        segunda: Optional[Senal] = None

        def tag(**kw) -> str:
            try:
                return tags.construir_tag(perfil, campo=campo.numero, nivel=nivel.codigo or None, **kw)
            except ValueError as e:
                aviso(str(e))
                return ""

        def offset(tipo: str, cuantos: int = 1) -> None:
            if fija("offset") and s.offset is not None:
                offsets.reservar(tipo, s.offset + cuantos)
            else:
                s.offset = offsets.tomar(tipo, cuantos)

        tipo = s.tipo_punto.value
        if s.funcion == Funcion.RESERVA:
            for nombre, valor in (("tag_hmi", NA), ("desc_hmi", "RESERVA"), ("tag_scada", NA),
                                  ("desc_scada", "RESERVA"), ("observaciones", "RESERVA")):
                if not fija(nombre):
                    setattr(s, nombre, valor)
            for e in ESTADOS:
                if not fija(e):
                    setattr(s, e, NA)
            offset(tipo)

        elif s.funcion == Funcion.MEDICION:
            if not s.medicion_codigo:
                aviso("falta el código de medición (AR, AU, AP...)")
            else:
                suf = _sufijo(perfil, s.medicion_codigo, s.unidad)
                if suf is None:
                    aviso(f"código de medición desconocido: {s.medicion_codigo}")
                else:
                    if not fija("tag_scada"):
                        var = tags.proxima_variable(perfil, usadas_med, m)
                        usadas_med.add(var)
                        m = var + 1
                        s.tag_scada = tag(variable=var, medicion=s.medicion_codigo)
                    raw = perfil.sufijos_medicion["rangos_raw"][suf["rango_raw"]]
                    tope = min(raw["max"], perfil.sufijos_medicion.get("max_raw_a_escribir", raw["max"]))
                    for nombre, valor in (("s0", raw["min"]), ("s1", tope)):
                        if not fija(nombre):
                            setattr(s, nombre, valor)
                    if not fija("unidad"):
                        s.unidad = suf["unidad"] or NA
            if s.s2 == NA or s.s3 == NA:
                aviso("faltan MIN EU / MAX EU (valores de ingeniería que fija el aparato)")
            offset(tipo)

        elif s.funcion == Funcion.COMANDO and s.par and s.par in senal_por_par:
            pareja = senal_por_par[s.par]
            if not fija("tag_scada"):
                s.tag_scada = pareja.tag_scada
            if not fija("offset"):
                s.offset = pareja.offset
            if not fija("desc_scada") and not s.desc_scada:
                s.desc_scada = pareja.desc_scada

        else:  # alarma, señalización o comando sin pareja
            if s.funcion == Funcion.COMANDO and s.par:
                aviso(f"el comando no tiene señalización con par '{s.par}'; se trata como comando suelto")
            bits = _bits(perfil, s)
            comando = s.funcion == Funcion.COMANDO or (
                s.funcion == Funcion.SENALIZACION and bool(s.par) and s.par in pares_con_comando)
            if not fija("tag_scada"):
                var = tags.proxima_variable(perfil, usadas, v)
                usadas.add(var)
                v = var + 1
                s.tag_scada = tag(variable=var, bits=bits, comando=comando)
            filas = 2 if (s.funcion == Funcion.SENALIZACION and bits == 2) else 1
            offset(tipo, filas)
            if s.funcion == Funcion.SENALIZACION:
                if s.par:
                    senal_por_par.setdefault(s.par, s)
                if filas == 2:
                    segunda = Senal(
                        funcion=s.funcion, tipo_punto=s.tipo_punto, controlador=s.controlador,
                        offset=(s.offset or 0) + 1, s0="", s1="", s2="", s3="", unidad=NA,
                        observaciones=s.obs_segunda_fila, segunda_fila=True)
                    if not s.obs_segunda_fila:
                        aviso("falta el texto de la 2ª fila del doble bit (obs_segunda_fila)")

        resultado.append(s)
        if segunda is not None:
            resultado.append(segunda)
    campo.senales = resultado


def _bits(perfil: Perfil, s: Senal) -> int:
    if s.estado_id:
        try:
            return perfil.estado(s.estado_id)["bits"]
        except KeyError:
            pass
    return 1 if s.funcion == Funcion.ALARMAS else 2


def _comunes(perfil: Perfil, campo: Campo, prefijo: str, s: Senal, aviso) -> None:
    fijo = lambda nombre: nombre in s.fijos  # noqa: E731
    if s.tipo_punto is None:
        s.tipo_punto = TIPO_POR_FUNCION[s.funcion]
    if not s.controlador:
        s.controlador = campo.controlador
    if s.funcion in (Funcion.ALARMAS, Funcion.SENALIZACION, Funcion.COMANDO):
        estado_id = s.estado_id or ("alarma_actuo" if s.funcion == Funcion.ALARMAS else None)
        if estado_id is None:
            aviso("falta estado_id (tipo de estados de la señalización/comando)")
        else:
            try:
                e = perfil.estado(estado_id)
            except KeyError:
                aviso(f"estado_id desconocido: {estado_id}")
            else:
                s.estado_id = estado_id
                for k in ESTADOS:
                    if not fijo(k):
                        setattr(s, k, e[k])
        if not fijo("unidad"):
            s.unidad = NA
    if s.funcion == Funcion.RESERVA:
        return
    texto = s.observaciones
    if not texto:
        aviso("sin observaciones: no se pueden proponer TAG/DESC. HMI")
        return
    if not fijo("tag_hmi"):
        s.tag_hmi = tag_hmi_desde(texto)
    if not fijo("desc_hmi"):
        s.desc_hmi = desc_hmi_desde(prefijo, texto)
    if not fijo("desc_scada") and not s.desc_scada:
        try:
            s.desc_scada = tags.construir_desc_scada(perfil, prefijo, sin_acentos(texto))
        except ValueError as e:
            aviso(f"DESC. SCADA a definir a mano ({e})")
