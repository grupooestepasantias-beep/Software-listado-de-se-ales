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


VOCABULARIO = {  # el OCR pierde las tildes y a veces junta palabras: se restauran las del vocabulario de los planos
    "ALIMENTACION": "ALIMENTACIÓN", "SENALIZACION": "SEÑALIZACIÓN", "DISTRIBUCION": "DISTRIBUCIÓN",
    "EXPLORACION": "EXPLORACIÓN", "MIMICOS": "MÍMICOS", "CALEFACCION": "CALEFACCIÓN", "ILUMINACION": "ILUMINACIÓN",
    "POSITIVOOSCILANTE": "POSITIVO OSCILANTE", "TENSION": "TENSIÓN", "PROTECCION": "PROTECCIÓN", "MEDICION": "MEDICIÓN",
}


def restaurar_texto(texto_):
    return re.sub(r"[A-ZÑ]+", lambda m: VOCABULARIO.get(m.group(0), m.group(0)), texto_)


def _tension_de_otro_nivel(codigo, tension):
    """Q48.1 (48 V) bajo un título 'Distribución de 110 Vcc': el interruptor está después del convertidor, no es de esa tensión."""
    m = re.match(r"Q(\d{2,3})", codigo)
    numero = re.match(r"(\d+)", tension)
    return bool(m and numero and int(m.group(1)) in (24, 48, 60, 125) and int(m.group(1)) != int(numero.group(1)))


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
    descripcion = restaurar_texto(cabecera[2]) if cabecera else ""
    if cabecera and titulo and titulo[2].upper() != descripcion.upper():
        descripcion += f" ({restaurar_texto(titulo[2])})"
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
            if _tension_de_otro_nivel(q, tension):
                tension = ""  # el plano no dice la tensión de ese circuito: la completa el usuario
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
    m = re.fullmatch(r"[-I1l]?(Q[A-Z0-9]{1,3}(?:\.\d)?)", t)
    if m:
        return "-" + m.group(1)
    m = re.fullmatch(r"-?(PW\d+)", t)  # fuente de alimentación
    if m:
        return "-" + m.group(1)
    m = re.fullmatch(r"-?K([A-HJ-Z])(\d+)\.(\d+)", t)
    if m:
        return f"-K{m.group(1)}{m.group(2)}.{m.group(3)}"
    m = re.fullmatch(r"-?K[1Il]?(\d+)\.(\d+)", t)
    return f"-KI{m.group(1)}.{m.group(2)}" if m else ""


def _es_titulo_de_entradas(texto_):
    """'ENTRADAS DIGITALES' (el OCR lo lee a veces cortado: 'SDIGITALES'); 'SALIDAS DIGITALES' no cuenta."""
    t = re.sub(r"\s+", "", texto_).upper()
    return "DIGITALES" in t and not re.search(r"SALIDAS?DIGITALES", t)


def _leer_hoja_de_entradas(img):
    """OCR de la hoja completa + una relectura ampliada de la franja de los elementos (texto chico, el OCR lo pierde)."""
    import cv2
    import numpy as np
    lecturas = [[t, c, list(caja)] for t, c, caja in _leer(img)]
    titulo = next((caja for t, c, caja in lecturas if c >= 0.7 and _es_titulo_de_entradas(t)), None)
    if titulo:
        y0 = int(titulo[1]) + 400
        banda = img[y0:y0 + 700]
        grande = cv2.resize(banda, None, fx=AMPLIACION, fy=AMPLIACION, interpolation=cv2.INTER_CUBIC)
        for t, c, (a0, b0, a1, b1) in _leer(np.ascontiguousarray(grande)):
            lecturas.append([t, c, [a0 / AMPLIACION, b0 / AMPLIACION + y0, a1 / AMPLIACION, b1 / AMPLIACION + y0]])
    for t, c, (a0, b0, a1, b1) in list(lecturas):  # números de borne (1, 2, 3…) sobre los puntos de la bornera "-XFI"
        if re.fullmatch(r"-?XFI\d*", t.replace(" ", "")) and c >= 0.7:
            y0, x0 = max(0, int(b0) - 90), int(a1)
            zona = img[y0:int(b1) + 40, x0:]
            grande = cv2.resize(zona, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
            for t2, c2, (d0, e0, d1, e1) in _leer(np.ascontiguousarray(grande)):
                lecturas.append([t2, c2, [x0 + d0 / 3, y0 + e0 / 3, x0 + d1 / 3, y0 + e1 / 3]])
    return lecturas


def _par_consecutivo(digitos):
    """'12' -> '1-2', '910' -> '9-10' si son dos números consecutivos; si no, ''."""
    for i in range(1, len(digitos)):
        a, b = digitos[:i], digitos[i:]
        if not b.startswith("0") and not a.startswith("0") and int(b) == int(a) + 1:
            return f"{a}-{b}"
    return ""


def _hojas_de_entradas(ruta, progreso):
    """OCR completo de las hojas 'ENTRADAS DIGITALES': {hoja: [[texto, confianza, caja]]}."""
    doc = pymupdf.open(ruta)
    n = len(doc)
    hojas = {}
    for pagina in doc:
        if progreso:
            progreso(f"Buscando las hojas de entradas digitales ({pagina.number + 1} de {n})…", 0.5 * pagina.number / n)
        img = _imagen(pagina, 250)
        if any(_es_titulo_de_entradas(t) for t, c, _ in _banda_superior(img) if c >= 0.7):
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
    hojas = _con_cache(ruta, "entradas-raw-v3", lambda: _hojas_de_entradas(ruta, progreso))
    salida = []
    for num in sorted(hojas, key=int):
        lecturas = [(t.strip(), c, tuple(caja)) for t, c, caja in hojas[num] if c >= 0.7]
        titulo = next((caja for t, c, caja in lecturas if _es_titulo_de_entradas(t)), None)
        if not titulo:
            continue
        ty = titulo[1]
        elementos = [(caja[0], _elemento(t)) for t, c, caja in lecturas if ty + 400 < caja[1] < ty + 1100 and _elemento(t)]
        for t, c, caja in lecturas:  # bornes de bornera: "-XFI" y, sobre cada punto, el número de borne
            m = re.fullmatch(r"-?(XFI\d*)", t.replace(" ", ""))
            if m and ty + 400 < caja[1] < ty + 1200:
                numeros = sorted((c2[0], t2) for t2, cc, c2 in lecturas
                                 if re.fullmatch(r"\d{1,3}", t2) and cc >= 0.7 and c2[0] > caja[0] and caja[1] - 70 < c2[1] < caja[1] + 25)
                unicos = []  # el OCR repite cada número (y a veces lo parte: "910" y "9", "10"): uno por posición, el más largo
                for x, n in numeros:
                    if unicos and x - unicos[-1][0] < 60:
                        if len(n) > len(unicos[-1][1]):
                            unicos[-1] = (x, n)
                    else:
                        unicos.append((x, n))
                numeros = unicos
                pares = [_par_consecutivo(n) for _, n in numeros]
                if len(numeros) >= 2 and all(pares):  # cada señal usa dos puntos: el OCR junta "1 2" en "12"
                    numeros = [(x, p_) for (x, _), p_ in zip(numeros, pares)]
                elementos += [(x, f"-{m.group(1)}/{n}") for x, n in numeros]
        elementos.sort()
        columnas = []
        for t, c, caja in sorted(lecturas, key=lambda l: (l[2][0], l[2][1])):
            if ty + 25 < caja[1] < ty + 170 and caja[3] - caja[1] < 70 and not _elemento(t) and len(t) > 2:
                if columnas and abs(columnas[-1][0] - caja[0]) < 40:
                    columnas[-1][1].append((caja[1], t))
                else:
                    columnas.append([caja[0], [(caja[1], t)]])
        nombres = [(c[0], " ".join(t for _, t in sorted(c[1]))) for c in columnas]
        usados = set()
        nombres.sort()
        for x, el in elementos:  # el elemento pertenece a la columna cuyo encabezado empieza antes (hasta ~120 px a la derecha)
            previas = [n for n in nombres if n[0] <= x + 120]
            if not previas:
                continue
            x_col, nom = previas[-1]
            if x_col not in usados:
                usados.add(x_col)
                salida.append((nom, el, int(num)))
    return salida


# ---------------------------------------------------------------- comandos (bobinas -KC1.3, -KC2.3…)
def _es_hoja_de_comandos(banda):
    return any("COMAND" in re.sub(r"\s+", "", t).upper().replace("0", "O") for t, c, _ in banda if c >= 0.7)


def _hojas_de_comandos(ruta, progreso):
    """{hoja: [[texto, confianza, caja]]} de las hojas de comando: solo las bobinas -KC<k>.<n> y los encabezados de verbo."""
    doc = pymupdf.open(ruta)
    n = len(doc)
    hojas = {}
    for pagina in doc:
        if progreso:
            progreso(f"Buscando las hojas de comandos ({pagina.number + 1} de {n})…", pagina.number / n)
        img = _imagen(pagina, 250)
        if _es_hoja_de_comandos(_banda_superior(img)):
            lecturas = _leer(img)
            hojas[str(pagina.number + 1)] = [[t, c, list(caja)] for t, c, caja in lecturas
                                              if re.fullmatch(r"-?K[CO0][12]\.\d", t.replace(" ", ""))]
    return hojas


def _bandas_de_comandos(ruta, hojas):
    """Textos de la franja superior de cada hoja de comando (dicen si es la celda de ENTRADA o la de SALIDA y a veces el interruptor)."""
    doc = pymupdf.open(ruta)
    return {num: [t for t, c, _ in _banda_superior(_imagen(doc[int(num) - 1], 250)) if c >= 0.7] for num in hojas}


def elementos_de_comandos(ruta, progreso=None):
    """[(verbo, lado, elemento, hoja, interruptor)]: bobinas -KC1.n (Apertura) y -KC2.n (Cierre) de la celda de ENTRADA o de SALIDA.

    La numeración de las bobinas cambia entre revisiones (rB: -KC1.1/-KC2.1 y -KC1.2/-KC2.2; r2: .3 y .2), así que la celda
    se toma del título de la hoja ("CELDA ENTRADA" / "CELDA SALIDA", y el interruptor 252-0n si el título lo dice).
    En cada hoja -KC1 va a la izquierda de -KC2 (ABRIR / CERRAR): si el orden no coincide, la bobina no se usa.
    """
    if not disponible():
        return []
    hojas = _con_cache(ruta, "comandos-raw-v1", lambda: _hojas_de_comandos(ruta, progreso))
    bandas = _con_cache(ruta, "comandos-bandas-v1", lambda: _bandas_de_comandos(ruta, hojas))
    salida, vistos = [], set()
    for num in sorted(hojas, key=int):
        texto_ = re.sub(r"\s+", "", " ".join(bandas.get(num, []))).upper().replace("0", "O")
        lado = "ENTRADA" if "CELDAENTRADA" in texto_ else "SALIDA" if "CELDASALIDA" in texto_ else ""
        interruptor = (re.search(r"252-?(\d\d)", " ".join(bandas.get(num, [])).replace(" ", "")) or [None, ""])[1]
        bobinas = {}
        for t, c, caja in hojas[num]:
            m = re.fullmatch(r"-?K[CO0]([12])\.(\d)", t.replace(" ", ""))
            if m and c >= 0.85:
                bobinas.setdefault(m.group(2), {})[int(m.group(1))] = (caja[0], m.group(0).replace("O", "C").replace("0", "C"))
        for por_k in bobinas.values():
            if not lado or set(por_k) != {1, 2} or not por_k[1][0] < por_k[2][0]:
                continue
            for k, verbo in ((1, "Apertura"), (2, "Cierre")):
                if (k, lado) not in vistos:
                    vistos.add((k, lado))
                    nombre = por_k[k][1]
                    salida.append((verbo, lado, nombre if nombre.startswith("-") else "-" + nombre, int(num), interruptor))
    return salida
