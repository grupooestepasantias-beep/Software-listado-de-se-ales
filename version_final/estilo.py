"""Estilo de redacción del listado. Dos estilos, deducidos de los listados hechos a mano:

* ETAP (obra Aguada Pichana): DESC. HMI = prefijo del campo + texto sin tildes; un TAG HMI por cada estado de una señal
  doble (abierto / cerrado); estados ABIERTO/CERRADO, LOCAL/REMOTO, error_0/error_1 (texto del Excel oficial, 2026-11-13).
* USRE (obra Senillosa, `USRE-0119-SET-C-T-LI-Ls-0744`): DESC. HMI sin prefijo y en Título; los dos estados de una señal
  doble comparten UN solo TAG/DESC. HMI (`Reconectador_15201_Abierto_Cerrado`, la 2.ª fila va vacía); los códigos de equipo
  van sin barra (152/01 -> 15201); estados con el nombre del propio estado (ABIERTO/CERRADO, error_0/error_1); alarmas con
  FALTA / FALLA / ACTUO según el texto; un rótulo «en local» con una sola entrada es UNA fila con un solo offset.

El estilo se detecta por el nombre del PDF (USRE-… o ETAP-…) y se puede cambiar en «Datos…».
"""
from __future__ import annotations

import re
import unicodedata

ETAP, USRE = "ETAP", "USRE"
ESTILOS = (ETAP, USRE)

_CODIGO = re.compile(r"\b(\d{2,3}[A-Z]{0,2})/(\d{2})\b")
_CHICAS = {"de", "del", "la", "las", "el", "los", "en", "y", "e", "a", "al", "por", "con", "sin", "para", "o", "u"}
_SIGLAS = re.compile(r"^(?:[A-Z]{2,4}|\d\w*|[A-Z]\d\w*|\w*\d\w*)$")        # TM, TV, RBC, 25204, 13,2kV, 50N: no se tocan


def detectar(nombres) -> str:
    """USRE si algún PDF se llama USRE-…; ETAP en cualquier otro caso."""
    return USRE if any("USRE-" in str(n).upper() for n in nombres) else ETAP


def sin_barra(texto: str) -> str:
    """'Reconectador 152/01 alarma' -> 'Reconectador 15201 alarma' (código de equipo sin barra)."""
    return _CODIGO.sub(r"\1\2", texto)


def titulo(texto: str) -> str:
    """Cada palabra con mayúscula inicial, salvo artículos y preposiciones; siglas y códigos quedan como están."""
    palabras = texto.split()
    salida = []
    for i, p in enumerate(palabras):
        nucleo = p.strip("()-.,/")
        anterior = palabras[i - 1].lower() if i else ""
        if nucleo.lower() == "a" and anterior == "grupo":                       # 'Grupo A', no 'a'
            salida.append("A")
        elif nucleo.lower() in _CHICAS and nucleo == nucleo.lower() and i > 0:  # 'En' ya escrito en mayúscula se respeta
            salida.append(p.lower())
        elif _SIGLAS.match(nucleo) and nucleo != nucleo.lower() and not nucleo.istitle():
            salida.append(p)
        else:
            salida.append("/".join(x[:1].upper() + x[1:] for x in p.split("/")))
    return " ".join(salida)


def _plano(t: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", t.lower()) if unicodedata.category(c) != "Mn")


def partir_par(p0: str, p1: str) -> tuple[str, str, str]:
    """Dos rótulos de una señal doble -> (raíz común, estado 1, estado 2).
    'Reconectador 152/01 Abierto' + 'Reconectador 152/01 Cerrado' -> ('Reconectador 152/01', 'Abierto', 'Cerrado').
    Si hay un código de equipo, la raíz llega hasta él ('… 152/01 en local' / '… en remoto' -> estados 'en local', 'en remoto')."""
    a, b = p0.split(), p1.split()
    k = 0                                              # estado al PRINCIPIO ('Apertura reconectador 152/01' / 'Cierre …')
    while k < min(len(a), len(b)) - 1 and a[-1 - k].lower() == b[-1 - k].lower():
        k += 1
    if k and a[0].lower() != b[0].lower():
        return " ".join(a[len(a) - k:]), " ".join(a[:len(a) - k]), " ".join(b[:len(b) - k])
    n = 0
    while n < min(len(a), len(b)) and a[n].lower() == b[n].lower():
        n += 1
    for i, w in enumerate(a[:n]):                      # la raíz termina en el código del equipo, si lo hay
        if _CODIGO.fullmatch(w) or re.fullmatch(r"\d{3,5}[A-Z]{0,2}\d{0,2}", w):
            n = i + 1
            break
    n = min(n, len(a) - 1, len(b) - 1) if min(len(a), len(b)) > 1 else 0
    return " ".join(a[:n]), " ".join(a[n:]), " ".join(b[n:])


def nombre_estado(texto: str) -> str:
    """'en Local' -> 'LOCAL'; 'Abierto' -> 'ABIERTO'; 'Apertura' -> 'ABRIR'; 'Cierre' -> 'CERRAR'."""
    t = _plano(texto).strip()
    t = re.sub(r"^en\s+", "", t)
    return {"apertura": "ABRIR", "cierre": "CERRAR", "telecontrol": "TELE"}.get(t, t.upper())


def texto_doble(p0: str, p1: str) -> str:
    """Rótulo único de una señal doble: 'Reconectador 152/01 Abierto/Cerrado'."""
    raiz, e0, e1 = partir_par(p0, p1)
    if e0.lower().startswith("en ") and e1.lower().startswith("en "):          # 'En Local/En Remoto'
        e0, e1 = "En" + e0[2:], "En" + e1[2:]
    return f"{raiz} {e0}/{e1}".strip()
