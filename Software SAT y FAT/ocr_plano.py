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
    return hashlib.sha1(f"{os.path.abspath(ruta)}|{st.st_size}|{st.st_mtime_ns}|termicas-v3".encode()).hexdigest()


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


def _a_original(giro, x, y, ancho, alto):
    """Punto (x, y) de la imagen girada con np.rot90(giro) -> coordenadas de la imagen original (ancho x alto)."""
    return (ancho - 1 - y, x) if giro == 1 else (y, alto - 1 - x)


def _banda_superior(img):
    """Textos de la franja superior de la hoja (títulos y encabezados de columnas), en píxeles de la hoja."""
    import numpy as np
    return _leer(np.ascontiguousarray(img[: int(img.shape[0] * 0.2)]))


def _termicas_de_la_hoja(pagina):
    """{codigo: (x, y)} de las térmicas de la hoja (posición en píxeles a 300 dpi) y los textos de la franja superior."""
    import cv2
    import numpy as np
    encontradas = {}
    img = _imagen(pagina, 300)
    alto0, ancho0 = img.shape[:2]
    for giro in (1, 3):
        rotada = np.ascontiguousarray(np.rot90(img, giro))
        lecturas = _leer(rotada)
        alto, ancho = rotada.shape[:2]
        for t, c, (x0, y0, x1, y1) in lecturas:
            m = CODIGO.match(t)
            if m and c >= CONFIANZA and not re.fullmatch(r"Q\d+\.", m.group(1)):
                encontradas.setdefault(m.group(1), _a_original(giro, (x0 + x1) / 2, (y0 + y1) / 2, ancho0, alto0))
        for t, c, (x0, y0, x1, y1) in lecturas:
            if CORRIENTE.match(t) and c >= CONFIANZA:
                oy, ox = max(0, int(y0) - ENTORNO), max(0, int(x0) - ENTORNO)
                recorte = rotada[oy:min(alto, int(y1) + ENTORNO), ox:min(ancho, int(x1) + ENTORNO)]
                grande = cv2.resize(recorte, None, fx=AMPLIACION, fy=AMPLIACION, interpolation=cv2.INTER_CUBIC)
                for t2, c2, (a0, b0, a1, b1) in _leer(np.ascontiguousarray(grande)):
                    m = CODIGO.match(t2)
                    if m and c2 >= CONFIANZA and not re.fullmatch(r"Q\d+\.", m.group(1)):
                        cx, cy = ox + (a0 + a1) / 2 / AMPLIACION, oy + (b0 + b1) / 2 / AMPLIACION
                        encontradas.setdefault(m.group(1), _a_original(giro, cx, cy, ancho0, alto0))
    return encontradas, _banda_superior(img)


TENSION = re.compile(r"(\d{2,3})\s?V\s?(CC|CA|DC|AC)\b", re.I)


def _columna(x, textos):
    """El texto (x0, x1, texto) cuyo centro está más cerca de x."""
    return min(textos, key=lambda t: abs((t[0] + t[1]) / 2 - x)) if textos else None


def _descripcion_y_tension(posicion, banda):
    """Encabezado de columna y título de la hoja más cercanos (en horizontal) a la térmica."""
    x = posicion[0]
    lineas = sorted(((x0, y0, x1, re.sub(r"(?<=[A-Z])0(?=[A-Z])", "O", t)) for t, c, (x0, y0, x1, y1) in banda
                     if c >= 0.7 and len(t) > 2), key=lambda l: l[1])
    es_titulo = lambda t: bool(TENSION.search(t)) and t.upper().startswith(("CIRCUIT", "DISTRIB"))
    titulos = [(x0, x1, t) for x0, y0, x1, t in lineas if es_titulo(t)]
    cabeceras = [(x0, x1, t) for x0, y0, x1, t in lineas
                 if not es_titulo(t) and t.upper() == t and sum(ch.isalpha() for ch in t) >= 5 and "/" not in t.replace(" / ", "")]
    titulo = _columna(x, titulos)
    cabecera = _columna(x, cabeceras)
    tension = ""
    if titulo:
        m = TENSION.search(titulo[2])
        tension = f"{m.group(1)} {'VCA' if m.group(2).upper() in ('CA', 'AC') else 'VCC'}"
    descripcion = cabecera[2] if cabecera else ""
    if cabecera and titulo and titulo[2].upper() != descripcion.upper():
        descripcion += f" ({titulo[2]})"
    return descripcion, tension



def _con_cache(ruta, etiqueta, calcular):
    """Resultado JSON guardado en la caché del usuario (clave = huella del archivo + etiqueta)."""
    archivo = os.path.join(_carpeta_cache(), _clave(ruta) + "-" + etiqueta + ".json")
    if os.path.exists(archivo):
        with open(archivo, encoding="utf-8") as f:
            return json.load(f)
    resultado = calcular()
    with open(archivo, "w", encoding="utf-8") as f:
        json.dump(resultado, f)
    return resultado


def _hojas_con_termicas(ruta, progreso):
    """Datos crudos del OCR de las hojas con interruptores: {hoja: {"posiciones": {Q: [x, y]}, "banda": [[t, c, caja]]}}."""
    import numpy as np
    doc = pymupdf.open(ruta)
    n = len(doc)
    candidatas = []
    for pagina in doc:
        if progreso:
            progreso(f"Buscando interruptores en la hoja {pagina.number + 1} de {n}…", 0.4 * pagina.number / n)
        rapido = _leer(np.ascontiguousarray(np.rot90(_imagen(pagina, 150), 3)))
        if any(CORRIENTE.match(t) and c >= CONFIANZA for t, c, _ in rapido):
            candidatas.append(pagina.number)
    hojas = {}
    for i, num in enumerate(candidatas):
        if progreso:
            progreso(f"Leyendo las térmicas de la hoja {num + 1} (OCR)…", 0.4 + 0.6 * i / max(len(candidatas), 1))
        posiciones, banda = _termicas_de_la_hoja(doc[num])
        hojas[str(num + 1)] = {"posiciones": {q: list(p) for q, p in posiciones.items()},
                               "banda": [[t, c, list(caja)] for t, c, caja in banda]}
    return hojas


def termicas_en_hojas(ruta, progreso=None):
    """{térmica: {"paginas", "tension", "descripcion"}} que el OCR lee en las hojas con interruptores termomagnéticos.

    tension y descripcion salen del título y del encabezado de columna de la hoja (a confirmar). Devuelve {} sin OCR.
    """
    if not disponible():
        return {}
    hojas = _con_cache(ruta, "termicas-raw-v1", lambda: _hojas_con_termicas(ruta, progreso))
    encontradas = {}
    for num, hoja in hojas.items():
        for q, pos in hoja["posiciones"].items():
            descripcion, tension = _descripcion_y_tension(pos, [(t, c, tuple(caja)) for t, c, caja in hoja["banda"]])
            e = encontradas.setdefault(q, {"paginas": [], "tension": tension, "descripcion": descripcion})
            e["paginas"].append(int(num))
    for q in list(encontradas):  # "Q48" suelto es lectura parcial de "Q48.1"
        if any(o.startswith(q + ".") for o in encontradas):
            del encontradas[q]
    return encontradas


# ---------------------------------------------------------------- elementos de las entradas digitales (-KI3.2, -QC…)
def _elemento(texto_):
    """Nombre normalizado del elemento (contacto de relé o térmica) o ''. El OCR lee la I de -KI3.2 como 1 o l."""
    t = texto_.strip().replace(" ", "")
    m = re.fullmatch(r"[-I]?(Q[A-Z0-9]{1,3}(?:\.\d)?)", t)
    if m:
        return "-" + m.group(1)
    m = re.fullmatch(r"-?K([A-HJ-Z])(\d+)\.(\d+)", t)
    if m:
        return f"-K{m.group(1)}{m.group(2)}.{m.group(3)}"
    m = re.fullmatch(r"-?K[1Il]?(\d+)\.(\d+)", t)
    return f"-KI{m.group(1)}.{m.group(2)}" if m else ""


def _leer_hoja_de_entradas(img):
    """OCR de la hoja completa + una relectura ampliada de la franja de los elementos (texto chico, el OCR lo pierde)."""
    import cv2
    import numpy as np
    lecturas = [[t, c, list(caja)] for t, c, caja in _leer(img)]
    titulo = next((caja for t, c, caja in lecturas if c >= 0.7 and "ENTRADASDIGITALES" in re.sub(r"\s+", "", t).upper()), None)
    if titulo:
        y0 = int(titulo[1]) + 400
        banda = img[y0:y0 + 700]
        grande = cv2.resize(banda, None, fx=AMPLIACION, fy=AMPLIACION, interpolation=cv2.INTER_CUBIC)
        for t, c, (a0, b0, a1, b1) in _leer(np.ascontiguousarray(grande)):
            lecturas.append([t, c, [a0 / AMPLIACION, b0 / AMPLIACION + y0, a1 / AMPLIACION, b1 / AMPLIACION + y0]])
    return lecturas


def _hojas_de_entradas(ruta, progreso):
    """OCR completo de las hojas 'ENTRADAS DIGITALES': {hoja: [[texto, confianza, caja]]}."""
    doc = pymupdf.open(ruta)
    n = len(doc)
    hojas = {}
    for pagina in doc:
        if progreso:
            progreso(f"Buscando las hojas de entradas digitales ({pagina.number + 1} de {n})…", 0.5 * pagina.number / n)
        img = _imagen(pagina, 250)
        if any("ENTRADASDIGITALES" in re.sub(r"\s+", "", t).upper() for t, c, _ in _banda_superior(img) if c >= 0.7):
            if progreso:
                progreso(f"Leyendo los elementos de la hoja {pagina.number + 1} (OCR)…", 0.5 + 0.5 * pagina.number / n)
            hojas[str(pagina.number + 1)] = _leer_hoja_de_entradas(img)
    return hojas


def elementos_de_entradas(ruta, progreso=None):
    """[(nombre de la señal según la hoja, elemento, hoja)] en orden de hoja y de columna. Devuelve [] sin OCR.

    En cada hoja el encabezado de cada columna trae el nombre de la señal y debajo va su elemento: se emparejan por
    posición solo si hay la misma cantidad de encabezados y de elementos (si no, la hoja se descarta).
    """
    if not disponible():
        return []
    hojas = _con_cache(ruta, "entradas-raw-v2", lambda: _hojas_de_entradas(ruta, progreso))
    salida = []
    for num in sorted(hojas, key=int):
        lecturas = [(t.strip(), c, tuple(caja)) for t, c, caja in hojas[num] if c >= 0.7]
        titulo = next((caja for t, c, caja in lecturas if "ENTRADASDIGITALES" in re.sub(r"\s+", "", t).upper()), None)
        if not titulo:
            continue
        ty = titulo[1]
        elementos = sorted(((caja[0], _elemento(t)) for t, c, caja in lecturas if ty + 400 < caja[1] < ty + 1100 and _elemento(t)))
        columnas = []
        for t, c, caja in sorted(lecturas, key=lambda l: (l[2][0], l[2][1])):
            if ty + 25 < caja[1] < ty + 170 and caja[3] - caja[1] < 70 and not _elemento(t) and len(t) > 2:
                if columnas and abs(columnas[-1][0] - caja[0]) < 40:
                    columnas[-1][1].append((caja[1], t))
                else:
                    columnas.append([caja[0], [(caja[1], t)]])
        nombres = [(c[0], " ".join(t for _, t in sorted(c[1]))) for c in columnas]
        usados = set()
        for x, el in elementos:  # cada elemento queda bajo su columna (a lo sumo ~110 px a un lado del encabezado)
            if not nombres:
                break
            x_col, nom = min(nombres, key=lambda n: abs(n[0] - x))
            if abs(x_col - x) <= 110 and x_col not in usados:
                usados.add(x_col)
                salida.append((nom, el, int(num)))
    return salida
