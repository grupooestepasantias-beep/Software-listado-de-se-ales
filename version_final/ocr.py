"""OCR de las hojas de un plano cuyo contenido está dibujado (sin texto): usa rapidocr-onnxruntime si está instalado
(opcional: sin él la app sigue funcionando y avisa que no pudo leer los bornes).

El resultado de cada hoja se guarda en una caché local (`%TEMP%\\listado_ocr_cache`, clave = archivo + tamaño + fecha + hoja +
dpi + recorte): leer una hoja tarda ~15 s, pero se hace una sola vez por archivo.

Cada caja es {x, y, w, h, texto, conf} en píxeles de la hoja ya girada (como se la ve en pantalla)."""
from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path
from typing import Optional

CACHE = Path(tempfile.gettempdir()) / "listado_ocr_cache"
_motor = None


def disponible() -> bool:
    try:
        import numpy  # noqa: F401
        import rapidocr_onnxruntime  # noqa: F401
    except ImportError:
        return False
    return True


def _ocr():
    global _motor
    if _motor is None:
        from rapidocr_onnxruntime import RapidOCR
        _motor = RapidOCR()
    return _motor


def _archivo_cache(ruta: Path, n: int, dpi: int, recorte) -> Path:
    st = ruta.stat()
    clave = f"{ruta.name}|{st.st_size}|{int(st.st_mtime)}|{n}|{dpi}|{recorte}"
    return CACHE / (hashlib.sha1(clave.encode("utf-8")).hexdigest() + ".json")


def necesita_ocr(page, min_caracteres: int = 700, min_dibujos: int = 800) -> bool:
    """Una hoja con poco texto y muchísimos trazos tiene el contenido dibujado (texto en vectores)."""
    return len(page.get_text().strip()) < min_caracteres and len(page.get_drawings()) >= min_dibujos


def leer_hoja(ruta, n: int, dpi: int = 200, doc=None, recorte: Optional[tuple[float, float, float, float]] = None) -> Optional[dict]:
    """{hoja, ancho, alto, cajas} de la hoja `n` (desde 1), o None si no hay motor de OCR. `recorte` = (x0, y0, x1, y1) como
    proporciones de la hoja: sirve para mirar solo una franja (ej. el encabezado de una tabla), mucho más rápido."""
    ruta = Path(str(ruta))
    cache = _archivo_cache(ruta, n, dpi, recorte)
    if cache.exists():
        try:
            return json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            pass
    if not disponible():
        return None
    import numpy as np
    import pymupdf
    propio = doc is None
    doc = doc or pymupdf.open(str(ruta))
    try:
        pm = doc[n - 1].get_pixmap(dpi=dpi)
        img = np.frombuffer(pm.samples, dtype=np.uint8).reshape(pm.h, pm.w, pm.n)[:, :, :3]
        ancho, alto = pm.width, pm.height
        dx = dy = 0
        if recorte:
            x0, y0, x1, y1 = recorte
            dx, dy = int(x0 * ancho), int(y0 * alto)
            img = np.ascontiguousarray(img[dy:int(y1 * alto), dx:int(x1 * ancho)])
        res, _ = _ocr()(img)
    finally:
        if propio:
            doc.close()
    cajas = []
    for box, texto, conf in res or []:
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        cajas.append({"x": int(min(xs)) + dx, "y": int(min(ys)) + dy, "w": int(max(xs) - min(xs)), "h": int(max(ys) - min(ys)),
                      "texto": texto, "conf": round(float(conf), 2)})
    datos = {"hoja": n, "ancho": ancho, "alto": alto, "cajas": cajas}
    CACHE.mkdir(exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps(datos, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache)
    return datos
