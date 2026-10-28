"""Lectura de planos de ingeniería (PDF) para llenar las columnas A-G del listado.

Cada columna rotulada de las páginas de bornes es una señal; "Positivo/Negativo" (alimentación) se
ignora. Las parejas Abierto/Cerrado, Local/Remoto, etc. forman una señal de doble bit (2 filas).
El vocabulario sale de plantillas/<id>/lectura_plano.json.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from hmi import desc_hmi_desde, tag_hmi_desde
from modelo import Campo, Funcion, Nivel, Senal
from perfiles import Perfil

RAIZ_PLANTILLAS = Path(__file__).parent / "plantillas"


class PdfNoDisponible(RuntimeError):
    pass


@dataclass
class LecturaSenal:
    pagina: int
    funcion: Funcion
    texto: str                                           # en doble bit: "Seccionador X Abierto/Cerrado"
    es_reserva: bool = False
    columnas: list[str] = field(default_factory=list)    # rótulos originales (1 o 2), en orden de estados


@dataclass
class PaginaLeida:
    pagina: int
    nivel: str
    campo: str
    senales: list[LecturaSenal]


def cargar_config(perfil: Perfil) -> dict:
    ruta = RAIZ_PLANTILLAS / perfil.id / "lectura_plano.json"
    if not ruta.is_file():
        raise FileNotFoundError(f"no existe {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


def _lineas_verticales(page, x_min: float) -> list[tuple[float, float, str]]:
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            if abs(l["dir"][0]) >= 0.1:
                continue
            t = " ".join("".join(s["text"] for s in l["spans"]).split())
            if len(t) > 2 and not t.isdigit() and l["bbox"][0] >= x_min:
                out.append((l["bbox"][0], l["bbox"][1], t))
    return out


def _bandas(lineas, tol: float = 12.0) -> list[list[tuple[float, float, str]]]:
    """Agrupa por la y de arranque del texto (cada módulo queda en su propia franja)."""
    grupos: list[list] = []
    for x, y, t in sorted(lineas, key=lambda l: l[1]):
        if grupos and abs(y - grupos[-1][0][1]) <= tol:
            grupos[-1].append((x, y, t))
        else:
            grupos.append([(x, y, t)])
    return [sorted(g) for g in grupos]


def _par(a: str, b: str, pares: list[dict]) -> Optional[tuple[dict, str, str, str]]:
    """Si a y b son los dos lados de un par (mismo equipo): (par, base, rótulo del 1º estado, del 2º)."""
    for p in pares:
        s0, s1 = p["sufijos"]
        for x, y in ((a, b), (b, a)):
            if x.endswith(" " + s0) and y.endswith(" " + s1):
                base = x[: -len(s0)].strip()
                if base == y[: -len(s1)].strip():
                    return p, base, x, y
    return None


def _senales_de_banda(textos: list[str], cfg: dict, pagina: int) -> list[LecturaSenal]:
    """textos = rótulos del módulo en orden de bornes (1 → n)."""
    ign = tuple(cfg["ignorar_prefijos"])
    utiles = [t for t in textos if not t.startswith(ign)]
    salida = any(t.endswith(tuple(" " + w for w in cfg["palabras_salida"])) for t in utiles)
    res, i = [], 0
    while i < len(utiles):
        t = utiles[i]
        if t.lower() == cfg["reserva"].lower():
            res.append(LecturaSenal(pagina, Funcion.RESERVA, "Reserva", True, [t]))
            i += 1
            continue
        enc = _par(t, utiles[i + 1], cfg["pares_doble_bit"]) if i + 1 < len(utiles) else None
        if enc:
            par, base, e0, e1 = enc
            s0, s1 = par["sufijos"]
            res.append(LecturaSenal(pagina, Funcion(par["tipo"]), f"{base} {s0}/{s1}", False, [e0, e1]))
            i += 2
            continue
        res.append(LecturaSenal(pagina, Funcion.COMANDO if salida else Funcion.ALARMAS, t, False, [t]))
        i += 1
    return res


def _adivinar(textos: list[str]) -> tuple[str, str]:
    campos = Counter(m.group(1).zfill(2) for t in textos
                     for m in re.finditer(r"(?i)campo\s?0?(\d{1,2})", t))
    niveles = Counter(m.group(1).replace(",", ".").upper() + "KV" for t in textos
                      for m in re.finditer(r"(?i)(\d+(?:[.,]\d+)?)\s?k\s?v", t))
    return (niveles.most_common(1)[0][0] if niveles else "",
            campos.most_common(1)[0][0] if campos else "")


def leer_plano(ruta, perfil: Perfil, avance: Optional[Callable[[int, int], None]] = None,
               solo_paginas: Optional[set[int]] = None) -> list[PaginaLeida]:
    try:
        import pymupdf
    except ImportError as e:
        raise PdfNoDisponible("falta pymupdf (python -m pip install pymupdf)") from e
    cfg = cargar_config(perfil)
    ign = tuple(cfg["ignorar_prefijos"])
    paginas: list[PaginaLeida] = []
    with pymupdf.open(str(ruta)) as doc:
        for n, page in enumerate(doc, start=1):
            if avance:
                avance(n, len(doc))
            if solo_paginas is not None and n not in solo_paginas:
                continue
            # el cajetín del plano queda a la izquierda: se descarta por posición relativa al ancho
            lineas = _lineas_verticales(page, cfg["x_minimo_rel"] * page.rect.width)
            # página de bornes = muchas columnas rotuladas + alimentación (Positivo/Negativo) o reservas
            marcas = sum(t.startswith(ign) or t.lower() == cfg["reserva"].lower() for _, _, t in lineas)
            if len(lineas) < cfg["min_columnas_pagina"] or marcas < 2:
                continue
            senales: list[LecturaSenal] = []
            for banda in _bandas(lineas):
                # con la página girada 270° el borne 1 es la etiqueta de mayor x; con 90° es la de menor x
                orden = banda[::-1] if page.rotation != 90 else banda
                senales += _senales_de_banda([t for _, _, t in orden], cfg, n)
            nivel, campo = _adivinar([t for _, _, t in lineas])
            if senales:
                paginas.append(PaginaLeida(n, nivel, campo, senales))
    return paginas


def codigo_nivel(nombre: str, cfg: dict) -> str:
    """Dígito del nivel de tensión ('33KV' -> '2'); '' si no se reconoce."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*k\s*v", nombre, re.I)
    if not m:
        return ""
    kv = float(m.group(1).replace(",", "."))
    for regla in cfg.get("codigo_nivel", []):
        if any(abs(kv - x) < 1e-6 for x in regla["kv"]):
            return regla["codigo"]
    return ""


def controlador_por_defecto(nivel: str, cfg: dict) -> str:
    """'33KV' -> 'SEL-2241-33kV' (regla del cliente; se puede cambiar fila por fila)."""
    kv = re.sub(r"(?i)\s*k\s*v$", "kV", nivel.strip())
    return cfg.get("controlador", "").format(nivel=kv) if nivel else ""


def _filas(ls: LecturaSenal, prefijo: str, controlador: str) -> list[Senal]:
    """Filas del listado de una señal: 1, o 2 si es doble bit (la 2ª sin TAG ni DESC. HMI)."""
    if ls.es_reserva:
        return [Senal(funcion=Funcion.RESERVA, controlador=controlador, tag_hmi="N/A", es_reserva=True)]
    s = Senal(funcion=ls.funcion, controlador=controlador, tag_hmi=tag_hmi_desde(ls.texto),
              desc_hmi=desc_hmi_desde(prefijo, ls.texto))
    filas = [s]
    if len(ls.columnas) == 2:
        filas.append(Senal(funcion=ls.funcion, controlador=controlador, segunda_fila=True))
    return filas


def a_niveles(paginas: list[PaginaLeida], perfil: Perfil,
              destinos: Optional[dict[int, tuple]] = None, lugar: str = "") -> list[Nivel]:
    """Arma Nivel > Campo > Senal.

    `destinos` = {pagina: (nivel, campo, descripcion[, controlador[, nombre del campo]])} editados por el usuario.
    `lugar` = nombre por defecto del campo en el prefijo (ej. 'LC' -> '204LC'); `nombre` lo pisa por campo."""
    cfg = cargar_config(perfil)
    orden = {f: i for i, f in enumerate(perfil.orden_funciones)}
    niveles: dict[str, Nivel] = {}
    campos: dict[tuple[str, str], Campo] = {}
    reservas: list[tuple[str, str, Senal]] = []
    for pg in paginas:
        nivel, campo, desc, *resto = (destinos or {}).get(pg.pagina, (pg.nivel, pg.campo, ""))
        nv = niveles.setdefault(nivel, Nivel(nombre=nivel, codigo=codigo_nivel(nivel, cfg)))
        cp = campos.get((nivel, campo))
        if cp is None:
            nombre = resto[1] if len(resto) > 1 and resto[1] else lugar  # LC, GTR01, TRAFO1…
            ctl = resto[0] if resto and resto[0] else controlador_por_defecto(nivel, cfg)
            cp = campos[(nivel, campo)] = Campo(numero=campo, descripcion=desc,
                                                prefijo=f"{nv.codigo}{campo}{nombre}", controlador=ctl)
            nv.campos.append(cp)
        for ls in pg.senales:
            filas = _filas(ls, cp.prefijo, cp.controlador)
            if ls.es_reserva:  # van todas juntas al final de la hoja
                reservas.append((nivel, campo, filas[0]))
            else:
                cp.senales += filas
    # función en el orden fijo del perfil, sin separar las 2 filas de un doble bit
    for cp in campos.values():
        grupos, actual = [], None
        for s in cp.senales:
            if s.segunda_fila:
                actual.append(s)
            else:
                actual = [s]
                grupos.append(actual)
        grupos.sort(key=lambda g: orden.get(g[0].funcion.value, 99))
        cp.senales = [s for g in grupos for s in g]
    for nv in niveles.values():  # un campo (o nivel) con solo reservas no tiene filas propias
        nv.campos = [c for c in nv.campos if c.senales]
    resultado = [nv for nv in niveles.values() if nv.campos]
    if reservas:
        con_nivel = len(niveles) > 1  # con varios niveles el número de campo solo no alcanza
        for nivel, campo, s in reservas:  # el campo se aclara en la descripción
            s.desc_hmi = f"RESERVA {nivel + ' ' if con_nivel and nivel else ''}Campo {campo}"
        resultado.append(Nivel(nombre="RESERVAS", campos=[Campo(numero="", senales=[s for _, _, s in reservas])]))
    return resultado
