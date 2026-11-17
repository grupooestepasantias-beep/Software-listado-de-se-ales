"""Placa de cada módulo de E/S cuando el plano la trae DIBUJADA (sin texto): «UTR1.1.1», «UTR1.1.2»… sobre cada módulo.

`pdf_plano._placas_de_modulos` lee las placas del texto del PDF; en los planos donde están dibujadas (por ejemplo el
TCONTROL 13,2 kV, USRE-…-Ad-0821) quedaban vacías. Aquí se leen con OCR de la franja de arriba de la hoja, que es donde
va el rótulo, y se devuelven de izquierda a derecha, en el mismo orden que los módulos. Lo que no se puede leer (o no
coincide con la cantidad de módulos) queda vacío: no se adivina. Es rápido (una franja) y queda en la caché de `ocr.py`."""
from __future__ import annotations

import re
from pathlib import Path

import ocr

_PLACA = re.compile(r"^UTR\d+(?:\.\d+)*\.[A-Z0-9]+$")
DPI = 200
FRANJA = (0.0, 0.0, 1.0, 0.45)           # (x0, y0, x1, y1) de la hoja: los rótulos van arriba de los módulos


def _limpiar(t: str) -> str:
    """El OCR lee el 1 como I o l y mete espacios: «UTRI.1 .1» -> «UTR1.1.1»."""
    t = re.sub(r"\s+", "", t.strip().upper())
    return re.sub(r"(?<=[.R])[IL](?=\.|\d|$)", "1", t)


def por_ocr(page, cantidad: int) -> list[str]:
    """Las `cantidad` placas dibujadas de la hoja, de izquierda a derecha; [] si no hay OCR o no hay una por módulo."""
    if not ocr.disponible():
        return []
    ruta = Path(page.parent.name)
    d = ocr.leer_hoja(ruta, page.number + 1, dpi=DPI, doc=page.parent, recorte=FRANJA)
    if not d:
        return []
    placas = sorted((c["x"], _limpiar(c["texto"])) for c in d["cajas"] if c["conf"] >= 0.6 and _PLACA.match(_limpiar(c["texto"])))
    vistas, unicas = set(), []
    for x, t in placas:                          # una placa leída dos veces no cuenta dos veces
        if t not in vistas:
            vistas.add(t)
            unicas.append(t)
    return unicas if len(unicas) == cantidad else []
