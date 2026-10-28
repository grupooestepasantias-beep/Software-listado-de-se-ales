"""Validador del listado de señales (tarea 3.1). Lee las reglas del perfil.

validar_proyecto(proyecto, perfil) -> list[Problema]. "error" = no se debería entregar así; "aviso" = revisar.
No modifica el proyecto.
"""
from __future__ import annotations

import difflib
from collections import defaultdict
from dataclasses import dataclass

import tags
from modelo import NA, Funcion, Proyecto, Senal, TipoPunto
from perfiles import Perfil

TIPOS_POR_FUNCION = {
    Funcion.ALARMAS: {"DI"}, Funcion.SENALIZACION: {"DI"}, Funcion.COMANDO: {"DO"},
    Funcion.MEDICION: {"AI", "AO"}, Funcion.RESERVA: {"DI", "DO"},
}
TEXTOS = ("controlador", "tag_hmi", "desc_hmi", "tag_scada", "desc_scada", "observaciones", "unidad", "placa", "entrada")


@dataclass
class Problema:
    gravedad: str       # "error" | "aviso"
    ubicacion: str
    mensaje: str

    def __str__(self) -> str:
        return f"[{self.gravedad}] {self.ubicacion}: {self.mensaje}"


def _sugerir(valor, permitidos) -> str:
    """' (¿'x'?)' si `valor` parece una mala escritura de un valor permitido (mayúsculas, ERR_0 vs error_0...)."""
    por_minuscula = {str(p).lower(): p for p in permitidos}
    cerca = difflib.get_close_matches(str(valor).lower(), list(por_minuscula), n=1, cutoff=0.8)
    return f" (¿'{por_minuscula[cerca[0]]}'?)" if cerca else ""


def validar_proyecto(proyecto: Proyecto, perfil: Perfil) -> list[Problema]:
    out: list[Problema] = []
    estados_ok = {v for e in perfil.estados["estados"] for v in (e["s0"], e["s1"], e["s2"], e["s3"])} | {NA}
    unidades_ok = set(perfil.unidades["analogicas"]) | {NA}
    orden = {f: i for i, f in enumerate(perfil.orden_funciones)}

    por_tag: dict[str, list[tuple[str, Senal]]] = defaultdict(list)
    por_offset: dict[tuple[str, int], list[str]] = defaultdict(list)
    por_desc: dict[str, list[tuple[str, Senal]]] = defaultdict(list)
    por_entrada: dict[tuple[str, str, int], list[str]] = defaultdict(list)

    for nivel in proyecto.niveles:
        for campo in nivel.campos:
            previa: Senal | None = None
            ultimo_orden = -1
            pares_sen = {s.par for s in campo.senales if s.funcion == Funcion.SENALIZACION and s.par and not s.segunda_fila}
            for i, s in enumerate(campo.senales, 1):
                ub = f"{nivel.nombre} / campo {campo.numero} / fila {i} ({s.observaciones or s.funcion.value})"
                err = lambda m, ub=ub: out.append(Problema("error", ub, m))  # noqa: E731
                avi = lambda m, ub=ub: out.append(Problema("aviso", ub, m))  # noqa: E731

                for t in TEXTOS:  # espacios/tabulaciones sobrantes (el ejemplo tiene tags con tabulación)
                    v = getattr(s, t)
                    if isinstance(v, str) and v != v.strip():
                        err(f"{t} tiene espacios o tabulaciones sobrantes: {v!r}")

                # --- orden y dobles filas
                if s.segunda_fila:
                    if not (previa and previa.funcion == Funcion.SENALIZACION and not previa.segunda_fila):
                        err("2ª fila de doble bit sin su señalización en la fila anterior")
                    if s.tipo_punto != TipoPunto.DI:
                        err("la 2ª fila de un doble bit debe ser DI")
                else:
                    f = orden.get(s.funcion.value, len(orden))
                    if f < ultimo_orden:
                        err(f"fuera de orden: {s.funcion.value} después de una función posterior "
                            f"(orden {perfil.orden_funciones})")
                    ultimo_orden = max(ultimo_orden, f)
                    if s.funcion == Funcion.SENALIZACION and s.estado_id:
                        try:
                            if perfil.estado(s.estado_id)["bits"] == 2:
                                sig = campo.senales[i] if i < len(campo.senales) else None
                                if not (sig and sig.segunda_fila):
                                    err("señalización de doble bit sin 2ª fila")
                        except KeyError:
                            err(f"estado_id desconocido: {s.estado_id}")
                    if s.funcion == Funcion.COMANDO and s.par and s.par not in pares_sen:
                        avi(f"el comando no tiene señalización con par '{s.par}'")
                previa = s

                # --- tipo de punto
                if s.tipo_punto is None:
                    err("falta el tipo de punto (DI/AI/DO/AO)")
                elif s.tipo_punto.value not in TIPOS_POR_FUNCION[s.funcion]:
                    err(f"{s.funcion.value} no puede ser {s.tipo_punto.value}")
                tipo = s.tipo_punto.value if s.tipo_punto else "?"

                if s.segunda_fila:
                    if s.offset is None:
                        err("falta OFFSET")
                    else:
                        por_offset[(tipo, s.offset)].append(ub)
                    continue

                # --- tag, descripciones
                for p in tags.validar_tag(perfil, s):
                    err(p)
                if s.funcion != Funcion.RESERVA:
                    if not s.desc_scada:
                        avi("falta DESC. SCADA")
                    if not s.tag_hmi or not s.desc_hmi:
                        avi("falta TAG HMI o DESC. HMI")
                    if " " in s.tag_hmi:
                        err(f"TAG HMI con espacios: {s.tag_hmi!r}")
                if s.tag_scada and s.tag_scada != tags.NO_APLICA:
                    por_tag[s.tag_scada].append((ub, s))
                if s.desc_scada and s.desc_scada != "RESERVA":
                    por_desc[s.desc_scada].append((ub, s))
                if s.offset is None:
                    err("falta OFFSET")
                else:
                    por_offset[(tipo, s.offset)].append(ub)

                # --- estados / rangos / unidades
                if s.tipo_punto and not s.tipo_punto.es_analogico:
                    for k in ("s0", "s1", "s2", "s3"):
                        v = getattr(s, k)
                        if v not in estados_ok:
                            sug = _sugerir(v, estados_ok)
                            (err if sug else avi)(f"{k.upper()} '{v}' no es un estado del perfil{sug}")
                    if s.estado_id:
                        try:
                            e = perfil.estado(s.estado_id)
                            if (s.s0, s.s1, s.s2, s.s3) != (e["s0"], e["s1"], e["s2"], e["s3"]):
                                avi(f"los estados no coinciden con '{s.estado_id}'")
                        except KeyError:
                            pass
                    if s.unidad != NA:
                        err(f"una señal digital lleva UNITS N/A, no '{s.unidad}'")
                elif s.tipo_punto:
                    try:
                        v = [float(getattr(s, k)) for k in ("s0", "s1", "s2", "s3")]
                    except (TypeError, ValueError):
                        avi("MIN/MAX RAW y EU de una medición deben ser números (completar MIN/MAX EU)")
                    else:
                        if v[0] >= v[1] or v[2] >= v[3]:
                            err("MIN debe ser menor que MAX (RAW y EU)")
                    if s.unidad not in unidades_ok:
                        err(f"UNITS '{s.unidad}' no está en la lista del perfil{_sugerir(s.unidad, unidades_ok)}")
                    elif s.unidad == NA and s.medicion_codigo not in (None, "AFP"):
                        avi("una medición sin unidad (N/A)")

                # --- placa / entrada
                if s.tipo_punto in (TipoPunto.DI, TipoPunto.DO):
                    if (s.placa == NA) != (s.entrada == NA):
                        err("PLACA y ENTRADA deben completarse juntas (o ambas N/A)")
                    elif s.placa != NA:
                        nums = s.entrada.split("/")
                        if not all(x.isdigit() for x in nums):
                            err(f"ENTRADA con formato no válido: {s.entrada!r}")
                        else:
                            if s.tipo_punto == TipoPunto.DO and s.estado_id:
                                try:
                                    if perfil.estado(s.estado_id)["bits"] == 2 and len(nums) != 2:
                                        err(f"un comando de doble bit ocupa dos salidas (ej. '1/2'), no {s.entrada!r}")
                                except KeyError:
                                    pass
                            for x in nums:
                                por_entrada[(tipo, s.placa, int(x))].append(ub)
                elif s.tipo_punto and (s.placa != NA or s.entrada != NA):
                    avi("una señal analógica lleva PLACA/ENTRADA N/A")

    # --- duplicados globales
    for tag, lista in por_tag.items():
        if len(lista) > 1:
            funciones = sorted(s.funcion.value for _, s in lista)
            if funciones == ["COMANDO", "SEÑALIZACION"]:
                continue  # el comando comparte tag con su señalización
            out.append(Problema("error", lista[0][0], f"tag repetido {tag} en {len(lista)} filas"))
    for (tipo, off), lista in por_offset.items():
        if len(lista) > 1:
            out.append(Problema("error", lista[0], f"OFFSET {off} repetido en {len(lista)} filas {tipo}"))
    for desc, lista in por_desc.items():
        if len(lista) > 1:
            funciones = sorted(s.funcion.value for _, s in lista)
            if funciones == ["COMANDO", "SEÑALIZACION"]:
                continue
            out.append(Problema("error", lista[0][0], f"DESC. SCADA repetida '{desc}' en {len(lista)} filas"))
    for (tipo, placa, n), lista in por_entrada.items():
        if len(lista) > 1:
            out.append(Problema("error", lista[0], f"entrada {placa}.{n} ({tipo}) usada en {len(lista)} filas"))
    return out
