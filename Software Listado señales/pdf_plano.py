"""Lectura de planos de ingeniería (PDF) para llenar las columnas A-G del listado.

Cada columna rotulada de las páginas de bornes es una señal; "Positivo/Negativo" (alimentación) se
ignora. Las parejas Abierto/Cerrado, Local/Remoto, etc. forman una señal de doble bit (2 filas).
El vocabulario sale de plantillas/<id>/lectura_plano.json.
"""
from __future__ import annotations

import json
import re
from collections import Counter
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Callable, Optional

import correcciones
from hmi import desc_hmi_desde, tag_hmi_desde
from modelo import Campo, Funcion, Nivel, Senal, TipoPunto
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
    # UTR: número de entrada (DI17) o salida (DO9) de cada columna, en el mismo orden que `columnas`; el módulo de la
    # página (0 = el de más a la izquierda) y su tipo (DI, DO o AI). Vacío si el plano no permite saberlo.
    entradas: list[int] = field(default_factory=list)
    tipo: str = ""
    modulo: int = -1
    verificacion: str = ""          # resultado del cruce con otros documentos (cruce.verificar), para anotar la fila


@dataclass
class ModuloLeido:
    tipo: str                   # DI | DO | AI
    etiquetas: int              # cuántas señales (columnas rotuladas, sin Positivo/Negativo) tiene
    aviso: str = ""             # si la numeración salió por orden y no por posición


@dataclass
class PaginaLeida:
    pagina: int
    nivel: str
    campo: str
    senales: list[LecturaSenal]
    descripcion: str = ""       # subtítulo del cajetín (ej. "TRANSF TR02 132Kv")
    origen: str = "modulo"      # "modulo" (E/S del control) o "rele" (tira de un tablero de protección)
    mediciones: bool = False    # la página nombra a un multimedidor: el campo lleva el juego de mediciones
    modulos: list[ModuloLeido] = field(default_factory=list)   # módulos de E/S, de izquierda a derecha
    archivo: str = ""           # nombre del PDF de donde salió (varios PDF en una misma carga)
    inferidos: list[str] = field(default_factory=list)   # datos que NO están escritos en el cajetín: "nivel", "campo"
    parte: int = 0              # una hoja con módulos de varios campos se parte en un PaginaLeida por campo (1, 2…)

    @property
    def clave(self):
        """Identifica la página entre varios PDF (el número de página solo se repite de un archivo a otro) y, si la
        hoja se partió por campo, cada parte."""
        base = (self.archivo, self.pagina) if self.archivo else self.pagina
        return base + (self.parte,) if self.parte and isinstance(base, tuple) else (base, self.parte) if self.parte else base


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
    if not principal:  # cajetín sin "TABLERO…": el título con la tensión ("TCONTROL 13,2kV - DETALLE ENTRADAS DIGITALES")
        kv = None
        for b in page.get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                if abs(l["dir"][0]) >= 0.1 or l["bbox"][1] < h * 0.5 or l["bbox"][0] > 120:
                    continue
                t = " ".join("".join(s["text"] for s in l["spans"]).split())
                if re.search(r"\d\s*k\s*v\b.*\s-\s", t, re.I) and not re.match(r"(OBRA|PROYECTO)", t, re.I):
                    kv = kv or re.search(r"(\d+(?:[.,]\d+)?)\s*k\s*v", t, re.I)
        return {"nivel": kv.group(1).replace(".", ",") + "KV" if kv else "", "campo": "", "descripcion": ""}
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
            if x.lower().endswith(" " + s0.lower()) and y.lower().endswith(" " + s1.lower()):  # "cerrado"/"Cerrado"
                base = x[: -len(s0)].strip()
                if base.lower() == y[: -len(s1)].strip().lower():
                    return p, base, x, y
    return None


def _es_analogico(textos: list[str], cfg: dict) -> bool:
    """Módulo de entradas analógicas: sin Positivo/Negativo y con rangos (0-150º C) en los rótulos."""
    ign = tuple(cfg["ignorar_prefijos"])
    return (all(not t.startswith(ign) for t in textos)
            and bool(re.compile(cfg.get("rango_analogico", r"(?!x)x")).search(" ".join(textos))))


def _paso_de(bandas) -> float:
    """Separación entre bornes consecutivos (pt): mediana de las separaciones chicas entre etiquetas vecinas."""
    from statistics import median
    d = [abs(b[0] - a[0]) for banda in bandas for a, b in zip(banda, banda[1:])]
    d = [x for x in d if 5 < x < 18]
    return median(d) if d else 12.0


def _numerar_modulo(orden: list[tuple[float, float, str]], x0: float, paso: float,
                    cfg: dict) -> tuple[str, list[Optional[int]], str]:
    """Número de entrada (DI) o salida (DO) de cada rótulo de un módulo.

    El plano numera los bornes del módulo (1-32), pero lo que va en el listado es el número de la ENTRADA (DI17):
    los bornes de alimentación (Negativo) no cuentan. Ej.: el borne 21 es DI17 porque los bornes 10, 12, 14 y 16 son
    negativos. En un módulo de salidas la salida n está en el borne par 2n (DO9 = borne 18). La posición de cada
    rótulo da su borne (el módulo son 2 bloques de 16 y entre ellos queda un hueco de ~2,4 pasos, medido en el plano).

    `orden` = rótulos (x, y, texto) en orden de bornes; `x0` = x del borne 1. Devuelve (tipo, [número o None para la
    alimentación], aviso). Si la geometría no cierra, numera por orden y lo avisa."""
    ign = tuple(cfg["ignorar_prefijos"])
    textos = [t for _, _, t in orden]
    if _es_analogico(textos, cfg):
        return "AI", [None] * len(textos), ""
    cm = cfg.get("modulos", {})
    por_bloque, sep = cm.get("bornes_por_bloque", 16), cm.get("separacion_bloques_en_pasos", 2.4)
    negativos = set(cm.get("bornes_negativos_entradas", [10, 12, 14, 16, 26, 28, 30, 32]))
    n_pos = sum(t.lower().startswith("positivo") for t in textos)
    n_neg = sum(t.lower().startswith("negativo") for t in textos)
    salida = any(t.endswith(tuple(" " + w for w in cfg["palabras_salida"])) for t in textos)
    tipo = "DO" if (salida or n_pos > n_neg) else "DI"

    bornes = []
    for x, _, _ in orden:
        d = abs(x - x0) / paso
        bornes.append(round(d - sep) + 1 if d > por_bloque + 1.0 else round(d) + 1)
    numeros: list[Optional[int]] = []
    valido = len(set(bornes)) == len(bornes) and all(1 <= k <= 2 * por_bloque for k in bornes)
    if valido:
        for k, t in zip(bornes, textos):
            if t.startswith(ign):
                valido = valido and ((k in negativos) if tipo == "DI" else (k % 2 == 1))
                numeros.append(None)
            elif tipo == "DI":
                valido = valido and k not in negativos
                numeros.append(k - sum(1 for n in negativos if n < k))
            else:
                valido = valido and k % 2 == 0
                numeros.append(k // 2)
    if valido:
        return tipo, numeros, ""
    rango, numeros = 0, []
    for t in textos:
        if t.startswith(ign):
            numeros.append(None)
        else:
            rango += 1
            numeros.append(rango)
    return tipo, numeros, "numeración por orden de aparición (la posición de los bornes no cerró): verificala en el plano"


def _senales_de_banda(textos: list[str], cfg: dict, pagina: int, numeros: Optional[list] = None,
                      tipo: str = "", modulo: int = -1) -> list[LecturaSenal]:
    """textos = rótulos del módulo en orden de bornes (1 → n). `numeros` = número de entrada/salida de cada rótulo
    (None para la alimentación), `tipo` = DI/DO/AI y `modulo` = posición del módulo en la página (opcionales)."""
    ign = tuple(cfg["ignorar_prefijos"])
    nums = list(numeros) if numeros is not None else [None] * len(textos)
    idx = [i for i, t in enumerate(textos) if not t.startswith(ign)]
    utiles = [textos[i] for i in idx]
    un = [nums[i] for i in idx]
    if len(utiles) == len(textos) and re.compile(cfg.get("rango_analogico", r"(?!x)x")).search(" ".join(textos)):
        # módulo de entradas analógicas (sin Positivo/Negativo y con rangos): cada rótulo es una MEDICION; las
        # "Reserva" no se cuentan porque ocupan varios bornes por entrada (+, -, GND)
        return [LecturaSenal(pagina, Funcion.MEDICION, t, False, [t], tipo=tipo or "AI", modulo=modulo)
                for t in utiles if t.lower() != cfg["reserva"].lower()]
    salida = any(t.endswith(tuple(" " + w for w in cfg["palabras_salida"])) for t in utiles)
    res, i = [], 0
    while i < len(utiles):
        t = utiles[i]
        if t.lower() == cfg["reserva"].lower():
            res.append(LecturaSenal(pagina, Funcion.RESERVA, "Reserva", True, [t],
                                    entradas=[un[i]] if un[i] is not None else [], tipo=tipo, modulo=modulo))
            i += 1
            continue
        enc = _par(t, utiles[i + 1], cfg["pares_doble_bit"]) if i + 1 < len(utiles) else None
        if enc:
            par, base, e0, e1 = enc
            s0, s1 = par["sufijos"]
            ents = [un[i], un[i + 1]] if e0 == t else [un[i + 1], un[i]]   # el número de cada estado, no de cada posición
            res.append(LecturaSenal(pagina, Funcion(par["tipo"]), f"{base} {s0}/{s1}", False, [e0, e1],
                                    entradas=ents if None not in ents else [], tipo=tipo, modulo=modulo))
            i += 2
            continue
        res.append(LecturaSenal(pagina, Funcion.COMANDO if salida else Funcion.ALARMAS, t, False, [t],
                                entradas=[un[i]] if un[i] is not None else [], tipo=tipo, modulo=modulo))
        i += 1
    return res


def _adivinar(textos: list[str]) -> tuple[str, str]:
    campos = Counter(m.group(1).zfill(2) for t in textos
                     for m in re.finditer(r"(?i)campo\s?0?(\d{1,2})", t))
    niveles = Counter(m.group(1).replace(",", ".").upper() + "KV" for t in textos
                      for m in re.finditer(r"(?i)(\d+(?:[.,]\d+)?)\s?k\s?v", t))
    return (niveles.most_common(1)[0][0] if niveles else "",
            campos.most_common(1)[0][0] if campos else "")


def _campo_de_textos(textos: list[str]) -> str:
    """Campo al que apuntan los rótulos de un módulo: 'Campo 03 mando…' o el código de equipo '152/03', '189T/03'."""
    votos = Counter()
    for t in textos:
        for m in re.finditer(r"(?i)\bcampo\s?0?(\d{1,2})\b", t):
            votos[m.group(1).zfill(2)] += 2
        for m in re.finditer(r"\b\d{2,3}[A-Z]{0,2}/(\d{2})\b", t):
            votos[m.group(1)] += 1
    return votos.most_common(1)[0][0] if votos else ""


def _partir_por_campo(senales: list[LecturaSenal], modulos: list[ModuloLeido]
                      ) -> list[tuple[str, list[LecturaSenal], list[ModuloLeido]]]:
    """Hoja con módulos de varios campos (ej. 4 módulos DI, uno por campo): una parte por campo, en orden de módulo.
    Los módulos sin pista de campo (o con un solo campo en toda la hoja) no se tocan: queda una única parte."""
    por_modulo: dict[int, list[LecturaSenal]] = {}
    for s in senales:
        por_modulo.setdefault(s.modulo, []).append(s)
    # trozos (módulo, campo, señales): un módulo que atiende a dos campos (ej. salidas de 152/01 y 152/03 en la misma
    # placa) se corta donde cambia el campo; las señales sin pista ('Comando protección grupo A') siguen a la anterior
    trozos: list[tuple[int, str, list[LecturaSenal]]] = []
    for m in sorted(por_modulo):
        ss = por_modulo[m]
        pistas = [_campo_de_textos(s.columnas) for s in ss]
        fuertes = Counter(p for p in pistas if p)
        if len([c for c, n in fuertes.items() if n >= 2]) >= 2:
            ult = next(p for p in pistas if p)
            actual: list[LecturaSenal] = []
            campo_actual = ""
            for s, p in zip(ss, pistas):
                if p and p != ult:
                    ult = p
                if actual and ult != campo_actual:
                    trozos.append((m, campo_actual, actual))
                    actual = []
                actual.append(s)
                campo_actual = ult
            trozos.append((m, campo_actual, actual))
        else:
            trozos.append((m, _campo_de_textos([t for s in ss for t in s.columnas]), ss))
    if len({c for _, c, _ in trozos if c}) < 2 or not all(c for _, c, _ in trozos):
        return [("", senales, modulos)]
    grupos: dict[str, list[tuple[int, list[LecturaSenal]]]] = {}
    for m, campo, ss in trozos:
        grupos.setdefault(campo, []).append((m, ss))
    partes = []
    for campo, piezas in grupos.items():
        mods = list(dict.fromkeys(m for m, _ in piezas))
        nuevo = {m: i for i, m in enumerate(mods)}   # la placa de cada módulo se numera dentro de su parte
        partes.append((campo, [replace(s, modulo=nuevo[m]) for m, ss in piezas for s in ss],
                       [modulos[m] for m in mods if 0 <= m < len(modulos)]))
    return partes


def _inferidos(tit: dict, nivel: str, campo: str) -> list[str]:
    """Nivel/campo que no figuran en el cajetín y se dedujeron de los rótulos de la hoja (puede fallar: se revisa)."""
    return [d for d, adivinado in (("nivel", nivel), ("campo", campo)) if not tit[d] and adivinado]


def leer_planos(rutas, perfil: Perfil, avance: Optional[Callable[[str, int, int], None]] = None
                ) -> tuple[list[PaginaLeida], list[dict]]:
    """Lee varios PDF. Un archivo con problemas no frena a los demás: queda anotado en el informe.

    Devuelve (páginas de todos los archivos, informe) con un dict por archivo:
    {archivo, ruta, estado: ok|sin_senales|error, paginas, leidas, mensaje, info}."""
    todas: list[PaginaLeida] = []
    informe: list[dict] = []
    for ruta in rutas:
        nombre = Path(str(ruta)).name
        fila = {"archivo": nombre, "ruta": str(ruta), "estado": "ok", "paginas": 0, "leidas": 0, "mensaje": "", "info": {}}
        informe.append(fila)
        try:
            pgs = leer_plano(ruta, perfil, avance=(lambda n, t, nombre=nombre: avance(nombre, n, t)) if avance else None,
                             info=fila["info"])
        except (PdfSinTexto, PdfNoEsquema, PdfNoDisponible) as e:
            fila.update(estado="error", mensaje=str(e))
            continue
        except Exception as e:  # PDF dañado, vocabulario roto…
            fila.update(estado="error", mensaje=f"{type(e).__name__}: {e}")
            continue
        fila["paginas"], fila["leidas"] = fila["info"].get("paginas", 0), len(pgs)
        if not pgs:
            i = fila["info"]
            fila.update(estado="sin_senales", mensaje=(
                f"{i.get('paginas', '?')} páginas, ninguna con módulos de E/S ni tira de relé "
                f"({i.get('con_rotulos', '?')} con rótulos). Probablemente no es un esquema funcional de control o protección."))
        todas += pgs
    return todas, informe


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
    nombre = Path(str(ruta)).name
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
                    descripcion=tit["descripcion"], origen="rele", archivo=nombre,
                    inferidos=_inferidos(tit, nivel, campo)))
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
            # x del borne 1 (el módulo de más arriba en la hoja) y separación entre bornes: dan el número de entrada
            x0 = (max if page.rotation != 90 else min)(x for b in bandas for x, _, _ in b)
            paso = _paso_de(bandas)
            en_pantalla = bandas if page.rotation != 90 else bandas[::-1]   # módulos de izquierda a derecha
            modulos: list[Optional[ModuloLeido]] = [None] * len(bandas)
            for banda in bandas:
                # con la página girada 270° el borne 1 es la etiqueta de mayor x; con 90° es la de menor x
                orden = banda[::-1] if page.rotation != 90 else banda
                pos = next(i for i, b in enumerate(en_pantalla) if b is banda)
                tipo_m, nums, aviso = _numerar_modulo(orden, x0, paso, cfg)
                lect = _senales_de_banda([t for _, _, t in orden], cfg, n, numeros=nums, tipo=tipo_m, modulo=pos)
                modulos[pos] = ModuloLeido(tipo_m, len(lect), aviso)
                senales += lect
            nivel, campo = _adivinar([t for _, _, t in lineas])
            tit = _titulo(page, cfg)
            mide = bool(re.search(cfg.get("mediciones", {}).get("detectar", r"(?!x)x"),
                                  " ".join(t for _, _, t in lineas), re.I))
            if senales:
                mods = [m for m in modulos if m is not None]
                partes = _partir_por_campo(senales, mods)
                for k, (campo_p, sen_p, mod_p) in enumerate(partes, 1):
                    paginas.append(PaginaLeida(
                        n, tit["nivel"] or nivel, campo_p or tit["campo"] or campo, sen_p,
                        descripcion=tit["descripcion"], mediciones=mide, modulos=mod_p, archivo=nombre,
                        inferidos=_inferidos(tit, nivel, campo_p or campo), parte=k if len(partes) > 1 else 0))
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


def _siguiente_placa(placa: str) -> str:
    """'A4.2' -> 'A4.3' (suma 1 al último número); sin número queda igual."""
    m = re.match(r"^(.*?)(\d+)$", placa)
    return f"{m.group(1)}{int(m.group(2)) + 1}" if m else placa


def expandir_placas(texto: str, cantidad: int) -> list[str]:
    """Placas de los módulos de una página, de izquierda a derecha. Alcanza con escribir la primera:
    'A4.2' para 3 módulos -> ['A4.2', 'A4.3', 'A4.4']; cada módulo sin placa sigue a la anterior."""
    dadas = [p.strip() for p in re.split(r"[,;\s]+", texto or "") if p.strip()]
    while dadas and len(dadas) < cantidad:
        dadas.append(_siguiente_placa(dadas[-1]))
    return dadas


def _utr(ls: LecturaSenal, filas: list[Senal], placa: str) -> None:
    """TIPO, PLACA y ENTRADA de las filas de una señal, según el módulo del plano.

    DI: cada columna (cada fila de un doble bit) lleva su número de entrada. DO: un comando de dos bornes
    (Apertura/Cierre) ocupa un par de salidas y va como '9/10' en una sola fila, igual que el ETAP."""
    if ls.tipo in ("DI", "DO", "AI"):
        for f in filas:
            f.tipo_punto = TipoPunto(ls.tipo)
    if ls.tipo not in ("DI", "DO") or not ls.entradas:
        return
    if ls.funcion == Funcion.COMANDO and len(ls.entradas) == 2:
        filas[0].entrada = f"{ls.entradas[0]}/{ls.entradas[1]}"
        afectadas = filas[:1]
    else:
        for f, n in zip(filas, ls.entradas):
            f.entrada = str(n)
        afectadas = filas[:len(ls.entradas)]
    if placa:
        for f in afectadas:
            f.placa = placa


def _filas(ls: LecturaSenal, prefijo: str, controlador: str, cfg: dict, rele: str = "",
           placa: str = "") -> list[Senal]:
    """Filas del listado de una señal: 1, o 2 si es doble bit (la 2ª sin TAG ni DESC. HMI)."""
    controlador = _controlador(ls, controlador, rele, cfg)
    if ls.es_reserva:
        filas = [Senal(funcion=Funcion.RESERVA, controlador=controlador, tag_hmi="N/A", es_reserva=True)]
        _utr(ls, filas, placa)
        return filas
    s = Senal(funcion=ls.funcion, controlador=controlador, tag_hmi=tag_hmi_desde(ls.texto, cfg),
              desc_hmi=desc_hmi_desde(prefijo, ls.texto, cfg))
    filas = [s]
    if len(ls.columnas) == 2:
        filas.append(Senal(funcion=ls.funcion, controlador=controlador, segunda_fila=True))
    _utr(ls, filas, placa)
    return filas


def _anotar(filas: list[Senal], ls: LecturaSenal, pg: PaginaLeida, aprendidas: dict, prefijo: str) -> None:
    """Deja en `observaciones` de qué archivo/página salió la señal, su rótulo original y si fue leída, inferida
    (nivel/campo deducidos de la hoja) o corregida por el usuario en una carga anterior. Las correcciones guardadas
    pisan TAG/DESC. HMI de la fila."""
    origen = "leído"
    if pg.inferidos:
        origen = "inferido: " + ", ".join(pg.inferidos)
    if not ls.es_reserva:
        c = correcciones.aplicar(aprendidas, ls.texto, prefijo)
        if c:
            for campo, valor in c.items():
                setattr(filas[0], campo, valor)
            origen += " | corregido por el usuario"
    filas[0].observaciones = " | ".join(
        x for x in (f"{pg.archivo} p.{ls.pagina}".strip(), f"rótulo: {ls.texto}" if not ls.es_reserva else "", origen,
                    ls.verificacion) if x)
    for f in filas[1:]:
        f.observaciones = f"{pg.archivo} p.{ls.pagina}".strip()


def a_niveles(paginas: list[PaginaLeida], perfil: Perfil,
              destinos: Optional[dict[int, tuple]] = None, lugar: str = "") -> list[Nivel]:
    """Arma Nivel > Campo > Senal.

    `destinos` = {pagina: (nivel, campo, descripcion[, controlador[, nombre del campo[, relé[, ¿mediciones?[, placas]]]]])}.
    `placas` = placas de los módulos de la página, de izquierda a derecha (ej. 'A4.2'; ver expandir_placas).
    `lugar` = nombre por defecto del campo en el prefijo (ej. 'LC' -> '204LC'); `nombre` lo pisa por campo."""
    cfg = cargar_config(perfil)
    orden = {f: i for i, f in enumerate(perfil.orden_funciones)}
    niveles: dict[str, Nivel] = {}
    campos: dict[tuple[str, str], Campo] = {}
    reservas: list[tuple[str, str, Senal]] = []
    con_mediciones: set[tuple[str, str]] = set()
    vistas: dict[tuple, str] = {}
    aprendidas = correcciones.cargar(perfil.id)
    for pg in paginas:
        por_defecto = (destinos or {}).get(pg.pagina, (pg.nivel, pg.campo, pg.descripcion))
        nivel, campo, desc, *resto = (destinos or {}).get(pg.clave, por_defecto)
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
        placas = expandir_placas(resto[4] if len(resto) > 4 else "", len(pg.modulos))
        for ls in pg.senales:
            placa = placas[ls.modulo] if 0 <= ls.modulo < len(placas) else ""
            if not ls.es_reserva:  # la misma señal en dos PDF (ej. control y protección) entra una sola vez
                dup = (nivel, campo, ls.funcion, correcciones.clave(ls.texto))
                if dup in vistas and vistas[dup] != pg.archivo:
                    continue
                vistas.setdefault(dup, pg.archivo)
            filas = _filas(ls, cp.prefijo, cp.controlador, cfg, rele, placa)
            _anotar(filas, ls, pg, aprendidas, cp.prefijo)
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
