"""Lectura y validación de los planos PDF de ingeniería.

Todo lo que se carga en los anexos sale de los PDF y conserva su respaldo (archivo, página, módulo,
terminal, borne y referencia). Nada se completa por suposición: lo que el plano no dice queda como
pendiente y el generador lo reclama al usuario.

- leer_funcional(ruta)  -> señales (DI) y comandos (DO) con respaldo + problemas de lectura
- leer_termicas(rutas)  -> térmicas (-Q…) con las páginas donde aparecen
- validar_planos(...)   -> identidad, revisión, estación y coherencia entre planos
- comparar_con_pdf(...) -> contrasta lo que hay en las tablas con lo que dicen los planos
"""
import hashlib
import os
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass

import pymupdf

from validador import ADVERTENCIA, BLOQUEANTE, CONSISTENCIA, DOCUMENTAL, INFO, Hallazgo

COMUNES = re.compile(r"^(negativo|positivo)\b|^110$", re.I)

# SUGERENCIAS tomadas de los protocolos de referencia (La Paz). NO están en los planos: solo se usan
# si el usuario las pide y las confirma; después de aplicarlas quedan como dato ingresado por el usuario.
SUGERENCIAS_TERMICAS = {
    "Q220": ("220 VCA", "Termomagnética general"),
    "Q221": ("220 VCA", "Iluminación"),
    "Q222": ("220 VCA", "Toma"),
    "Q223": ("220 VCA", "Toma"),
    "Q224": ("220 VCA", "Ventilación y calefacción"),
    "Q4": ("220 VCA", "Alimentación segura (UPS)"),
    "Q1": ("110 VCC", "Circuito de alimentación general"),
    "QS": ("110 VCC", "Circuito de alimentación señalización y alarmas"),
    "Q2": ("110 VCC", "Circuito de alimentación Fuente 1"),
    "Q3": ("110 VCC", "Circuito de alimentación Fuente 2"),
}
ORDEN_TERMICAS = list(SUGERENCIAS_TERMICAS)


@dataclass
class Senal:
    borne: str
    nombre: str
    tipo: str          # DI (entrada digital) o DO (salida digital / comando)
    modulo: str        # A2.3, A1.8…
    terminal: int      # terminal dentro del módulo
    referencia: str    # H03/D01… (si el plano la indica)
    pagina_modulo: int
    pagina_cableado: int
    archivo: str

    def tupla(self):
        return (self.borne or (f"(ver {self.referencia})" if self.referencia else ""), self.nombre)


_CACHE = {}


def _clave(ruta):
    st = os.stat(ruta)
    return (os.path.abspath(ruta), st.st_mtime_ns, st.st_size)


def _abrir(ruta):
    return pymupdf.open(ruta)


def _titulo(pagina):
    texto = pagina.get_text()
    for t in ("DETALLE MODULO DI", "ENTRADAS DIGITALES", "SALIDAS DIGITALES"):
        if t in texto:
            return t
    return ""


def _lineas(pagina):
    """Líneas de texto con su caja, en coordenadas sin rotar."""
    for b in pagina.get_text("dict")["blocks"]:
        for linea in b.get("lines", []):
            texto = " ".join("".join(s["text"] for s in linea["spans"]).split())
            # Se descartan las letras grandes de las nubes de revisión ("C")
            if texto and (linea["spans"][0]["size"] < 12 or re.fullmatch(r"A\d+\.\d+", texto)):
                yield linea["bbox"], texto


def _modulos(pagina):
    """[(modulo, tipo, [(terminal, nombre), ...])] de una página DETALLE MODULO DI/DO."""
    lineas = list(_lineas(pagina))
    etiquetas = sorted((bb[1], bb[0], t) for bb, t in lineas if re.fullmatch(r"A\d+\.\d+", t))
    if not etiquetas:
        return []
    x_etiqueta = min(x for _, x, _ in etiquetas)
    columnas = {t: [] for _, _, t in etiquetas}
    for bb, t in lineas:
        if not (150 < bb[0] < x_etiqueta - 20):
            continue
        previas = [m for y, _, m in etiquetas if y <= bb[1] + 5]
        if previas:
            columnas[previas[-1]].append((bb[0], t))
    salida = []
    for _, _, modulo in etiquetas:
        textos = [t for _, t in sorted(columnas[modulo], key=lambda c: -c[0])]
        textos = [t for t in textos if t != "110"]
        if not textos:
            continue
        es_do = sum(t.lower().startswith("positivo") for t in textos) >= 4
        salida.append((modulo, "DO" if es_do else "DI", list(enumerate(textos, start=1))))
    return salida


def _slots_entradas(pagina):
    """Una página ENTRADAS DIGITALES: [(bornera, borne o '', referencia)] en orden."""
    palabras = [(w[0], w[1], w[4]) for w in pagina.get_text("words")]
    borneras = [(x, y, t) for x, y, t in palabras if re.fullmatch(r"-XFI\d+/", t)]
    if not borneras:
        return []
    bx, _, bornera = borneras[0]
    cables = sorted((y, t) for x, y, t in palabras if re.fullmatch(r"\d{3,4}", t) and bx - 75 < x < bx - 25)
    slots = []
    for y, _ in cables:
        borne = [t for x, yy, t in palabras if abs(x - bx) < 15 and re.fullmatch(r"\d{1,3}", t) and 0 < yy - y < 25]
        ref = [t for x, yy, t in palabras if re.fullmatch(r"H\d+/[A-Z]\d+", t) and abs(yy - y) < 15]
        slots.append((bornera.rstrip("/"), borne[0] if borne else "", ref[0] if ref else ""))
    return slots


def _slots_salidas(pagina):
    """Bornes de comando XF0n-m de una página SALIDAS DIGITALES, en orden de salida."""
    palabras = [(round(w[0] / 40), w[1], w[4]) for w in pagina.get_text("words") if re.fullmatch(r"XF\d+-\d+", w[4])]
    if not palabras:
        return []
    columnas = {}
    for x, y, t in palabras:
        columnas.setdefault(x, []).append((y, t))
    orden = sorted(columnas, key=lambda x: -len(columnas[x]))
    principal = sorted(columnas[orden[0]])
    if len(orden) > 1 and len(columnas[orden[1]]) == len(principal):
        otra = sorted(columnas[orden[1]])
        bornes = []
        for (_, a), (_, b) in zip(principal, otra):
            base, na = a.rsplit("-", 1)
            nb = b.rsplit("-", 1)[1]
            bornes.append(f"{base}-{min(int(na), int(nb))}/{max(int(na), int(nb))}")
        return bornes
    return [t for _, t in principal]


def _h(codigo, gravedad, ruta, pagina, desc, sol="", tipo=DOCUMENTAL, confirmable=False):
    h = Hallazgo(codigo, gravedad, tipo, os.path.basename(ruta), f"página {pagina}" if pagina else "", desc, sol)
    h.confirmable = confirmable
    return h


# ------------------------------------------------------------------ señales y comandos
def leer_funcional(ruta):
    """Lee el esquema funcional. Devuelve (senales, comandos, problemas).

    senales/comandos: listas de Senal (sin reservas ni comunes). problemas: [Hallazgo] de la lectura.
    """
    k = _clave(ruta)
    if ("funcional",) + k in _CACHE:
        return _CACHE[("funcional",) + k]
    doc = _abrir(ruta)
    archivo = os.path.basename(ruta)
    secciones, grupos = [], []
    for pagina in doc:
        n = pagina.number + 1
        texto = pagina.get_text()
        titulo = _titulo(pagina)
        if "PORTADA" in texto:
            secciones.append({"di": [], "do": []})
        elif "LISTADO MODULOS" in texto:
            grupos.append({"di": [], "do": []})
        elif titulo == "DETALLE MODULO DI" and grupos:
            for modulo, tipo, terminales in _modulos(pagina):
                dest = grupos[-1]["do" if tipo == "DO" else "di"]
                dest += [(modulo, t, nom, n) for t, nom in terminales if not COMUNES.search(nom)]
        elif titulo == "ENTRADAS DIGITALES" and secciones:
            secciones[-1]["di"] += [s + (n,) for s in _slots_entradas(pagina)]
        elif titulo == "SALIDAS DIGITALES" and secciones:
            secciones[-1]["do"] += [(b, n) for b in _slots_salidas(pagina)]

    secciones = [s for s in secciones if s["di"] or s["do"]]
    problemas, senales, comandos = [], [], []
    if not grupos:
        problemas.append(_h("S00", BLOQUEANTE, ruta, 0, "El PDF no tiene páginas 'DETALLE MODULO DI/DO': no parece un "
                            "esquema funcional con el formato esperado.", "Cargar el esquema funcional correcto."))
    for n, grupo in enumerate(grupos, start=1):
        clave = (len(grupo["di"]), len(grupo["do"]))
        seccion = next((s for s in secciones if (len(s["di"]), len(s["do"])) == clave), None)
        if seccion is None:
            pg = grupo["di"][0][3] if grupo["di"] else (grupo["do"][0][3] if grupo["do"] else 0)
            problemas.append(_h("S01", BLOQUEANTE, ruta, pg,
                                f"El grupo de módulos {n} ({clave[0]} entradas y {clave[1]} salidas) no coincide con ninguna "
                                "sección de hojas de cableado: no se pueden asignar los bornes.",
                                "Revisar el plano; los bornes de ese grupo no se completan por suposición."))
            seccion = {"di": [], "do": []}
        else:
            secciones.remove(seccion)
        for i, (modulo, terminal, nombre, pg) in enumerate(grupo["di"]):
            bornera, numero, ref, pgc = seccion["di"][i] if i < len(seccion["di"]) else ("", "", "", 0)
            if nombre.lower().startswith("reserva"):
                continue
            borne = f"{bornera}/{numero}" if numero else ""
            senales.append(Senal(borne, nombre, "DI", modulo, terminal, ref, pg, pgc, archivo))
        for i, (modulo, terminal, nombre, pg) in enumerate(grupo["do"]):
            if nombre.lower().startswith("reserva"):
                continue
            borne, pgc = seccion["do"][i] if i < len(seccion["do"]) else ("", 0)
            comandos.append(Senal(borne, nombre, "DO", modulo, terminal, "", pg, pgc, archivo))

    # Controles de coherencia de la lectura
    for s in senales + comandos:
        if not s.nombre.strip():
            problemas.append(_h("S05", BLOQUEANTE, ruta, s.pagina_modulo, f"Terminal {s.modulo}:{s.terminal} sin nombre de señal."))
        if not s.borne:
            ref = f" (el plano indica la referencia {s.referencia})" if s.referencia else ""
            problemas.append(_h("S03", BLOQUEANTE, ruta, s.pagina_modulo,
                                f"'{s.nombre}' ({s.modulo}:{s.terminal}) no tiene borne de bornera en el plano{ref}.",
                                "Ingresar el borne/elemento en la tabla del Anexo 2 (queda registrado como dato manual)."))
    for tipo, lista in (("entrada", senales), ("comando", comandos)):
        bornes = Counter(s.borne for s in lista if s.borne)
        for b, c in bornes.items():
            if c > 1:
                problemas.append(_h("S02", BLOQUEANTE, ruta, 0, f"El borne {b} aparece {c} veces ({tipo}s).",
                                    "Revisar el plano: un borne no puede tener dos señales.", CONSISTENCIA))
        por_nombre = Counter((s.borne.split("/")[0], s.nombre) for s in lista if s.borne)
        for (bornera, nombre), c in por_nombre.items():
            if c > 1:
                problemas.append(_h("S04", ADVERTENCIA, ruta, 0, f"La señal '{nombre}' está repetida {c} veces en {bornera}.",
                                    "Confirmar en el plano que no sea un error de carga.", CONSISTENCIA))
    resultado = (senales, comandos, problemas)
    _CACHE[("funcional",) + k] = resultado
    return resultado


# ------------------------------------------------------------------ térmicas
def leer_termicas(rutas):
    """Térmicas (-Q…) de los planos: [{'termica','paginas':[(archivo,n)],'tension': '110 VCC' | ''}].

    La tensión solo se informa si la misma página del plano la indica sin ambigüedad.
    """
    encontradas = {}
    for ruta in rutas:
        for pagina in _abrir(ruta):
            texto = pagina.get_text()
            codigos = set(re.findall(r"-(Q(?:\d+|S))\b", texto))
            tensiones = {f"{m[0]} {m[1].upper()}" for m in re.findall(r"\b(\d{2,3})\s?(VCC|VCA|Vcc|Vca)\b", texto)}
            for q in codigos:
                e = encontradas.setdefault(q, {"termica": q, "paginas": [], "tensiones": set()})
                e["paginas"].append((os.path.basename(ruta), pagina.number + 1))
                if len(tensiones) == 1:
                    e["tensiones"] |= tensiones
    orden = sorted(encontradas, key=lambda q: (ORDEN_TERMICAS.index(q) if q in ORDEN_TERMICAS else 99, q))
    salida = []
    for q in orden:
        e = encontradas[q]
        salida.append({"termica": q, "paginas": e["paginas"],
                       "tension": next(iter(e["tensiones"])) if len(e["tensiones"]) == 1 else ""})
    return salida


def filas_termicas(rutas):
    """Filas para la tabla del Anexo 1: (tensión, descripción, térmica). Lo que el plano no dice queda vacío."""
    return [(t["tension"], "", t["termica"]) for t in leer_termicas(rutas)]


def aplicar_sugerencias(filas):
    """Completa SOLO los campos vacíos con las sugerencias de los protocolos de referencia (a confirmar)."""
    salida = []
    for grupo, desc, q in filas:
        sug = SUGERENCIAS_TERMICAS.get(q.lstrip("-"))
        salida.append((grupo or (sug[0] if sug else ""), desc or (sug[1] if sug else ""), q))
    return salida


# ------------------------------------------------------------------ compatibilidad con la API anterior
def extraer_senales(ruta):
    senales, comandos, problemas = leer_funcional(ruta)
    avisos = [h.descripcion for h in problemas]
    return [s.tupla() for s in senales], [s.tupla() for s in comandos], avisos


def extraer_termicas(*rutas):
    return filas_termicas(rutas)


# ------------------------------------------------------------------ validación de los planos
def _sin_acentos(t):
    return "".join(c for c in unicodedata.normalize("NFD", t) if unicodedata.category(c) != "Mn")


def _norm(t):
    return re.sub(r"[^a-z0-9]", "", _sin_acentos(t).casefold())


def analizar_plano(ruta):
    """Identidad del plano: número, tipo, revisión del archivo y del cuadro, estación y huella."""
    doc = _abrir(ruta)
    nombre = os.path.basename(ruta)
    info = {"ruta": ruta, "nombre": nombre, "paginas": len(doc), "numero": "", "tipo": "", "obra": "",
            "rev_archivo": "", "rev_cuadro": "", "estacion_portada": "", "estacion_hojas": "", "hash": ""}
    textos = [p.get_text() for p in doc]
    primeras = " ".join(textos[:3])
    m = re.search(r"\b(ET[A-Z]{0,3}-[A-Z0-9]+-(\d{3,4})-ET-CT-PL-(EF|TP|EC)-?\d{3,4})\b", primeras)
    if m:
        info["numero"], info["obra"], info["tipo"] = m.group(1), m.group(2), m.group(3)
    else:
        t = re.search(r"(?:^|[-_ ])(EF|TP|EC)(?=[-_ .\d]|$)", os.path.splitext(nombre)[0].upper())
        info["tipo"] = t.group(1) if t else ""
    r = re.search(r"[_-]r([A-Za-z])(?=\W|$)", os.path.splitext(nombre)[0])
    info["rev_archivo"] = r.group(1).upper() if r else ""
    revs = re.findall(r"\n([A-Z])\n(\d{2}/\d{2}/\d{2})\n", textos[0]) if textos else []
    info["rev_cuadro"] = revs[-1][0] if revs else ""
    estaciones = []
    for i, t in enumerate(textos):
        for linea in t.split("\n"):
            m2 = re.match(r"^\s*E\s*\.\s*T\s*\.?\s+([A-ZÁÉÍÓÚÑ][A-ZÁÉÍÓÚÑ ]{2,})\s*$", linea)
            if m2:
                estaciones.append((i, " ".join(m2.group(1).split())))
    if estaciones:
        info["estacion_portada"] = next((e for i, e in estaciones if i == 0), "")
        resto = Counter(e for i, e in estaciones if i > 0)
        info["estacion_hojas"] = resto.most_common(1)[0][0] if resto else info["estacion_portada"]
    with open(ruta, "rb") as f:
        info["hash"] = hashlib.sha256(f.read()).hexdigest()
    return info


def validar_planos(rutas, datos, necesita_funcional=False):
    """Controles de los PDF cargados. Devuelve [Hallazgo]; los marcados `confirmable` los puede aceptar el usuario."""
    hs, planos = [], []
    for ruta in rutas:
        try:
            planos.append(analizar_plano(ruta))
        except Exception as e:
            hs.append(_h("PDF01", BLOQUEANTE, ruta, 0, f"No se pudo leer el PDF: {e}", "Cargar un PDF válido."))
    for p in planos:
        ruta = p["ruta"]
        if not p["numero"]:
            hs.append(_h("PDF08", ADVERTENCIA, ruta, 1, "No se encontró el número de plano en la portada.",
                         "Verificar que sea el plano correcto."))
        if p["rev_archivo"] and p["rev_cuadro"] and p["rev_archivo"] != p["rev_cuadro"]:
            hs.append(_h("PDF02", BLOQUEANTE, ruta, 1, f"El archivo dice revisión {p['rev_archivo']} pero el cuadro de "
                         f"revisiones del plano llega a la {p['rev_cuadro']}.", "Cargar la revisión vigente.",
                         CONSISTENCIA, True))
        if p["estacion_portada"] and p["estacion_hojas"] and p["estacion_portada"] != p["estacion_hojas"]:
            hs.append(_h("PDF06", BLOQUEANTE, ruta, 1, f"La portada del plano dice 'E.T. {p['estacion_portada']}' y el resto de "
                         f"las hojas dicen 'E.T. {p['estacion_hojas']}'.",
                         "Corregir el plano o confirmar que es un error solo de la portada.", CONSISTENCIA, True))
        est = p["estacion_hojas"] or p["estacion_portada"]
        nombre_obra = datos.get("NOMBRE", "")
        if est and nombre_obra and _norm(nombre_obra) not in _norm(est) and _norm(est) not in _norm(nombre_obra):
            hs.append(_h("PDF05", BLOQUEANTE, ruta, 1, f"El plano es de la estación '{est}' y la obra cargada es '{nombre_obra}'.",
                         "Cargar los planos de este tablero o confirmar que es el mismo.", CONSISTENCIA, True))
        nro = re.sub(r"\D", "", datos.get("NRO_OBRA", ""))
        if p["obra"] and nro and int(p["obra"]) != int(nro):
            hs.append(_h("PDF07", BLOQUEANTE, ruta, 1, f"El plano pertenece a la obra {int(p['obra'])} y se cargó la obra {nro}.",
                         "Cargar los planos de esta obra o corregir el nº de obra.", CONSISTENCIA, True))
    vistos = {}
    for p in planos:
        if p["hash"] in vistos:
            hs.append(_h("PDF09", ADVERTENCIA, p["ruta"], 0, f"Es el mismo archivo que {vistos[p['hash']]}."))
        vistos[p["hash"]] = p["nombre"]
    por_tipo = {}
    for p in planos:
        por_tipo.setdefault(p["tipo"], []).append(p)
    if necesita_funcional and not por_tipo.get("EF"):
        hs.append(Hallazgo("PDF10", BLOQUEANTE, DOCUMENTAL, "Planos", "", "Falta el esquema funcional (EF), de donde salen las "
                           "señales y comandos.", "Cargar el PDF del esquema funcional."))
    if por_tipo.get("EF") and por_tipo.get("TP"):
        ef, tp = por_tipo["EF"][0], por_tipo["TP"][0]
        rev_ef, rev_tp = ef["rev_cuadro"] or ef["rev_archivo"], tp["rev_cuadro"] or tp["rev_archivo"]
        if rev_ef and rev_tp and rev_ef != rev_tp:
            hs.append(Hallazgo("PDF03", BLOQUEANTE, CONSISTENCIA, f"{ef['nombre']} / {tp['nombre']}", "",
                               f"Revisiones incompatibles: funcional en revisión {rev_ef} y constructivo en revisión {rev_tp}.",
                               "Cargar planos de la misma revisión."))
        if ef["numero"] and tp["numero"]:
            base = lambda n: re.sub(r"-(EF|TP|EC)-", "-", n)
            if base(ef["numero"]) != base(tp["numero"]):
                hs.append(Hallazgo("PDF04", BLOQUEANTE, CONSISTENCIA, f"{ef['nombre']} / {tp['nombre']}", "",
                                   f"Los planos tienen números distintos ({ef['numero']} y {tp['numero']}).",
                                   "Cargar los planos del mismo tablero."))
    return hs


# ------------------------------------------------------------------ contraste tablas vs planos
def comparar_con_pdf(actual, del_plano, que):
    """Contrasta [(borne, nombre)] de la tabla con lo que leyó el plano. Devuelve [Hallazgo].

    - señal del plano que falta en la tabla  -> BLOQUEANTE
    - señal de la tabla que el plano no tiene o con otro nombre -> BLOQUEANTE (sin respaldo)
    - borne completado a mano donde el plano no tenía borne -> INFO (dato manual registrado)
    """
    hs = []
    base = {}
    for s in del_plano:
        base.setdefault(s.borne or f"(ver {s.referencia})" if not s.borne else s.borne, []).append(s)
    sin_borne = {s.nombre: s for s in del_plano if not s.borne}
    usados = set()
    for borne, nombre in actual:
        if borne in base and borne and not borne.startswith("("):
            nombres = [s.nombre for s in base[borne]]
            if nombre in nombres:
                usados.add((borne, nombre))
                continue
            hs.append(Hallazgo("R10", BLOQUEANTE, CONSISTENCIA, "Anexo 2", que,
                               f"{borne}: la tabla dice '{nombre}' y el plano dice '{nombres[0]}'.",
                               "Los nombres deben coincidir exactamente con la ingeniería."))
        elif nombre in sin_borne and (not borne or borne.startswith("(") or borne not in base):
            s = sin_borne[nombre]
            usados.add((s.borne or f"(ver {s.referencia})", nombre))
            if borne and not borne.startswith("("):
                hs.append(Hallazgo("R12", INFO, DOCUMENTAL, "Anexo 2", que,
                                   f"Borne '{borne}' ingresado manualmente para '{nombre}' (el plano no lo indica"
                                   f"{', referencia ' + s.referencia if s.referencia else ''}).",
                                   "Dato manual registrado en el informe."))
        else:
            hs.append(Hallazgo("R11", BLOQUEANTE, CONSISTENCIA, "Anexo 2", que,
                               f"'{nombre}' ({borne or 'sin borne'}) no figura en el plano cargado (dato sin respaldo).",
                               "Quitarla o cargar el plano que la contiene. No se admiten señales inventadas."))
    for s in del_plano:
        clave = (s.borne or f"(ver {s.referencia})", s.nombre)
        if clave not in usados:
            hs.append(Hallazgo("R13", BLOQUEANTE, CONSISTENCIA, "Anexo 2", que,
                               f"Falta en la tabla: {clave[0]} '{s.nombre}' (plano {s.archivo}, página {s.pagina_modulo}).",
                               "Todas las señales del plano deben estar en el anexo."))
    return hs


# ------------------------------------------------------------------ hardware y tensiones del plano
def contar_modulos(ruta):
    """(módulos DI, módulos DO) que dibuja el plano funcional en las hojas DETALLE MODULO DI/DO."""
    k = _clave(ruta)
    if ("modulos",) + k not in _CACHE:
        di = do = 0
        for pagina in _abrir(ruta):
            if _titulo(pagina) == "DETALLE MODULO DI":
                for _, tipo, _t in _modulos(pagina):
                    di += tipo == "DI"
                    do += tipo == "DO"
        _CACHE[("modulos",) + k] = (di, do)
    return _CACHE[("modulos",) + k]


def tensiones_cc(rutas):
    """Tensiones continuas que mencionan los planos (p. ej. {110}). Sirve para detectar referencias que no corresponden."""
    valores = set()
    for ruta in rutas:
        for pagina in _abrir(ruta):
            valores |= {int(v) for v in re.findall(r"\b(\d{2,3})\s?V\s?(?:CC|Vcc|DC)\b", pagina.get_text(), re.I)}
    return valores
