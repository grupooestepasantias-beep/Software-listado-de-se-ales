"""Pruebas de generación, estructura, índice, tablas, anexos y paquete completo."""
import os
import re
import shutil
import sys
import tempfile
import unittest
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import docx
from docx.oxml.ns import qn

import datos_prueba as D
import generador_sat as g
import validador
import word_tools

HAY_WORD = word_tools.word_disponible()
PAQUETE = {}


def paquete(*args, **kw):
    """Los datos de prueba son ficticios: no hay PDF contra los que contrastar."""
    kw.setdefault("respaldo_pdf", False)
    return g.generar_paquete(*args, **kw)


def setUpModule():
    PAQUETE["carpeta"] = tempfile.mkdtemp(prefix="sat_pruebas_")
    PAQUETE["resultado"] = paquete(
        D.DATOS, D.DOCUMENTOS, D.COMPONENTES, D.TERMICAS, D.SENALES, D.COMANDOS, PAQUETE["carpeta"],
        incluir=g.CANONICOS, pdf=HAY_WORD)
    PAQUETE["rutas"] = dict(zip(g.CANONICOS, PAQUETE["resultado"]["archivos"]))


def tearDownModule():
    shutil.rmtree(PAQUETE["carpeta"], ignore_errors=True)


def texto(el):
    return "".join(t.text or "" for t in el.iter(qn("w:t")))


ANEXOS_SAT = ("SAT_A1", "SAT_A2")  # formato de los SAT de referencia: sin índice, documentos, observaciones ni firmas


def abrir(clave):
    return docx.Document(PAQUETE["rutas"][clave])


class PaqueteCompleto(unittest.TestCase):
    def test_se_generan_los_cuatro_documentos(self):
        self.assertEqual(len(PAQUETE["rutas"]), 6)
        for ruta in PAQUETE["rutas"].values():
            self.assertTrue(os.path.getsize(ruta) > 20000, ruta)
        nombres = sorted(os.path.basename(r) for r in PAQUETE["rutas"].values())
        esperados = sorted(g.nombre_salida(D.DATOS, f, a) for f in ("SAT", "FAT") for a in (None, 1, 2))
        self.assertEqual(nombres, esperados)
        self.assertIn("CLIENTE PRUEBA - Obra 000 - Tablero de Control Estación Prueba - Protocolo FAT - rA.docx", esperados)

    def test_el_paquete_es_apto_y_sin_advertencias(self):
        informe = PAQUETE["resultado"]["informe"]
        self.assertTrue(informe.apto, informe.a_texto())
        self.assertEqual(informe.advertencias, [], informe.a_texto())

    def test_sin_marcadores_sin_reemplazar(self):
        for clave, ruta in PAQUETE["rutas"].items():
            for parte, xml in validador.Doc(ruta).xml_partes():
                self.assertNotIn("{{", re.sub(r"<[^>]+>", "", xml), f"{clave} {parte}")

    def test_no_quedan_datos_de_otros_proyectos(self):
        prohibidos = ["La Paz", "Nueva California", "Santa Rosa", "San Martín", "EDESTE", "Neuquén", "205-"]
        for clave, ruta in PAQUETE["rutas"].items():
            xml = " ".join(x for _, x in validador.Doc(ruta).xml_partes())
            plano = re.sub(r"<[^>]+>", "", xml)
            for p in prohibidos:
                self.assertNotIn(p, plano, f"{clave} conserva '{p}' de otro proyecto")

    def test_portada_y_encabezados_con_los_datos_cargados(self):
        for clave, ruta in PAQUETE["rutas"].items():
            d = validador.Doc(ruta)
            self.assertEqual(d.portada["obra"], D.DATOS["OBRA"], clave)
            self.assertEqual(d.portada["tablero"], "Tablero de Control – Estación Prueba", clave)
            self.assertEqual(d.portada["fecha"], "02/11/2026", clave)
            for t in d.encabezados_pagina():
                self.assertIn("000 - CLIENTE PRUEBA – Estación Prueba", t)

    def test_tipos_detectados(self):
        tipos = {k: validador.Doc(r).tipo for k, r in PAQUETE["rutas"].items()}
        self.assertEqual(tipos, {k: k for k in g.CANONICOS})


class Estructura(unittest.TestCase):
    def encabezados(self, clave):
        d = validador.Doc(PAQUETE["rutas"][clave])
        return [(e["numero"], e["texto"]) for e in d.encabezados]

    def test_sat_tiene_3_1_a_3_3_y_no_tiene_estructura_fat(self):
        numeros = [n for n, _ in self.encabezados("SAT")]
        self.assertEqual(numeros, ["1", "2", "3", "3.1", "3.2", "3.3", "3.3.1", "4", "5"])
        textos = " ".join(t for _, t in self.encabezados("SAT")).casefold()
        self.assertNotIn("propiedades dieléctricas", textos)
        self.assertNotIn("punto a punto", textos)

    def test_fat_tiene_3_1_a_3_5_1(self):
        numeros = [n for n, _ in self.encabezados("FAT")]
        self.assertEqual(numeros, ["1", "2", "3", "3.1", "3.2", "3.3", "3.4", "3.5", "3.5.1", "4", "5"])

    def test_fat_numera_los_capitulos_desde_1_sin_contar_el_titulo_del_indice(self):
        # Antes "Contenido" era el capítulo 1 y "Pruebas por realizar" salía como 4 con apartados 3.x
        self.assertEqual(self.encabezados("FAT")[0], ("1", "OBJETO"))

    def test_anexos(self):
        a1 = [t for _, t in self.encabezados("FAT_A1")]
        a2 = [t for _, t in self.encabezados("FAT_A2")]
        self.assertIn("ANEXO 1. Procedimiento de energizado", a1)
        self.assertIn("Listado de señales", a2)
        self.assertNotIn("Listado de señales", a1)

    def test_el_sat_no_incluye_los_anexos(self):
        txt = " ".join(p.text for p in abrir("SAT").paragraphs)
        self.assertNotIn("ANEXO 1. Procedimiento", txt)
        self.assertNotIn("ANEXO 2. Listado", txt)
        self.assertIn("referirse al Anexo 1", txt)
        self.assertIn("referirse al Anexo 2", txt)

    def test_observaciones_en_hoja_nueva_en_todos(self):
        for clave in [k for k in PAQUETE["rutas"] if k not in ANEXOS_SAT]:
            doc = abrir(clave)
            p = next(p for p in doc.paragraphs if p.text.strip().startswith("OBSERVACIONES"))
            self.assertTrue(p.paragraph_format.page_break_before, clave)

    def test_tabla_de_firma_en_dos_columnas_con_el_cliente(self):
        for clave in [k for k in PAQUETE["rutas"] if k not in ANEXOS_SAT]:
            doc = abrir(clave)
            t = next(t for t in doc.tables if t.rows[0].cells[0].text.strip() == "Por Grupo Oeste")
            self.assertEqual([c.text.strip() for c in t.rows[0].cells], ["Por Grupo Oeste", "Por CLIENTE PRUEBA"], clave)
            self.assertEqual([r.cells[0].text.strip() for r in t.rows if r.cells[0].text.strip()],
                             ["Por Grupo Oeste", "Nombre:", "Firma:", "Fecha:"], clave)

    def test_lectura_de_protecciones_es_opcional(self):
        sin = dict(D.DATOS, PROTECCIONES=False)
        with tempfile.TemporaryDirectory() as tmp:
            ruta = g.generar(sin, D.DOCUMENTOS, D.COMPONENTES, tmp, tipo="SAT")
            self.assertNotIn("Por último, se verificará", " ".join(p.text for p in docx.Document(ruta).paragraphs))
        self.assertIn("Por último, se verificará", " ".join(p.text for p in abrir("SAT").paragraphs))


@unittest.skipUnless(HAY_WORD, "Microsoft Word no está instalado")
class IndiceNumeracionYPaginas(unittest.TestCase):
    def test_el_indice_esta_actualizado_y_coincide_con_los_titulos(self):
        for clave, ruta in PAQUETE["rutas"].items():
            if clave in ANEXOS_SAT:
                continue
            d = validador.Doc(ruta)
            self.assertFalse(d.indice_sin_actualizar, clave)
            self.assertGreaterEqual(len(d.indice), 4, clave)
            for titulo, pagina in d.indice:
                self.assertTrue(pagina.isdigit(), f"{clave}: '{titulo}' sin página")

    def test_los_numeros_de_pagina_del_indice_coinciden_con_el_pdf(self):
        for clave, ruta in PAQUETE["rutas"].items():
            if clave in ANEXOS_SAT:
                continue
            pdf = os.path.splitext(ruta)[0] + ".pdf"
            self.assertTrue(os.path.exists(pdf), pdf)
            malos = [h for h in validador._paginas_del_indice(validador.Doc(ruta), pdf)]
            self.assertEqual(malos, [], "\n".join(h.linea() for h in malos))

    def test_el_indice_tiene_hipervinculos_validos(self):
        for clave, ruta in PAQUETE["rutas"].items():
            if clave in ANEXOS_SAT:
                continue
            with zipfile.ZipFile(ruta) as z:
                xml = z.read("word/document.xml").decode("utf8")
            anclas = set(re.findall(r'<w:hyperlink[^>]*w:anchor="([^"]+)"', xml))
            marcadores = set(re.findall(r'<w:bookmarkStart[^>]*w:name="([^"]+)"', xml))
            self.assertGreaterEqual(len(anclas), 4, clave)
            self.assertTrue(anclas <= marcadores, f"{clave}: anclas sin marcador {anclas - marcadores}")

    def test_total_de_paginas_del_pie_coincide_con_el_real(self):
        import pymupdf
        for clave, ruta in PAQUETE["rutas"].items():
            pdf = pymupdf.open(os.path.splitext(ruta)[0] + ".pdf")
            ultima = pdf[len(pdf) - 1].get_text()
            self.assertRegex(ultima, rf"P[aá]gina\s+{len(pdf)}\s+de\s+{len(pdf)}", clave)

    def test_no_hay_hojas_en_blanco(self):
        import pymupdf
        for clave, ruta in PAQUETE["rutas"].items():
            pdf = pymupdf.open(os.path.splitext(ruta)[0] + ".pdf")
            for i, pagina in enumerate(pdf, 1):
                if i == 1:  # la portada tiene pocas líneas por diseño
                    continue
                lineas = [l for l in pagina.get_text().split("\n") if l.strip()]
                self.assertGreater(len(lineas), 8, f"{clave}: la hoja {i} está prácticamente vacía")


class PiesDePagina(unittest.TestCase):
    def test_todas_las_plantillas_usan_campo_numpages(self):
        for nombre in g.PLANTILLAS.values():
            with zipfile.ZipFile(os.path.join(os.path.dirname(AQUI), nombre)) as z:
                pies = [z.read(n).decode("utf8") for n in z.namelist() if re.match(r"word/footer\d+\.xml", n)]
            con_pagina = [p for p in pies if "PAGE" in p]
            self.assertTrue(con_pagina, nombre)
            for p in con_pagina:
                self.assertIn("NUMPAGES", p, f"{nombre}: el total de páginas es texto fijo")


class Tablas(unittest.TestCase):
    def test_documentos_de_referencia(self):
        for clave in [k for k in PAQUETE["rutas"] if k not in ANEXOS_SAT]:
            t = next(t for t in abrir(clave).tables if t.rows[0].cells[0].text.strip().endswith(".pdf"))
            self.assertEqual([[c.text for c in r.cells] for r in t.rows], [list(x) for x in D.DOCUMENTOS], clave)

    def test_componentes_en_orden(self):
        for clave in ("SAT", "FAT"):
            t = next(t for t in abrir(clave).tables if t.rows[0].cells[0].text.strip() == "COMPONENTES DE HARDWARE")
            self.assertEqual([r.cells[0].text for r in t.rows[1:]], [c for c, _ in D.COMPONENTES], clave)

    def test_filas_no_se_parten_y_encabezado_se_repite(self):
        t = next(t for t in abrir("FAT").tables if t.rows[0].cells[0].text.strip() == "COMPONENTES DE HARDWARE")
        self.assertIsNotNone(t.rows[0]._tr.find(".//" + qn("w:tblHeader")))
        for r in t.rows:
            self.assertIsNotNone(r._tr.find(".//" + qn("w:cantSplit")))

    def test_anexo_1_cuenta_y_agrupa_las_termicas(self):
        d = validador.Doc(PAQUETE["rutas"]["FAT_A1"])
        externa = d.tabla("energizado")
        filas = validador._filas(externa)
        self.assertEqual(filas[0][:3], ["Paso", "Circuito (térmica)", "Tensión esperada"])
        self.assertEqual([(f[0], f[1], f[2]) for f in filas[1:]], [
            ("1", "Iluminación –Q221", "220 VCA"), ("2", "Toma –Q222", "220 VCA"),
            ("3", "Circuito de alimentación general –Q1", "110 VCC"), ("4", "Circuito de alimentación Fuente 1 –Q2", "110 VCC")])

    def test_anexo_2_cuenta_senales_y_comandos(self):
        d = validador.Doc(PAQUETE["rutas"]["FAT_A2"])
        senales = [f for f in validador._filas(d.tabla("senales")) if f[0].startswith("-XFI1/")]
        self.assertEqual([(f[0], f[1]) for f in senales], D.SENALES)
        comandos = [f for t in (validador._anidadas(d.tabla("comandos")) or [d.tabla("comandos")]) for f in validador._filas(t) if f[0].startswith("XF")]
        self.assertEqual([(f[0], f[1]) for f in comandos], D.COMANDOS)

    def test_encabezado_de_la_tabla_larga_se_repite(self):
        d = validador.Doc(PAQUETE["rutas"]["FAT_A2"])
        self.assertIsNotNone(d.tabla("senales").find(".//" + qn("w:tblHeader")))


class CasosLimite(unittest.TestCase):
    def generar_a2(self, senales, comandos):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = g.generar_anexo2(D.DATOS, D.DOCUMENTOS, senales, comandos, tmp)
            return validador.Doc(ruta), _leer(ruta)

    def test_caracteres_especiales_xml_y_unicode(self):
        raros = [("-XFI1/1", 'Señal <A> & "B" > C – 50 % ñandú ✔'), ("-XFI1/2", "Línea 1 con tilde á é í ó ú ü")]
        d, doc = self.generar_a2(raros, [("XF01-2", "Comando <ok> & más")])
        filas = [f for f in validador._filas(d.tabla("senales")) if f[0].startswith("-XFI1/")]
        self.assertEqual([(f[0], f[1]) for f in filas], raros)

    def test_muchas_senales(self):
        muchas = [(f"-XFI9/{i}", f"Señal {i}") for i in range(1, 1501)]
        d, _ = self.generar_a2(muchas, COMANDOS_1)
        filas = [f for f in validador._filas(d.tabla("senales")) if f[0].startswith("-XFI9/")]
        self.assertEqual(len(filas), 1500)

    def test_una_sola_senal(self):
        d, _ = self.generar_a2([("-XFI1/1", "Única")], COMANDOS_1)
        self.assertEqual(len([f for f in validador._filas(d.tabla("senales")) if f[0].startswith("-XFI1/")]), 1)

    def test_un_solo_documento_de_referencia(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = g.generar(D.DATOS, D.DOCUMENTOS[:1], D.COMPONENTES, tmp, tipo="SAT")
            t = next(t for t in docx.Document(ruta).tables if t.rows[0].cells[0].text.strip().endswith(".pdf"))
            self.assertEqual(len(t.rows), 1)

    def test_nombre_de_archivo_con_caracteres_prohibidos(self):
        n = g.nombre_salida(dict(D.DATOS, NOMBRE='Est: "A/B"'), "SAT")
        self.assertFalse(set('\\/:*?"<>|') & set(n))

    def test_anexo_1_con_una_sola_termica(self):
        with tempfile.TemporaryDirectory() as tmp:
            ruta = g.generar_anexo1(D.DATOS, D.DOCUMENTOS, D.TERMICAS[:1], tmp)
            filas = validador._filas(validador.Doc(ruta).tabla("energizado"))
        self.assertEqual(len(filas), 2)


COMANDOS_1 = [("XF01-2", "Comando")]


def _leer(ruta):
    return docx.Document(ruta)


if __name__ == "__main__":
    unittest.main(verbosity=2)
