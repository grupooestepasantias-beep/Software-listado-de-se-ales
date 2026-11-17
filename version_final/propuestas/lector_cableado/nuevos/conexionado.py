"""Bornera y borne de EQUIPO de cada señal (columnas BORNERA EQUIPO y N° DE BORNE EQUIPO del formato completo).

Esos bornes son los del equipo de campo (interruptor `XP`/17, seccionador `L0`/41, protección `1XP1`/22…): NO están en los PDF
de ingeniería (ni como texto ni dibujados); salen del conexionado de cada equipo. Pero el equipo es el mismo de una obra a
otra: «Interruptor – Abierto» va al mismo borne en todos los campos que usan ese interruptor. Por eso se APRENDEN de un
listado oficial ya hecho (`herramientas/aprender_conexionado.py <Excel>`) y se guardan como DATOS en
`perfiles/<perfil>/conexionado_equipos.json`, que se puede corregir o ampliar a mano; el código no cambia de obra a obra.

Cómo se busca (sin adivinar):
  1. La señal se reconoce por su rótulo normalizado: sin tildes, con el código de equipo reemplazado por «#»
     («Interruptor 252 / 01 Abierto» y «Interruptor 25201 Abierto» -> «interruptor # abierto»; reconectador = interruptor).
  2. Se buscan las filas aprendidas con ese rótulo en el mismo NIVEL (33KV, 13,2KV…) y, si las hay, en el mismo TIPO DE CAMPO
     (primera palabra de la descripción del campo: «Entrada», «LM», «TR»…).
  3. Solo se completa si TODAS las filas que coinciden dan el mismo (bornera, borne). Si dos campos del mismo tipo difieren,
     o no hay ninguna, queda vacío: no se elige una.
Lo completado figura como dato de la REGLA (no del plano) y hay que confirmarlo contra el conexionado de la obra.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

ARCHIVO = "conexionado_equipos.json"
_TIERRA = re.compile(r"\b\d{2,3}\s*t\s*/?\s*\d{2,3}\b", re.I)       # 28T901, 189T03, 229T / 01: cuchilla/puesta a tierra
_CODIGO = re.compile(r"\b\d{3}\s*[A-Z]{0,2}\s*/?\s*\d{2}\b|\b\d{3,5}[A-Z]{0,2}\d{0,2}\b", re.I)    # 252 / 01, 25201
_ALIAS = (("reconectador", "interruptor"), ("apertura", "abrir"), ("cierre", "cerrar"), ("abiertos", "abierto"),
          ("remota", "remoto"), ("desenergizado", "falta tension"))


def _sin_tildes(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def clave_de(texto: str) -> str:
    """Rótulo normalizado de una señal para reconocerla de una obra a otra."""
    t = _sin_tildes(texto or "").lower()
    t = _TIERRA.sub("#t", t)               # «#t»: el código de una puesta a tierra, que NO es el del seccionador común
    t = _CODIGO.sub("#", t)
    t = re.sub(r"[^a-z0-9#/]+", " ", t)
    for viejo, nuevo in _ALIAS:
        t = re.sub(rf"\b{viejo}\b", nuevo, t)
    return " ".join(t.split())


UMBRAL = 0.75        # parecido mínimo entre el rótulo de la señal y el de la regla
MARGEN = 0.1         # cuánto mejor tiene que ser la mejor regla que la siguiente
_VACIAS = {"de", "del", "la", "el", "los", "las", "en", "y", "a", "por", "con", "al", "un", "una", "tv", "llave"}


def _palabras(texto: str) -> list[str]:
    """Palabras comparables: sin código de equipo, con las abreviaturas del plano expandidas («Transf.» = «transformador»)."""
    import bornes
    salida = []
    for w in clave_de(texto).replace("#", " ").replace("/", " ").split():
        w = bornes.ABREVIATURAS.get(w, w)
        w = {"trafo": "transformador", "tpo1": "tp01", "tr01": "tp01", "secun": "secundario", "venti": "ventilacion"}.get(w, w)
        if w not in _VACIAS:
            salida.append(w)
    return salida


def _parecido(a: list[str], b: list[str]) -> float:
    if not a or not b:
        return 0.0
    def igual(x, y):
        return x == y or (min(len(x), len(y)) >= 4 and (x.startswith(y) or y.startswith(x)))
    acierta = sum(1 for w in b if any(igual(w, x) for x in a))
    return acierta / max(len(a), len(b))


def tipo_de_campo(descripcion: str) -> str:
    """Primera palabra (solo letras) de la descripción del campo: «TR01 Lado 33KV» -> «tr»; «Entrada TR01» -> «entrada»."""
    m = re.search(r"[a-z]+", _sin_tildes(descripcion or "").lower())
    return m.group(0) if m else ""


def nivel_normal(nivel: str) -> str:
    return re.sub(r"[^A-Z0-9,]+", "", _sin_tildes(nivel or "").upper())


@dataclass(frozen=True)
class Regla:
    clave: str
    nivel: str
    tipo_campo: str
    bornera: str
    borne: str
    fuente: str = ""
    etiqueta: str = ""        # rótulo original del listado de donde se aprendió (para el parecido)


class Conexionado:
    def __init__(self, reglas: Optional[list[Regla]] = None):
        self.reglas: list[Regla] = list(reglas or [])
        self._por_clave: dict[str, list[Regla]] = {}
        for r in self.reglas:
            self._por_clave.setdefault(r.clave, []).append(r)

    @classmethod
    def cargar(cls, carpeta_perfil) -> "Conexionado":
        ruta = Path(carpeta_perfil) / ARCHIVO
        if not ruta.is_file():
            return cls()
        datos = json.loads(ruta.read_text(encoding="utf-8"))
        return cls([Regla(**r) for r in datos.get("reglas", [])])

    def guardar(self, carpeta_perfil, nota: str = "") -> Path:
        ruta = Path(carpeta_perfil) / ARCHIVO
        datos = {"nota": nota or "Bornera y borne de equipo aprendidos de un listado oficial. Se pueden corregir a mano.",
                 "reglas": [r.__dict__ for r in sorted(self.reglas, key=lambda r: (r.nivel, r.clave, r.tipo_campo, r.bornera, r.borne))]}
        ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=1), encoding="utf-8")
        return ruta

    def buscar(self, etiqueta: str, nivel: str = "", descripcion_campo: str = "", campo: str = "") -> tuple[str, str]:
        """(bornera, borne) de equipo para esa señal, o ('', '') si no se sabe con certeza.

        Una bornera aprendida como plantilla («1XP{c}») usa el último dígito del número de campo (campo 103 -> «1XP3»)."""
        candidatas = self._por_clave.get(clave_de(etiqueta), []) or self._parecidas(etiqueta)
        if not candidatas:
            return "", ""
        n = nivel_normal(nivel)
        en_nivel = [r for r in candidatas if not r.nivel or not n or nivel_normal(r.nivel) == n]
        tipo = tipo_de_campo(descripcion_campo)
        for grupo in ([r for r in en_nivel if tipo and r.tipo_campo == tipo], en_nivel):
            valores = {(r.bornera, r.borne) for r in grupo}
            if len(valores) == 1:
                bornera, borne = next(iter(valores))
                if "{c}" in bornera:
                    digito = re.search(r"(\d)\D*$", campo or "")
                    if not digito:
                        return "", ""
                    bornera = bornera.replace("{c}", digito.group(1))
                return bornera, borne
            if len(valores) > 1:                      # hay datos pero no coinciden: no se elige uno
                return "", ""
        return "", ""

    def _parecidas(self, etiqueta: str) -> list[Regla]:
        """Sin coincidencia exacta: las reglas cuyo rótulo se parece lo suficiente (palabras con las abreviaturas del plano,
        sin el código de equipo). Solo si UNA clave es claramente la mejor; si dos quedan casi iguales, ninguna."""
        a = _palabras(etiqueta)
        if len(a) < 2:
            return []
        puntajes: dict[str, float] = {}
        for clave in self._por_clave:
            puntajes[clave] = _parecido(a, _palabras(clave))
        orden = sorted(puntajes.items(), key=lambda kv: -kv[1])
        if not orden or orden[0][1] < UMBRAL:
            return []
        if len(orden) > 1 and orden[0][1] - orden[1][1] < MARGEN and orden[1][1] >= UMBRAL:
            return []
        return self._por_clave[orden[0][0]]

    def __len__(self):
        return len(self.reglas)


_CACHE: dict[str, Conexionado] = {}


def del_perfil(perfil) -> Conexionado:
    """La tabla del perfil (cacheada)."""
    carpeta = str(getattr(perfil, "carpeta", perfil))
    if carpeta not in _CACHE:
        _CACHE[carpeta] = Conexionado.cargar(carpeta)
    return _CACHE[carpeta]
