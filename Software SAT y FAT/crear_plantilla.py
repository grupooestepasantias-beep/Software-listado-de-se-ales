"""Crea las plantillas de los protocolos a partir de documentos existentes.

- plantilla_sat.docx          desde el SAT de Santa Rosa rB (sin anexos)
- plantilla_fat.docx          desde "Protocolo de ensayo FAT.docx" (La Paz)
- plantilla_fat_anexo1.docx   desde "... FAT - La Paz Anexo1.docx" (energizado)
- plantilla_fat_anexo2.docx   desde "... FAT - La Paz Anexo2.docx" (listado de señales)

Los datos variables pasan a ser marcadores {{...}} y las tablas que se completan quedan con
una sola fila modelo. Los completa generador_sat.py. Los documentos de origen solo se leen.

Correcciones estructurales que se aplican a todas las plantillas (ver INFORME.md):
- el índice es un campo TOC real de Word (números de página e hipervínculos correctos);
- "Contenido" no es un capítulo (antes desplazaba toda la numeración en los FAT);
- el total de páginas del pie es un campo NUMPAGES (antes era texto fijo en los FAT);
- las correcciones de redacción de CORRECCIONES (ortografía/puntuación, sin cambiar el sentido).

Uso:  python crear_plantilla.py [sat_origen.docx] [carpeta_fat_origen]
"""
import copy
import os
import re
import sys

import docx
from docx.oxml import OxmlElement
from docx.shared import Pt, RGBColor
from docx.oxml.ns import qn

from docx_util import (encabezados_y_pies, estilos_indice, filas_xml, marcar_fila, nivel_esquema, parrafo_indice,
                       parrafos, quitar_numeracion, reemplazar, texto, total_paginas_en_campo)

ORIGEN_SAT = r"\\192.168.15.101\Archivos\PasantiasMM\la paz\SAT\Protocolo de ensayo SAT - Santa Rosa - rB.docx"
ORIGEN_FAT = r"\\192.168.15.101\Archivos\PasantiasMM\la paz\FAT"
CARPETA = os.path.dirname(os.path.abspath(__file__))

# Correcciones de ortografía y puntuación del texto fijo. No cambian ningún procedimiento.
CORRECCIONES = [
    ("bandejas rebatibles. Etc.)", "bandejas rebatibles, etc.)"),
    ("correspondiente(48VCC/110VCC)", "correspondiente (48VCC/110VCC)"),
    ("TOMA Y VETILACIÓN", "TOMA Y VENTILACIÓN"),
]

TEXTO_PROTECCIONES = ("Por último, se verificará la correcta lectura de señales de protecciones "
                      "enviando instrucción desde RTU a Scada Survalent.")


def poner_runs(parrafo, valores):
    """Asigna valores a los runs del párrafo en orden (None = dejar como está)."""
    for run, valor in zip(parrafo.runs, valores):
        if valor is not None:
            run.text = valor


def buscar_parrafo(doc, empieza):
    for p in doc.paragraphs:
        if p.text.strip().startswith(empieza):
            return p
    raise ValueError(f"No se encontró el párrafo que empieza con: {empieza!r}")


def reemplazar_en_doc(doc, reemplazos):
    """Aplica los reemplazos a los párrafos fuera de tablas, a la tabla de firma y a los encabezados."""
    todos = list(doc.paragraphs)
    for t in doc.tables:
        if t.rows[0].cells[0].text.strip() == "Por Grupo Oeste":
            todos += [p for c in t._cells for p in c.paragraphs]
    for h in encabezados_y_pies(doc):
        todos += list(h.paragraphs) + [p for t in h.tables for c in t._cells for p in c.paragraphs]
    for p in todos:
        for viejo, nuevo in reemplazos:
            if viejo in p.text:
                reemplazar(p, viejo, nuevo)


def recortar_tabla(tbl, conservar):
    """Deja las primeras `conservar` filas (encabezados + fila modelo)."""
    for tr in filas_xml(tbl)[conservar:]:
        tbl.remove(tr)


def tabla_refs(doc):
    return next(t for t in doc.tables if t.rows[0].cells[0].text.lower().strip().endswith(".pdf"))


def tabla_firma(doc):
    return next(t for t in doc.tables if t.rows[0].cells[0].text.strip() == "Por Grupo Oeste")


def partir_en_dos_columnas(tabla, titulo_derecha):
    """Duplica la única columna de la tabla; la nueva queda vacía salvo el título de la primera fila."""
    grid = tabla._tbl.tblGrid
    cols = grid.findall(qn("w:gridCol"))
    total = sum(int(c.get(qn("w:w"))) for c in cols)
    for c in cols:
        grid.remove(c)
    for _ in range(2):
        col = OxmlElement("w:gridCol")
        col.set(qn("w:w"), str(total // 2))
        grid.append(col)
    for n, tr in enumerate(tabla._tbl.findall(qn("w:tr"))):
        tc = tr.find(qn("w:tc"))
        tcw = tc.get_or_add_tcPr().find(qn("w:tcW"))
        if tcw is not None:
            tcw.set(qn("w:w"), str(total // 2))
            tcw.set(qn("w:type"), "dxa")
        nueva = copy.deepcopy(tc)
        for i, t in enumerate(nueva.findall(".//" + qn("w:t"))):
            t.text = titulo_derecha if (n == 0 and i == 0) else ""
        tc.addnext(nueva)


def observaciones_en_hoja_nueva(doc, tabla):
    """'OBSERVACIONES' empieza en hoja nueva y la tabla de firma queda más abajo y sin partirse."""
    from docx.text.paragraph import Paragraph
    buscar_parrafo(doc, "OBSERVACIONES").paragraph_format.page_break_before = True
    # Los párrafos vacíos que había antes de la tabla se reemplazan por un único espaciado fijo
    previo = tabla._tbl.getprevious()
    while (previo is not None and previo.tag == qn("w:p") and not texto(previo).strip()
           and previo.find(".//" + qn("w:sectPr")) is None and previo.find(".//" + qn("w:br")) is None):
        anterior = previo.getprevious()
        previo.getparent().remove(previo)
        previo = anterior
    separador = OxmlElement("w:p")
    tabla._tbl.addprevious(separador)
    Paragraph(separador, doc._body).paragraph_format.space_before = Pt(110)
    for i, fila in enumerate(tabla.rows):
        marcar_fila(fila._tr)
        if i < len(tabla.rows) - 1:
            for celda in fila.cells:
                for p in celda.paragraphs:
                    p.paragraph_format.keep_with_next = True


# Reemplazos comunes a los FAT de La Paz (portada, encabezado, firma)
REEMPLAZOS_FAT = [
    ("205-EDESTE_Reemplazo RTUs", "{{OBRA}}"),
    ("Tablero de Control – La Paz", "{{TIPO_TABLERO}} – {{NOMBRE}}"),
    ("REV: A", "REV: {{REVISION}}"),
    ("– 205 - EDESTE – La Paz", "– {{NRO_OBRA}} - {{CLIENTE}} – {{NOMBRE}}"),
    ("Por EDESTE", "Por {{CLIENTE}}"),
]


def fecha_portada(doc):
    p = next(p for p in doc.paragraphs if p.text.strip() == "Fecha:")
    p.runs[0].text = "Fecha: {{FECHA}}"


def agregar_ubicacion(doc):
    """Portada: línea 'Ubicación' justo debajo de 'Proyecto/Obra' (copia su formato)."""
    from docx.text.paragraph import Paragraph
    obra = buscar_parrafo(doc, "Proyecto/Obra:")
    nuevo = copy.deepcopy(obra._p)
    obra._p.addnext(nuevo)
    p = Paragraph(nuevo, obra._parent)
    p.runs[0].text = "Ubicación: {{UBICACION}}"
    for r in p.runs[1:]:
        r._r.getparent().remove(r._r)


# ---------------------------------------------------------------- correcciones comunes
def corregir_textos(doc):
    for p in parrafos(doc):
        for viejo, nuevo in CORRECCIONES:
            if viejo in p.text:
                reemplazar(p, viejo, nuevo)


def niveles_de_esquema(doc):
    """Los apartados escritos con su número a mano (3.1., 3.3.1.) entran al índice con su nivel."""
    patron = re.compile(r"^\d+\.\d+(\.\d+)?\.?\s")
    for p in doc.paragraphs:
        t = p.text.strip()
        if patron.match(t) and not p.style.name.lower().startswith(("heading", "título")):
            profundo = t.split()[0].rstrip(".").count(".") >= 2
            nivel_esquema(p._p, 2 if profundo else 1)
            if profundo:  # el índice copia el formato del título: sin versalitas queda legible
                for sc in p._p.iter(qn("w:smallCaps")):
                    sc.getparent().remove(sc)
    # Títulos que no son apartados del índice ("Descripción", grupos de energización)
    for p in parrafos(doc):
        t = p.text.strip()
        if t == "Descripción":
            # Estilo "Título 3" lo mete en el índice: se pasa a texto normal con el mismo aspecto
            p.style = doc.styles["Normal"]
            for r in p.runs:
                r.bold = True
                r.font.size = Pt(10)
            p.paragraph_format.keep_with_next = True
        elif t.startswith("ENERGIZACIÓN"):
            nivel_esquema(p._p, 9)


def indice_en_campo_sdt(doc):
    """FAT y anexos: reemplaza el bloque de índice (con entradas viejas) por un campo TOC real."""
    for sdt in doc.element.body.findall(qn("w:sdt")):
        contenido = sdt.find(qn("w:sdtContent"))
        todos = list(contenido.iter(qn("w:p")))
        titulo = todos[0]
        secciones = [s for p in todos for s in p.findall(qn("w:pPr") + "/" + qn("w:sectPr"))]
        quitar_numeracion(titulo)
        for estilo in doc.styles:
            if estilo.style_id == "TtuloTDC":  # mismo aspecto que los demás títulos
                estilo.font.name = "Arial"
                estilo.font.size = Pt(14)
                estilo.font.bold = True
                estilo.font.color.rgb = RGBColor(0, 0, 0)
        toc = parrafo_indice()
        if secciones:
            toc.get_or_add_pPr().append(secciones[0])
        sdt.addprevious(titulo)
        sdt.addprevious(toc)
        sdt.getparent().remove(sdt)
        return
    raise ValueError("No se encontró el índice del documento")


def indice_en_campo_sat(doc):
    """SAT: reemplaza las líneas del índice escritas a mano por un campo TOC real."""
    con_puntos = [p for p in doc.paragraphs if re.search(r"\.{8,}", p.text)]
    if not con_puntos:
        raise ValueError("No se encontraron las líneas del índice")
    # También las líneas de continuación sin puntos (p. ej. el comienzo de "3.3.1. Prueba de...")
    primero, ultimo = con_puntos[0]._p, con_puntos[-1]._p
    lineas, actual = [], primero
    while actual is not None:
        lineas.append(actual)
        if actual is ultimo:
            break
        actual = actual.getnext()
    previo = primero.getprevious()
    if previo is not None and previo.tag == qn("w:p") and re.match(r"^\s*\d+\.\d+\.\d+\.", texto(previo)):
        lineas.insert(0, previo)
    secciones = [s for p in lineas for s in p.findall(qn("w:pPr") + "/" + qn("w:sectPr"))]
    toc = parrafo_indice()
    if secciones:
        toc.get_or_add_pPr().append(secciones[0])
    lineas[0].addprevious(toc)
    for p in lineas:
        p.getparent().remove(p)


def agregar_lectura_de_protecciones(doc):
    """El SAT de Santa Rosa omite el párrafo de protecciones que sí tienen Nueva California, La Paz y el FAT."""
    if any(p.text.strip().startswith("Por último") for p in doc.paragraphs):
        return
    base = buscar_parrafo(doc, "También se analizará la indicación de salidas digitales")
    nuevo = copy.deepcopy(base._p)
    base._p.addnext(nuevo)
    from docx.text.paragraph import Paragraph
    p = Paragraph(nuevo, base._parent)
    p.runs[0].text = TEXTO_PROTECCIONES
    for r in p.runs[1:]:
        r._r.getparent().remove(r._r)


def terminar_con_punto(doc, empieza):
    for p in doc.paragraphs:
        if p.text.strip().startswith(empieza) and not p.text.rstrip().endswith("."):
            ultimo = [r for r in p.runs if r.text.strip()][-1]
            ultimo.text = ultimo.text.rstrip() + "."


def espaciadores_a_saltos(doc, minimo=8):
    """Reemplaza los bloques de párrafos vacíos usados para "empujar" contenido a la hoja siguiente
    por un salto de página real en el párrafo que sigue (si la tabla anterior crece, no deja hojas en blanco)."""
    def vacio(el):
        return (el.tag == qn("w:p") and not texto(el).strip() and el.find(".//" + qn("w:drawing")) is None
                and el.find(".//" + qn("w:br")) is None and el.find(".//" + qn("w:sectPr")) is None
                and el.find(".//" + qn("w:bookmarkStart")) is None)
    cuerpo = list(doc.element.body.iterchildren())
    primero = next((i for i, e in enumerate(cuerpo) if e.tag == qn("w:p") and texto(e).strip().upper() == "OBJETO"), 0)
    bloque, convertidos = [], 0
    for el in cuerpo[primero:] + [None]:
        if el is not None and vacio(el):
            bloque.append(el)
            continue
        if len(bloque) >= minimo and el is not None and el.tag == qn("w:p"):
            from docx.text.paragraph import Paragraph
            Paragraph(el, doc._body).paragraph_format.page_break_before = True
            for v in bloque:
                v.getparent().remove(v)
            convertidos += 1
        bloque = []
    return convertidos


def formato_tablas(doc):
    """Filas que no se parten entre hojas; encabezados que se repiten en las tablas que cruzan hojas."""
    from docx_util import tablas_hoja
    for tbl in tablas_hoja(doc):
        filas = tbl.findall(qn("w:tr"))
        if not filas:
            continue
        primera = texto(filas[0]).strip()
        encabezados = {0} if primera.startswith(("COMPONENTES DE HARDWARE", "VERIFICACIÓN")) else set()
        if primera.startswith("Comandos"):
            encabezados = {0, 1}
        for i, tr in enumerate(filas):
            marcar_fila(tr, no_partir=True, encabezado=i in encabezados)


def saltos_de_pagina(doc, con_indice_sdt):
    """Capítulos que empiezan en hoja nueva (antes lo lograban con párrafos vacíos o con el bloque de índice)."""
    for p in doc.paragraphs:
        t = p.text.strip().upper()
        if (con_indice_sdt and t == "OBJETO") or t.startswith(("REGISTRO DE COMPONENTES PRINCIPALES", "ANEXO 1.")):
            p.paragraph_format.page_break_before = True


def normalizar(doc, con_indice_sdt):
    espaciadores_a_saltos(doc)
    saltos_de_pagina(doc, con_indice_sdt)
    formato_tablas(doc)
    corregir_textos(doc)
    niveles_de_esquema(doc)
    estilos_indice(doc)
    total_paginas_en_campo(doc)
    if con_indice_sdt:
        indice_en_campo_sdt(doc)
    else:
        indice_en_campo_sat(doc)
    terminar_con_punto(doc, "Por último, se verificará")


# ---------------------------------------------------------------- SAT
def crear_sat(origen):
    doc = docx.Document(origen)
    body = doc.element.body

    # 1. Borrar los anexos: desde el título "ANEXO 1." hasta el final (se conserva el sectPr final)
    hijos = list(body.iterchildren())
    inicio = next(i for i, el in enumerate(hijos)
                  if el.tag == qn("w:p") and texto(el).strip().upper().startswith("ANEXO 1."))
    for el in hijos[inicio:]:
        if el.tag != qn("w:sectPr"):
            body.remove(el)

    # 2. Quitar "ANEXO 1 ....." y "ANEXO 2 ....." del índice, moviendo el salto de sección si lo tienen
    lineas = [p for p in doc.paragraphs if p.text.startswith("ANEXO") and "...." in p.text]
    anterior = lineas[0]._p.getprevious()
    for p in lineas:
        sect = p._p.find(qn("w:pPr") + "/" + qn("w:sectPr"))
        if sect is not None:
            anterior.get_or_add_pPr().append(sect)
        p._p.getparent().remove(p._p)

    # 3. Portada
    fecha_portada(doc)
    obra = buscar_parrafo(doc, "Proyecto/Obra:")
    poner_runs(obra, [None, None, "{{OBRA}}"] + [""] * (len(obra.runs) - 3))
    agregar_ubicacion(doc)
    tablero = buscar_parrafo(doc, "Tablero:")
    poner_runs(tablero, [None, "{{TIPO_TABLERO}} ", "– {{NOMBRE}}"] + [""] * (len(tablero.runs) - 3))

    # 4. Objeto
    objeto = buscar_parrafo(doc, "El presente documento tiene como finalidad")
    poner_runs(objeto, [None, "{{TIPO_TABLERO_MAYUS}} – ", "{{NOMBRE_MAYUS}}", " de {{CLIENTE}}."]
               + [""] * (len(objeto.runs) - 4))

    # 5. Encabezados de página: "Título: Protocolo Ensayo – 205 - EDESTE – Santa Rosa"
    reemplazar_en_doc(doc, [("– 205 - EDESTE – Santa Rosa", "– {{NRO_OBRA}} - {{CLIENTE}} – {{NOMBRE}}")])

    # 6. Tablas: documentos de referencia (sin encabezado) y componentes (fila 0 = encabezado)
    recortar_tabla(tabla_refs(doc)._tbl, 1)
    t_comp = next(t for t in doc.tables if t.rows[0].cells[0].text.strip() == "COMPONENTES DE HARDWARE")
    recortar_tabla(t_comp._tbl, 2)

    # 7. Redacción: párrafo de protecciones (estándar de Nueva California) y correcciones comunes
    agregar_lectura_de_protecciones(doc)

    # 8. "5. OBSERVACIONES" en hoja nueva y firma en dos columnas
    t_firma = tabla_firma(doc)
    partir_en_dos_columnas(t_firma, "Por {{CLIENTE}}")
    observaciones_en_hoja_nueva(doc, t_firma)

    # 9. Índice real, pies de página, estilos y niveles
    normalizar(doc, con_indice_sdt=False)
    anexos_en_indice_y_etiquetas(doc)
    guardar(doc, "plantilla_sat.docx")


def anexos_en_indice_y_etiquetas(doc):
    """SAT: el índice cierra con 'ANEXO 1' y 'ANEXO 2' (archivos aparte, sin página) y los recuadros dicen 'del Anexo N'."""
    toc = next(p for p in doc.element.body.iter(qn("w:p")) if any("TOC" in (i.text or "") for i in p.iter(qn("w:instrText"))))
    sec = toc.find(qn("w:pPr") + "/" + qn("w:sectPr"))
    seccion = doc.sections[0]
    ancho = int((seccion.page_width - seccion.left_margin - seccion.right_margin) / 635)
    ultimo = toc
    for n in (1, 2):
        p = OxmlElement("w:p")
        ppr = OxmlElement("w:pPr")
        tabs = OxmlElement("w:tabs")
        tab = OxmlElement("w:tab")
        for k, v in (("val", "right"), ("leader", "dot"), ("pos", str(ancho))):
            tab.set(qn(f"w:{k}"), v)
        tabs.append(tab)
        ppr.append(tabs)
        sp = OxmlElement("w:spacing")
        sp.set(qn("w:after"), "100")
        ppr.append(sp)
        p.append(ppr)
        r = OxmlElement("w:r")
        rpr = OxmlElement("w:rPr")
        f = OxmlElement("w:rFonts")
        for k in ("ascii", "hAnsi", "cs"):
            f.set(qn(f"w:{k}"), "Arial")
        rpr.append(f)
        b = OxmlElement("w:b")
        rpr.append(b)
        sz = OxmlElement("w:sz")
        sz.set(qn("w:val"), "20")
        rpr.append(sz)
        r.append(rpr)
        t = OxmlElement("w:t")
        t.text = f"ANEXO {n}"
        r.append(t)
        r.append(OxmlElement("w:tab"))
        p.append(r)
        ultimo.addnext(p)
        ultimo = p
    if sec is not None:  # el salto de sección que cerraba el índice pasa a la última línea
        toc.find(qn("w:pPr")).remove(sec)
        ultimo.find(qn("w:pPr")).append(sec)
    for p in parrafos(doc):
        for viejo, nuevo in (("Verificación anexo 1.", "Verificación del Anexo 1"),
                             ("Verificación anexo 2", "Verificación del Anexo 2")):
            if p.text.strip() == viejo:
                reemplazar(p, viejo, nuevo)


# ---------------------------------------------------------------- FAT
def crear_fat(origen):
    doc = docx.Document(origen)
    fecha_portada(doc)
    reemplazar_en_doc(doc, REEMPLAZOS_FAT + [
        ("del tablero de control de La Paz,", "del {{TIPO_TABLERO_MINUS}} de {{NOMBRE}},"),
    ])
    agregar_ubicacion(doc)
    recortar_tabla(tabla_refs(doc)._tbl, 1)
    t_comp = next(t for t in doc.tables if t.rows[0].cells[0].text.strip() == "COMPONENTES DE HARDWARE")
    recortar_tabla(t_comp._tbl, 2)
    observaciones_en_hoja_nueva(doc, tabla_firma(doc))
    normalizar(doc, con_indice_sdt=True)
    guardar(doc, "plantilla_fat.docx")


def crear_fat_anexo1(origen):
    doc = docx.Document(origen)
    fecha_portada(doc)
    reemplazar_en_doc(doc, REEMPLAZOS_FAT + [
        ("del tablero de control de La Paz y", "del {{TIPO_TABLERO_MINUS}} de {{NOMBRE}} y"),
    ])
    agregar_ubicacion(doc)
    recortar_tabla(tabla_refs(doc)._tbl, 1)
    # Tabla de energizado: una tabla anidada por grupo (220 VCA / 110 VCC) con fila ítem + fila espacio
    externa = next(t for t in doc.tables if "ENERGIZACIÓN" in texto(t._tbl))
    for anidada in externa._tbl.iter(qn("w:tbl")):
        if anidada is not externa._tbl:
            recortar_tabla(anidada, 2)
    observaciones_en_hoja_nueva(doc, tabla_firma(doc))
    normalizar(doc, con_indice_sdt=True)
    guardar(doc, "plantilla_fat_anexo1.docx")


def crear_fat_anexo2(origen):
    doc = docx.Document(origen)
    fecha_portada(doc)
    reemplazar_en_doc(doc, REEMPLAZOS_FAT + [
        ("TABLERO DE CONTROL – La Paz de EDESTE", "{{TIPO_TABLERO_MAYUS}} – {{NOMBRE}} de {{CLIENTE}}"),
    ])
    agregar_ubicacion(doc)
    recortar_tabla(tabla_refs(doc)._tbl, 1)
    # Señales: 6 filas de encabezado + 1 modelo
    t_sen = next(t for t in doc.tables if t.rows[0].cells[-1].text.strip() == "SCADA SURVALENT")
    recortar_tabla(t_sen._tbl, 7)
    # Comandos: tabla anidada con 2 filas de encabezado + 1 modelo
    externa = next(t for t in doc.tables if "Comandos" in texto(t._tbl))
    anidada = next(el for el in externa._tbl.iter(qn("w:tbl")) if el is not externa._tbl)
    recortar_tabla(anidada, 3)
    observaciones_en_hoja_nueva(doc, tabla_firma(doc))
    normalizar(doc, con_indice_sdt=True)
    guardar(doc, "plantilla_fat_anexo2.docx")


# ---------------------------------------------------------------- Anexos del SAT (formato de los SAT hechos a mano)
ORIGEN_SAT_ANEXOS = r"\\192.168.15.101\Archivos\PasantiasMM\la paz\Words\words listos"
REEMPLAZOS_SAT_ANEXO = [
    ("205-EDESTE_Reemplazo RTUs", "{{OBRA}}"),
    ("Tablero de Control – La Paz", "{{TIPO_TABLERO}} – {{NOMBRE}}"),
    ("– 205 - EDESTE – La Paz", "– {{NRO_OBRA}} - {{CLIENTE}} – {{NOMBRE}}"),
    ("– 205 - EDESTE – Santa Rosa", "– {{NRO_OBRA}} - {{CLIENTE}} – {{NOMBRE}}"),
    ("Protocolo Ensayo Interno", "Protocolo Ensayo"),
]


def _anexo_sat_base(origen):
    """Portada simple ('PROTOCOLO DE ENSAYO – ANEXO N', Tipo: SAT) sin índice, objeto ni firmas, como los SAT de referencia."""
    doc = docx.Document(origen)
    fecha_portada(doc)
    reemplazar_en_doc(doc, REEMPLAZOS_SAT_ANEXO)
    agregar_ubicacion(doc)
    corregir_textos(doc)
    total_paginas_en_campo(doc)
    primera = doc.sections[0]
    for sec in doc.sections[1:]:  # los originales difieren por décimas de milímetro entre secciones
        sec.page_width, sec.page_height = primera.page_width, primera.page_height
    return doc


def crear_sat_anexo1(origen):
    """Anexo 1 del SAT: lista de verificación por grupo de tensión (una tabla anidada por grupo, fila ítem + espacio)."""
    doc = _anexo_sat_base(origen)
    externa = next(t for t in doc.tables if "ENERGIZACIÓN" in texto(t._tbl))
    for anidada in list(externa._tbl.iter(qn("w:tbl"))):
        if anidada is not externa._tbl:
            recortar_tabla(anidada, 2)
    guardar(doc, "plantilla_sat_anexo1.docx")


def crear_sat_anexo2(origen):
    """Anexo 2 del SAT: tabla de señales y recuadro de verificación (los comandos se insertan al generar)."""
    doc = _anexo_sat_base(origen)
    t_sen = next(t for t in doc.tables if t.rows[0].cells[-1].text.strip() == "SCADA SURVALENT")
    recortar_tabla(t_sen._tbl, 7)
    externa = next(t for t in doc.tables if "Comandos" in texto(t._tbl))
    anidada = next(el for el in externa._tbl.iter(qn("w:tbl")) if el is not externa._tbl)
    recortar_tabla(anidada, 3)
    guardar(doc, "plantilla_sat_anexo2.docx")


def guardar(doc, nombre):
    ruta = os.path.join(CARPETA, nombre)
    doc.save(ruta)
    print("Plantilla creada:", ruta)


def main(origen_sat=ORIGEN_SAT, carpeta_fat=ORIGEN_FAT):
    crear_sat(origen_sat)
    crear_fat(os.path.join(carpeta_fat, "Protocolo de ensayo FAT.docx"))
    crear_fat_anexo1(os.path.join(carpeta_fat, "Protocolo de ensayo FAT - La Paz Anexo1.docx"))
    crear_fat_anexo2(os.path.join(carpeta_fat, "Protocolo de ensayo FAT - La Paz Anexo2.docx"))
    crear_sat_anexo1(os.path.join(ORIGEN_SAT_ANEXOS, "Protocolo de ensayo SAT - Anexo 1 - La Paz - rC.docx"))
    crear_sat_anexo2(os.path.join(ORIGEN_SAT_ANEXOS, "Protocolo de ensayo SAT - Anexo 2 - La Paz - rC.docx"))


if __name__ == "__main__":
    main(*sys.argv[1:3])
