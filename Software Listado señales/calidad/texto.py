"""Normalizacion de una descripcion: reglas controladas, cada una registrada.

`normalizar` no sabe nada de Excel ni de EPEN: recibe el texto, la letra de columna, el NIVEL de la fila y las
reglas del cliente. Devuelve el texto final, los pasos aplicados (para el registro de cambios) y las dudas que
quedan para revision humana (no se corrigen por suposicion)."""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

from .reglas import Reglas

ALTA, MEDIA = "alta", "media"

RE_KV = re.compile(r"(?<![\w.,])(\d+)(?:[.,](\d+))?\s*[kK][vV](?![A-Za-z0-9])")
RE_KV_FINAL = re.compile(r"(?<![\w.,])(\d+(?:,\d+)?)kV\b")
RE_SIN_UNIDAD = re.compile(r"((?i:\bcampo\s+\d+\s+))(\d+(?:,\d+)?)(?=\s+(?!kV\b)[A-Za-z])")
RE_SEPARADOR = re.compile(r"(?<=[0-9A-Za-z\x00])- (?=\S)")
RE_CAMPO_PEGADO = re.compile(r"\b(Campo|CAMPO|campo)(?=\d)")
RE_REPETIDA = re.compile(r"\b([A-Za-z]{3,})\s+\1\b", re.IGNORECASE)


@dataclass
class Paso:
    tipo: str          # ortografia | espacios | formato | nomenclatura | tildes
    regla: str
    antes: str
    despues: str
    confianza: str
    motivo: str


@dataclass
class Duda:
    tipo: str          # nivel_distinto | palabra_repetida | excede_largo | largo_previo | tension_sin_unidad
    detalle: str
    propuesta: str = ""


@dataclass
class Resultado:
    original: str
    final: str
    pasos: list = field(default_factory=list)
    dudas: list = field(default_factory=list)


def numero_de_nivel(nivel) -> str | None:
    """'33KV' -> '33', '6,6KV' / '6.6kV' -> '6,6'; 'SSAA' u otro no numerico -> None."""
    if not isinstance(nivel, str):
        return None
    m = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*[kK][vV]\s*", nivel)
    return m.group(1).replace(".", ",") if m else None


def sin_tildes(t: str) -> str:
    return unicodedata.normalize("NFC", "".join(
        c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn"))


def _conservar_caja(original: str, nuevo: str) -> str:
    if original.isupper():
        return nuevo.upper()
    if original[:1].isupper():
        return nuevo[:1].upper() + nuevo[1:]
    return nuevo[:1].lower() + nuevo[1:]


def _enmascarar(t: str, patrones) -> tuple[str, list[str]]:
    guardados: list[str] = []

    def sub(m):
        guardados.append(m.group(0))
        return f"\x00{len(guardados) - 1}\x00"
    for p in patrones:
        t = p.sub(sub, t)
    return t, guardados


def _restaurar(t: str, guardados: list[str]) -> str:
    return re.sub(r"\x00(\d+)\x00", lambda m: guardados[int(m.group(1))], t)


def normalizar(texto: str, letra: str, reglas: Reglas, nivel=None) -> Resultado:
    res = Resultado(texto, texto)
    if not isinstance(texto, str) or texto.strip() in reglas.intactos or texto.startswith("="):
        return res
    guardados: list[str] = []
    actual, guardados = _enmascarar(texto, reglas.patrones)
    num_nivel = numero_de_nivel(nivel)
    datos = reglas.datos

    def paso(tipo, regla, nuevo, confianza, motivo):
        nonlocal actual
        if nuevo != actual:
            res.pasos.append(Paso(tipo, regla, _restaurar(actual, guardados), _restaurar(nuevo, guardados),
                                  confianza, motivo))
            actual = nuevo

    # 1. espacios
    limpio = "\n".join(re.sub(r"[ \t\u00a0]+", " ", ln).strip() for ln in actual.split("\n")).strip()
    paso("espacios", "espacios", limpio, ALTA, "espacios dobles, al borde o no separables")

    # 2. separadores y 'Campo04'
    if datos.get("separadores", True):
        paso("formato", "separador_guion", RE_SEPARADOR.sub(" - ", actual), ALTA, "'X- texto' -> 'X - texto' (estilo del ETAP)")
    if datos.get("campo_pegado", True):
        paso("formato", "campo_pegado", RE_CAMPO_PEGADO.sub(r"\1 ", actual), ALTA, "'Campo04' -> 'Campo 04'")

    # 3. tension: 33KV / 33Kv / 33 KV / 6.6KV -> 33kV / 6,6kV
    t = datos.get("tension")
    if t:
        unidad, dec = t.get("unidad", "kV"), t.get("decimal", ",")

        def kv(m):
            return m.group(1) + (dec + m.group(2) if m.group(2) else "") + unidad
        paso("formato", "tension_unidad", RE_KV.sub(kv, actual), ALTA,
             f"unidad de tension uniforme ({unidad}, decimal '{dec}')")

        def completar(m):
            if m.group(2) not in t.get("niveles", []):
                return m.group(0)
            if num_nivel is not None and m.group(2) == num_nivel:
                return f"{m.group(1)}{m.group(2)}{unidad}"
            res.dudas.append(Duda("tension_sin_unidad",
                                  f"'{m.group(2)}' sin unidad y el NIVEL de la fila ({nivel}) no lo confirma"))
            return m.group(0)
        paso("ortografia", "tension_sin_unidad", RE_SIN_UNIDAD.sub(completar, actual), MEDIA,
             "numero de nivel sin unidad que coincide con el NIVEL de la fila")

    # 4. errores conocidos (diccionario configurable)
    for mal, bien in datos.get("errores_conocidos", {}).items():
        if mal == bien:
            continue
        rx = re.compile(rf"\b{re.escape(mal)}\b", re.IGNORECASE)
        paso("ortografia", f"error_conocido:{mal}",
             rx.sub(lambda m, b=bien: _conservar_caja(m.group(0), b), actual), ALTA, f"'{mal}' -> '{bien}'")

    # 5. terminos / siglas
    for r in datos.get("terminos", []):
        if letra not in r.get("columnas", [letra]):
            continue
        rx = re.compile(rf"(?<![\w]){re.escape(r['buscar'])}(?![\w])")
        paso("nomenclatura", r.get("regla", "termino"), rx.sub(r["poner"], actual), ALTA, r.get("motivo", ""))

    # 6. tildes segun el sistema destino
    modo = reglas.modo_tildes
    if modo == "quitar":
        paso("tildes", "sin_tildes", sin_tildes(actual), ALTA, "el sistema destino y el ETAP usan ASCII")
    elif modo == "agregar":
        for sin, con in datos["tildes"]["diccionario"].items():
            rx = re.compile(rf"\b{re.escape(sin)}\b", re.IGNORECASE)
            paso("tildes", f"tilde:{sin}", rx.sub(lambda m, c=con: _conservar_caja(m.group(0), c), actual), ALTA,
                 f"'{sin}' -> '{con}'")

    final = _restaurar(actual, guardados)

    # dudas que no se corrigen solas
    for m in RE_REPETIDA.finditer(final):
        res.dudas.append(Duda("palabra_repetida", f"'{m.group(0)}' repetida", propuesta=m.group(1)))
    if num_nivel is not None:
        for m in RE_KV_FINAL.finditer(final):
            if m.group(1) != num_nivel and m.group(1) in datos.get("tension", {}).get("niveles", []):
                res.dudas.append(Duda("nivel_distinto",
                                      f"el texto dice {m.group(1)}kV y el NIVEL de la fila es {nivel}"))

    # largo del sistema destino: una correccion nunca puede pasar el limite
    limite = reglas.largo(letra)
    if limite and len(final) > limite:
        if len(texto) <= limite:
            res.dudas.append(Duda("excede_largo", f"la correccion mediria {len(final)} > {limite}", propuesta=final))
            res.final, res.pasos = texto, []
            return res
        res.dudas.append(Duda("largo_previo", f"mide {len(final)} y el limite es {limite} (ya excedia antes)"))
    if texto.strip() and not final.strip():
        res.dudas.append(Duda("vaciado", "la correccion dejaba la celda vacia", propuesta=""))
        res.final, res.pasos = texto, []
        return res
    res.final = final
    return res
