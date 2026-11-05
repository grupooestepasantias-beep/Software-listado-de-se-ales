"""Control de calidad DOCUMENTAL de los protocolos SAT/FAT y sus anexos.

Qué valida: estructura, numeración, índice, campos completos, tablas, consistencia entre
documentos, ortografía frecuente y formato.
Qué NO valida: ningún criterio técnico de ingeniería (valores, normas, procedimientos, nombres de
señales, modelos de equipos). Cada hallazgo indica su tipo (FORMATO, DOCUMENTAL o CONSISTENCIA)
para no confundir un control de forma con una validación técnica.
"""
import datetime
import os
import re
import zipfile
from dataclasses import dataclass, field

import docx
from docx.oxml.ns import qn

BLOQUEANTE, ADVERTENCIA, INFO = "BLOQUEANTE", "ADVERTENCIA", "INFO"
FORMATO, DOCUMENTAL, CONSISTENCIA = "FORMATO", "DOCUMENTAL", "CONSISTENCIA"
AVISO_ALCANCE = ("Control documental y de formato. No valida criterios técnicos de ingeniería "
                 "(valores, normas, procedimientos, nombres de señales ni modelos de equipos): "
                 "eso lo debe revisar el responsable técnico.")


@dataclass
class Hallazgo:
    codigo: str
    gravedad: str
    tipo: str
    archivo: str
    apartado: str
    descripcion: str
    solucion: str = ""
    confirmable: bool = False  # el usuario puede confirmar que el dato es correcto (queda registrado)

    def linea(self):
        return (f"[{self.gravedad}] [{self.tipo}] {self.codigo} - {self.archivo} - {self.apartado or 'General'}: "
                f"{self.descripcion}" + (f"  Solución: {self.solucion}" if self.solucion else ""))


@dataclass
class Informe:
    hallazgos: list = field(default_factory=list)
    archivos: list = field(default_factory=list)

    @property
    def bloqueantes(self):
        return [h for h in self.hallazgos if h.gravedad == BLOQUEANTE]

    @property
    def advertencias(self):
        return [h for h in self.hallazgos if h.gravedad == ADVERTENCIA]

    @property
    def apto(self):
        return not self.bloqueantes

    @property
    def listo(self):
        """Listo para entregar: sin bloqueantes y sin advertencias pendientes."""
        return not self.bloqueantes and not self.advertencias

    def resumen(self):
        n_b, n_a = len(self.bloqueantes), len(self.advertencias)
        n_i = len(self.hallazgos) - n_b - n_a
        if n_b:
            estado = "NO LISTO PARA ENTREGAR: hay errores bloqueantes"
        elif n_a:
            estado = "NO LISTO PARA ENTREGAR: hay advertencias sin resolver"
        else:
            estado = "LISTO PARA ENTREGAR"
        return f"{estado} - {n_b} bloqueantes, {n_a} advertencias, {n_i} informativos."

    def a_texto(self):
        orden = {BLOQUEANTE: 0, ADVERTENCIA: 1, INFO: 2}
        lineas = ["INFORME DE CONTROL DE CALIDAD", datetime.datetime.now().strftime("%d/%m/%Y %H:%M"),
                  self.resumen(), AVISO_ALCANCE, "", "Archivos revisados:"]
        lineas += [f"  - {os.path.basename(a)}" for a in self.archivos]
        lineas.append("")
        for h in sorted(self.hallazgos, key=lambda h: (orden[h.gravedad], h.archivo)):
            lineas.append(h.linea())
        return "\n".join(lineas)


# ---------------------------------------------------------------- lectura del documento
def _norm(t):
    return re.sub(r"\s+", " ", t.replace("\xa0", " ")).strip()


def _clave(t):
    """Texto de un título sin numeración ni signos, para compararlo."""
    t = _norm(t).casefold()
    t = re.sub(r"^\d+(\.\d+)*\.?\s*", "", t)
    return t.rstrip(":. ")


def _txt(el):
    return "".join(x.text or "" for x in el.iter(qn("w:t")))


def _txt_tab(el):
    """Como _txt, pero respeta los tabuladores (en el índice separan título y página)."""
    partes = []
    for x in el.iter():
        if x.tag == qn("w:t"):
            partes.append(x.text or "")
        elif x.tag == qn("w:tab") and x.getparent().tag == qn("w:r"):
            partes.append("\t")
    return "".join(partes)


class Doc:
    """Vista de un .docx con lo necesario para controlarlo."""

    def __init__(self, ruta):
        self.ruta = ruta
        self.nombre = os.path.basename(ruta)
        self.d = docx.Document(ruta)
        self.portada, self.encabezados, self.indice, self.parrafos, self.tablas = {}, [], [], [], []
        self.indice_sin_actualizar = False
        self._leer()
        self.tipo = self._tipo()

    def _leer(self):
        apartado, n1 = "Portada", 0
        for el in self.d.element.body.iterchildren():
            if el.tag == qn("w:tbl"):
                self.tablas.append((el, apartado))
                continue
            if el.tag != qn("w:p"):
                continue
            t = _norm(_txt(el))
            sid = el.find(qn("w:pPr") + "/" + qn("w:pStyle"))
            sid = sid.get(qn("w:val")) if sid is not None else ""
            self.parrafos.append((t, apartado, sid))
            if sid in ("TDC1", "TDC2", "TDC3"):
                partes = [p for p in re.split(r"\t", _txt_tab(el).replace("\xa0", " ")) if p.strip()]
                pagina = partes[-1].strip() if len(partes) > 1 and partes[-1].strip().isdigit() else ""
                titulo = " ".join(p.strip() for p in (partes[:-1] if pagina else partes))
                titulo = re.sub(r"^\d+\.\s*", "", _norm(titulo)) if re.match(r"^\d+\.\s", _norm(titulo)) else _norm(titulo)
                self.indice.append((titulo, pagina))
                continue
            if t.startswith("Índice: se completa"):
                self.indice_sin_actualizar = True
                continue
            if sid == "Ttulo1" and t:
                num = el.find(qn("w:pPr") + "/" + qn("w:numPr"))
                sin_numero = num is not None and num.find(qn("w:numId")) is not None \
                    and num.find(qn("w:numId")).get(qn("w:val")) == "0"
                if sin_numero:
                    numero = ""
                else:
                    n1 += 1
                    numero = f"{n1}"
                self.encabezados.append({"nivel": 1, "numero": numero, "texto": t, "manual": False})
                apartado = (numero + ". " if numero else "") + t
            else:
                m = re.match(r"^(\d+(?:\.\d+)+)\.?\s+(\S.*)$", t)
                if m:
                    outline = el.find(qn("w:pPr") + "/" + qn("w:outlineLvl"))
                    if outline is not None and outline.get(qn("w:val")) in ("1", "2"):
                        self.encabezados.append({"nivel": m.group(1).count(".") + 1, "numero": m.group(1),
                                                 "texto": m.group(2), "manual": True})
                        apartado = f"{m.group(1)}. {m.group(2)}"
        self._leer_portada()

    def _leer_portada(self):
        for t, _, _ in self.parrafos[:40]:
            for clave, patron in (("tipo", r"Tipo:\s*(\w+)"), ("fecha", r"Fecha:\s*([^\n]*?)\s*$"),
                                  ("obra", r"Proyecto/Obra:\s*(.*)$"), ("tablero", r"^Tablero:\s*(.*)$"),
                                  ("ubicacion", r"^Ubicación:\s*(.*)$"),
                                  ("rev", r"^REV:\s*(.*)$"), ("anexo", r"^Anexo\s+(\d+)\s*$")):
                m = re.search(patron, t)
                if m and clave not in self.portada:
                    self.portada[clave] = m.group(1).strip()
        if "tipo" not in self.portada:
            for t, _, _ in self.parrafos[:15]:
                m = re.search(r"PROTOCOLO DE ENSAYO\s+(FAT|SAT)", t)
                if m:
                    self.portada["tipo"] = m.group(1)
                    break
        if "anexo" not in self.portada:  # anexos del SAT: portada "PROTOCOLO DE ENSAYO – ANEXO N"
            for t, _, _ in self.parrafos[:15]:
                m = re.match(r"^PROTOCOLO DE ENSAYO\s*[–-]\s*ANEXO\s+(\d)\s*$", t, re.I)
                if m:
                    self.portada["anexo"] = m.group(1)
                    break
        # Si "Tipo: SAT Fecha: ..." está en un solo párrafo, la fecha queda pegada al tipo
        fecha = self.portada.get("fecha", "")
        self.portada["fecha"] = re.sub(r"^\s*", "", fecha)

    def _tipo(self):
        base = self.portada.get("tipo", "").upper()
        if base not in ("SAT", "FAT"):
            return "DESCONOCIDO"
        if "anexo" in self.portada:
            return f"{base}_A{self.portada['anexo']}" if self.portada["anexo"] in ("1", "2") else "DESCONOCIDO"
        return base

    def texto_completo(self):
        """Todo el texto visible: cuerpo, tablas, encabezados y pies."""
        partes = [t for t, _, _ in self.parrafos]
        partes += [_norm(_txt(tc)) for el, _ in self.tablas for tc in el.iter(qn("w:tc"))]
        for _, xml in self.xml_partes():
            partes.append(re.sub(r"<[^>]+>", " ", xml) if "header" in _ or "footer" in _ else "")
        return "\n".join(partes)

    # ---- utilidades
    def encabezados_pagina(self):
        textos = set()
        for s in self.d.sections:
            for h in (s.header, s.first_page_header, s.even_page_header):
                for p in h.paragraphs:
                    if "Título:" in p.text:
                        textos.add(_norm(p.text))
        return sorted(textos)

    def xml_partes(self):
        with zipfile.ZipFile(self.ruta) as z:
            for n in z.namelist():
                if re.match(r"word/(document|header\d*|footer\d*)\.xml$", n):
                    yield n, z.read(n).decode("utf8", "ignore")

    def tabla(self, rol):
        for el, apartado in self.tablas:
            texto = _norm(_txt(el))
            if rol == "refs" and apartado.upper().endswith("DOCUMENTOS DE REFERENCIA"):
                return el
            if rol == "componentes" and texto.startswith("COMPONENTES DE HARDWARE"):
                return el
            if rol == "firma" and texto.startswith("Por Grupo Oeste"):
                return el
            if rol == "senales" and "SCADA SURVALENT" in texto and "Comandos" not in texto:
                return el
            if rol == "comandos" and texto.startswith("Comandos"):
                return el
            if rol == "energizado" and texto.startswith("Paso"):
                return el
        return None


def _filas(tbl_el):
    """Filas directas de una tabla: lista de listas de textos de celda."""
    return [[_norm(_txt(c)) for c in tr.findall(qn("w:tc"))] for tr in tbl_el.findall(qn("w:tr"))]


def _anidadas(tbl_el):
    return [t for t in tbl_el.iter(qn("w:tbl")) if t is not tbl_el]


# ---------------------------------------------------------------- reglas
ESTRUCTURA = {
    "SAT": {"h1": ["objeto", "documentos de referencia", "pruebas por realizar",
                   "registro de componentes principales de hardware ensayados", "observaciones"],
            "sub": [("3.1", "inspección visual"), ("3.2", "energizado progresivo"), ("3.3", "ensayos funcionales"),
                    ("3.3.1", "prueba de funcionamiento")],
            "prohibidos": ["propiedades dieléctricas", "ensayo punto a punto"]},
    "FAT": {"h1": ["objeto", "documentos de referencia", "pruebas por realizar",
                   "registro de componentes principales de hardware ensayados", "observaciones"],
            "sub": [("3.1", "inspección visual"), ("3.2", "propiedades dieléctricas"), ("3.3", "ensayo punto a punto"),
                    ("3.4", "energizado progresivo"), ("3.5", "ensayos funcionales"),
                    ("3.5.1", "prueba de funcionamiento")],
            "prohibidos": []},
    "FAT_A1": {"h1": ["objeto", "documentos de referencia", "anexo 1. procedimiento de energizado", "observaciones"],
               "sub": [], "prohibidos": ["listado de señales"]},
    "FAT_A2": {"h1": ["objeto", "documentos de referencia", "listado de señales", "observaciones"],
               "sub": [], "prohibidos": ["procedimiento de energizado"]},
}

# Anexos del SAT (formato de los SAT de referencia): portada simple, título del anexo y su tabla; sin índice ni firmas
ESTRUCTURA["SAT_A1"] = {"h1": [], "sub": [], "prohibidos": ["listado de señales"]}
ESTRUCTURA["SAT_A2"] = {"h1": [], "sub": [], "prohibidos": ["procedimiento de energizado"]}


def _anexo_sat(d):
    return d.tipo in ("SAT_A1", "SAT_A2")

ORTOGRAFIA = {  # error frecuente -> corrección sugerida (palabra completa, sin distinguir mayúsculas)
    "vetilación": "ventilación", "vetilacion": "ventilación", "c0upler": "coupler",
    "verificacion": "verificación", "inspeccion": "inspección", "energizacion": "energización",
    "alimentacion": "alimentación", "proteccion": "protección", "protecciones": None,
    "comunicacion": "comunicación", "instalacion": "instalación", "operacion": "operación",
    "aislacion": "aislación", "dielectrica": "dieléctrica", "dielectricas": "dieléctricas",
    "tension": "tensión", "señalizacion": "señalización", "identificacion": "identificación",
    "descripcion": "descripción", "informacion": "información", "numero": "número", "ingenieria": "ingeniería",
    "ubicacion": "ubicación", "funcion": "función", "rigidez dielectrica": "rigidez dieléctrica",
    "continuidad electrica": "continuidad eléctrica", "electrica": "eléctrica",
}
ORTOGRAFIA = {k: v for k, v in ORTOGRAFIA.items() if v}


def _h(cod, grav, tipo, doc, apartado, desc, sol=""):
    return Hallazgo(cod, grav, tipo, doc.nombre, apartado, desc, sol)


def validar_documento(ruta, pdf=None):
    """Controles de un documento. `pdf` (opcional) permite verificar los números de página del índice."""
    d = Doc(ruta)
    hs = []
    hs += _campos_sin_completar(d)
    hs += _portada(d)
    hs += _estructura(d)
    hs += _numeracion(d)
    hs += _indice(d, pdf)
    hs += _tablas(d)
    hs += _consistencia_interna(d)
    hs += _referencias_cruzadas(d)
    hs += _ortografia(d)
    hs += _formato(d)
    return hs


def _campos_sin_completar(d):
    hs = []
    for parte, xml in d.xml_partes():
        marcadores = sorted(set(re.findall(r"\{\{\w+\}\}", re.sub(r"<[^>]+>", "", xml))))
        if marcadores:
            hs.append(_h("C01", BLOQUEANTE, DOCUMENTAL, d, parte, "Campos sin completar: " + ", ".join(marcadores),
                         "Completar el dato en la ventana y volver a generar."))
    return hs


def _portada(d):
    hs = []
    base = ["fecha", "obra", "ubicacion", "tablero"]
    esperado = {"SAT": ["tipo"] + base, "FAT": ["tipo"] + base}
    for anexo in ("FAT_A1", "FAT_A2"):
        esperado[anexo] = base + ["rev", "anexo"]
    for anexo in ("SAT_A1", "SAT_A2"):  # los anexos del SAT no llevan revisión en la portada
        esperado[anexo] = ["tipo"] + base + ["anexo"]
    if d.tipo == "DESCONOCIDO":
        return [_h("C02", BLOQUEANTE, DOCUMENTAL, d, "Portada", "No se pudo identificar si es SAT, FAT o anexo.",
                   "Revisar 'Tipo:' en la portada.")]
    for campo in esperado[d.tipo]:
        if not d.portada.get(campo, "").strip():
            hs.append(_h("C02", BLOQUEANTE, DOCUMENTAL, d, "Portada", f"Falta el dato de portada: {campo}.",
                         "Completarlo y volver a generar."))
    fecha = d.portada.get("fecha", "")
    if fecha:
        try:
            datetime.datetime.strptime(fecha, "%d/%m/%Y")
        except ValueError:
            hs.append(_h("C03", BLOQUEANTE, DOCUMENTAL, d, "Portada", f"La fecha '{fecha}' no tiene el formato dd/mm/aaaa."))
    tipo_en_nombre = re.search(r"Protocolo (SAT|FAT)\b", d.nombre)
    if tipo_en_nombre and d.tipo != "DESCONOCIDO" and tipo_en_nombre.group(1) != d.tipo.split("_")[0]:
        hs.append(_h("C04", BLOQUEANTE, DOCUMENTAL, d, "Portada",
                     f"El archivo se llama {tipo_en_nombre.group(1)} pero el documento dice {d.tipo.split('_')[0]}."))
    return hs


def _estructura(d):
    if d.tipo not in ESTRUCTURA:
        return []
    regla, hs = ESTRUCTURA[d.tipo], []
    claves_h1 = [_clave(e["texto"]) for e in d.encabezados if e["nivel"] == 1]
    todas = [_clave(e["texto"]) for e in d.encabezados]
    for req in regla["h1"]:
        if _clave(req) not in claves_h1:
            hs.append(_h("E01", BLOQUEANTE, DOCUMENTAL, d, "Estructura", f"Falta el apartado obligatorio '{req.upper()}'.",
                         "Regenerar con la plantilla del tipo de documento."))
    for numero, titulo in regla["sub"]:
        hallado = [e for e in d.encabezados if e["numero"] == numero and _clave(e["texto"]).startswith(titulo)]
        if not hallado:
            hs.append(_h("E01", BLOQUEANTE, DOCUMENTAL, d, "Estructura", f"Falta el apartado {numero} ({titulo}).",
                         "Regenerar con la plantilla del tipo de documento."))
    for prohibido in regla["prohibidos"]:
        if any(t.startswith(prohibido) for t in todas):
            hs.append(_h("E02", BLOQUEANTE, DOCUMENTAL, d, "Estructura",
                         f"Contiene '{prohibido}', apartado que no corresponde a un documento {d.tipo}.",
                         "Usar la plantilla correcta para este tipo de documento."))
    # FAT y SAT son documentos independientes: no se mezclan los ensayos de uno en el otro
    otro = "FAT" if d.tipo.startswith("SAT") else "SAT"
    if re.search(rf"\b{otro}\b", d.texto_completo()):
        hs.append(_h("E04", BLOQUEANTE, DOCUMENTAL, d, "Estructura",
                     f"Un documento {d.tipo.split('_')[0]} menciona '{otro}': no se pueden mezclar ensayos FAT y SAT.",
                     "Quitar la referencia o regenerar con la plantilla correcta."))
    vistos = {}
    for e in d.encabezados:
        k = (e["nivel"], _clave(e["texto"]))
        if k in vistos:
            hs.append(_h("E03", BLOQUEANTE if e["nivel"] == 1 else ADVERTENCIA, DOCUMENTAL, d, e["texto"],
                         f"Título duplicado: '{e['texto']}'.", "Eliminar o renombrar el apartado repetido."))
        vistos[k] = True
    return hs


def _numeracion(d):
    hs = []
    ultimo_h1, ultimo_h2, previo = "", "", {}
    for e in d.encabezados:
        if e["nivel"] == 1:
            if e["numero"]:
                ultimo_h1 = e["numero"]
            continue
        partes = e["numero"].split(".")
        if e["nivel"] == 2:
            if partes[0] != ultimo_h1:
                hs.append(_h("N01", BLOQUEANTE, FORMATO, d, f"{e['numero']}. {e['texto']}",
                             f"El apartado {e['numero']} cuelga del capítulo {ultimo_h1 or '(sin número)'}: "
                             f"la numeración no coincide.", "Corregir la numeración en la plantilla."))
            esperado = previo.get(("2", partes[0]), 0) + 1
            if int(partes[1]) != esperado:
                hs.append(_h("N02", BLOQUEANTE, FORMATO, d, f"{e['numero']}. {e['texto']}",
                             f"Salto de numeración: se esperaba {partes[0]}.{esperado}.", "Corregir la numeración."))
            previo[("2", partes[0])] = int(partes[1])
            ultimo_h2 = e["numero"]
        elif e["nivel"] == 3:
            if ".".join(partes[:2]) != ultimo_h2:
                hs.append(_h("N01", BLOQUEANTE, FORMATO, d, f"{e['numero']}. {e['texto']}",
                             f"El apartado {e['numero']} no corresponde al {ultimo_h2} que lo precede."))
    return hs


def _indice(d, pdf):
    hs = []
    if _anexo_sat(d):
        return hs
    if not d.indice and not d.indice_sin_actualizar:
        if d.tipo != "DESCONOCIDO":
            hs.append(_h("I01", BLOQUEANTE, DOCUMENTAL, d, "Índice", "El documento no tiene índice."))
        return hs
    if d.indice_sin_actualizar or not d.indice:
        return [_h("I02", BLOQUEANTE, DOCUMENTAL, d, "Índice",
                   "El índice no está actualizado (sin números de página).",
                   "Generar con Microsoft Word instalado, o abrir el documento y actualizar el campo (F9).")]
    titulos = [e for e in d.encabezados if e["nivel"] in (1, 2, 3)]
    claves_idx = [_clave(t) for t, _ in d.indice]
    claves_enc = [_clave(e["texto"]) for e in titulos]
    for e in titulos:
        if e["nivel"] <= 2 and _clave(e["texto"]) not in claves_idx:
            hs.append(_h("I03", BLOQUEANTE, DOCUMENTAL, d, "Índice", f"El índice no incluye '{e['texto']}'."))
    for (t, pag), k in zip(d.indice, claves_idx):
        if k not in claves_enc:
            hs.append(_h("I04", BLOQUEANTE, DOCUMENTAL, d, "Índice", f"El índice incluye '{t}', que no existe en el documento."))
        if not pag:
            hs.append(_h("I05", BLOQUEANTE, DOCUMENTAL, d, "Índice", f"La entrada '{t}' no tiene número de página."))
    if pdf and os.path.exists(pdf):
        hs += _paginas_del_indice(d, pdf)
    return hs


def _paginas_del_indice(d, pdf):
    try:
        import pymupdf
        paginas = [[_norm(l).casefold() for l in p.get_text().split("\n") if l.strip()] for p in pymupdf.open(pdf)]
    except Exception:
        return []
    hs = []
    hojas_indice = [i for i, lineas in enumerate(paginas) if sum("...." in l for l in lineas) >= 2]
    desde = (max(hojas_indice) + 1) if hojas_indice else 1
    for titulo, pag in d.indice:
        if not pag:
            continue
        objetivo = _clave(titulo)[:32]
        real = None
        for i in range(desde, len(paginas)):
            if any(objetivo in l and len(l) <= len(_clave(titulo)) + 8 + 40 and l.index(objetivo) <= 8
                   for l in paginas[i]):
                real = i + 1
                break
        if real is not None and str(real) != pag:
            hs.append(_h("I06", BLOQUEANTE, DOCUMENTAL, d, "Índice",
                         f"'{titulo}': el índice dice página {pag} pero está en la {real}.",
                         "Actualizar el índice (F9) o regenerar."))
    return hs


def _tablas(d):
    hs = []
    refs = d.tabla("refs")
    if refs is not None:
        filas = _filas(refs)
        if not filas or all(not any(f) for f in filas):
            hs.append(_h("T01", BLOQUEANTE, DOCUMENTAL, d, "Documentos de referencia", "La tabla no tiene documentos."))
        for i, f in enumerate(filas, 1):
            if not any(f):
                hs.append(_h("T02", BLOQUEANTE, DOCUMENTAL, d, "Documentos de referencia", f"La fila {i} está vacía."))
            elif len(f) >= 2 and not f[0]:
                hs.append(_h("T02", BLOQUEANTE, DOCUMENTAL, d, "Documentos de referencia", f"La fila {i} no tiene archivo."))
            elif len(f) >= 2 and not f[1]:
                hs.append(_h("T03", ADVERTENCIA, DOCUMENTAL, d, "Documentos de referencia",
                             f"'{f[0]}' no tiene descripción.", "Escribir la descripción del documento."))
    comp = d.tabla("componentes")
    if comp is not None:
        filas = _filas(comp)[1:]
        if not filas:
            hs.append(_h("T04", BLOQUEANTE, DOCUMENTAL, d, "Registro de componentes", "La tabla no tiene componentes."))
        for i, f in enumerate(filas, 1):
            if not f[0]:
                hs.append(_h("T04", BLOQUEANTE, DOCUMENTAL, d, "Registro de componentes", f"La fila {i} no tiene nombre de componente."))
        if filas and all(len(f) > 1 and not f[1] for f in filas):
            hs.append(_h("T05", INFO, DOCUMENTAL, d, "Registro de componentes",
                         "Ningún componente tiene número de serie (se completa durante el ensayo)."))
        modelos = {}
        for f in filas:
            m = re.search(r"M[ÓO]DULO (DI|DO) (SEL [\d-]+)", f[0].upper())
            if m:
                modelos.setdefault(m.group(2), set()).add(m.group(1))
        for modelo, tipos in modelos.items():
            if len(tipos) > 1:
                hs.append(_h("T06", BLOQUEANTE, CONSISTENCIA, d, "Registro de componentes",
                             f"El modelo {modelo} figura como DI y como DO a la vez.",
                             "Corregir el nombre de los módulos (decisión técnica del responsable)."))
    if d.tipo.endswith("_A2"):
        hs += _tabla_senales(d)
    if d.tipo == "SAT_A1":
        items = {_norm(_txt(tc)) for el, _ in d.tablas for tc in el.iter(qn("w:tc"))
                 if _norm(_txt(tc)).startswith("Verificación") and not _norm(_txt(tc)).startswith("Verificación de")}
        if not items:
            hs.append(_h("T07", BLOQUEANTE, DOCUMENTAL, d, "Anexo 1", "El anexo no tiene ningún circuito a verificar."))
        for i in sorted(items):
            if not re.search(r"–\s*Q\w+$", i):
                hs.append(_h("T08", BLOQUEANTE, DOCUMENTAL, d, "Anexo 1", f"'{i}' no indica la térmica (–Q…)."))
    elif d.tipo.endswith("_A1"):
        en = d.tabla("energizado")
        filas = _filas(en)[1:] if en is not None else []
        filas = [f for f in filas if any(f)]
        if not filas:
            hs.append(_h("T07", BLOQUEANTE, DOCUMENTAL, d, "Anexo 1", "El anexo no tiene ningún paso de energizado."))
        for n, f in enumerate(filas, 1):
            if f[0] != str(n):
                hs.append(_h("T08", BLOQUEANTE, FORMATO, d, "Anexo 1", f"Los pasos no están numerados en orden (fila {n}: '{f[0]}')."))
            if not re.search(r"–\s*Q\w+$", f[1]):
                hs.append(_h("T08", BLOQUEANTE, DOCUMENTAL, d, "Anexo 1", f"'{f[1]}' no indica la térmica (–Q…)."))
            if not f[2].strip():
                hs.append(_h("T14", BLOQUEANTE, DOCUMENTAL, d, "Anexo 1", f"El paso {n} no indica la tensión esperada."))
        for requerido in ("Condiciones previas", "Criterio de aceptación"):
            if not any(t.strip().startswith(requerido) for t, _, _ in d.parrafos):
                hs.append(_h("T07", BLOQUEANTE, DOCUMENTAL, d, "Anexo 1", f"Falta la sección '{requerido}'."))
    firma = d.tabla("firma")
    if _anexo_sat(d):
        pass
    elif firma is None:
        hs.append(_h("T09", BLOQUEANTE, DOCUMENTAL, d, "Firmas", "Falta la tabla de firmas."))
    else:
        filas = _filas(firma)
        if len(filas[0]) != 2 or not filas[0][1].startswith("Por "):
            hs.append(_h("T09", BLOQUEANTE, FORMATO, d, "Firmas",
                         "La tabla de firmas debe tener dos columnas: 'Por Grupo Oeste' y 'Por <cliente>'."))
    return hs


def _tabla_senales(d):
    hs = []
    sen, cmd = d.tabla("senales"), d.tabla("comandos")
    exactas = {"BORNE/", "ELEMENTO", "BORNE/ELEMENTO", "BORNE / ELEMENTO", "SEÑAL", "COMANDOS", "ACSELERATOR RTAC",
               "SCADA SURVALENT", "TIPO(ESTADO/ANALOGICA)"}

    def es_cabecera(fila):
        for c in fila:
            u = c.upper().strip()
            if u in exactas or "SATISFACTORIO" in u or re.match(r"^[-–]\s+NO APLICA", u):
                return True
        return False

    for rol, tabla, apartado in (("señales", sen, "Listado de señales"), ("comandos", cmd, "Comandos")):
        if tabla is None:
            if rol == "señales":
                hs.append(_h("T10", BLOQUEANTE, DOCUMENTAL, d, apartado, "Falta la tabla de señales."))
            continue
        filas = [f for t in ([tabla] if rol == "señales" else (_anidadas(tabla) or [tabla])) for f in _filas(t)]
        datos = [f for f in filas if len(f) >= 2 and not es_cabecera(f) and (f[0] or f[1])]
        if not datos:
            hs.append(_h("T10", BLOQUEANTE, DOCUMENTAL, d, apartado, f"No hay {rol} cargados."))
            continue
        vistos = set()
        for f in datos:
            if not f[1]:
                hs.append(_h("T11", BLOQUEANTE, DOCUMENTAL, d, apartado, f"El borne '{f[0]}' no tiene descripción de la señal."))
            if not f[0] or f[0].startswith("("):
                hs.append(_h("T12", BLOQUEANTE, DOCUMENTAL, d, apartado, f"'{f[1]}' no tiene borne definido ('{f[0]}').",
                             "Completar el borne/elemento."))
            elif f[0] in vistos:
                hs.append(_h("T13", ADVERTENCIA, CONSISTENCIA, d, apartado, f"El borne {f[0]} aparece más de una vez."))
            vistos.add(f[0])
    if sen is not None and len(_filas(sen)) > 15:
        encabezado_repetido = sen.find(".//" + qn("w:tblHeader")) is not None
        if not encabezado_repetido:
            hs.append(_h("F01", ADVERTENCIA, FORMATO, d, "Listado de señales",
                         "La tabla larga no repite el encabezado en cada página."))
    return hs


def _consistencia_interna(d):
    hs = []
    obra, tablero = d.portada.get("obra", ""), d.portada.get("tablero", "")
    encabezados = d.encabezados_pagina()
    m_obra = re.match(r"^(\S+?)[-_]", obra)
    nro = m_obra.group(1) if m_obra else ""
    nombre = tablero.split("–")[-1].strip() if "–" in tablero else ""
    firma = d.tabla("firma")
    cliente = ""
    if firma is not None:
        f = _filas(firma)
        if f and len(f[0]) > 1 and f[0][1].startswith("Por "):
            cliente = f[0][1][4:].strip()
    for t in encabezados:
        if nro and nro not in t:
            hs.append(_h("K01", BLOQUEANTE, CONSISTENCIA, d, "Encabezado", f"El encabezado '{t}' no incluye el nº de obra {nro}."))
        if cliente and cliente not in t:
            hs.append(_h("K01", BLOQUEANTE, CONSISTENCIA, d, "Encabezado", f"El encabezado '{t}' no incluye el cliente {cliente}."))
        if nombre and not t.endswith(nombre):
            hs.append(_h("K01", BLOQUEANTE, CONSISTENCIA, d, "Encabezado", f"El encabezado '{t}' no termina en '{nombre}'."))
    if nombre:
        objeto = next((t for t, _, _ in d.parrafos if "tiene como finalidad" in t or t.startswith("Establecer el procedimiento")
                       or t.startswith("Detallar el procedimiento")), "")
        if objeto and nombre.casefold() not in objeto.casefold():
            hs.append(_h("K02", BLOQUEANTE, CONSISTENCIA, d, "1. Objeto", f"El objeto no menciona el tablero '{nombre}'."))
        if nombre == nombre.lower() and nombre.isalpha():
            hs.append(_h("F02", ADVERTENCIA, FORMATO, d, "Portada", f"El nombre '{nombre}' está todo en minúsculas.",
                         "Escribirlo como nombre propio (p. ej. con mayúscula inicial)."))
    return hs


def _referencias_cruzadas(d):
    hs = []
    def tema(s):
        energizado, senales = "energizado" in s, "señales" in s
        return "1" if energizado and not senales else "2" if senales and not energizado else None

    for t, apartado, sid in d.parrafos:
        if sid in ("TDC1", "TDC2", "TDC3"):
            continue
        fin_previo = 0
        for m in re.finditer(r"Anexo\s+(\d+)", t):
            n = m.group(1)
            antes = t[max(fin_previo, m.start() - 60):m.start()].casefold()
            despues = re.split(r"Anexo\s+\d", t[m.end():m.end() + 90])[0].casefold()
            fin_previo = m.end()
            esperado = tema(despues) or tema(antes)  # lo que se describe junto a la mención
            if n not in ("1", "2"):
                hs.append(_h("R01", BLOQUEANTE, DOCUMENTAL, d, apartado, f"Referencia a 'Anexo {n}', que no existe."))
            elif esperado and esperado != n:
                que = "El procedimiento de energizado está en el Anexo 1" if esperado == "1" \
                    else "El listado de señales está en el Anexo 2"
                hs.append(_h("R02", BLOQUEANTE, DOCUMENTAL, d, apartado, f"{que}, no en el Anexo {n}."))
    if d.tipo.endswith(("_A1", "_A2")):
        n = d.portada.get("anexo", "")
        titulo = next((e["texto"] for e in d.encabezados if e["texto"].upper().startswith("ANEXO")), "")
        if titulo and not re.match(rf"ANEXO\s+{n}\b", titulo, re.I):
            hs.append(_h("R03", BLOQUEANTE, DOCUMENTAL, d, "Identificación del anexo",
                         f"La portada dice Anexo {n} pero el título es '{titulo}'."))
        m = re.search(r"Anexo (\d)", d.nombre)
        if m and m.group(1) != n:
            hs.append(_h("R03", BLOQUEANTE, DOCUMENTAL, d, "Identificación del anexo",
                         f"El archivo es del Anexo {m.group(1)} pero el documento es el Anexo {n}."))
    return hs


def _ortografia(d):
    hs = []
    patron = re.compile(r"\b(" + "|".join(re.escape(k) for k in sorted(ORTOGRAFIA, key=len, reverse=True)) + r")\b", re.I)
    textos = [(t, a) for t, a, s in d.parrafos if s not in ("TDC1", "TDC2", "TDC3")]
    refs = d.tabla("refs")
    omitir = {f[0] for f in _filas(refs)} if refs is not None else set()
    de_ingenieria = (d.tabla("senales"), d.tabla("comandos"))  # nombres tal cual los dice el plano: no se corrigen
    for el, apartado in d.tablas:
        if any(el is x for x in de_ingenieria if x is not None):
            continue
        for tr in el.iter(qn("w:tr")):
            for tc in tr.findall(qn("w:tc")):
                t = _norm(_txt(tc))
                if t and t not in omitir:
                    textos.append((t, apartado))
    vistos = set()
    for t, apartado in textos:
        for m in patron.finditer(t):
            palabra = m.group(1)
            if (palabra.casefold(), apartado) in vistos:
                continue
            vistos.add((palabra.casefold(), apartado))
            hs.append(_h("O01", ADVERTENCIA, FORMATO, d, apartado,
                         f"Posible error ortográfico: '{palabra}'.", f"Debería decir '{ORTOGRAFIA[palabra.casefold()]}'."))
        if re.search(r"\S {2,}\S", t) and len(t) > 25:
            if ("espacios", apartado) not in vistos:
                vistos.add(("espacios", apartado))
                hs.append(_h("O02", INFO, FORMATO, d, apartado, "Hay espacios dobles dentro de un texto."))
        if re.search(r"\s[,.;:]\s|,,|\.\.(?!\.)", t) and "...." not in t and "…" not in t:
            hs.append(_h("O03", ADVERTENCIA, FORMATO, d, apartado, f"Puntuación dudosa en: '{t[:60]}'."))
    return hs


def _formato(d):
    hs = []
    tam = {(s.page_width, s.page_height) for s in d.d.sections}
    if len(tam) > 1:
        hs.append(_h("F03", ADVERTENCIA, FORMATO, d, "Página", "Las secciones tienen distinto tamaño de página."))
    seguidas = mayor = 0
    pasado_el_indice = False
    for el in d.d.element.body.iterchildren():
        if el.tag == qn("w:p") and _txt(el).strip().upper() in ("OBJETO", "1. OBJETO"):
            pasado_el_indice = True  # la portada usa párrafos vacíos para centrar el título: es parte del diseño
        if not pasado_el_indice:
            continue
        if el.tag == qn("w:p") and not _txt(el).strip() and el.find(".//" + qn("w:drawing")) is None \
                and el.find(".//" + qn("w:br")) is None and el.find(".//" + qn("w:sectPr")) is None:
            seguidas += 1
            mayor = max(mayor, seguidas)
        else:
            seguidas = 0
    if mayor > 8:
        hs.append(_h("F04", ADVERTENCIA, FORMATO, d, "General", f"Hay {mayor} párrafos vacíos seguidos."))
    return hs


# ---------------------------------------------------------------- paquete
def validar_paquete(rutas, con_pdf=True):
    """Controla cada documento y la coherencia entre todos los del mismo proyecto."""
    informe = Informe(archivos=list(rutas))
    docs = []
    for r in rutas:
        pdf = os.path.splitext(r)[0] + ".pdf" if con_pdf else None
        try:
            informe.hallazgos += validar_documento(r, pdf)
            docs.append(Doc(r))
        except Exception as e:
            informe.hallazgos.append(Hallazgo("X01", BLOQUEANTE, DOCUMENTAL, os.path.basename(r), "",
                                              f"No se pudo leer el documento: {e}", "Regenerarlo."))
    informe.hallazgos += _consistencia_paquete(docs)
    return informe


def _cliente(d):
    f = d.tabla("firma")
    filas = _filas(f) if f is not None else []
    return filas[0][1][4:].strip() if filas and len(filas[0]) > 1 and filas[0][1].startswith("Por ") else ""


def _filas_tabla(d, rol):
    t = d.tabla(rol)
    return _filas(t) if t is not None else []


def _consistencia_paquete(docs):
    hs = []
    if len(docs) < 2:
        return hs
    ref = docs[0]
    campos = (("obra", "Proyecto/Obra"), ("tablero", "Tablero"), ("ubicacion", "Ubicación"))
    familia = lambda d: d.tipo.split("_")[0]
    for d in docs[1:]:
        for clave, etiqueta in campos:
            a, b = ref.portada.get(clave, ""), d.portada.get(clave, "")
            if a != b:
                hs.append(Hallazgo("P01", BLOQUEANTE, CONSISTENCIA, d.nombre, "Portada",
                                   f"{etiqueta} distinto al de {ref.nombre}: '{b}' vs '{a}'.",
                                   "Unificar el dato y regenerar todo el paquete."))
        # El FAT y el SAT se ensayan en fechas distintas: la fecha solo debe coincidir dentro de la misma familia
        par = next((x for x in docs if familia(x) == familia(d)), d)
        if par is not d and par.portada.get("fecha") != d.portada.get("fecha"):
            hs.append(Hallazgo("P01", ADVERTENCIA, CONSISTENCIA, d.nombre, "Portada",
                               f"Fecha distinta a la de {par.nombre}: '{d.portada.get('fecha')}' vs '{par.portada.get('fecha')}'."))
        if _cliente(d) != _cliente(ref) and _cliente(d) and _cliente(ref):  # los anexos del SAT no llevan firmas
            hs.append(Hallazgo("P01", BLOQUEANTE, CONSISTENCIA, d.nombre, "Firmas",
                               f"Cliente distinto al de {ref.nombre}: '{_cliente(d)}' vs '{_cliente(ref)}'."))
        anexos_mismos = [x for x in docs if "_A" in x.tipo and familia(x) == "FAT"]  # el SAT no muestra revisión en los anexos
        if "_A" in d.tipo and familia(d) == "FAT" and anexos_mismos and d.portada.get("rev") != anexos_mismos[0].portada.get("rev"):
            hs.append(Hallazgo("P02", ADVERTENCIA, CONSISTENCIA, d.nombre, "Portada",
                               f"Revisión distinta a la de {anexos_mismos[0].nombre}."))
        if d.tabla("refs") is not None and ref.tabla("refs") is not None and _filas_tabla(d, "refs") != _filas_tabla(ref, "refs"):
            hs.append(Hallazgo("P03", ADVERTENCIA, CONSISTENCIA, d.nombre, "Documentos de referencia",
                               f"La lista de documentos de referencia difiere de la de {ref.nombre}.",
                               "Si no es intencional, usar los mismos planos en todo el paquete."))
    principales = [d for d in docs if d.tipo in ("SAT", "FAT")]
    for a, b in zip(principales, principales[1:]):
        ca, cb = _filas_tabla(a, "componentes"), _filas_tabla(b, "componentes")
        if [f[0] for f in ca] != [f[0] for f in cb]:
            hs.append(Hallazgo("P04", ADVERTENCIA, CONSISTENCIA, b.nombre, "Registro de componentes",
                               f"La lista de componentes difiere de la de {a.nombre}."))
    # Las señales de los anexos 2 de SAT y FAT salen del mismo plano: deben ser las mismas
    a2 = [d for d in docs if d.tipo.endswith("_A2")]
    if len(a2) == 2:
        s = [{(f[0], f[1]) for f in _filas_tabla(d, "senales") if f and f[0]} for d in a2]
        if s[0] != s[1]:
            hs.append(Hallazgo("P06", BLOQUEANTE, CONSISTENCIA, a2[1].nombre, "Listado de señales",
                               f"El listado de señales difiere del de {a2[0].nombre}.", "Regenerar ambos anexos con el mismo plano."))
    tipos = {d.tipo for d in docs}
    for d in principales:
        mencionados = {m for t, _, _ in d.parrafos for m in re.findall(r"Anexo\s+(\d)", t)}
        for n in sorted(mencionados):
            if f"{d.tipo}_A{n}" not in tipos:
                hs.append(Hallazgo("P05", ADVERTENCIA, DOCUMENTAL, d.nombre, "Referencias a anexos",
                                   f"Menciona el Anexo {n} y no está incluido en esta entrega.",
                                   f"Generar también el Anexo {n} o confirmar que ya existe para este tablero."))
    return hs


def validar_datos_previos(datos, documentos, componentes, termicas, senales, comandos, incluir):
    """Controles de lo cargado en la ventana, antes de generar. Devuelve [Hallazgo] (archivo = 'Datos')."""
    hs = []

    def h(cod, grav, ap, desc, sol=""):
        hs.append(Hallazgo(cod, grav, DOCUMENTAL, "Datos cargados", ap, desc, sol))

    if not documentos:
        h("D01", BLOQUEANTE, "Documentos de referencia", "No hay documentos de referencia cargados.",
          "Agregar al menos el esquema funcional y el constructivo.")
    for archivo, desc in documentos:
        if not archivo.strip():
            h("D02", BLOQUEANTE, "Documentos de referencia", "Hay una fila sin nombre de archivo.")
        elif not desc.strip():
            h("D03", ADVERTENCIA, "Documentos de referencia", f"'{archivo}' no tiene descripción.")
    if ("SAT" in incluir or "FAT" in incluir) and not componentes:
        h("D04", BLOQUEANTE, "Componentes", "No hay componentes de hardware cargados.", "Usar 'Cargar set típico…' o agregarlos.")
    if any(not c.strip() for c, _ in componentes):
        h("D04", BLOQUEANTE, "Componentes", "Hay un componente sin nombre.")
    if any(k.endswith("A1") for k in incluir):
        if not termicas:
            h("D05", BLOQUEANTE, "Anexo 1", "No hay térmicas cargadas para el energizado.", "Subir el PDF del plano.")
        for grupo, desc, q in termicas:
            if not q.strip():
                h("D09", BLOQUEANTE, "Anexo 1", "Hay una fila sin térmica.")
            if not grupo.strip():
                h("D09", BLOQUEANTE, "Anexo 1", f"Falta la tensión nominal esperada de {q} (el plano no la indica).",
                  "Ingresarla en la tabla del Anexo 1.")
            if not desc.strip():
                h("D09", BLOQUEANTE, "Anexo 1", f"Falta la descripción del circuito de {q} (el plano no la indica).",
                  "Ingresarla en la tabla del Anexo 1.")
    if any(k.endswith("A2") for k in incluir):
        if not senales:
            h("D06", BLOQUEANTE, "Anexo 2", "No hay señales cargadas.", "Subir el PDF del esquema funcional.")
        if not comandos:
            h("D07", ADVERTENCIA, "Anexo 2", "No hay comandos cargados.")
        sin_borne = [n for b, n in senales if not b.strip() or b.startswith("(")]
        if sin_borne:
            h("D08", BLOQUEANTE, "Anexo 2", f"{len(sin_borne)} señales sin borne (ej.: {sin_borne[0]}).",
              "Ingresar el borne/elemento: el plano no lo define.")
    return hs
