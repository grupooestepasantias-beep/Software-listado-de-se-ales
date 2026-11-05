"""Genera los protocolos SAT y FAT (cada uno con sus Anexos 1 y 2) a partir de las plantillas.

Principio: ningún dato técnico se inventa. Las señales, comandos y térmicas salen de los PDF cargados y se
contrastan con ellos antes de generar; lo que el plano no dice se reclama al usuario (revisar_previos).
"""
import copy
import csv
import os
import re
import sys
import zipfile

import docx
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Pt
from docx.table import _Cell

import extraer_pdf
import gestion
import validador
import word_tools
from docx_util import (celdas_xml, encabezados_y_pies, filas_xml, marcar_fila, parrafos, poner_texto_celda,
                       reemplazar, texto)


def carpeta_programa():
    # Al empaquetar con PyInstaller los archivos de datos quedan en sys._MEIPASS
    return getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))


PLANTILLAS = {
    "SAT": "plantilla_sat.docx",
    "FAT": "plantilla_fat.docx",
    "FAT_ANEXO1": "plantilla_fat_anexo1.docx",
    "FAT_ANEXO2": "plantilla_fat_anexo2.docx",
}
PLANTILLA = os.path.join(carpeta_programa(), PLANTILLAS["SAT"])
CANONICOS = ("SAT", "SAT_A1", "SAT_A2", "FAT", "FAT_A1", "FAT_A2")


def ruta_plantilla(clave):
    return os.path.join(carpeta_programa(), PLANTILLAS[clave])


def normalizar_incluir(incluir):
    """Acepta las claves anteriores ('A1','A2' = anexos del FAT) y devuelve las canónicas, en orden."""
    alias = {"A1": "FAT_A1", "A2": "FAT_A2"}
    pedidas = {alias.get(k, k) for k in incluir}
    desconocidas = pedidas - set(CANONICOS)
    if desconocidas:
        raise ValueError(f"Documento desconocido: {sorted(desconocidas)}")
    return tuple(k for k in CANONICOS if k in pedidas)


# Palabras del nombre de archivo -> tipo de esquema
ESQUEMAS = [
    (r"(^|[-_ .])EF([-_ .\d]|$)|FUNCIONAL", "ESQUEMA FUNCIONAL"),
    (r"(^|[-_ .])(TP|EC)([-_ .\d]|$)|TOPOGR|CONSTRUCTIVO", "ESQUEMA CONSTRUCTIVO"),
    (r"(^|[-_ .])(UF|UN)([-_ .\d]|$)|UNIFILAR", "ESQUEMA UNIFILAR"),
    (r"(^|[-_ .])(LS|LA)([-_ .\d]|$)|LISTA|SE[ÑN]ALES|BORNERA", "LISTA DE SEÑALES"),
]


def deducir_descripcion(nombre_archivo, tipo_tablero, tension):
    """'ETSM-205-ET-CT-PL-EF-1001-rC.pdf' -> 'TABLERO DE CONTROL DE 33 KV ESQUEMA FUNCIONAL'.

    Devuelve '' si no reconoce el tipo de plano, para completarlo a mano.
    """
    nombre = os.path.splitext(os.path.basename(nombre_archivo))[0].upper()
    for patron, esquema in ESQUEMAS:
        if re.search(patron, nombre):
            partes = [tipo_tablero.strip().upper()]
            if tension.strip():
                partes.append("DE " + tension.strip().upper())
            partes.append(esquema)
            return " ".join(p for p in partes if p)
    return ""


def es_esquema_funcional(nombre_archivo):
    return re.search(ESQUEMAS[0][0], os.path.splitext(os.path.basename(nombre_archivo))[0].upper()) is not None


def _seguro(texto_):
    return re.sub(r'[\\/:*?"<>|]', "-", texto_).strip()


def nombre_base(datos):
    """Identifica el tablero: cliente, obra y tablero (nunca nombres aleatorios)."""
    return _seguro(f"{datos['CLIENTE']} - Obra {datos['NRO_OBRA']} - {datos['TIPO_TABLERO']} {datos['NOMBRE']}")


def nombre_salida(datos, tipo="SAT", anexo=None):
    """'EDESTE - Obra 205 - Tablero de Control La Paz - Protocolo FAT - rA - Anexo 1.docx'."""
    nombre = f"{nombre_base(datos)} - Protocolo {tipo}"
    if datos.get("REVISION"):
        nombre += f" - r{datos['REVISION']}"
    if anexo:
        nombre += f" - Anexo {anexo}"
    return nombre + ".docx"


def _marcadores(datos):
    tipo = datos.get("TIPO_TABLERO", "")
    return {
        "{{FECHA}}": datos.get("FECHA", ""),
        "{{OBRA}}": datos.get("OBRA", ""),
        "{{UBICACION}}": datos.get("UBICACION", ""),
        "{{TIPO_TABLERO}}": tipo,
        "{{TIPO_TABLERO_MAYUS}}": tipo.upper(),
        "{{TIPO_TABLERO_MINUS}}": tipo.lower(),
        "{{NOMBRE}}": datos.get("NOMBRE", ""),
        "{{NOMBRE_MAYUS}}": datos.get("NOMBRE", "").upper(),
        "{{CLIENTE}}": datos.get("CLIENTE", ""),
        "{{NRO_OBRA}}": datos.get("NRO_OBRA", ""),
        "{{REVISION}}": datos.get("REVISION", ""),
    }


def reemplazar_marcadores(doc, datos):
    marcadores = _marcadores(datos)
    contenedores = [doc] + list(encabezados_y_pies(doc))
    for c in contenedores:
        for p in parrafos(c):
            if "{{" not in p.text:
                continue
            for clave, valor in marcadores.items():
                while clave in p.text and reemplazar(p, clave, valor):
                    pass


def llenar_filas(tbl, modelos, filas):
    """Clona las filas modelo (lista de <w:tr>) por cada elemento de `filas` y borra los modelos.

    modelos[0] recibe los textos; las demás (p. ej. una fila de espacio) se copian tal cual.
    """
    anterior = modelos[-1]
    for valores in filas:
        copias = [copy.deepcopy(m) for m in modelos]
        for tr in copias:
            anterior.addnext(tr)
            anterior = tr
        for tc, valor in zip(celdas_xml(copias[0]), valores):
            if valor is not None:
                poner_texto_celda(_Cell(tc, None), valor)
    for m in modelos:
        tbl.remove(m)


def llenar_tabla(tabla, indice_modelo, filas):
    """Compatibilidad: clona la fila `indice_modelo` de una tabla de python-docx."""
    llenar_filas(tabla._tbl, [tabla.rows[indice_modelo]._tr], filas)


def _tabla_refs(doc):
    return next(t for t in doc.tables if t.rows[0].cells[0].text.lower().strip().endswith(".pdf"))


def _tabla_componentes(doc):
    return next(t for t in doc.tables if t.rows[0].cells[0].text.strip() == "COMPONENTES DE HARDWARE")


TEXTO_PROTECCIONES = "Por último, se verificará la correcta lectura de señales de protecciones"


def _corregir_tension_cc(doc, vcc):
    """El texto fijo dice "(48VCC/110VCC)"; si los planos solo mencionan `vcc` se deja solo lo que el plano respalda."""
    nuevo = "/".join(f"{v}VCC" for v in sorted(vcc))
    for p in parrafos(doc):
        if "48VCC/110VCC" in p.text:
            reemplazar(p, "48VCC/110VCC", nuevo)


def _preparar(doc, datos, tipo, anexo):
    """Opciones del documento: protecciones opcionales; los anexos del SAT llevan 'SAT' en la portada."""
    if not datos.get("PROTECCIONES", True):
        for p in list(doc.paragraphs):
            if p.text.strip().startswith(TEXTO_PROTECCIONES):
                p._p.getparent().remove(p._p)
    if datos.get("VCC_PLANO") and 48 not in datos["VCC_PLANO"]:
        _corregir_tension_cc(doc, datos["VCC_PLANO"])
    if anexo and tipo == "SAT":
        for p in doc.paragraphs[:40]:
            if "PROTOCOLO DE ENSAYO FAT" in p.text:
                reemplazar(p, "PROTOCOLO DE ENSAYO FAT", "PROTOCOLO DE ENSAYO SAT")


def ruta_de_salida(datos, carpeta, tipo, anexo=None):
    return os.path.join(carpeta, nombre_salida(datos, tipo, anexo))


def _guardar(doc, datos, destino, tipo, anexo=None):
    datos_doc = dict(datos, FECHA=gestion.fecha_de(datos, tipo))  # cada ensayo lleva su propia fecha
    _preparar(doc, datos_doc, tipo, anexo)
    reemplazar_marcadores(doc, datos_doc)
    if not destino.lower().endswith(".docx"):
        destino = ruta_de_salida(datos, destino, tipo, anexo)
    gestion.guardar_docx_seguro(doc, destino)  # archiva la versión anterior, nunca la pisa
    return destino


def generar(datos, documentos, componentes, destino, plantilla=PLANTILLA, tipo="SAT"):
    """Protocolo principal (SAT o FAT). Devuelve la ruta generada."""
    if tipo != "SAT" and plantilla == PLANTILLA:
        plantilla = ruta_plantilla(tipo)
    doc = docx.Document(plantilla)
    llenar_tabla(_tabla_refs(doc), 0, documentos or [("", "")])
    llenar_tabla(_tabla_componentes(doc), 1, componentes or [("", "")])
    return _guardar(doc, datos, destino, tipo)


# ---------------------------------------------------------------- Anexo 1: procedimiento de energizado
# Texto tomado de los protocolos de referencia (apartado "Energizado progresivo"): no se agrega nada propio.
CONDICIONES_PREVIAS = [
    "Se realiza el energizado progresivo del tablero con la tensión nominal de alimentación de cada componente o grupo de ellos.",
    "Antes de energizar se comprueba, usando un multímetro, que la tensión sea la requerida.",
    "Al momento de inicio no hay ninguna señal de campo presente: se presta atención a las indicaciones que pudieran aparecer.",
    "En caso de ser necesario, se carga un programa básico en los controladores que permita proseguir con los ensayos "
    "(comprobación de estado de los propios controladores).",
    "Los controles se realizan siguiendo los lineamientos de la norma IEC 61439-1, párrafo 11.10.",
]
CRITERIO_ACEPTACION = (
    "Cada paso se aprueba cuando la tensión medida antes de energizar es la tensión esperada del circuito y las indicaciones "
    "observadas al energizar quedan registradas. El anexo se aprueba cuando todos los pasos de la secuencia están aprobados.")
COLUMNAS_PROCEDIMIENTO = [("Paso", 6), ("Circuito (térmica)", 30), ("Tensión esperada", 14), ("Tensión medida", 14),
                          ("Indicaciones observadas", 20), ("Resultado", 16)]


def _parrafo_nuevo(doc, texto_, negrita=False, sangria=0.0, antes=0, despues=4):
    p = doc.add_paragraph()
    run = p.add_run(texto_)
    run.bold = negrita
    run.font.name = "Arial"
    run.font.size = Pt(10)
    p.paragraph_format.space_before = Pt(antes)
    p.paragraph_format.space_after = Pt(despues)
    p.paragraph_format.keep_with_next = negrita
    if sangria:
        p.paragraph_format.left_indent = Pt(sangria)
    return p._p


def _celda(celda, texto_, negrita=False, centrado=False, fondo=None):
    p = celda.paragraphs[0]
    run = p.add_run(texto_)
    run.bold = negrita
    run.font.name = "Arial"
    run.font.size = Pt(8)
    p.paragraph_format.space_before = Pt(3)
    p.paragraph_format.space_after = Pt(3)
    if centrado:
        p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    if fondo:
        sh = OxmlElement("w:shd")
        sh.set(qn("w:val"), "clear")
        sh.set(qn("w:color"), "auto")
        sh.set(qn("w:fill"), fondo)
        celda._tc.get_or_add_tcPr().append(sh)


def _tabla_simple(doc, columnas, filas, centradas=(0,)):
    """Tabla con bordes, encabezado repetido y filas que no se parten (se inserta donde se la necesite)."""
    sec = doc.sections[0]
    ancho = int((sec.page_width - sec.left_margin - sec.right_margin) / 635)
    tabla = doc.add_table(rows=1 + len(filas), cols=len(columnas))
    tbl = tabla._tbl
    pr = tbl.tblPr
    bordes = OxmlElement("w:tblBorders")
    for lado in ("top", "left", "bottom", "right", "insideH", "insideV"):
        b = OxmlElement(f"w:{lado}")
        for k, v in (("val", "single"), ("sz", "4"), ("space", "0"), ("color", "808080")):
            b.set(qn(f"w:{k}"), v)
        bordes.append(b)
    pr.append(bordes)
    layout = OxmlElement("w:tblLayout")
    layout.set(qn("w:type"), "fixed")
    pr.append(layout)
    anchos = [int(ancho * p / 100) for _, p in columnas]
    for gc, w in zip(tbl.tblGrid.findall(qn("w:gridCol")), anchos):
        gc.set(qn("w:w"), str(w))
    for r_i, fila in enumerate(tabla.rows):
        valores = [c for c, _ in columnas] if r_i == 0 else filas[r_i - 1]
        for c_i, celda in enumerate(fila.cells):
            celda.width = docx.shared.Twips(anchos[c_i])
            _celda(celda, valores[c_i], negrita=r_i == 0, centrado=r_i == 0 or c_i in centradas, fondo="D9D9D9" if r_i == 0 else None)
        marcar_fila(fila._tr, no_partir=True, encabezado=r_i == 0)
    return tbl


def _tabla_procedimiento(doc, filas):
    """Tabla de la secuencia de energización: pasos verificables con valor esperado, medido y resultado."""
    return _tabla_simple(doc, COLUMNAS_PROCEDIMIENTO, filas)


COLUMNAS_COMANDOS = [("Comandos (borne)", 18), ("Señal (comando)", 46), ("ACSELERATOR RTAC", 18), ("SCADA SURVALENT", 18)]


def _insertar_comandos(doc, externa, comandos):
    """Los comandos DO van en una tabla propia (visible, con encabezado que se repite en cada hoja)."""
    anidada = next((el for el in externa.iter(qn("w:tbl")) if el is not externa), None)
    elementos = [_parrafo_nuevo(doc, f"Comandos (salidas digitales DO): {len(comandos)}", True, antes=10),
                 _parrafo_nuevo(doc, "✔ Satisfactorio     ✘ No satisfactorio     - No aplica", despues=4),
                 _tabla_simple(doc, COLUMNAS_COMANDOS, [(b, n, "", "") for b, n in comandos] or [("", "", "", "")])]
    for e in elementos:
        externa.addprevious(e)
    if anidada is not None:  # la tabla anidada se reemplaza; el contenedor conserva las verificaciones funcionales
        anidada.getparent().remove(anidada)


def _insertar_procedimiento(doc, termicas):
    """Reemplaza la lista de verificación del anexo por el procedimiento completo."""
    externa = next(t for t in doc.tables if "ENERGIZACIÓN" in texto(t._tbl))._tbl
    filas = []
    for n, (grupo, descripcion, termica) in enumerate(termicas, start=1):
        filas.append((str(n), f"{descripcion} –{termica.lstrip('-')}", grupo, "", "", "☐ Aprobado\n☐ Rechazado"))
    elementos = [_parrafo_nuevo(doc, "Condiciones previas", True, antes=6)]
    elementos += [_parrafo_nuevo(doc, f"{i}. {t}", sangria=12) for i, t in enumerate(CONDICIONES_PREVIAS, start=1)]
    elementos += [_parrafo_nuevo(doc, "Secuencia de energización", True, antes=8),
                  _tabla_procedimiento(doc, filas),
                  _parrafo_nuevo(doc, "Criterio de aceptación", True, antes=10),
                  _parrafo_nuevo(doc, CRITERIO_ACEPTACION)]
    for e in elementos:
        externa.addprevious(e)
    externa.getparent().remove(externa)


def generar_anexo1(datos, documentos, termicas, destino, tipo="FAT"):
    """Anexo 1 (energizado) del FAT o del SAT. termicas: [(tensión esperada, descripción del circuito, 'Q221')]."""
    doc = docx.Document(ruta_plantilla("FAT_ANEXO1"))
    llenar_tabla(_tabla_refs(doc), 0, documentos or [("", "")])
    _insertar_procedimiento(doc, termicas)
    return _guardar(doc, datos, destino, tipo, anexo=1)


def generar_anexo2(datos, documentos, senales, comandos, destino, tipo="FAT"):
    """Anexo 2 (listado de señales) del FAT o del SAT. senales y comandos: [(borne, nombre)]."""
    doc = docx.Document(ruta_plantilla("FAT_ANEXO2"))
    llenar_tabla(_tabla_refs(doc), 0, documentos or [("", "")])

    t_sen = next(t for t in doc.tables if t.rows[0].cells[-1].text.strip() == "SCADA SURVALENT")._tbl
    llenar_filas(t_sen, [filas_xml(t_sen)[6]], [(b, n, None, None) for b, n in senales] or [("", "", None, None)])

    externa = next(t for t in doc.tables if "Comandos" in texto(t._tbl))._tbl
    _insertar_comandos(doc, externa, comandos)
    return _guardar(doc, datos, destino, tipo, anexo=2)


# ---------------------------------------------------------------- control previo: nada sin respaldo
class DatosIncompletos(ValueError):
    """Faltan datos o hay inconsistencias sin resolver; `.hallazgos` tiene el detalle exacto."""

    def __init__(self, mensaje, hallazgos=()):
        super().__init__(mensaje)
        self.hallazgos = list(hallazgos)

    @property
    def solo_confirmables(self):
        bloq = [h for h in self.hallazgos if h.gravedad == validador.BLOQUEANTE]
        return bool(bloq) and all(h.confirmable for h in bloq)


def _tension_norm(t):
    return re.sub(r"\s+", "", t).upper()


def _rutas_pdf(pdfs):
    return {n: r for n, r in (pdfs or {}).items() if r and r.lower().endswith(".pdf") and os.path.exists(r)}


def revisar_previos(datos, documentos, componentes, termicas, senales, comandos, incluir, pdfs=None,
                    respaldo_pdf=True, confirmados=()):
    """Todo lo que impide entregar: datos faltantes, PDF incorrectos y datos sin respaldo en los planos.

    Devuelve [Hallazgo] (sin generar nada). Los PDF se leen de nuevo para contrastar cada fila con el plano.
    """
    incluir = normalizar_incluir(incluir)
    hs = []
    for campo, msg in gestion.validar_entradas(datos, incluir):
        hs.append(validador.Hallazgo("E00", validador.BLOQUEANTE, validador.DOCUMENTAL, "Datos de la obra", campo, msg))
    hs += validador.validar_datos_previos(datos, documentos, componentes, termicas, senales, comandos, incluir)
    necesita_a2 = any(k.endswith("A2") for k in incluir)
    necesita_a1 = any(k.endswith("A1") for k in incluir)
    if respaldo_pdf and (necesita_a1 or necesita_a2 or documentos):
        disponibles = _rutas_pdf(pdfs)
        for archivo, _ in documentos:
            if archivo and archivo not in disponibles:
                hs.append(validador.Hallazgo("D10", validador.BLOQUEANTE, validador.DOCUMENTAL, "Documentos de referencia",
                                             archivo, f"El documento de referencia '{archivo}' no tiene su PDF cargado: "
                                             "no se puede comprobar su contenido.", "Cargarlo con 'Cargar PDF de ingeniería…'."))
        rutas = [r for n, r in disponibles.items() if any(n == a for a, _ in documentos)] or list(disponibles.values())
        if rutas:
            hs += extraer_pdf.validar_planos(rutas, datos, necesita_funcional=necesita_a2)
        if necesita_a2:
            funcionales = [r for r in rutas if es_esquema_funcional(r)]
            del_plano_s, del_plano_c = [], []
            for r in funcionales:
                try:
                    s, c, problemas = extraer_pdf.leer_funcional(r)
                except Exception as e:
                    hs.append(validador.Hallazgo("PDF01", validador.BLOQUEANTE, validador.DOCUMENTAL, os.path.basename(r), "",
                                                 f"No se pudo leer el esquema funcional: {e}", "Cargar un PDF válido."))
                    continue
                del_plano_s += s
                del_plano_c += c
                hs += [p for p in problemas if p.codigo != "S03"]  # S03 (sin borne) lo informa D08 hasta que se complete
            if funcionales:
                hs += extraer_pdf.comparar_con_pdf(senales, del_plano_s, "Señales")
                hs += extraer_pdf.comparar_con_pdf(comandos, del_plano_c, "Comandos")
        funcionales_hw = [x for x in rutas if es_esquema_funcional(x)]
        if funcionales_hw and componentes and any(not k.endswith(("A1", "A2")) for k in incluir):
            di, do = (sum(v) for v in zip(*(extraer_pdf.contar_modulos(x) for x in funcionales_hw)))
            t_di = sum(1 for c, _ in componentes if re.match(r"M[ÓO]DULO DI\b", c.upper()))
            t_do = sum(1 for c, _ in componentes if re.match(r"M[ÓO]DULO DO\b", c.upper()))
            if (t_di, t_do) != (di, do):
                hs.append(validador.Hallazgo("R30", validador.BLOQUEANTE, validador.CONSISTENCIA, "Componentes", "Hardware",
                                             f"El plano funcional dibuja {di} módulos DI y {do} DO y la tabla de componentes tiene "
                                             f"{t_di} DI y {t_do} DO.", "Completar los módulos que faltan (o quitar los que sobran)."))
        if necesita_a1 and rutas:
            plano = {t["termica"]: t for t in extraer_pdf.leer_termicas(rutas)}
            tabla = {q.lstrip("-"): grupo for grupo, _, q in termicas if q.strip()}
            for q in tabla:
                if q not in plano:
                    hs.append(validador.Hallazgo("R20", validador.BLOQUEANTE, validador.CONSISTENCIA, "Anexo 1", q,
                                                 f"La térmica -{q} no figura en los planos cargados (dato sin respaldo).",
                                                 "Quitarla o cargar el plano que la contiene."))
            for q, t in plano.items():
                if q not in tabla:
                    hs.append(validador.Hallazgo("R21", validador.BLOQUEANTE, validador.CONSISTENCIA, "Anexo 1", q,
                                                 f"La térmica -{q} está en el plano ({t['paginas'][0][0]}, página "
                                                 f"{t['paginas'][0][1]}) y falta en el Anexo 1.", "Agregarla a la tabla."))
                elif t["tension"] and tabla[q] and _tension_norm(t["tension"]) != _tension_norm(tabla[q]):
                    hs.append(validador.Hallazgo("R22", validador.BLOQUEANTE, validador.CONSISTENCIA, "Anexo 1", q,
                                                 f"-{q}: la tabla dice {tabla[q]} y el plano indica {t['tension']}.",
                                                 "Corregir la tensión esperada."))
    salida = []
    for h in hs:
        if h.confirmable and (h.codigo, h.archivo) in set(confirmados):
            h = validador.Hallazgo(h.codigo, validador.INFO, h.tipo, h.archivo, h.apartado,
                                   h.descripcion + f" [Confirmado por {gestion.usuario()}]", h.solucion)
        salida.append(h)
    return salida


PENDIENTES_FAT = [
    ("Ensayos dieléctricos", "Tensiones de prueba (500 Vcc, 2000 Vca / 2800 Vcc, 60 s), valor esperado >100 MΩ y normas "
     "(IEC 60255-27 / IEC 61439-1; la tabla cita IEC 255-5) son texto fijo del protocolo: los planos no los indican."),
    ("Anexo 1 / energizado", "La tensión de los circuitos Q220-Q223 (220 VCA) no figura en los planos (solo mencionan 110 V)."),
    ("Hardware", "Los modelos RTAC SEL 2241, POWER COUPLER SEL 2243 y módulos SEL 2244-2/2244-3 no figuran en los planos."),
    ("Ensayos funcionales", "Las referencias a SCADA SURVALENT y a la lista de señales provienen del protocolo, no de los planos."),
]


def pendientes_de_confirmacion(archivos, termicas):
    """Datos que el protocolo trae y los planos NO permiten verificar: se informan, no se dan por validados."""
    salida = []
    for a in archivos:
        nombre = os.path.basename(a)
        for apartado, texto_ in PENDIENTES_FAT:
            if "Ensayos dieléctricos" in apartado and "Protocolo FAT - " in nombre and "Anexo" in nombre:
                continue
            if apartado.startswith("Anexo 1") and not nombre.endswith("Anexo 1.docx"):
                continue
            if apartado == "Ensayos dieléctricos" and "Protocolo FAT" not in nombre:
                continue
            salida.append(validador.Hallazgo("PEND", validador.INFO, validador.CONSISTENCIA, nombre, apartado,
                                             "PENDIENTE DE CONFIRMACIÓN: " + texto_, "Confirmar con ingeniería."))
    return salida


def documentos_previstos(datos, carpeta, incluir):
    """[(clave, ruta)] de lo que se generaría con esa selección (para avisar si ya existen)."""
    mapa = {"SAT": ("SAT", None), "SAT_A1": ("SAT", 1), "SAT_A2": ("SAT", 2),
            "FAT": ("FAT", None), "FAT_A1": ("FAT", 1), "FAT_A2": ("FAT", 2)}
    return [(k, ruta_de_salida(datos, carpeta, *mapa[k])) for k in normalizar_incluir(incluir)]


# ---------------------------------------------------------------- trazabilidad y paquete
def _escribir_archivo_seguro(ruta, escribir):
    gestion.archivar_existente(ruta)
    escribir(ruta)
    return ruta


def trazabilidad(carpeta, datos, senales, comandos, termicas, pdfs):
    """CSV con el origen de cada señal, comando y térmica (plano, página, módulo, terminal, referencia)."""
    plano_s, plano_c, plano_t = {}, {}, {}
    for r in [r for r in _rutas_pdf(pdfs).values() if es_esquema_funcional(r)]:
        s, c, _ = extraer_pdf.leer_funcional(r)
        for x in s:
            plano_s.setdefault((x.borne or f"(ver {x.referencia})", x.nombre), x)
        for x in c:
            plano_c.setdefault((x.borne, x.nombre), x)
    for t in extraer_pdf.leer_termicas(list(_rutas_pdf(pdfs).values())) if _rutas_pdf(pdfs) else []:
        plano_t[t["termica"]] = t
    filas = []

    def fila_senal(tipo, borne, nombre, origen_dict):
        x = origen_dict.get((borne, nombre)) or next((v for (b, n), v in origen_dict.items() if n == nombre and not v.borne), None)
        if x:
            manual = "" if x.borne == borne else " (borne ingresado a mano)"
            return [tipo, borne, nombre, x.modulo, x.terminal, x.referencia, x.archivo, x.pagina_modulo, x.pagina_cableado,
                    "plano" + manual]
        return [tipo, borne, nombre, "", "", "", "", "", "", "MANUAL (sin respaldo en el plano)"]

    filas += [fila_senal("Señal DI", b, n, plano_s) for b, n in senales]
    filas += [fila_senal("Comando DO", b, n, plano_c) for b, n in comandos]
    for grupo, desc, q in termicas:
        t = plano_t.get(q.lstrip("-"))
        pag = f"{t['paginas'][0][0]}" if t else ""
        filas.append(["Térmica", f"-{q.lstrip('-')}", f"{desc} ({grupo})", "", "", "", pag, t["paginas"][0][1] if t else "",
                      "", "plano (térmica); descripción y tensión ingresadas por el usuario" if t else "MANUAL"])
    ruta = os.path.join(carpeta, f"{nombre_base(datos)} - Trazabilidad - r{datos['REVISION']}.csv")

    def escribir(r):
        with open(r, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["tipo", "borne/elemento (anexo)", "señal/descripción (anexo)", "módulo", "terminal", "referencia",
                        "plano", "página del módulo", "página del cableado", "origen"])
            w.writerows(filas)
    return _escribir_archivo_seguro(ruta, escribir)


def generar_paquete(datos, documentos, componentes, termicas, senales, comandos, carpeta,
                    incluir=CANONICOS, pdf=True, progreso=None, pdfs=None,
                    respaldo_pdf=True, confirmados=(), zip_paquete=True):
    """Genera los documentos elegidos, actualiza índices con Word, exporta PDF, los controla y arma el ZIP.

    pdfs: {nombre_de_archivo: ruta} de los planos cargados (contra ellos se comprueba todo).
    Lanza DatosIncompletos (sin crear nada) si falta información o hay algo sin respaldo.
    Devuelve {archivos, pdfs, zip, trazabilidad, informe, estado, word, archivadas}.
    """
    def avisar(texto_, fraccion):
        if progreso:
            progreso(texto_, fraccion)

    incluir = normalizar_incluir(incluir)
    if not incluir:
        raise ValueError("No hay ningún documento seleccionado para generar.")
    avisar("Verificando los datos contra los PDF de ingeniería…", 0.02)
    previos = revisar_previos(datos, documentos, componentes, termicas, senales, comandos, incluir, pdfs,
                              respaldo_pdf, confirmados)
    bloqueantes = [h for h in previos if h.gravedad == validador.BLOQUEANTE]
    if bloqueantes:
        raise DatosIncompletos("No se genera nada: hay problemas sin resolver:\n- " + "\n- ".join(
            f"{h.descripcion}" for h in bloqueantes), previos)

    antes = {ruta: os.path.exists(ruta) for _, ruta in documentos_previstos(datos, carpeta, incluir)}
    datos = dict(datos)
    if respaldo_pdf and _rutas_pdf(pdfs):
        datos["VCC_PLANO"] = extraer_pdf.tensiones_cc(list(_rutas_pdf(pdfs).values()))
    acciones = {
        "SAT": lambda: generar(datos, documentos, componentes, carpeta, tipo="SAT"),
        "FAT": lambda: generar(datos, documentos, componentes, carpeta, tipo="FAT"),
    }
    for fam in ("SAT", "FAT"):
        acciones[f"{fam}_A1"] = lambda fam=fam: generar_anexo1(datos, documentos, termicas, carpeta, tipo=fam)
        acciones[f"{fam}_A2"] = lambda fam=fam: generar_anexo2(datos, documentos, senales, comandos, carpeta, tipo=fam)
    archivos = []
    for i, clave in enumerate(incluir):
        avisar(f"Generando {clave.replace('_', ' ')}…", 0.1 + 0.35 * i / len(incluir))
        archivos.append(acciones[clave]())

    avisar("Actualizando índices y números de página con Word" + (" y exportando PDF…" if pdf else "…"), 0.5)
    word = word_tools.actualizar(archivos, pdf=pdf)
    avisar("Controlando la calidad de los documentos…", 0.85)
    informe = validador.validar_paquete(archivos, con_pdf=pdf)
    for r in word:
        if not r["ok"]:
            informe.hallazgos.append(validador.Hallazgo(
                "W01", validador.BLOQUEANTE if pdf else validador.ADVERTENCIA, validador.FORMATO, os.path.basename(r["path"]),
                "Índice, páginas y PDF", "No se pudo actualizar el índice ni exportar el PDF con Word: "
                + (r["error"] or "error desconocido"),
                "Instalar/abrir Microsoft Word y volver a generar (o abrir el documento y actualizar el índice con F9)."))
    informe.hallazgos += [h for h in previos if h.gravedad != validador.BLOQUEANTE]
    informe.hallazgos += pendientes_de_confirmacion(archivos, termicas)

    avisar("Armando la trazabilidad y el paquete…", 0.92)
    extras = []
    if any(k.endswith("A2") or k.endswith("A1") for k in incluir):
        extras.append(trazabilidad(carpeta, datos, senales if any(k.endswith("A2") for k in incluir) else [],
                                   comandos if any(k.endswith("A2") for k in incluir) else [],
                                   termicas if any(k.endswith("A1") for k in incluir) else [], pdfs))
    base = f"{nombre_base(datos)} - r{datos['REVISION']}"
    ruta_informe = os.path.join(carpeta, f"{base} - Informe de control de calidad.txt")
    def escribir_informe(r):
        with open(r, "w", encoding="utf-8") as f:
            f.write(informe.a_texto())
    _escribir_archivo_seguro(ruta_informe, escribir_informe)
    extras.append(ruta_informe)
    listo = informe.listo
    estado = "LISTO PARA ENTREGAR" if listo else "NO LISTO PARA ENTREGAR"
    ruta_zip = ""
    pdfs_generados = [r["pdf"] for r in word if r.get("pdf")]
    if zip_paquete:
        ruta_zip = os.path.join(carpeta, ("" if listo else "BORRADOR - ") + f"Paquete - {base}.zip")

        def escribir_zip(r):
            with zipfile.ZipFile(r, "w", zipfile.ZIP_DEFLATED) as z:
                for a in archivos + pdfs_generados + extras:
                    z.write(a, os.path.basename(a))
        _escribir_archivo_seguro(ruta_zip, escribir_zip)

    archivadas = [a for a in (_ultima_version(r) for r in archivos if antes.get(r)) if a]
    gestion.registrar(carpeta, "generar_paquete", estado=estado, incluir=list(incluir), pdf=bool(pdf),
                      archivos=[{"archivo": os.path.basename(a), "sha256": gestion.sha256(a)} for a in archivos],
                      bloqueantes=len(informe.bloqueantes), advertencias=len(informe.advertencias),
                      confirmados=[list(c) for c in confirmados], obra=datos.get("OBRA", ""),
                      tablero=datos.get("NOMBRE", ""), revision=datos.get("REVISION", ""),
                      planos=[{"archivo": n, "sha256": gestion.sha256(r)} for n, r in _rutas_pdf(pdfs).items()])
    avisar("Listo.", 1.0)
    return {"archivos": archivos, "pdfs": pdfs_generados, "zip": ruta_zip, "trazabilidad": extras[0] if len(extras) > 1 else "",
            "informe": informe, "estado": estado, "word": word, "archivadas": archivadas}


def _ultima_version(ruta):
    versiones = gestion.listar_versiones(ruta)
    return versiones[0][0] if versiones else ""
