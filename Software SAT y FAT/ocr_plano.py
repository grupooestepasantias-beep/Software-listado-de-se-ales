"""Lectura por OCR de lo que un plano trae dibujado como líneas en vez de texto (p. ej. los nombres de las térmicas -QC, -QS…).

Usa rapidocr-onnxruntime. Es lento, así que:
- primero una pasada rápida para encontrar las hojas con interruptores termomagnéticos (corrientes "10A", "4A"…);
- después, en esas hojas, una pasada fina en las dos orientaciones del texto vertical y una relectura ampliada
  alrededor de cada corriente encontrada (ahí está el nombre del interruptor);
- el resultado se guarda en disco (clave = huella del archivo) y se reutiliza.
Sin rapidocr instalado la app sigue funcionando: avisa y las térmicas se cargan a mano.
"""
import hashlib
import json
import os
import re
import tempfile

import pymupdf

CODIGO = re.compile(r"^-?(Q(?:[A-Z]{1,3}\d?|\d{1,3}(?:\.\d{1,2})?))$")
CORRIENTE = re.compile(r"^\d{1,3}\s?A$")
CONFIANZA = 0.85
AMPLIACION = 1.6
ENTORNO = 170  # píxeles (a 300 dpi) alrededor de cada corriente que se releen ampliados
_motor = None


def disponible():
    try:
        import cv2  # noqa: F401
        import numpy  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
    except Exception:
        return False
    return True


def _carpeta_cache():
    base = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "GeneradorSAT", "cache_ocr")
    os.makedirs(base, exist_ok=True)
    return base


def _clave(ruta):
    st = os.stat(ruta)
    return hashlib.sha1(f"{os.path.abspath(ruta)}|{st.st_size}|{st.st_mtime_ns}|termicas-v2".encode()).hexdigest()


def _ocr():
    global _motor
    if _motor is None:
        from rapidocr_onnxruntime import RapidOCR
        _motor = RapidOCR(max_side_len=5000, min_side_len=30)  # sin reducir la imagen: el texto del CAD es chico
    return _motor


def _imagen(pagina, dpi):
    import numpy as np
    pix = pagina.get_pixmap(dpi=dpi)
    return np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3]


def _leer(img):
    """[(texto, confianza, (x0, y0, x1, y1))] de una imagen."""
    res, _ = _ocr()(img)
    salida = []
    for caja, t, c in res or []:
        xs, ys = [p[0] for p in caja], [p[1] for p in caja]
        salida.append((t.strip(), float(c), (min(xs), min(ys), max(xs), max(ys))))
    return salida


def _codigos(lecturas):
    for t, c, _ in lecturas:
        m = CODIGO.match(t)
        if m and c >= CONFIANZA and not re.fullmatch(r"Q\d+\.", m.group(1)):
            yield m.group(1)


def _termicas_de_la_hoja(pagina):
    import cv2
    import numpy as np
    encontradas = set()
    img = _imagen(pagina, 300)
    for giro in (1, 3):
        rotada = np.ascontiguousarray(np.rot90(img, giro))
        lecturas = _leer(rotada)
        encontradas |= set(_codigos(lecturas))
        alto, ancho = rotada.shape[:2]
        for t, c, (x0, y0, x1, y1) in lecturas:
            if CORRIENTE.match(t) and c >= CONFIANZA:
                recorte = rotada[max(0, int(y0) - ENTORNO):min(alto, int(y1) + ENTORNO),
                                 max(0, int(x0) - ENTORNO):min(ancho, int(x1) + ENTORNO)]
                grande = cv2.resize(recorte, None, fx=AMPLIACION, fy=AMPLIACION, interpolation=cv2.INTER_CUBIC)
                encontradas |= set(_codigos(_leer(np.ascontiguousarray(grande))))
    return encontradas


def termicas_en_hojas(ruta, progreso=None):
    """{codigo: [paginas]} de las térmicas que el OCR lee en las hojas con interruptores termomagnéticos.

    progreso(texto, fraccion) se llama durante el proceso. Devuelve {} si no hay OCR disponible.
    """
    if not disponible():
        return {}
    archivo = os.path.join(_carpeta_cache(), _clave(ruta) + ".json")
    if os.path.exists(archivo):
        with open(archivo, encoding="utf-8") as f:
            return json.load(f)
    doc = pymupdf.open(ruta)
    n = len(doc)
    candidatas = []
    for pagina in doc:
        if progreso:
            progreso(f"Buscando interruptores en la hoja {pagina.number + 1} de {n}…", 0.4 * pagina.number / n)
        rapido = _leer(__import__("numpy").ascontiguousarray(__import__("numpy").rot90(_imagen(pagina, 150), 3)))
        if any(CORRIENTE.match(t) and c >= CONFIANZA for t, c, _ in rapido):
            candidatas.append(pagina.number)
    encontradas = {}
    for i, num in enumerate(candidatas):
        if progreso:
            progreso(f"Leyendo las térmicas de la hoja {num + 1} (OCR)…", 0.4 + 0.6 * i / max(len(candidatas), 1))
        for q in _termicas_de_la_hoja(doc[num]):
            encontradas.setdefault(q, []).append(num + 1)
    for q in list(encontradas):  # "Q48" suelto es lectura parcial de "Q48.1"
        if any(o.startswith(q + ".") for o in encontradas):
            del encontradas[q]
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(encontradas, f)
    return encontradas
