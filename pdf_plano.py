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


class PdfNoEsquema(RuntimeError):
    """El PDF es otro tipo de documento (por ejemplo la impresión de un listado de señales)."""


class PdfSinTexto(RuntimeError):
    """El PDF no trae texto utilizable (imágenes o una exportación recortada): hay que usar la versión original."""


@dataclass
class LecturaSenal:
    pagina: int
    funcion: Funcion
    texto: str                                           # en doble bit: "Seccionador X Abierto/Cerrado"
    es_reserva: bool = False
    columnas: list[str] = field(default_factory=list)    # rótulos originales (1 o 2), en orden de estados
    de_rele: bool = False                                # viene de una tira de un tablero de protección


@dataclass
class PaginaLeida:
    pagina: int
    nivel: str
    campo: str
    senales: list[LecturaSenal]
    descripcion: str = ""       # subtítulo del cajetín (ej. "TRANSF TR02 132Kv")
    origen: str = "modulo"      # "modulo" (E/S del control) o "rele" (tira de un tablero de protección)
    mediciones: bool = False    # la página nombra a un multimedidor: el campo lleva el juego de mediciones


def cargar_config(perfil: Perfil) -> dict:
    ruta = RAIZ_PLANTILLAS / perfil.id / "lectura_plano.json"
    if not ruta.is_file():
        raise FileNotFoundError(f"no existe {ruta}")
    return json.loads(ruta.read_text(encoding="utf-8"))


_ROTULO_DE_CABLE = re.compile(
    r"^[-+]?[A-Za-z]{0,3}\d+(?:[./-]\d+)*[A-Za-z]?$|^[-+][A-Za-z]+\d*(?:[./]\d+)?$|^\d+(?:[.,]\d+)?\s*mm2.*$"
    r"|^H\d+/\d?[A-Z]\d?$", re.I)


def _es_rotulo(t: str, cfg: dict) -> bool:
    """Descarta lo que no es el nombre de una señal: rótulos de cable/borne (-X1.6, H23/4A, 1,5mm2/Ne) y textos
    demasiado cortos (FASE R, 110 Vcc (+)). 'Reserva' y la alimentación (Positivo/Negativo) se conservan."""
    if t.lower() == cfg["reserva"].lower() or t.startswith(tuple(cfg["ignorar_prefijos"])):
        return True
    if _ROTULO_DE_CABLE.match(t):
        return False
    palabras = re.findall(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]+", t)
    return sum(map(len, palabras)) >= 8 and any(len(w) >= 5 for w in palabras)


def _titulo(page, cfg: dict) -> dict:
    """Datos del cajetín del plano: nivel, campo y descripción. Ej. 'ET AP - TC3 04 - TABLERO DE CONTROL CAMPO 04'
    + 'TRANSF TR02 132Kv' -> nivel 132KV, campo 04, descripción 'TRANSF TR02 132Kv'."""
    h = page.rect.height
    lineas = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            if abs(l["dir"][0]) >= 0.1 or l["bbox"][1] < h * 0.9 or l["bbox"][0] > 120:
                continue
            t = " ".join("".join(s["text"] for s in l["spans"]).split())
            if len(t) > 6:
                lineas.append((-l["bbox"][0], t))  # el título principal es el de mayor x (arriba en la hoja girada)
    lineas = [t for _, t in sorted(lineas)]
    principal = next((t for t in lineas if "TABLERO" in t.upper()), "")
    if not principal:
        return {"nivel": "", "campo": "", "descripcion": ""}
    i = lineas.index(principal)
    sub = next((t for t in lineas[i + 1:] if not re.search(r"ESQUEMA|^ETAP|AMPLIACION|^\d", t, re.I)), "")
    campos = re.search(r"CAMPO\s+(\d{1,2})(?:\s*[-/]\s*\d{1,2})*", principal, re.I)
    campo = campos.group(1).zfill(2) if campos and not re.search(r"CAMPO\s+\d{1,2}\s*[-/]", principal, re.I) else ""
    dig = re.search(r"\bT[A-Z]{1,3}(\d)\b", principal)
    nivel = cfg.get("nivel_por_digito", {}).get(dig.group(1), "") if dig else ""
    if not nivel:
        kv = re.search(r"(\d+(?:[.,]\d+)?)\s*k\s*v", principal + " " + sub, re.I)
        nivel = kv.group(1).replace(".", ",") + "KV" if kv else ""
    return {"nivel": nivel, "campo": campo, "descripcion": sub}


def _celdas_de_tira(page, cfg: dict) -> list[str]:
    """Señales de una hoja de protección: la tira de celdas de arriba ("SEÑALIZACION A SISTEMA DE CONTROL - CAMPO 06").

    Cada celda es un grupo de líneas centradas en la misma x; las cabeceras de grupo (ej. "PROTECCION PRINCIPAL") se
    anteponen a las celdas cercanas. Devuelve [] si la hoja no es de ese tipo."""
    t = cfg.get("tiras_rele")
    if not t:
        return []
    alto = page.rect.height
    lineas = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            if abs(l["dir"][0]) >= 0.1:
                continue
            x0, y0, x1, y1 = l["bbox"]
            cx, cy = (y0 + y1) / 2, alto - (x0 + x1) / 2  # hoja girada 270°: x_pantalla = y, y_pantalla = alto - x
            txt = " ".join("".join(s["text"] for s in l["spans"]).split())
            if len(txt) > 1 and cy < t["alto_tira"] and 100 < cx < page.rect.width - 20:
                lineas.append((cx, cy, txt))
    if not lineas:
        return []
    titulo = min(lineas, key=lambda l: l[1])
    if not any(re.search(p, titulo[2], re.I) for p in t["titulos"]):
        return []
    resto = sorted((l for l in lineas if l is not titulo and l[1] > titulo[1] + 8))
    por_columna: list[list[tuple[float, float, str]]] = []
    for l in resto:  # celdas = líneas apiladas con el mismo centro
        for g in por_columna:
            if abs(l[0] - sum(x[0] for x in g) / len(g)) <= t["tolerancia_celda"]:
                g.append(l)
                break
        else:
            por_columna.append([l])
    grupos: list[list[tuple[float, float, str]]] = []
    for g in por_columna:  # un salto vertical grande separa la cabecera de grupo de la celda que tiene debajo
        actual: list[tuple[float, float, str]] = []
        for l in sorted(g, key=lambda x: x[1]):
            if actual and l[1] - actual[-1][1] > t["salto_vertical"]:
                grupos.append(actual)
                actual = []
            actual.append(l)
        grupos.append(actual)
    celdas = [(sum(x[0] for x in g) / len(g), min(x[1] for x in g), len(g),
               " ".join(x[2] for x in sorted(g, key=lambda x: x[1]))) for g in grupos]
    if not celdas:
        return []
    from statistics import median
    ref = median(c[1] for c in celdas)
    sin_prefijo = {h.upper() for h in t["cabeceras_sin_prefijo"]}
    cabeceras = [c for c in celdas if (c[2] == 1 and c[1] < ref - 10) or c[3].upper() in sin_prefijo]
    salida = []
    for cx, cy, n, txt in sorted(celdas):
        if (cx, cy, n, txt) in cabeceras or txt.lower() == cfg["reserva"].lower():
            continue
        cerca = [h for h in cabeceras if abs(h[0] - cx) <= t["alcance_cabecera"]]
        h = min(cerca, key=lambda h: abs(h[0] - cx)) if cerca else (cabeceras[0] if len(cabeceras) == 1 else None)
        prefijo = re.sub(r"\s*-\s*RESERVAS?\s*$", "", h[3], flags=re.I) if h else ""  # "… TR02 - RESERVAS" es un rótulo de cabecera
        salida.append(f"{prefijo} {txt}" if h and h[3].upper() not in sin_prefijo else txt)
    return salida


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
    if len(utiles) == len(textos) and re.compile(cfg.get("rango_analogico", r"(?!x)x")).search(" ".join(textos)):
        # módulo de entradas analógicas (sin Positivo/Negativo y con rangos): cada rótulo es una MEDICION; las
        # "Reserva" no se cuentan porque ocupan varios bornes por entrada (+, -, GND)
        return [LecturaSenal(pagina, Funcion.MEDICION, t, False, [t]) for t in utiles
                if t.lower() != cfg["reserva"].lower()]
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
               solo_paginas: Optional[set[int]] = None, info: Optional[dict] = None) -> list[PaginaLeida]:
    """Páginas con señales del PDF. Si se pasa `info`, se completa con estadísticas para explicar un resultado vacío."""
    try:
        import pymupdf
    except ImportError as e:
        raise PdfNoDisponible("falta pymupdf (python -m pip install pymupdf)") from e
    cfg = cargar_config(perfil)
    ign = tuple(cfg["ignorar_prefijos"])
    paginas: list[PaginaLeida] = []
    info = info if info is not None else {}
    info.update(paginas=0, caracteres=0, con_rotulos=0, con_franja=0, con_tira=0, rotaciones=set())
    with pymupdf.open(str(ruta)) as doc:
        info["paginas"] = len(doc)
        if len(doc) and re.search(r"LISTADO\s+DE\s+SE.ALES", doc[0].get_text(), re.I) and doc[0].rotation == 0:
            raise PdfNoEsquema("Ese PDF es la impresión de un listado de señales, no un esquema funcional. "
                               "Elegí el esquema funcional (EF) del tablero de control o de protección.")
        for n, page in enumerate(doc, start=1):
            if avance:
                avance(n, len(doc))
            if solo_paginas is not None and n not in solo_paginas:
                continue
            info["rotaciones"].add(page.rotation)
            tira = _celdas_de_tira(page, cfg)
            if tira:  # hoja de protección: una señal del relé al control por celda
                info["con_tira"] += 1
                tit = _titulo(page, cfg)
                nivel, campo = _adivinar(tira)
                paginas.append(PaginaLeida(
                    n, tit["nivel"] or nivel, tit["campo"] or campo,
                    [LecturaSenal(n, Funcion.ALARMAS, t, False, [t], de_rele=True) for t in tira],
                    descripcion=tit["descripcion"], origen="rele"))
                continue
            # el cajetín del plano queda a la izquierda: se descarta por posición relativa al ancho
            todas = _lineas_verticales(page, cfg["x_minimo_rel"] * page.rect.width)
            info["caracteres"] += sum(len(l[2]) for l in todas)
            info["con_rotulos"] += len(todas) >= cfg["min_columnas_pagina"]
            lineas = [l for l in todas if _es_rotulo(l[2], cfg)]
            # módulo de E/S = franja de etiquetas alineadas (al menos N); las tiras de cabecera y los rótulos de
            # cableado quedan en franjas de 1-2 etiquetas y no cuentan
            bandas = [b for b in _bandas(lineas) if len(b) >= cfg.get("min_etiquetas_modulo", 8)]
            if not bandas:
                continue
            info["con_franja"] += 1
            marcas = sum(t.startswith(ign) or t.lower() == cfg["reserva"].lower() for b in bandas for _, _, t in b)
            if marcas < 2:
                continue
            senales: list[LecturaSenal] = []
            for banda in bandas:
                # con la página girada 270° el borne 1 es la etiqueta de mayor x; con 90° es la de menor x
                orden = banda[::-1] if page.rotation != 90 else banda
                senales += _senales_de_banda([t for _, _, t in orden], cfg, n)
            nivel, campo = _adivinar([t for _, _, t in lineas])
            tit = _titulo(page, cfg)
            mide = bool(re.search(cfg.get("mediciones", {}).get("detectar", r"(?!x)x"),
                                  " ".join(t for _, _, t in lineas), re.I))
            if senales:
                paginas.append(PaginaLeida(n, tit["nivel"] or nivel, tit["campo"] or campo, senales,
                                           descripcion=tit["descripcion"], mediciones=mide))
        if not paginas and sum(len(pg.get_text()) for pg in doc) < 30 * len(doc):  # casi sin caracteres en todo el PDF
            raise PdfSinTexto("Ese PDF no trae texto utilizable (son imágenes o una exportación recortada). "
                              "Usá la versión original del esquema funcional.")
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


def tension_texto(nivel: str) -> str:
    """'33KV' -> '33kV'; '6.6 KV' -> '6,6kV' (coma decimal, como el ETAP); '' si el nivel no trae tensión."""
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*k\s*v", nivel, re.I)
    return f"{m.group(1).replace('.', ',')}kV" if m else ""


def controlador_por_defecto(nivel: str, cfg: dict) -> str:
    """'33KV' -> 'SEL-2241-33kV': el final es la tensión del nivel (regla del cliente; editable por fila)."""
    kv = tension_texto(nivel)
    return cfg.get("controlador", "").format(nivel=kv) if kv else ""


def controlador_con_tension(modelo: str, nivel: str) -> str:
    """'SEL-2241' + nivel '33KV' -> 'SEL-2241-33kV'. Si el modelo ya termina en una tensión, o el nivel no
    tiene, queda igual."""
    kv = tension_texto(nivel)
    if not kv or re.search(r"-\d+(?:[.,]\d+)?kV$", modelo):
        return modelo
    return f"{modelo}-{kv}"


def con_tension_del_nivel(controlador: str, nivel: str) -> str:
    """Cambia la tensión al final de un controlador ('SEL-2241-33kV') por la del nivel. Si el controlador no
    termina en una tensión (un relé, SEL-3555…) queda igual."""
    kv = tension_texto(nivel)
    if not kv or not re.search(r"-\d+(?:[.,]\d+)?kV$", controlador):
        return controlador
    return re.sub(r"\d+(?:[.,]\d+)?kV$", kv, controlador)


def filas_mediciones(nivel: str, campo: str, prefijo: str, cfg: dict) -> list[Senal]:
    """Juego de mediciones de un campo (ETAP: 13): FUNCION MEDICION, controlador del multimedidor, y la
    descripción/tag con el mismo estilo del listado ('204AP TENSION CAMPO 04 33kV FASE R')."""
    m = cfg.get("mediciones")
    if not m:
        return []
    filas = []
    for plantilla in m["juego"]:
        texto = plantilla.format(campo=campo, tension=tension_texto(nivel)).strip()
        filas.append(Senal(funcion=Funcion.MEDICION, controlador=m["controlador"],
                           tag_hmi=tag_hmi_desde(texto, cfg), desc_hmi=desc_hmi_desde(prefijo, texto, cfg)))
    return filas


def _controlador(ls: LecturaSenal, controlador: str, rele: str, cfg: dict) -> str:
    """Las señales de protección (tiras de relé y patrones del cliente) llevan el relé del campo; el resto, el del campo."""
    if rele and (ls.de_rele or any(re.search(p, ls.columnas[0] if ls.columnas else ls.texto, re.I)
                                   for p in cfg.get("rele_patrones", []))):
        return rele
    return controlador


def _filas(ls: LecturaSenal, prefijo: str, controlador: str, cfg: dict, rele: str = "") -> list[Senal]:
    """Filas del listado de una señal: 1, o 2 si es doble bit (la 2ª sin TAG ni DESC. HMI)."""
    controlador = _controlador(ls, controlador, rele, cfg)
    if ls.es_reserva:
        return [Senal(funcion=Funcion.RESERVA, controlador=controlador, tag_hmi="N/A", es_reserva=True)]
    s = Senal(funcion=ls.funcion, controlador=controlador, tag_hmi=tag_hmi_desde(ls.texto, cfg),
              desc_hmi=desc_hmi_desde(prefijo, ls.texto, cfg))
    filas = [s]
    if len(ls.columnas) == 2:
        filas.append(Senal(funcion=ls.funcion, controlador=controlador, segunda_fila=True))
    return filas


def a_niveles(paginas: list[PaginaLeida], perfil: Perfil,
              destinos: Optional[dict[int, tuple]] = None, lugar: str = "") -> list[Nivel]:
    """Arma Nivel > Campo > Senal.

    `destinos` = {pagina: (nivel, campo, descripcion[, controlador[, nombre del campo[, relé[, ¿mediciones?]]]])}.
    `lugar` = nombre por defecto del campo en el prefijo (ej. 'LC' -> '204LC'); `nombre` lo pisa por campo."""
    cfg = cargar_config(perfil)
    orden = {f: i for i, f in enumerate(perfil.orden_funciones)}
    niveles: dict[str, Nivel] = {}
    campos: dict[tuple[str, str], Campo] = {}
    reservas: list[tuple[str, str, Senal]] = []
    con_mediciones: set[tuple[str, str]] = set()
    for pg in paginas:
        nivel, campo, desc, *resto = (destinos or {}).get(pg.pagina, (pg.nivel, pg.campo, pg.descripcion))
        nv = niveles.setdefault(nivel, Nivel(nombre=nivel, codigo=codigo_nivel(nivel, cfg)))
        cp = campos.get((nivel, campo))
        if cp is None:
            nombre = resto[1] if len(resto) > 1 and resto[1] else lugar  # LC, GTR01, TRAFO1…
            ctl = resto[0] if resto and resto[0] else controlador_por_defecto(nivel, cfg)
            cp = campos[(nivel, campo)] = Campo(numero=campo, descripcion=desc,
                                                prefijo=f"{nv.codigo}{campo}{nombre}", controlador=ctl)
            nv.campos.append(cp)
        rele = resto[2] if len(resto) > 2 else ""
        mide = resto[3] if len(resto) > 3 else pg.mediciones
        if mide and (nivel, campo) not in con_mediciones:  # una sola vez por campo, aunque tenga varias páginas
            con_mediciones.add((nivel, campo))
            cp.senales += filas_mediciones(nivel, campo, cp.prefijo or f"{nv.codigo}{campo}", cfg)
        for ls in pg.senales:
            filas = _filas(ls, cp.prefijo, cp.controlador, cfg, rele)
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
