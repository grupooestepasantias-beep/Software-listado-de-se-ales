"""OCR de las páginas de un plano que no traen texto (el texto está dibujado como líneas/vectores o es una imagen).

Usa rapidocr-onnxruntime si está instalado (opcional: sin él la app sigue funcionando y avisa qué páginas no pudo leer).
El resultado de cada página se guarda en `cache_ocr/` (clave = archivo + tamaño + fecha + página + dpi): el OCR tarda
unos 20 s por página, pero se hace una sola vez por archivo.

Cada caja devuelta es {x, y, w, h, texto, conf} en píxeles de la página ya girada (como se la ve en pantalla)."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Callable, Optional

CACHE = Path(__file__).parent / "cache_ocr"
_motor = None


def disponible() -> bool:
    try:
        import rapidocr_onnxruntime  # noqa: F401
        import numpy  # noqa: F401
    except ImportError:
        return False
    return True


def _ocr():
    global _motor
    if _motor is None:
        from rapidocr_onnxruntime import RapidOCR
        _motor = RapidOCR()
    return _motor


def _archivo_cache(ruta: Path, n: int, dpi: int) -> Path:
    st = ruta.stat()
    clave = f"{ruta.resolve()}|{st.st_size}|{int(st.st_mtime)}|{n}|{dpi}"
    return CACHE / (hashlib.sha1(clave.encode("utf-8")).hexdigest() + ".json")


def necesita_ocr(page, min_caracteres: int = 700, min_dibujos: int = 800) -> bool:
    """Una hoja con poco texto y muchísimos trazos tiene el contenido dibujado (texto en vectores): hay que leerla
    con OCR. También las que son una sola imagen sin texto."""
    texto = len(page.get_text().strip())
    if texto >= min_caracteres:
        return False
    return len(page.get_drawings()) >= min_dibujos or (texto < 50 and bool(page.get_images()))


def leer_pagina(ruta, n: int, dpi: int = 200, doc=None) -> Optional[list[dict]]:
    """Cajas de texto de la página `n` (desde 1), o None si no hay motor de OCR. Usa y completa la caché."""
    ruta = Path(str(ruta))
    cache = _archivo_cache(ruta, n, dpi)
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
        res, _ = _ocr()(img)
    finally:
        if propio:
            doc.close()
    cajas = []
    for box, texto, conf in res or []:
        xs, ys = [p[0] for p in box], [p[1] for p in box]
        cajas.append({"x": int(min(xs)), "y": int(min(ys)), "w": int(max(xs) - min(xs)), "h": int(max(ys) - min(ys)),
                      "texto": texto, "conf": round(float(conf), 2)})
    CACHE.mkdir(exist_ok=True)
    tmp = cache.with_suffix(".tmp")
    tmp.write_text(json.dumps(cajas, ensure_ascii=False), encoding="utf-8")
    tmp.replace(cache)
    return cajas


def leer_paginas(ruta, paginas: list[int], dpi: int = 200,
                 avance: Optional[Callable[[int, int], None]] = None) -> dict[int, Optional[list[dict]]]:
    """OCR de varias páginas de un PDF (abre el archivo una sola vez)."""
    import pymupdf
    salida: dict[int, Optional[list[dict]]] = {}
    with pymupdf.open(str(ruta)) as doc:
        for i, n in enumerate(paginas, 1):
            if avance:
                avance(i, len(paginas))
            salida[n] = leer_pagina(ruta, n, dpi, doc)
    return salida
