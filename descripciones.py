"""DESC. SCADA por reglas (lineamientos del cliente); lo que las reglas no definen se le pregunta al usuario.

Estructura (PDF de lineamientos, pág. 3): {nivel}{campo}{nombre del campo} + equipo + descripción, máx. 20.
  * equipo      INT, SBA, SBB, ST…    (reglas_descripcion.json → "equipo")
  * descripción F/U AUX, DIS, otros…  ("frase"; lo no definido es "abreviatura autodescriptiva": se pregunta)
  * estados y comandos: sin descripción (ej. Abierto/Cerrado); otros estados (Local/Remoto…) se preguntan
Las respuestas del usuario se guardan en plantillas/<id>/abreviaturas_usuario.json y no se vuelven a preguntar.
"""
from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from modelo import Funcion, Proyecto, Senal
from perfiles import Perfil

RAIZ_PLANTILLAS = Path(__file__).parent / "plantillas"
TIPOS = ("equipo", "frase", "estado", "texto", "largo")


def _norm(t: str) -> str:
    t = unicodedata.normalize("NFKD", t or "")
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    return " ".join(re.sub(r"[^a-z0-9#/ ]", " ", t).split())


@dataclass
class Pendiente:
    tipo: str        # equipo | frase | estado | texto | largo
    clave: str       # lo que se guarda en la memoria
    pregunta: str    # texto que ve el usuario
    ejemplo: str     # una señal que lo necesita
    borrador: str = ""
    maximo: int = 20  # largo máximo del texto a responder (ya descontado el prefijo si se conoce)
    respuesta: str = ""
    exacta: str = ""  # texto con sus números (para las respuestas que llevan números: TC3-01 ≠ TC3-02)


@dataclass
class Informe:
    por_reglas: int = 0
    por_memoria: int = 0
    pendientes: list[Pendiente] = field(default_factory=list)


class Reglas:
    def __init__(self, perfil: Perfil, base: Optional[Path] = None):
        carpeta = base or RAIZ_PLANTILLAS / perfil.id
        self.ruta_memoria = carpeta / "abreviaturas_usuario.json"
        self.maximo = perfil.largo_max("desc_scada") or 20
        datos = json.loads((carpeta / "reglas_descripcion.json").read_text(encoding="utf-8"))
        self.sinonimos = datos.get("sinonimos_equipo", {})
        self.equipo, self.frase, self.estado = datos["equipo"], datos["frase"], datos["estado"]
        self.texto = datos.get("texto", {})  # abreviaturas completas de señales sin equipo (del listado del cliente)
        self.memoria: dict[str, dict[str, str]] = {t: {} for t in TIPOS}
        if self.ruta_memoria.is_file():
            for t, d in json.loads(self.ruta_memoria.read_text(encoding="utf-8")).items():
                self.memoria.setdefault(t, {}).update(d)

    def guardar_memoria(self) -> None:
        self.ruta_memoria.write_text(json.dumps(self.memoria, ensure_ascii=False, indent=2, sort_keys=True),
                                     encoding="utf-8")

    def recordar(self, p: Pendiente) -> None:
        # una respuesta con números vale solo para ese texto exacto; sin números vale para todos los parecidos
        clave = p.exacta if p.exacta and re.search(r"\d", p.respuesta) else p.clave
        self.memoria[p.tipo][clave] = p.respuesta.strip()

    def buscar_texto(self, tipo: str, texto: str) -> Optional[tuple[str, str]]:
        """Abreviatura completa de un texto: primero la respuesta exacta, después la general."""
        exacta = _norm(texto)
        if exacta in self.memoria[tipo]:
            return self.memoria[tipo][exacta], "memoria"
        return self.buscar(tipo, re.sub(r"\d+", "#", exacta))

    # ---- consulta de una abreviatura: primero lo que dijo el usuario, después las reglas del cliente
    def buscar(self, tipo: str, clave: str) -> Optional[tuple[str, str]]:
        if clave in self.memoria[tipo]:
            return self.memoria[tipo][clave], "memoria"
        if tipo == "equipo":
            palabra, _, letras = clave.partition("|")
            r = self.equipo.get(palabra)
            if isinstance(r, dict):
                r = r.get(letras.upper())
            return (r, "reglas") if r is not None else None
        regla = getattr(self, tipo, {}).get(clave)
        return (regla, "reglas") if regla is not None else None


def analizar(texto: str, sinonimos: dict[str, str]) -> tuple[str, str, str]:
    """'Secc. 229SL04 Falta Tensión Auxiliar' -> ('seccionador', 'SL', 'falta tension auxiliar').
    Si el texto no empieza por un equipo conocido, la palabra de equipo es ''."""
    palabras = _norm(texto).split()
    if not palabras:
        return "", "", ""
    primera = sinonimos.get(palabras[0], palabras[0])
    if primera not in (set(sinonimos.values()) | {"interruptor", "seccionador"}):
        return "", "", " ".join(palabras)
    letras, resto = "", palabras[1:]
    if resto and re.fullmatch(r"(?=.*\d)[a-z0-9]+", resto[0]):  # código de equipo: 229sl04, 25204
        letras = "".join(re.findall(r"[a-z]+", resto[0])).upper()
        resto = resto[1:]
    return primera, letras, " ".join(re.sub(r"\d+", "#", sinonimos.get(w, w)) for w in resto)


def _unir(prefijo: str, *partes: str, maximo: int = 20) -> str:
    partes_ok = [p for p in partes if p]
    for sep in (" ", ""):  # el listado a veces pega las partes cuando no entran
        d = sep.join([prefijo, *partes_ok]) if sep else prefijo + "".join(partes_ok)
        if len(d) <= maximo:
            return d
    return ""


def proponer(s: Senal, prefijo: str, reglas: Reglas, informe: Informe) -> Optional[str]:
    """DESC. SCADA de una señal, o None si falta algún dato (queda anotado en el informe)."""
    eq, letras, frase = analizar(s.observaciones, reglas.sinonimos)
    ejemplo, falta, origenes = s.observaciones, [], []
    propia = reglas.buscar_texto("largo", s.observaciones)
    if propia:  # el usuario ya dio la abreviatura completa de esta señal
        informe_origen(informe, ["memoria"])
        return _unir(prefijo, propia[0], maximo=reglas.maximo) or None

    def pedir(tipo, clave, pregunta, borrador=""):
        if not any(p.tipo == tipo and p.clave == clave for p in informe.pendientes):
            informe.pendientes.append(Pendiente(tipo, clave, pregunta, ejemplo, borrador,
                                                max(reglas.maximo - len(prefijo) - 1, 1),
                                                exacta=_norm(s.observaciones) if tipo == "texto" else ""))
        falta.append(clave)

    # sin equipo reconocible: el texto completo es "autodescriptivo" y lo define el usuario
    if not eq:
        k = _norm(s.observaciones)
        r = reglas.buscar_texto("texto", s.observaciones)
        if r is None:
            pedir("texto", re.sub(r"\d+", "#", k), f"Abreviatura para «{s.observaciones}»")
            return None
        origenes.append(r[1])
        informe_origen(informe, origenes)
        return _unir(prefijo, r[0], maximo=reglas.maximo) or _largo(s, prefijo, reglas, informe, ejemplo)

    r_eq = reglas.buscar("equipo", f"{eq}|{letras}")
    if r_eq is None:
        pedir("equipo", f"{eq}|{letras}", f"Abreviatura del equipo «{eq.capitalize()} {letras}»",
              f"{eq[:3].upper()}{letras}")
    else:
        origenes.append(r_eq[1])

    if s.funcion in (Funcion.SENALIZACION, Funcion.COMANDO) and s.estado_id:
        r_f = reglas.buscar("estado", s.estado_id)
        if r_f is None:
            pedir("estado", s.estado_id, f"Abreviatura del estado «{s.s1}/{s.s2}» (ej. «{s.observaciones}»)",
                  f"{str(s.s1)[:1]}/{str(s.s2)[:1]}")
    else:
        r_f = reglas.buscar("frase", frase) if frase else ("", "reglas")
        if r_f is None:
            # parte de la frase ya conocida (ej. "falta tension auxiliar" + "ssaa"): solo se pregunta el resto
            conocidas = [k for k in {**reglas.frase, **reglas.memoria["frase"]} if frase.startswith(k + " ")]
            if conocidas:
                k = max(conocidas, key=len)
                resto = frase[len(k) + 1:]
                r_k, r_resto = reglas.buscar("frase", k), reglas.buscar("frase", resto)
                if r_resto is None:
                    pedir("frase", resto, f"Abreviatura de «{resto}» (sigue a «{k}» = {r_k[0]})")
                else:
                    r_f = (f"{r_k[0]} {r_resto[0]}".strip(), "memoria" if "memoria" in (r_k[1], r_resto[1]) else "reglas")
            else:
                pedir("frase", frase, f"Abreviatura de «{frase}»")
    if falta:
        return None
    origenes.append(r_f[1])
    informe_origen(informe, origenes)
    return _unir(prefijo, r_eq[0], r_f[0], maximo=reglas.maximo) or _largo(s, prefijo, reglas, informe, ejemplo)


def informe_origen(informe: Informe, origenes: list[str]) -> None:
    if "memoria" in origenes:
        informe.por_memoria += 1
    else:
        informe.por_reglas += 1


def _largo(s: Senal, prefijo: str, reglas: Reglas, informe: Informe, ejemplo: str) -> Optional[str]:
    """Las partes conocidas no entran juntas en 20: se pide la abreviatura completa de esta señal."""
    propia = reglas.buscar_texto("largo", s.observaciones)
    if propia:
        return _unir(prefijo, propia[0], maximo=reglas.maximo) or None
    clave = re.sub(r"\d+", "#", _norm(s.observaciones))
    if not any(p.tipo == "largo" and p.exacta == _norm(s.observaciones) for p in informe.pendientes):
        informe.pendientes.append(Pendiente(
            "largo", clave, f"No entra en {reglas.maximo}: abreviatura completa de «{s.observaciones}»",
            ejemplo, "", max(reglas.maximo - len(prefijo) - 1, 1), exacta=_norm(s.observaciones)))
    return None


def aplicar(proyecto: Proyecto, perfil: Perfil, reglas: Optional[Reglas] = None) -> tuple[Informe, Reglas]:
    """Completa DESC. SCADA de las señales que no la tienen (las deja como fijas para el generador)."""
    reglas = reglas or Reglas(perfil)
    informe = Informe()
    for nivel in proyecto.niveles:
        for campo in nivel.campos:
            prefijo = campo.prefijo or f"{nivel.codigo}{campo.numero}"
            asignadas: list[tuple[Senal, str]] = []
            vistas = {s.desc_scada for s in campo.senales if s.desc_scada}
            for s in campo.senales:
                # el comando lleva la misma descripción que su señalización: la copia el generador
                if s.segunda_fila or s.es_reserva or s.funcion in (Funcion.RESERVA, Funcion.MEDICION, Funcion.COMANDO) \
                        or s.desc_scada or "desc_scada" in s.fijos or not s.observaciones:
                    continue
                d = proponer(s, prefijo, reglas, informe)
                if d:
                    asignadas.append((s, d))
            repetidas = {d for d in (d for _, d in asignadas) if [x for _, x in asignadas].count(d) > 1 or d in vistas}
            for s, d in asignadas:
                if d in repetidas:  # dos señales del campo no pueden llamarse igual: que el usuario las distinga
                    clave = re.sub(r"\d+", "#", _norm(s.observaciones))
                    if not any(p.tipo == "largo" and p.exacta == _norm(s.observaciones) for p in informe.pendientes):
                        informe.pendientes.append(Pendiente(
                            "largo", clave, f"«{d}» se repite en el campo: abreviatura propia de «{s.observaciones}»",
                            s.observaciones, "", max(reglas.maximo - len(prefijo) - 1, 1),
                            exacta=_norm(s.observaciones)))
                    continue
                s.desc_scada = d
                s.fijos.append("desc_scada")
    return informe, reglas
