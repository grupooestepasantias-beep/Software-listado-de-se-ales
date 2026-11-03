"""Utilidades comunes para trabajar con los .docx de los protocolos."""
import copy

from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def reemplazar(parrafo, viejo, nuevo):
    """Reemplaza `viejo` por `nuevo` aunque esté repartido en varios runs.

    El texto nuevo queda en el primer run afectado (con su formato); el resto de los runs
    conserva su formato y solo pierde la parte reemplazada. Devuelve True si reemplazó.
    """
    runs = parrafo.runs
    textos = [r.text for r in runs]
    completo = "".join(textos)
    i = completo.find(viejo)
    if i < 0 or not viejo:
        return False
    j = i + len(viejo)
    pos, primero = 0, True
    for run, texto in zip(runs, textos):
        a, b = pos, pos + len(texto)
        pos = b
        if b <= i or a >= j:
            continue
        ini, fin = max(i, a) - a, min(j, b) - a
        if primero:
            run.text = texto[:ini] + nuevo + texto[fin:]
            primero = False
        else:
            run.text = texto[fin:]
    return True


def parrafos(contenedor, con_tablas=True):
    """Párrafos de un documento, encabezado o celda (incluye tablas anidadas si con_tablas)."""
    yield from contenedor.paragraphs
    if con_tablas:
        for t in contenedor.tables:
            for fila in t.rows:
                for celda in fila.cells:
                    yield from parrafos(celda)


def encabezados_y_pies(doc):
    vistos = set()
    for s in doc.sections:
        for h in (s.header, s.first_page_header, s.even_page_header,
                  s.footer, s.first_page_footer, s.even_page_footer):
            if id(h._element) not in vistos:
                vistos.add(id(h._element))
                yield h


def texto(el):
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


def poner_texto_celda(celda, valor):
    """Escribe en la celda conservando el formato del primer run (o de la marca de párrafo)."""
    p = celda.paragraphs[0]
    for extra in celda.paragraphs[1:]:
        extra._p.getparent().remove(extra._p)
    if p.runs:
        p.runs[0].text = valor
        for run in p.runs[1:]:
            run._r.getparent().remove(run._r)
    else:
        run = p.add_run(valor)
        rpr = p._p.find(qn("w:pPr") + "/" + qn("w:rPr"))
        if rpr is not None:
            nuevo = copy.deepcopy(rpr)
            nuevo.tag = qn("w:rPr")
            run._r.insert(0, nuevo)


# Orden que exige el esquema OOXML para los hijos de <w:pPr> que van después de outlineLvl
_DESPUES_DE_OUTLINE = ("divId", "cnfStyle", "rPr", "sectPr", "pPrChange")


def nivel_esquema(p_xml, nivel):
    """Asigna nivel de esquema (0 = título 1) a un párrafo sin cambiar su aspecto, para el índice."""
    ppr = p_xml.get_or_add_pPr()
    existente = ppr.find(qn("w:outlineLvl"))
    if existente is not None:
        ppr.remove(existente)
    nuevo = OxmlElement("w:outlineLvl")
    nuevo.set(qn("w:val"), str(nivel))
    siguiente = next((c for c in ppr if c.tag.split("}")[1] in _DESPUES_DE_OUTLINE), None)
    if siguiente is not None:
        siguiente.addprevious(nuevo)
    else:
        ppr.append(nuevo)


def parrafo_indice(texto_provisorio="Índice: se completa al generar (en Word: clic derecho > Actualizar campos)."):
    """Párrafo con un campo TOC de Word (niveles 1-3, con hipervínculos)."""
    p = OxmlElement("w:p")
    partes = [("fldChar", "begin"), ("instrText", " TOC \\h \\z \\u "), ("fldChar", "separate"),
              ("t", texto_provisorio), ("fldChar", "end")]
    for tipo, valor in partes:
        r = OxmlElement("w:r")
        el = OxmlElement(f"w:{tipo}")
        if tipo == "fldChar":
            el.set(qn("w:fldCharType"), valor)
            if valor == "begin":
                el.set(qn("w:dirty"), "true")
        else:
            el.set(qn("xml:space"), "preserve")
            el.text = valor
        r.append(el)
        p.append(r)
    return p


def _run_campo(tipo, valor=None, rpr=None):
    r = OxmlElement("w:r")
    if rpr is not None:
        r.append(copy.deepcopy(rpr))
    if tipo == "fldChar":
        el = OxmlElement("w:fldChar")
        el.set(qn("w:fldCharType"), valor)
    elif tipo == "instrText":
        el = OxmlElement("w:instrText")
        el.set(qn("xml:space"), "preserve")
        el.text = valor
    else:
        el = OxmlElement("w:t")
        el.text = valor
    r.append(el)
    return r


def total_paginas_en_campo(doc):
    """Reemplaza el total de páginas escrito a mano ("Página 2 de 15") por un campo NUMPAGES.

    Devuelve la cantidad de pies corregidos.
    """
    corregidos = 0
    for hf in encabezados_y_pies(doc):
        for p in hf._element.iter(qn("w:p")):
            runs = p.findall(qn("w:r"))
            if any("NUMPAGES" in (i.text or "") for i in p.iter(qn("w:instrText"))):
                continue
            for k, r in enumerate(runs):
                if texto(r).strip() == "de" and "PAGE" in "".join(i.text or "" for i in p.iter(qn("w:instrText"))):
                    cola = [x for x in runs[k + 1:] if texto(x).strip().isdigit() and x.find(qn("w:fldChar")) is None]
                    if not cola:
                        break
                    rpr = cola[0].find(qn("w:rPr"))
                    ultimo = cola[-1]
                    for x in cola[:-1]:
                        p.remove(x)
                    for tipo, valor in (("fldChar", "begin"), ("instrText", " NUMPAGES "),
                                        ("fldChar", "separate"), ("t", "1"), ("fldChar", "end")):
                        ultimo.addprevious(_run_campo(tipo, valor, rpr))
                    p.remove(ultimo)
                    corregidos += 1
                    break
    return corregidos


def estilos_indice(doc, fuente="Arial", puntos=10):
    """Define los estilos 'toc 1/2/3' del índice (misma tipografía que el protocolo de referencia)."""
    estilos = doc.styles.element
    sangrias = {1: 0, 2: 284, 3: 567}
    for nivel in (1, 2, 3):
        sid = f"TDC{nivel}"
        for viejo in estilos.findall(qn("w:style")):
            if viejo.get(qn("w:styleId")) == sid:
                estilos.remove(viejo)
        xml = (
            f'<w:style xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
            f'w:type="paragraph" w:styleId="{sid}"><w:name w:val="toc {nivel}"/><w:basedOn w:val="Normal"/>'
            f'<w:next w:val="Normal"/><w:autoRedefine/><w:uiPriority w:val="39"/><w:unhideWhenUsed/>'
            f'<w:pPr><w:spacing w:before="0" w:after="40" w:line="240" w:lineRule="auto"/>'
            f'<w:ind w:left="{sangrias[nivel]}"/></w:pPr>'
            f'<w:rPr><w:rFonts w:ascii="{fuente}" w:hAnsi="{fuente}" w:cs="{fuente}"/><w:b/><w:bCs/>'
            f'<w:sz w:val="{puntos * 2}"/><w:szCs w:val="{puntos * 2}"/></w:rPr></w:style>')
        from lxml import etree
        estilos.append(etree.fromstring(xml))


def quitar_numeracion(p_xml):
    """Párrafo sin numeración automática y fuera del índice (nivel de esquema 'texto independiente')."""
    ppr = p_xml.get_or_add_pPr()
    ppr.get_or_add_numPr().get_or_add_numId().val = 0
    nivel_esquema(p_xml, 9)


_ORDEN_TRPR = ("cnfStyle", "divId", "gridBefore", "gridAfter", "wBefore", "wAfter", "cantSplit", "trHeight",
               "tblHeader", "tblCellSpacing", "jc", "hidden", "ins", "del", "trPrChange")


def marcar_fila(tr, no_partir=True, encabezado=False):
    """Fila que no se parte entre hojas y/o que se repite como encabezado (respeta el orden del esquema)."""
    trpr = tr.get_or_add_trPr()
    for nombre, activo in (("cantSplit", no_partir), ("tblHeader", encabezado)):
        if not activo or trpr.find(qn(f"w:{nombre}")) is not None:
            continue
        nuevo = OxmlElement(f"w:{nombre}")
        posterior = next((c for c in trpr if c.tag.split("}")[1] in _ORDEN_TRPR
                          and _ORDEN_TRPR.index(c.tag.split("}")[1]) > _ORDEN_TRPR.index(nombre)), None)
        if posterior is not None:
            posterior.addprevious(nuevo)
        else:
            trpr.append(nuevo)


def tablas_hoja(doc):
    """Tablas 'hoja' (sin otras tablas adentro), incluidas las anidadas."""
    for t in doc.element.body.iter(qn("w:tbl")):
        if not any(True for x in t.iter(qn("w:tbl")) if x is not t):
            yield t


def filas_xml(tbl):
    """Filas directas de una tabla (sin las de tablas anidadas)."""
    return tbl.findall(qn("w:tr"))


def celdas_xml(tr):
    return tr.findall(qn("w:tc"))
