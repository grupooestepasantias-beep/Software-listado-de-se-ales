"""Bornera y borne de cada señal leídos de las HOJAS DE CABLEADO del plano funcional (dibujadas, sin texto) con OCR.

Origen: el lector de bornes de la app «Protocolos FAT y SAT» (FAT/SAT), que resuelve el mismo problema en los planos de
Arroyito y La Paz. Cada hoja de cableado trae, arriba, una franja de celdas con el NOMBRE de cada señal («Subir Tap»,
«INTERRUPTOR 252/01 CERRADO») y, abajo, una fila de bornes dibujados como círculos con su número y la bornera a la
izquierda («-XT.1:  31  32  33»). La señal de cada borne es la de la celda de arriba. No hace falta la tabla del final del plano.

Salida: `FilaBorne` (la misma de `bornes.py`, con `descripcion` = nombre de la celda), así que `bornes.buscar()` y
`desde_pdf` las usan sin cambios. Las filas leídas de las tablas del final del plano y estas se suman.

Qué resuelve respecto del OCR de `ocr.py`:
  * `RapidOCR()` por defecto REDUCE las imágenes grandes (lado máx. 2000 px): el texto chico de los planos (números de
    borne, «229T») se confunde. Aquí se lee a 250 dpi SIN reducir (`max_side_len=5000`).
  * El OCR lee el círculo del borne como «O» o «0» pegado al número («21O», «270»): se limpia por fila.
  * Los nombres traen ceros por oes («INTERRUPT0R252/01») y palabras pegadas a números («252/01CERRADO»): se normalizan.
  * Las celdas se toman de las líneas VERTICALES del encabezado (vectores del PDF), no de la posición del texto.
La lectura solo informa: lo que no se puede leer queda vacío y no se adivina.
"""
from __future__ import annotations

import hashlib
import json
import re
import tempfile
from pathlib import Path
from typing import Callable, Optional

from bornes import FilaBorne

DPI = 250
CONFIANZA = 0.6
CACHE = Path(tempfile.gettempdir()) / "listado_ocr_cache"
_motor = None

_STRIP = re.compile(r"^-?(X[A-Z0-9]{0,4}(?:\.[A-Z0-9]+)?)\s*[:;.]?$", re.I)      # «-X1.1:», «-XT.1:», «-XDI.G:», «-X00»
_NUMERO = re.compile(r"^(\d{1,3})\s?[OoQD0]?$")                                    # «31», «21O», «23 O», «270»


def disponible() -> bool:
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
    except Exception:
        return False
    return True


def _ocr():
    global _motor
    if _motor is None:
        from rapidocr_onnxruntime import RapidOCR
        _motor = RapidOCR(max_side_len=5000, min_side_len=30)       # sin reducir la imagen: el texto del CAD es chico
    return _motor


# ------------------------------------------------------------------ texto de los nombres
def limpiar_nombre(t: str) -> str:
    """«INTERRUPT0R252/01CERRADO» -> «INTERRUPTOR 252/01 CERRADO» (ceros por oes, letras pegadas a números)."""
    t = re.sub(r"(?<=[A-Za-zÁÉÍÓÚÑ])0(?=[A-Za-zÁÉÍÓÚÑ]|\b)", "O", t)
    t = re.sub(r"(?<=[A-Za-z])(?=\d)|(?<=\d)(?=[A-Za-z])", " ", t) if re.search(r"[A-Za-z]{3,}\d|\d[A-Za-z]{3,}", t) else t
    return " ".join(t.split())


# ------------------------------------------------------------------ análisis de una hoja (función pura, sin PDF ni OCR)
def celdas_de_encabezado(bordes: list[float], ancho: float) -> list[tuple[float, float]]:
    """[(x0, x1)] de las celdas a partir de las posiciones x de las líneas verticales del encabezado."""
    xs = sorted(bordes)
    unidos: list[float] = []
    for x in xs:                                   # las líneas dobles (marco) se funden
        if not unidos or x - unidos[-1] > 12:
            unidos.append(x)
    return [(a, b) for a, b in zip(unidos, unidos[1:]) if b - a > 60 and a >= 0 and b <= ancho]


def _extender_celdas(celdas: list[tuple[float, float]], nombres: list[dict], ancho: float) -> list[tuple[float, float]]:
    """Las celdas de los extremos suelen no tener su línea vertical entre las leídas: se agregan, con el ancho típico,
    mientras haya texto de encabezado fuera de las celdas conocidas."""
    if len(celdas) < 2:
        return celdas
    paso = sorted(b - a for a, b in celdas)[len(celdas) // 2]
    celdas = list(celdas)
    cx = lambda c: c["x"] + c["w"] / 2      # noqa: E731
    while any(celdas[0][0] - 1.6 * paso < cx(c) < celdas[0][0] for c in nombres) and celdas[0][0] - paso > -paso * 0.2:
        celdas.insert(0, (celdas[0][0] - paso, celdas[0][0]))
    while any(celdas[-1][1] < cx(c) < celdas[-1][1] + 1.6 * paso for c in nombres) and celdas[-1][1] + paso < ancho + paso * 0.2:
        celdas.append((celdas[-1][1], celdas[-1][1] + paso))
    return celdas


def _valores_de_fila(fila: list[dict]) -> list[tuple[dict, int]]:
    """[(caja, número de borne)] de una fila de números ordenada por x.

    El círculo del borne se lee como «O»/«0» pegado al número: «10» puede ser el borne 1 (con círculo) o el 10, y «270» el 27.
    Los bornes de una fila van en orden y separados por un paso parecido: de las lecturas posibles se elige la que sigue la
    secuencia, y lo que no la sigue (un «5» de otro símbolo, lejos de la fila) se descarta."""
    if not fila:
        return []
    x = lambda n: n["x"] + n["w"] / 2        # noqa: E731
    opciones = []
    for n in fila:
        d = _NUMERO.match(n["texto"].strip()).group(1)
        o = [int(d)]
        if len(d) >= 2 and d.endswith("0") and d == n["texto"].strip().replace(" ", ""):
            o.append(int(d[:-1]))              # «270» -> 27 + círculo
        opciones.append(o)
    if len(fila) == 1:
        return [(fila[0], opciones[0][-1] if len(opciones[0]) > 1 and opciones[0][0] > 99 else opciones[0][0])]
    difs = sorted(x(b) - x(a) for a, b in zip(fila, fila[1:]) if x(b) - x(a) > 5)
    paso = difs[len(difs) // 2] if difs else 80.0
    salto = lambda a, b: max(1, round((x(b) - x(a)) / paso))      # noqa: E731
    # primer valor: el que mejor encaja con el segundo
    mejor = min(((abs((o2 - o1) - salto(fila[0], fila[1])), o1) for o1 in opciones[0] for o2 in opciones[1]), key=lambda s: s[0])
    prev_n, prev = fila[0], mejor[1]
    salida = [(fila[0], prev)]
    for n, o in zip(fila[1:], opciones[1:]):
        esperado = prev + salto(prev_n, n)
        elegido = min(o, key=lambda v: abs(v - esperado))
        if abs(elegido - esperado) > 1:
            continue                                  # no sigue la secuencia: es de otro símbolo
        salida.append((n, elegido))
        prev_n, prev = n, elegido
    return salida


def analizar_hoja(cajas: list[dict], bordes: list[float], ancho: int, alto: int, hoja: int = 0) -> list[FilaBorne]:
    """Filas (bornera, borne, nombre de la señal) de una hoja de cableado ya leída con OCR.

    cajas: [{x, y, w, h, texto, conf}] en píxeles; bordes: x de las líneas verticales del encabezado, en píxeles."""
    ytop = max((b[1] for b in bordes if isinstance(b, (tuple, list))), default=0)     # donde empieza la fila de nombres
    bordes = [b[0] if isinstance(b, (tuple, list)) else b for b in bordes]
    cj = [c for c in cajas if c["conf"] >= CONFIANZA]
    cy = lambda c: c["y"] + c["h"] / 2        # noqa: E731
    cx = lambda c: c["x"] + c["w"] / 2        # noqa: E731
    celdas = celdas_de_encabezado(bordes, ancho)
    y_ini, y_fin = alto * 0.05, alto * 0.16
    ancho_celda = max((b - a for a, b in celdas), default=0)
    # los títulos de grupo abarcan varias celdas: no son el nombre de ninguna señal
    candidatos = [c for c in cj if max(y_ini, ytop) < cy(c) < y_fin and len(c["texto"].strip()) > 1
                  and not re.fullmatch(r"[\d,.\s]+", c["texto"].strip()) and c["w"] <= 1.3 * ancho_celda]
    celdas = _extender_celdas(celdas, candidatos, ancho)
    if candidatos:   # un nombre ocupa hasta 3 renglones: lo de más abajo (referencias de cable, «+110VCC») no es nombre
        y0 = min(cy(c) for c in candidatos)
        candidatos = [c for c in candidatos if cy(c) <= y0 + 100]
    # --- nombres: el texto de la franja de encabezado, por celda
    nombres: list[list[dict]] = [[] for _ in celdas]
    for c in candidatos:
        if True:
            for i, (a, b) in enumerate(celdas):
                if a <= cx(c) < b:
                    nombres[i].append(c)
                    break
    texto_celda = [limpiar_nombre(" ".join(t["texto"] for t in sorted(n, key=lambda t: (round(t["y"] / 25), t["x"]))))
                   for n in nombres]
    # --- bornes: números sobre una fila que tiene su bornera («-XT.1:») a la izquierda
    franjas = [c for c in cj if _STRIP.match(c["texto"].strip()) and len(c["texto"].strip()) >= 3 and cy(c) > alto * 0.2]
    numeros = []
    for c in sorted((c for c in cj if _NUMERO.match(c["texto"].strip()) and cy(c) > alto * 0.2), key=lambda c: (-c["conf"], c["x"])):
        if not any(abs(cx(c) - cx(o)) < 30 and abs(cy(c) - cy(o)) < 30 for o in numeros):     # el de más confianza por posición
            numeros.append(c)
    salida: list[FilaBorne] = []
    if any(f["texto"].strip().endswith(":") for f in franjas):
        # «-X1.1:» (con dos puntos) rotula la fila de bornes de la señal; «-X1.1» sin ellos rotula el cable al común de la bobina
        franjas = [f for f in franjas if f["texto"].strip().endswith(":")]
    for f in franjas:
        fila = sorted((n for n in numeros if abs(cy(n) - cy(f)) < 75 and n["x"] > f["x"] - 60), key=lambda n: n["x"])
        if not fila:
            continue
        for n, numero in _valores_de_fila(fila):
            for i, (a, b) in enumerate(celdas):
                if a <= cx(n) < b:
                    nombre = texto_celda[i]
                    if nombre and not re.fullmatch(r"reserva", nombre, re.I):
                        bornera = _STRIP.match(f["texto"].strip()).group(1).upper().replace("D0", "DO")
                        salida.append(FilaBorne(bornera, numero, nombre, hoja))
                    break
    unicas: dict[tuple, FilaBorne] = {}
    for f in salida:                              # una fila por (bornera, borne): el OCR a veces lee dos veces el mismo círculo
        unicas.setdefault((f.bornera, f.borne), f)
    return list(unicas.values())


# ------------------------------------------------------------------ leer de un PDF
def _bordes_del_encabezado(page, escala: float) -> list[tuple[float, float]]:
    """(x, y superior) en píxeles de las líneas verticales del encabezado (vectores del PDF)."""
    import pymupdf
    m = page.rotation_matrix
    alto = page.rect.height
    xs: list[float] = []
    for d in page.get_drawings():
        for it in d["items"]:
            puntos = []
            if it[0] == "l":
                puntos = [(it[1], it[2])]
            elif it[0] == "re":
                r = it[1]
                puntos = [(pymupdf.Point(r.x0, r.y0), pymupdf.Point(r.x0, r.y1)), (pymupdf.Point(r.x1, r.y0), pymupdf.Point(r.x1, r.y1))]
            for a, b in puntos:
                a, b = a * m, b * m
                if abs(a.x - b.x) < 0.8 and 12 < abs(a.y - b.y) < alto * 0.15 and alto * 0.03 < min(a.y, b.y) < alto * 0.16:
                    xs.append((a.x * escala, min(a.y, b.y) * escala))
    return xs


def _relectura_de_filas(img, cajas: list[dict]) -> list[dict]:
    """Los números de borne son chicos: el OCR de la hoja entera pierde varios. Se vuelve a leer, ampliada, la franja de
    cada fila que tiene su bornera («-XDI.1:», «-XT.1:»), a la derecha de ella."""
    import cv2
    import numpy as np
    alto, ancho = img.shape[:2]
    extra: list[dict] = []
    hechas: set[int] = set()
    for c in cajas:
        if c["conf"] < CONFIANZA or c["y"] < alto * 0.2 or not (_STRIP.match(c["texto"].strip()) and len(c["texto"].strip()) >= 3):
            continue
        if not c["texto"].strip().endswith(":") or round(c["y"] / 60) in hechas:
            continue
        hechas.add(round(c["y"] / 60))
        y0, y1, x0 = max(0, c["y"] - 70), min(alto, c["y"] + c["h"] + 110), max(0, c["x"] - 20)
        zona = img[y0:y1, x0:]
        grande = cv2.resize(zona, None, fx=2.5, fy=2.5, interpolation=cv2.INTER_CUBIC)
        res, _ = _ocr()(np.ascontiguousarray(grande))
        for box, texto, conf in res or []:
            xs, ys = [q[0] for q in box], [q[1] for q in box]
            extra.append({"x": int(x0 + min(xs) / 2.5), "y": int(y0 + min(ys) / 2.5), "w": int((max(xs) - min(xs)) / 2.5),
                          "h": int((max(ys) - min(ys)) / 2.5), "texto": texto, "conf": round(float(conf), 2)})
    return extra


def _clave_cache(ruta: Path, n: int) -> Path:
    st = ruta.stat()
    clave = f"{ruta.name}|{st.st_size}|{int(st.st_mtime)}|{n}|{DPI}|cableado-v2"
    return CACHE / (hashlib.sha1(clave.encode("utf-8")).hexdigest() + ".json")


def leer_hoja(ruta, n: int, doc=None) -> list[FilaBorne]:
    """Filas de la hoja `n` (desde 1). [] si no hay OCR o la hoja no es de cableado."""
    import numpy as np
    import pymupdf
    ruta = Path(str(ruta))
    cache = _clave_cache(ruta, n)
    propio = doc is None
    doc = doc or pymupdf.open(str(ruta))
    try:
        page = doc[n - 1]
        escala = DPI / 72
        if cache.exists():
            datos = json.loads(cache.read_text(encoding="utf-8"))
        else:
            if not disponible():
                return []
            pm = page.get_pixmap(dpi=DPI)
            img = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.h, pm.w, pm.n)[:, :, :3]
            res, _ = _ocr()(np.ascontiguousarray(img))
            cajas = []
            for box, texto, conf in res or []:
                xs, ys = [p[0] for p in box], [p[1] for p in box]
                cajas.append({"x": int(min(xs)), "y": int(min(ys)), "w": int(max(xs) - min(xs)), "h": int(max(ys) - min(ys)),
                              "texto": texto, "conf": round(float(conf), 2)})
            cajas += _relectura_de_filas(img, cajas)
            datos = {"ancho": pm.width, "alto": pm.height, "cajas": cajas, "bordes": _bordes_del_encabezado(page, escala)}
            CACHE.mkdir(exist_ok=True)
            tmp = cache.with_suffix(".tmp")
            tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
            tmp.replace(cache)
        return analizar_hoja(datos["cajas"], datos["bordes"], datos["ancho"], datos["alto"], n)
    finally:
        if propio:
            doc.close()


def hojas_de_cableado(doc, excluir=()) -> list[int]:
    """Hojas candidatas: las que tienen una franja de celdas en el encabezado y casi no tienen texto (contenido dibujado).
    `excluir`: hojas que ya se sabe que son otra cosa (p. ej. las tablas de bornes del final)."""
    import ocr as ocr_viejo
    return [i + 1 for i, pg in enumerate(doc) if (i + 1) not in set(excluir)
            and ocr_viejo.necesita_ocr(pg, min_caracteres=700, min_dibujos=800) and len(_bordes_del_encabezado(pg, 1.0)) >= 4]


def leer_cableado(ruta, avance: Optional[Callable[[int, int], None]] = None, excluir=()) -> list[FilaBorne]:
    """Todas las filas de las hojas de cableado del PDF ([] si no hay OCR). `avance(n, total)`."""
    import pymupdf
    filas: list[FilaBorne] = []
    if not disponible():
        return filas
    with pymupdf.open(str(ruta)) as doc:
        hojas = hojas_de_cableado(doc, excluir)
        for k, n in enumerate(hojas, 1):
            if avance:
                avance(k, len(hojas))
            filas += leer_hoja(ruta, n, doc)
    return filas
