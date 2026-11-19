"""El validador tiene que DETECTAR defectos: cada prueba rompe un documento bueno a propósito."""
import copy
import os
import shutil
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import docx
from docx.oxml.ns import qn

import datos_prueba as D
import docx_util
import generador_sat as g
import validador
import word_tools

HAY_WORD = word_tools.word_disponible()
BASE = {}


def paquete(*args, **kw):
    """Los datos de prueba son ficticios: no hay PDF contra los que contrastar."""
    kw.setdefault("respaldo_pdf", False)
    return g.generar_paquete(*args, **kw)


def setUpModule():
    BASE["carpeta"] = tempfile.mkdtemp(prefix="sat_validador_")
    r = paquete(D.DATOS, D.DOCUMENTOS, D.COMPONENTES, D.TERMICAS, D.SENALES, D.COMANDOS, BASE["carpeta"],
                          incluir=g.CANONICOS, pdf=False)
    BASE["rutas"] = dict(zip(g.CANONICOS, r["archivos"]))


def tearDownModule():
    shutil.rmtree(BASE["carpeta"], ignore_errors=True)


def parrafo(doc, empieza):
    """Primer párrafo del cuerpo (no del índice) que empieza con `empieza`."""
    return next(p for p in doc.paragraphs
                if p.text.strip().startswith(empieza) and p.runs and p.style.style_id not in ("TDC1", "TDC2", "TDC3"))


def poner(p, texto):
    for r in p.runs[1:]:
        r._r.getparent().remove(r._r)
    p.runs[0].text = texto


class Base(unittest.TestCase):
    def mutar(self, clave, cambio):
        """Copia el documento bueno, le aplica `cambio(doc)` y devuelve los hallazgos del validador."""
        doc = docx.Document(BASE["rutas"][clave])
        cambio(doc)
        ruta = os.path.join(tempfile.mkdtemp(dir=BASE["carpeta"]), os.path.basename(BASE["rutas"][clave]))
        doc.save(ruta)
        return validador.validar_documento(ruta)

    def codigos(self, hallazgos, gravedad=None):
        return {h.codigo for h in hallazgos if gravedad is None or h.gravedad == gravedad}

    def assertDetecta(self, hallazgos, codigo, gravedad):
        hit = [h for h in hallazgos if h.codigo == codigo and h.gravedad == gravedad]
        self.assertTrue(hit, f"No detectó {codigo}/{gravedad}. Detectó: {[h.linea()[:90] for h in hallazgos]}")
        h = hit[0]
        self.assertTrue(h.archivo and h.descripcion, "el hallazgo debe indicar archivo y descripción")
        return h


class DocumentoBueno(Base):
    def test_los_documentos_sin_romper_no_tienen_bloqueantes_salvo_indice(self):
        for clave, ruta in BASE["rutas"].items():
            hs = [h for h in validador.validar_documento(ruta) if h.gravedad == validador.BLOQUEANTE]
            self.assertEqual({h.codigo for h in hs} - {"I02"}, set(), f"{clave}: {[h.linea() for h in hs]}")

    @unittest.skipIf(HAY_WORD, "con Word el índice sí se actualiza")
    def test_sin_word_el_indice_queda_marcado(self):
        self.assertIn("I02", self.codigos(validador.validar_documento(BASE["rutas"]["SAT"])))


class Deteccion(Base):
    def test_c01_campos_sin_completar(self):
        hs = self.mutar("SAT", lambda d: poner(parrafo(d, "Tablero:"), "Tablero: {{TABLERO}}"))
        self.assertDetecta(hs, "C01", validador.BLOQUEANTE)

    def test_c02_portada_incompleta(self):
        hs = self.mutar("SAT", lambda d: poner(parrafo(d, "Proyecto/Obra:"), "Proyecto/Obra:"))
        self.assertDetecta(hs, "C02", validador.BLOQUEANTE)

    def test_c03_fecha_invalida(self):
        hs = self.mutar("SAT", lambda d: poner(parrafo(d, "Fecha:"), "Fecha: 31/02/2026"))
        self.assertDetecta(hs, "C03", validador.BLOQUEANTE)

    def test_c04_tipo_distinto_al_nombre_del_archivo(self):
        hs = self.mutar("SAT", lambda d: poner(parrafo(d, "Tipo:"), "Tipo: FAT"))
        self.assertDetecta(hs, "C04", validador.BLOQUEANTE)

    def test_e01_falta_apartado_obligatorio(self):
        def cambio(d):
            p = parrafo(d, "REGISTRO DE COMPONENTES")
            p._p.getparent().remove(p._p)
        self.assertDetecta(self.mutar("SAT", cambio), "E01", validador.BLOQUEANTE)

    def test_e02_estructura_fat_dentro_de_un_sat(self):
        def cambio(d):
            nuevo = copy.deepcopy(parrafo(d, "3.1. INSPECCIÓN")._p)
            parrafo(d, "3.1. INSPECCIÓN")._p.addnext(nuevo)
            from docx.text.paragraph import Paragraph
            poner(Paragraph(nuevo, d._body), "3.2. Propiedades dieléctricas")
        self.assertDetecta(self.mutar("SAT", cambio), "E02", validador.BLOQUEANTE)

    def test_e03_titulo_duplicado(self):
        def cambio(d):
            p = parrafo(d, "OBJETO")
            p._p.addnext(copy.deepcopy(p._p))
        self.assertDetecta(self.mutar("SAT", cambio), "E03", validador.BLOQUEANTE)

    def test_n02_salto_de_numeracion(self):
        hs = self.mutar("SAT", lambda d: poner(parrafo(d, "3.2."), "3.5. Energizado progresivo"))
        self.assertDetecta(hs, "N02", validador.BLOQUEANTE)

    def test_n01_apartado_bajo_otro_capitulo(self):
        hs = self.mutar("SAT", lambda d: poner(parrafo(d, "3.1."), "7.1. INSPECCIÓN VISUAL"))
        self.assertDetecta(hs, "N01", validador.BLOQUEANTE)

    def test_i04_entrada_de_indice_inexistente(self):
        if not HAY_WORD:
            self.skipTest("necesita el índice actualizado por Word")

        def cambio(d):
            p = next(p for p in d.paragraphs if p.style.style_id == "TDC1")
            nuevo = copy.deepcopy(p._p)
            p._p.addnext(nuevo)
            for t in nuevo.iter(qn("w:t")):
                t.text = "Capítulo que no existe" if t.text and len(t.text) > 3 else t.text
        self.assertIn("I04", self.codigos(self.mutar("SAT", cambio)))

    def test_t01_tabla_de_referencias_vacia(self):
        def cambio(d):
            t = next(t for t in d.tables if t.rows[0].cells[0].text.strip().endswith(".pdf"))
            for r in t.rows:
                for c in r.cells:
                    docx_util.poner_texto_celda(c, "")
        hs = self.mutar("SAT", cambio)
        self.assertTrue({"T01", "T02"} & self.codigos(hs, validador.BLOQUEANTE), [h.linea() for h in hs])

    def test_t03_documento_sin_descripcion_es_advertencia(self):
        def cambio(d):
            t = next(t for t in d.tables if t.rows[0].cells[0].text.strip().endswith(".pdf"))
            docx_util.poner_texto_celda(t.rows[0].cells[1], "")
        self.assertDetecta(self.mutar("SAT", cambio), "T03", validador.ADVERTENCIA)

    def test_t06_mismo_modelo_como_di_y_do_bloquea(self):
        def cambio(d):
            t = next(t for t in d.tables if t.rows[0].cells[0].text.strip() == "COMPONENTES DE HARDWARE")
            docx_util.poner_texto_celda(t.rows[2].cells[0], "MÓDULO DI SEL 2244-3")
        self.assertDetecta(self.mutar("SAT", cambio), "T06", validador.BLOQUEANTE)

    def test_t09_firma_en_una_columna(self):
        def cambio(d):
            t = next(t for t in d.tables if t.rows[0].cells[0].text.strip() == "Por Grupo Oeste")
            docx_util.poner_texto_celda(t.rows[0].cells[1], "")
        self.assertDetecta(self.mutar("SAT", cambio), "T09", validador.BLOQUEANTE)

    def test_t11_senal_sin_descripcion(self):
        def cambio(d):
            t = next(t for t in d.tables if "SCADA SURVALENT" in t.rows[0].cells[-1].text)
            fila = next(r for r in t.rows if r.cells[0].text.startswith("-XFI1/5"))
            docx_util.poner_texto_celda(fila.cells[1], "")
        self.assertDetecta(self.mutar("FAT_A2", cambio), "T11", validador.BLOQUEANTE)

    def test_t12_senal_sin_borne_bloquea(self):
        def cambio(d):
            t = next(t for t in d.tables if "SCADA SURVALENT" in t.rows[0].cells[-1].text)
            fila = next(r for r in t.rows if r.cells[0].text.startswith("-XFI1/5"))
            docx_util.poner_texto_celda(fila.cells[0], "(ver H3/C01)")
        self.assertDetecta(self.mutar("FAT_A2", cambio), "T12", validador.BLOQUEANTE)

    def test_t13_borne_duplicado(self):
        def cambio(d):
            t = next(t for t in d.tables if "SCADA SURVALENT" in t.rows[0].cells[-1].text)
            fila = next(r for r in t.rows if r.cells[0].text.startswith("-XFI1/6"))
            docx_util.poner_texto_celda(fila.cells[0], "-XFI1/5")
        self.assertDetecta(self.mutar("FAT_A2", cambio), "T13", validador.ADVERTENCIA)

    def test_r01_referencia_a_un_anexo_inexistente(self):
        hs = self.mutar("SAT", lambda d: poner(parrafo(d, "Para el listado de señales"),
                                               "Para el listado de señales, referirse al Anexo 3."))
        self.assertDetecta(hs, "R01", validador.BLOQUEANTE)

    def test_r02_anexo_equivocado(self):
        hs = self.mutar("SAT", lambda d: poner(parrafo(d, "Para el procedimiento del energizado"),
                                               "Para el procedimiento del energizado referirse al Anexo 2."))
        self.assertDetecta(hs, "R02", validador.BLOQUEANTE)

    def test_r03_titulo_de_anexo_no_coincide_con_la_portada(self):
        hs = self.mutar("FAT_A1", lambda d: poner(parrafo(d, "Anexo 1"), "Anexo 2"))
        self.assertIn("R03", self.codigos(hs, validador.BLOQUEANTE))

    def test_o01_errores_de_ortografia_frecuentes(self):
        hs = self.mutar("SAT", lambda d: poner(parrafo(d, "Realizar, de acuerdo"), "Verificacion de la tension en la VETILACIÓN."))
        textos = " ".join(h.descripcion for h in hs if h.codigo == "O01")
        for palabra in ("Verificacion", "tension", "VETILACIÓN"):
            self.assertIn(palabra, textos)
        self.assertTrue(all(h.gravedad == validador.ADVERTENCIA for h in hs if h.codigo == "O01"))

    def test_k01_encabezado_con_otro_proyecto(self):
        def cambio(d):
            for s in d.sections:
                for h in (s.header, s.first_page_header):
                    for p in h.paragraphs:
                        if "Título" in p.text:
                            for r in p.runs:
                                if "000" in r.text:
                                    r.text = r.text.replace("000", "999")
        self.assertDetecta(self.mutar("SAT", cambio), "K01", validador.BLOQUEANTE)

    def test_k02_el_objeto_no_menciona_el_tablero(self):
        def cambio(d):
            poner(parrafo(d, "El presente documento"), "El presente documento tiene como finalidad otra cosa.")
        self.assertDetecta(self.mutar("SAT", cambio), "K02", validador.BLOQUEANTE)

    def test_f02_nombre_en_minusculas_es_formato(self):
        h = self.assertDetecta(self.mutar("SAT", lambda d: poner(parrafo(d, "Tablero:"),
                                                               "Tablero: Tablero de Control – estacion")),
                               "F02", validador.ADVERTENCIA)
        self.assertEqual(h.tipo, validador.FORMATO)


class Paquete(Base):
    def copia_paquete(self):
        tmp = tempfile.mkdtemp(dir=BASE["carpeta"])
        rutas = {}
        for k, r in BASE["rutas"].items():
            rutas[k] = shutil.copy2(r, os.path.join(tmp, os.path.basename(r)))
        return rutas

    def test_p01_obra_distinta_entre_documentos(self):
        rutas = self.copia_paquete()
        d = docx.Document(rutas["FAT_A1"])
        poner(parrafo(d, "Proyecto/Obra:"), "Proyecto/Obra: 111-OTRA_Obra")
        d.save(rutas["FAT_A1"])
        hs = validador.validar_paquete(list(rutas.values()), con_pdf=False).hallazgos
        self.assertDetecta(hs, "P01", validador.BLOQUEANTE)

    def test_p01_fecha_distinta_es_advertencia(self):
        rutas = self.copia_paquete()
        d = docx.Document(rutas["FAT_A2"])
        poner(parrafo(d, "Fecha:"), "Fecha: 03/11/2026")
        d.save(rutas["FAT_A2"])
        hs = validador.validar_paquete(list(rutas.values()), con_pdf=False).hallazgos
        self.assertDetecta(hs, "P01", validador.ADVERTENCIA)

    def test_p03_documentos_de_referencia_distintos(self):
        rutas = self.copia_paquete()
        d = docx.Document(rutas["FAT"])
        t = next(t for t in d.tables if t.rows[0].cells[0].text.strip().endswith(".pdf"))
        docx_util.poner_texto_celda(t.rows[0].cells[0], "OTRO-PLANO.pdf")
        d.save(rutas["FAT"])
        hs = validador.validar_paquete(list(rutas.values()), con_pdf=False).hallazgos
        self.assertDetecta(hs, "P03", validador.ADVERTENCIA)

    def test_p04_componentes_distintos_entre_sat_y_fat(self):
        rutas = self.copia_paquete()
        d = docx.Document(rutas["FAT"])
        t = next(t for t in d.tables if t.rows[0].cells[0].text.strip() == "COMPONENTES DE HARDWARE")
        docx_util.poner_texto_celda(t.rows[1].cells[0], "RTAC SEL 3350")
        d.save(rutas["FAT"])
        hs = validador.validar_paquete(list(rutas.values()), con_pdf=False).hallazgos
        self.assertDetecta(hs, "P04", validador.ADVERTENCIA)

    def test_p05_anexo_referenciado_que_no_esta_en_la_entrega(self):
        rutas = self.copia_paquete()
        hs = validador.validar_paquete([rutas["SAT"], rutas["FAT"]], con_pdf=False).hallazgos
        self.assertDetecta(hs, "P05", validador.ADVERTENCIA)

    def test_el_informe_separa_bloqueantes_de_advertencias(self):
        rutas = self.copia_paquete()
        d = docx.Document(rutas["SAT"])
        poner(parrafo(d, "Tablero:"), "Tablero: {{X}}")
        poner(parrafo(d, "Realizar, de acuerdo"), "Verificacion de la tension.")
        d.save(rutas["SAT"])
        informe = validador.validar_paquete([rutas["SAT"]], con_pdf=False)
        self.assertFalse(informe.apto)
        self.assertTrue(informe.bloqueantes and informe.advertencias)
        self.assertIn("NO LISTO PARA ENTREGAR", informe.resumen())
        self.assertIn("No valida criterios técnicos", informe.a_texto())

    def test_cada_hallazgo_informa_archivo_apartado_descripcion_gravedad_y_tipo(self):
        d = docx.Document(BASE["rutas"]["SAT"])
        poner(parrafo(d, "Realizar, de acuerdo"), "Verificacion de la tension.")
        ruta = os.path.join(BASE["carpeta"], "x_" + os.path.basename(BASE["rutas"]["SAT"]))
        d.save(ruta)
        for h in validador.validar_documento(ruta):
            self.assertIn(h.gravedad, (validador.BLOQUEANTE, validador.ADVERTENCIA, validador.INFO))
            self.assertIn(h.tipo, (validador.FORMATO, validador.DOCUMENTAL, validador.CONSISTENCIA))
            self.assertTrue(h.archivo and h.descripcion and h.codigo)


class DatosPrevios(Base):
    def test_sin_documentos_ni_componentes_bloquea(self):
        hs = validador.validar_datos_previos(D.DATOS, [], [], D.TERMICAS, D.SENALES, D.COMANDOS, ("SAT", "FAT", "A1", "A2"))
        self.assertTrue({"D01", "D04"} <= self.codigos(hs, validador.BLOQUEANTE))

    def test_anexo_sin_datos_bloquea(self):
        hs = validador.validar_datos_previos(D.DATOS, D.DOCUMENTOS, D.COMPONENTES, [], [], [], ("A1", "A2"))
        self.assertTrue({"D05", "D06"} <= self.codigos(hs, validador.BLOQUEANTE))

    def test_los_anexos_no_exigen_componentes(self):
        hs = validador.validar_datos_previos(D.DATOS, D.DOCUMENTOS, [], D.TERMICAS, D.SENALES, D.COMANDOS, ("A1", "A2"))
        self.assertEqual(self.codigos(hs, validador.BLOQUEANTE), set())


if __name__ == "__main__":
    unittest.main(verbosity=2)
