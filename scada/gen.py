"""Motor SCADA: completa las columnas H-O (tag, offset, descripción SCADA, estados, unidades) de un
Proyecto cuya tabla A-G ya está (nivel, campo, controlador, función, TAG HMI, DESC. HMI).

Entrada por señal (modelo.Senal): funcion, desc_hmi (con el prefijo del campo), segunda_fila (la 2ª fila de un
doble bit va en blanco), es_reserva. Opcionales: estado_id, medicion_codigo, par (si el usuario ya los sabe).
Salida: tag_scada, offset, desc_scada, s0-s3, unidad, tipo_punto (+ estado_id, medicion_codigo, par).
Todo lo que está en Senal.fijos (editado a mano) se respeta. Las reglas están en perfiles/<cliente>/scada.json.
"""
from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from modelo import NA, Campo, Funcion, Nivel, Proyecto, Senal, TipoPunto  # noqa: E402

from . import descripcion  # noqa: E402
from . import texto as tx  # noqa: E402
from .perfil import PerfilScada  # noqa: E402

ESTADOS = ("s0", "s1", "s2", "s3")
TIPO_POR_FUNCION = {Funcion.ALARMAS: TipoPunto.DI, Funcion.SENALIZACION: TipoPunto.DI,
                    Funcion.COMANDO: TipoPunto.DO, Funcion.MEDICION: TipoPunto.AI, Funcion.RESERVA: TipoPunto.DI}
# Palabras que describen el estado (no el equipo): se quitan para emparejar una señalización con su comando.
PALABRAS_ESTADO = {
    "abierto", "cerrado", "abrir", "cerrar", "apertura", "cierre", "local", "remoto", "en", "de", "del", "la", "el", "y",
    "manual", "automatico", "automatica", "habilitar", "deshabilitar", "habilitado", "deshabilitado", "subir", "bajar",
    "marcha", "parada", "arranque", "extraido", "insertado", "telecontrol", "distancia", "mando", "d", "t", "-",
}


class ErrorGeneracion(ValueError):
    """Falta un dato que el software tiene que pedir al usuario (ej. offset inicial)."""


@dataclass
class Informe:
    avisos: list[str] = field(default_factory=list)
    pendientes: list[dict] = field(default_factory=list)   # descripciones SCADA a completar a mano
    origen: Counter = field(default_factory=Counter)        # cuántas DESC. SCADA salieron de usuario/glosario/reglas
    eu_por_defecto: int = 0                                  # mediciones con MIN/MAX EU calculados (RAW x factor)
    propuestas: list[dict] = field(default_factory=list)    # DESC. SCADA propuestas por palabras: a confirmar

    def aviso(self, ubic: str, msg: str) -> None:
        self.avisos.append(f"{ubic}: {msg}")


class _Offsets:
    def __init__(self, iniciales: dict[str, int], separacion: dict[str, int]):
        self.sig = {k: int(v) for k, v in iniciales.items()}
        self.separacion = separacion

    def tomar(self, tipo: str, n: int = 1) -> int:
        if tipo not in self.sig:
            raise ErrorGeneracion(f"falta el OFFSET inicial de {tipo}: hay que preguntarlo al usuario")
        v = self.sig[tipo]
        self.sig[tipo] += n
        return v

    def reservar(self, tipo: str, hasta: int) -> None:
        self.sig[tipo] = max(self.sig.get(tipo, hasta), hasta)

    def separar(self, tipos: set[str]) -> None:
        for t in tipos:
            if t in self.sig:
                self.sig[t] += self.separacion.get(t, 0)


# ---------------------------------------------------------------- campo / tag
def resolver_campo(perfil: PerfilScada, nivel: Nivel, campo: Campo, prefijo: str) -> tuple[Optional[str], Optional[str]]:
    """(dígito de nivel | None, código de campo | None). Especiales (TP1, SACC, UTR...) no llevan nivel."""
    esp = {c.upper() for c in perfil.tag["campos_especiales"]}
    for cand in (campo.numero, prefijo):
        if cand and cand.strip().upper() in esp:
            return None, cand.strip().upper()
    m = re.match(r"^(\d)(\d{2})", prefijo or "")
    if m:
        return m.group(1), m.group(2)
    if campo.numero and re.fullmatch(r"\d{2}", campo.numero.strip()) and nivel.codigo:
        return nivel.codigo, campo.numero.strip()
    m = re.search(r"\b(TP\d|RN\d)\b", (campo.descripcion or "").upper())
    if m and m.group(1) in esp:
        return None, m.group(1)
    return None, None


def construir_tag(perfil: PerfilScada, base: str, variable: int, *, bits: Optional[int] = None,
                  comando: bool = False, medicion: Optional[str] = None) -> str:
    cfg = perfil.tag
    dv = cfg["digitos_variable"]
    if not 0 <= variable < 10 ** dv:
        raise ErrorGeneracion(f"variable fuera de rango (0-{10 ** dv - 1}): {variable}")
    if medicion:
        return f"{base}.{variable:0{dv}d}{medicion}"
    if bits not in cfg["bits_validos"]:
        raise ErrorGeneracion(f"bits debe ser {cfg['bits_validos']}: {bits}")
    return f"{base}.{variable:0{dv}d}{bits}{cfg['sufijo_comando'] if comando else ''}"


def _proxima(v: int, usadas: set[int], saltear: set[int], tope: int) -> int:
    while v in usadas or v in saltear:
        v += 1
    if v >= tope:
        raise ErrorGeneracion("el campo no tiene más variables libres (00-99)")
    return v


# ---------------------------------------------------------------- estados / mediciones
def detectar_familia(perfil: PerfilScada, funcion: Funcion, texto_norm: str) -> Optional[dict]:
    clave = "senalizacion" if funcion == Funcion.SENALIZACION else "comando"
    for f in perfil.estados["familias"]:
        if any(re.search(rx, texto_norm) for rx in f.get(clave, [])):
            return f
    return None


def detectar_medicion(perfil: PerfilScada, texto_norm: str) -> Optional[dict]:
    for m in perfil.mediciones["juego"]:
        if re.search(m["patron"], texto_norm):
            return m
    return None


def clave_par(texto: str) -> str:
    """Texto sin las palabras de estado: 'Seccionador 329SA03 Abierto/Cerrado' y '... Abrir/Cerrar' coinciden."""
    palabras = [p for p in re.split(r"[\s/\-–]+", tx.norm(texto)) if p and p not in PALABRAS_ESTADO]
    return " ".join(palabras)


# ---------------------------------------------------------------- generación
def generar_scada(proyecto: Proyecto, perfil: PerfilScada, glosario: Optional[descripcion.Glosario] = None,
                  con_propuestas: bool = True) -> Informe:
    """Completa H-O de todas las señales (en el lugar). Lanza ErrorGeneracion si falta un offset inicial.
    con_propuestas: lo que no se puede resolver con reglas/glosario se completa con una propuesta por palabras
    (queda en Informe.propuestas para que el usuario la confirme); con False queda vacío y en Informe.pendientes."""
    glosario = glosario if glosario is not None else descripcion.Glosario.cargar(perfil.ruta_glosario)
    inf = Informe()
    offsets = _Offsets(proyecto.offsets_iniciales, perfil.offsets["separacion_entre_campos"])
    for nivel in proyecto.niveles:
        for campo in nivel.campos:
            _campo(proyecto, perfil, glosario, nivel, campo, offsets, inf, con_propuestas)
    return inf


def _campo(proyecto, perfil, glosario, nivel, campo, offsets, inf, con_propuestas) -> None:
    cfg = perfil.tag
    orden = {f: i for i, f in enumerate(perfil.datos["orden_funciones"])}
    # grupos: cada señal con su 2ª fila; se ordena por función (reservas al final) sin separar los grupos
    grupos: list[list[Senal]] = []
    for s in campo.senales:
        if s.segunda_fila and grupos:
            grupos[-1].append(s)
        elif not s.segunda_fila:
            grupos.append([s])
    grupos.sort(key=lambda g: orden.get(g[0].funcion.value, len(orden)))
    principales = [g[0] for g in grupos]

    prefijo = campo.prefijo or tx.prefijo_comun([s.desc_hmi for s in principales])
    ubic_c = f"{nivel.nombre} / {campo.numero or campo.descripcion}"
    dig, cod = resolver_campo(perfil, nivel, campo, prefijo)
    base = (f"{dig}{cod}" if dig else cod) if cod else None
    solo_reservas = all(x.funcion == Funcion.RESERVA or x.es_reserva for x in principales)
    if base is None and not solo_reservas:
        inf.aviso(ubic_c, "no se pudo deducir el campo del tag (¿prefijo del campo?); los tags quedan vacíos")
    nivel_tag = dig or ""
    v0 = cfg["variable_inicial_por_campo"].get(base, cfg["variable_inicial"]) if base else cfg["variable_inicial"]
    tope = 10 ** cfg["digitos_variable"]
    usadas: set[int] = set()
    usadas_med: set[int] = set()
    for s in principales:  # variables ya fijadas a mano
        m = re.match(r"^\w+\.(\d{2})(\w*)$", s.tag_scada or "") if "tag_scada" in s.fijos else None
        if m:
            (usadas_med if re.search(r"[A-Z]{2}", m.group(2)) else usadas).add(int(m.group(1)))
    v, m = v0, cfg["variable_inicial_medicion"]
    saltear_med = set(perfil.mediciones["saltear_variable_por_nivel"].get(nivel_tag, []))

    # 1) familias de estado y emparejamiento señalización <-> comando
    familia: dict[int, Optional[dict]] = {}
    for s in principales:
        if s.funcion in (Funcion.SENALIZACION, Funcion.COMANDO):
            if s.estado_id:
                try:
                    familia[id(s)] = perfil.familia(s.estado_id.split("_", 1)[-1])
                except KeyError:
                    familia[id(s)] = None
            else:
                familia[id(s)] = detectar_familia(perfil, s.funcion, tx.norm(s.desc_hmi))
    sen_por_clave: dict[tuple[str, str], Senal] = {}
    for s in principales:
        f = familia.get(id(s))
        if s.funcion == Funcion.SENALIZACION and f:
            sen_por_clave.setdefault((f["id"], s.par or clave_par(s.desc_hmi)), s)
    comandos_con_sen = {(familia[id(s)]["id"], s.par or clave_par(s.desc_hmi)) for s in principales
                        if s.funcion == Funcion.COMANDO and familia.get(id(s))}

    for clave_p in comandos_con_sen:  # la señalización guarda el enlace con su comando (para propagar lo que se confirme)
        pareja = sen_por_clave.get(clave_p)
        if pareja is not None and not pareja.par:
            pareja.par = clave_p[1]

    tipos_usados: set[str] = set()
    nuevos: list[Senal] = []
    meta: dict[int, dict] = {}   # id(señal) -> texto/origen de su DESC. SCADA (para distinguir repetidas)
    for n, g in enumerate(grupos, 1):
        s = g[0]
        ubic = f"{ubic_c} / fila {n} ({s.desc_hmi or s.funcion.value})"
        fija = lambda nombre, s=s: nombre in s.fijos  # noqa: E731
        if s.tipo_punto is None:
            s.tipo_punto = TIPO_POR_FUNCION[s.funcion]
        tipo = s.tipo_punto.value
        tipos_usados.add(tipo)
        _, texto_hmi = tx.separar_prefijo(s.desc_hmi)
        seg: Optional[Senal] = None

        def offset(t: str, cuantos: int = 1, s=s, fija=fija) -> None:
            if fija("offset") and s.offset is not None:
                offsets.reservar(t, s.offset + cuantos)
            else:
                s.offset = offsets.tomar(t, cuantos)

        if s.funcion == Funcion.RESERVA or s.es_reserva:
            r = perfil.datos["reservas"]
            for nombre, valor in (("tag_scada", r["tag"]), ("desc_scada", r["desc_scada"])):
                if not fija(nombre):
                    setattr(s, nombre, valor)
            for e in ESTADOS:
                if not fija(e):
                    setattr(s, e, NA)
            if not fija("unidad"):
                s.unidad = NA
            offset(tipo)

        elif s.funcion == Funcion.MEDICION:
            md = detectar_medicion(perfil, tx.norm(s.desc_hmi or s.observaciones))
            if s.medicion_codigo:
                md = next((x for x in perfil.mediciones["juego"] if x["codigo"] == s.medicion_codigo
                           and (not s.unidad or x["unidad"] == s.unidad)), md)
            if md is None:
                inf.aviso(ubic, "medición no reconocida: se necesita el código (AU, AR, AP...)")
            else:
                s.medicion_codigo = md["codigo"]
                serv = cod in perfil.mediciones["servicios_auxiliares"]["campos"]
                raw = md["raw"]
                unidad = md["unidad"]
                if serv:
                    sa = perfil.mediciones["servicios_auxiliares"]
                    if md["codigo"] in ("AU", "AV", "AW"):
                        raw, unidad = sa["raw_tension"], sa["unidad_tension"]
                    elif md["codigo"] in ("AR", "AS", "AT") and md["unidad"] == "A":
                        raw = sa["raw_corriente"]
                mx = perfil.mediciones["max_raw"]
                mn = -(mx + 1) if raw == "signed" else 0
                if base and not fija("tag_scada"):
                    var = _proxima(m, usadas_med, saltear_med, tope)
                    usadas_med.add(var)
                    m = var + 1
                    s.tag_scada = construir_tag(perfil, base, var, medicion=md["codigo"])
                for nombre, valor in (("s0", mn), ("s1", mx), ("s2", round(mn * md["factor"], 2)),
                                      ("s3", round(mx * md["factor"], 2))):
                    if not fija(nombre):
                        setattr(s, nombre, valor)
                if not fija("unidad"):
                    s.unidad = unidad
                if not fija("desc_scada") and md.get("desc"):
                    s.desc_scada = f"{prefijo} {md['desc']}".strip()
                    s.desc_scada_origen = "reglas"
                if not fija("s2") and not fija("s3"):
                    inf.eu_por_defecto += 1
            offset(tipo)

        elif s.funcion == Funcion.COMANDO and familia.get(id(s)) and \
                (familia[id(s)]["id"], s.par or clave_par(s.desc_hmi)) in sen_por_clave:
            pareja = sen_por_clave[(familia[id(s)]["id"], s.par or clave_par(s.desc_hmi))]
            s.par = s.par or clave_par(s.desc_hmi)
            for nombre in ("tag_scada", "desc_scada"):
                if not fija(nombre):
                    setattr(s, nombre, getattr(pareja, nombre))
            if not fija("desc_scada"):
                s.desc_scada_origen = pareja.desc_scada_origen
            if perfil.offsets["comando"] == "compartido":
                if not fija("offset"):
                    s.offset = pareja.offset
            else:
                offset(tipo)
            _estados(perfil, s, familia[id(s)], inf, ubic)

        else:  # alarma, señalización o comando sin pareja
            f = familia.get(id(s))
            if s.funcion == Funcion.ALARMAS:
                _alarma(perfil, s, tx.norm(s.desc_hmi), inf, ubic)
                bits = 1
            else:
                if f is None:
                    inf.aviso(ubic, "no se pudo deducir el tipo de estados (Abierto/Cerrado, Local/Remoto...)")
                else:
                    _estados(perfil, s, f, inf, ubic)
                bits = f["bits"] if f else 2
            clave_p = (f["id"], s.par or clave_par(s.desc_hmi)) if f else None
            con_comando = s.funcion == Funcion.SENALIZACION and clave_p in comandos_con_sen
            if base and not fija("tag_scada"):
                var = _proxima(v, usadas, set(), tope)
                usadas.add(var)
                v = var + 1
                s.tag_scada = construir_tag(perfil, base, var, bits=bits,
                                            comando=s.funcion == Funcion.COMANDO or con_comando)
            filas = 2 if (s.funcion == Funcion.SENALIZACION and bits == 2) else 1
            offset(tipo, filas)
            if s.funcion == Funcion.SENALIZACION and filas == 2:
                seg = next((x for x in g[1:] if x.segunda_fila), None) or Senal(funcion=s.funcion, segunda_fila=True)
                seg.funcion, seg.tipo_punto, seg.controlador = s.funcion, TipoPunto.DI, seg.controlador or s.controlador
                seg.offset = (s.offset or 0) + 1
                seg.tag_scada, seg.desc_scada = "", ""
                seg.s0 = seg.s1 = seg.s2 = seg.s3 = ""
                seg.unidad = NA

        # descripción SCADA (alarmas, señalizaciones y comandos sueltos)
        if s.funcion in (Funcion.ALARMAS, Funcion.SENALIZACION, Funcion.COMANDO) and not fija("desc_scada") \
                and not s.desc_scada and texto_hmi:
            estado = (familia.get(id(s)) or {}).get("id")
            res = descripcion.proponer(prefijo, texto_hmi, estado, perfil, glosario, con_propuestas)
            inf.origen[res.origen] += 1
            if res.desc:
                s.desc_scada = res.desc
                s.desc_scada_origen = res.origen
            meta[id(s)] = {"texto": texto_hmi, "ubicacion": ubic, "origen": res.origen}
            if res.origen == "propuesta":
                inf.propuestas.append({"ubicacion": ubic, "texto": s.desc_hmi, "propuesta": res.desc,
                                       "senal": s, "prefijo": prefijo, "texto_hmi": texto_hmi})
            elif res.origen == "pendiente":
                inf.pendientes.append({"ubicacion": ubic, "texto": s.desc_hmi, "motivo": res.motivo, "senal": s})
        if s.funcion in (Funcion.ALARMAS, Funcion.SENALIZACION, Funcion.COMANDO) and not fija("unidad"):
            s.unidad = NA

        nuevos.append(s)
        if seg is not None:
            nuevos.append(seg)
        elif len([x for x in g[1:] if x.segunda_fila]) and s.funcion == Funcion.SENALIZACION:
            inf.aviso(ubic, "sobra una 2ª fila: la señalización es de 1 bit; se descartó")
    _desambiguar(perfil, glosario, prefijo, nuevos, meta, inf, ubic_c)
    for s in principales:  # el comando vuelve a copiar la descripción de su señalización (pudo cambiar al distinguirla)
        f = familia.get(id(s))
        if s.funcion == Funcion.COMANDO and s.par and f and "desc_scada" not in s.fijos \
                and (f["id"], s.par) in sen_por_clave:
            pareja = sen_por_clave[(f["id"], s.par)]
            s.desc_scada, s.desc_scada_origen = pareja.desc_scada, pareja.desc_scada_origen
    campo.senales = nuevos
    offsets.separar(tipos_usados)


def _desambiguar(perfil, glosario, prefijo, filas, meta, inf, ubic_campo) -> None:
    """Dos señales de un campo no pueden llamarse igual. Si las repetidas eran propuestas, se vuelve a proponer
    conservando las palabras que distinguen a cada una; si no se logra (o no eran propuestas) queda un aviso."""
    grupos: dict[str, list[Senal]] = {}
    for s in filas:
        if s.segunda_fila or not s.desc_scada or s.funcion in (Funcion.RESERVA, Funcion.MEDICION):
            continue
        if s.funcion == Funcion.COMANDO and s.par:   # copia la de su señalización: es igual a propósito
            continue
        grupos.setdefault(s.desc_scada, []).append(s)
    for desc, grupo in grupos.items():
        if len(grupo) < 2:
            continue
        palabras = {id(s): set(re.split(r"[^a-z0-9]+", tx.norm(meta[id(s)]["texto"]))) - {""}
                    for s in grupo if id(s) in meta}
        for s in grupo:
            m = meta.get(id(s))
            if not m or m["origen"] != "propuesta":
                continue
            otras = set().union(*[v for k, v in palabras.items() if k != id(s)]) if len(palabras) > 1 else set()
            propias = palabras[id(s)] - otras
            nueva = descripcion.abreviar_por_palabras(prefijo, m["texto"], perfil, glosario, frozenset(propias)) \
                if propias else None
            if nueva and nueva != desc:
                s.desc_scada = nueva
                for p in inf.propuestas:
                    if p["ubicacion"] == m["ubicacion"]:
                        p["propuesta"] = nueva
        restantes = Counter(x.desc_scada for x in grupo)
        for d, n in restantes.items():
            if n > 1:
                inf.aviso(ubic_campo, f"DESC. SCADA repetida «{d}» en {n} señales: hay que distinguirlas")


def _estados(perfil: PerfilScada, s: Senal, f: dict, inf: Informe, ubic: str) -> None:
    s.estado_id = ("sen_" if s.funcion == Funcion.SENALIZACION else "com_") + f["id"]
    for k, valor in zip(ESTADOS, f["s"]):
        if k not in s.fijos:
            setattr(s, k, valor)


def _alarma(perfil: PerfilScada, s: Senal, texto_norm: str, inf: Informe, ubic: str) -> None:
    al = perfil.estados["alarma"]
    falla = any(re.search(rx, texto_norm) for rx in al.get("falla_detectar", []))
    s.estado_id = "alarma_falla" if falla else "alarma_actuo"
    for k, valor in zip(ESTADOS, al["falla" if falla else "normal"]):
        if k not in s.fijos:
            setattr(s, k, valor)
    if not falla and any(re.search(rx, texto_norm) for rx in al.get("falla_revisar", [])):
        inf.aviso(ubic, "¿es una falla de equipo (NORMAL/FALLA) en vez de una actuación (NORMAL/ACTUO)? revisar")
