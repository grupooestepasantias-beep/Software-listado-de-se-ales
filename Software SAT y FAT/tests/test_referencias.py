"""Comparación con los documentos de referencia de la red (se omite si la red no está disponible).

Los PDF de La Paz y los protocolos de Nueva California se usan SOLO COMO ENTRADA DE LECTURA para
comparar; nada se escribe en esas carpetas.
"""
import os
import re
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import docx
from docx.oxml.ns import qn

import datos_prueba as D
import extraer_pdf
import generador_sat as g

RED = r"\\192.168.15.101\Archivos\PasantiasMM\la paz"
EF = RED + r"\Ing\ET-LP-0205-ET-CT-PL-EF-1006_rC.pdf"
TP = RED + r"\Ing\ET-LP-0205-ET-CT-PL-TP-1006_rC.pdf"
NC_SAT = RED + r"\SAT\Protocolo de ensayo SAT - Nueva California.docx"
LP_A2 = RED + r"\FAT\Protocolo de ensayo FAT - La Paz Anexo2.docx"
LP_A1 = RED + r"\FAT\Protocolo de ensayo FAT - La Paz Anexo1.docx"


def norm(t):
    return re.sub(r"[^a-z0-9áéíóúñü]+", " ", t.casefold()).strip()


def hay(*rutas):
    return all(os.path.exists(r) for r in rutas)


@unittest.skipUnless(hay(EF, TP, LP_A2, LP_A1), "no hay acceso a los documentos de La Paz en la red")
class ExtraccionContraFATdeLaPaz(unittest.TestCase):
    """El FAT de La Paz hecho a mano es la referencia de los bornes del Anexo 1 y 2."""

    @classmethod
    def setUpClass(cls):
        cls.senales, cls.comandos, cls.avisos = extraer_pdf.extraer_senales(EF)
        cls.termicas = extraer_pdf.extraer_termicas(TP)
        d = docx.Document(LP_A2)
        cls.ref_bornes = []
        for t in d.tables[1].rows:
            c = [x.text.strip() for x in t.cells]
            if c[0].startswith("-XFI"):
                cls.ref_bornes.append(c[0])
        cls.ref_comandos = []
        for tbl in d.element.body.iter(qn("w:tbl")):
            for tr in tbl.findall(qn("w:tr")):
                celdas = ["".join(x.text or "" for x in tc.iter(qn("w:t"))).strip() for tc in tr.findall(qn("w:tc"))]
                if celdas and re.match(r"^XF0\d-\d+$", celdas[0]):
                    cls.ref_comandos.append(celdas[0])

    def test_cantidades_esperadas_del_plano_rC(self):
        self.assertEqual((len(self.senales), len(self.comandos), len(self.termicas)), (213, 28, 8))

    # Bornes del FAT de La Paz (hecho sobre el plano rB) que el plano rC ya no tiene como señal:
    # -XFI1/42..45 (seccionadores 229L02/229B02/229B01 que rC quitó) y -XFI3/40, -XFI3/80 (hoy "Reserva").
    # No es un error de lectura: se verificó contra el texto del plano. Si cambia esta lista, hay que revisarla.
    BORNES_QUE_RC_YA_NO_TIENE = ["-XFI1/42", "-XFI1/43", "-XFI1/44", "-XFI1/45", "-XFI3/40", "-XFI3/80"]

    def test_los_bornes_del_fat_de_referencia_estan_en_los_leidos(self):
        leidos = {b for b, _ in self.senales}
        faltan = [b for b in self.ref_bornes if b not in leidos]
        self.assertEqual(faltan, self.BORNES_QUE_RC_YA_NO_TIENE)

    def test_los_comandos_del_fat_de_referencia_estan_en_los_leidos(self):
        leidos = {b for b, _ in self.comandos}
        self.assertTrue({"XF01-2", "XF01-3", "XF01-5", "XF01-6"} <= leidos)
        faltan = [b for b in self.ref_comandos if b not in leidos]
        self.assertEqual(faltan, [], f"comandos del FAT de La Paz que no se leyeron: {faltan}")

    def test_borne_y_nombre_de_las_primeras_entradas(self):
        primeras = dict(self.senales)
        self.assertEqual(primeras["-XFI1/1"], "Interruptor 35201 en Local")
        self.assertEqual(primeras["-XFI1/3"], "Interruptor 35201 Abierto")
        self.assertEqual(primeras["-XFI1/4"], "Interruptor 35201 Cerrado")

    def test_no_se_cargan_reservas_ni_comunes(self):
        for _, nombre in self.senales + self.comandos:
            self.assertFalse(re.match(r"(?i)^(reserva|negativo|positivo)", nombre), nombre)

    def test_no_hay_bornes_duplicados(self):
        bornes = [b for b, _ in self.senales if b and not b.startswith("(")]
        self.assertEqual(len(bornes), len(set(bornes)))

    def test_lo_que_no_tiene_borne_queda_senalado(self):
        sin = [n for b, n in self.senales if not b or b.startswith("(")]
        self.assertEqual(sin, ["Falla Alimentación General"])
        self.assertTrue(any("no tiene borne" in a for a in self.avisos))

    def test_termicas_del_plano(self):
        self.assertEqual([q for _, _, q in self.termicas], ["Q220", "Q221", "Q222", "Q223", "Q1", "QS", "Q2", "Q3"])

    def test_el_anexo_1_de_referencia_tiene_las_mismas_termicas_salvo_las_que_no_estan_en_el_plano(self):
        d = docx.Document(LP_A1)
        txt = " ".join("".join(x.text or "" for x in p.iter(qn("w:t"))) for p in d.element.body.iter(qn("w:p")))
        ref = set(re.findall(r"–(Q\w+)", txt))
        leidas = {q for _, _, q in self.termicas}
        self.assertEqual(leidas - ref, set(), "térmicas leídas que el FAT de referencia no tenía")
        self.assertEqual(ref - leidas, {"Q224", "Q4"}, "las únicas térmicas del FAT viejo ausentes del plano rC")

    def test_pdf_inexistente_o_no_pdf_da_error_no_cuelgue(self):
        with self.assertRaises(Exception):
            extraer_pdf.extraer_senales(r"C:\no_existe.pdf")


@unittest.skipUnless(hay(NC_SAT), "no hay acceso al SAT de Nueva California en la red")
class ContraNuevaCalifornia(unittest.TestCase):
    ESPECIFICAS = ("TABLERO DE CONTROL", "Tablero:", "Nota 1", "Nota 2", "Para la correcta identificación")

    @classmethod
    def setUpClass(cls):
        import tempfile
        cls.tmp = tempfile.mkdtemp(prefix="sat_nc_")
        cls.ruta = g.generar(D.DATOS, D.DOCUMENTOS, D.COMPONENTES, cls.tmp, tipo="SAT")
        cls.nc = docx.Document(NC_SAT)
        cls.nuestro = docx.Document(cls.ruta)

    @classmethod
    def tearDownClass(cls):
        import shutil
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def prosa(d):
        return [p.text.strip() for p in d.paragraphs
                if len(p.text.strip()) > 45 and "...." not in p.text and "…" not in p.text
                and p.style.style_id not in ("TDC1", "TDC2", "TDC3")]

    def test_la_redaccion_fija_coincide_con_la_de_nueva_california(self):
        nuestras = {norm(t) for t in self.prosa(self.nuestro)}
        faltan = []
        for t in self.prosa(self.nc):
            if any(e in t for e in self.ESPECIFICAS) or "ensayos en fábrica" in t or re.match(r"^3\.\d", t):
                continue  # datos del proyecto, anexos (van aparte) y títulos
            if norm(t) not in nuestras:
                faltan.append(t[:90])
        self.assertEqual(faltan, [], "redacción de Nueva California que el generador no reproduce")

    def test_las_secciones_del_cuerpo_son_las_mismas(self):
        def titulos(d):
            salida = []
            for p in d.paragraphs:
                t = p.text.strip()
                if "...." in t or p.style.style_id in ("TDC1", "TDC2", "TDC3") or t.upper().startswith("ANEXO"):
                    continue
                if p.style.style_id == "Ttulo1" or re.match(r"^\d\.\d(\.\d)?\.?\s", t):
                    salida.append(norm(re.sub(r"^\d+(\.\d+)*\.?\s*", "", t))[:40])
            return [s for s in salida if s]
        nc = [t for t in titulos(self.nc) if t != "contenido"]
        # En Nueva California quedó suelta una línea del índice viejo ("Prueba de funcionamiento de gráfica,
        # registro de alarmas") que se cuenta como título: no es un apartado del cuerpo.
        nc = [t for t in nc if not t.startswith("prueba de funcionamiento de gráfica regi")]
        nuestro = [t for t in titulos(self.nuestro) if t != "contenido"]
        self.assertEqual(set(nuestro), set(nc))
        self.assertEqual([t for t in nuestro if t != "observaciones"],
                         [t for t in dict.fromkeys(nc) if t != "observaciones"], "mismo orden de los apartados")

    def test_el_indice_de_nueva_california_no_coincide_con_su_cuerpo_y_el_generado_si(self):
        """El índice de Nueva California lista 3.2 Propiedades dieléctricas y 3.3 Ensayo punto a punto,
        que su cuerpo no tiene. El generado construye el índice desde el cuerpo, así que no puede divergir."""
        txt_nc = " ".join(p.text for p in self.nc.paragraphs).casefold()
        self.assertIn("propiedades dieléctricas", txt_nc)  # aparece solo en su índice escrito a mano
        self.assertEqual(sum("propiedades dieléctricas" in p.text.casefold() for p in self.nc.paragraphs), 1)
        self.assertNotIn("propiedades dieléctricas", " ".join(p.text for p in self.nuestro.paragraphs).casefold())

    def test_tablas_del_cuerpo_en_el_mismo_orden(self):
        def roles(d):
            salida = []
            for t in d.tables:
                primera = t.rows[0].cells[0].text.strip()
                if primera.startswith(("ENERGIZACIÓN", "BORNE", "Comandos")) or "ENERGIZACIÓN" in t._tbl.xml:
                    break
                if primera.lower().endswith(".pdf") or primera.startswith("ETNC"):
                    salida.append("referencias")
                elif primera.startswith("COMPONENTES"):
                    salida.append("componentes")
                elif primera.startswith("Por Grupo Oeste"):
                    salida.append("firma")
                elif primera.startswith(("Verificación anexo", "Verificación del Anexo")):
                    continue  # recuadros de verificación: convención de Santa Rosa (no están en Nueva California)
                else:
                    salida.append("verificaciones")
            return salida
        self.assertEqual(roles(self.nuestro), roles(self.nc))

    def test_diferencia_conocida_en_fabrica_vs_en_sitio(self):
        """No se corrige solo: queda documentada para que el responsable la resuelva."""
        nc_txt = " ".join(p.text for p in self.nc.paragraphs)
        self.assertIn("protocolo de ensayos en fábrica", nc_txt)
        nuestro_txt = " ".join(p.text for p in self.nuestro.paragraphs)
        self.assertIn("protocolo de ensayos en sitio", nuestro_txt)


ARROYITO = r"\\192.168.15.101\Archivos\PasantiasMM\EDESTE\Funcional\USRE-01-19-ET-El-PL-Ef-1102_r2.pdf"


@unittest.skipUnless(hay(ARROYITO), "no hay acceso al plano funcional de EDESTE/Arroyito")
class PlanoConHojaResumenDeModulos(unittest.TestCase):
    """Formato sin hojas DETALLE MODULO ni bornes -XFI: los nombres salen de la hoja de módulos, el elemento no se lee."""

    @classmethod
    def setUpClass(cls):
        cls.s, cls.c, cls.p = extraer_pdf.leer_funcional(ARROYITO)

    def test_lee_nombres_de_senales_y_comandos_sin_reservas_ni_comunes(self):
        self.assertEqual((len(self.s), len(self.c)), (32, 4))
        nombres = [x.nombre for x in self.s + self.c]
        self.assertFalse([n for n in nombres if re.match(r"(?i)(reserva|com[uú]n|positivo)", n)])
        self.assertIn("Interruptor 252-03 Abierto", nombres)
        self.assertEqual(nombres.count("Disparo General"), 2)

    def test_el_elemento_no_se_inventa_y_se_avisa(self):
        self.assertTrue(all(not x.borne for x in self.s + self.c))
        self.assertIn("S06", {h.codigo for h in self.p})
        self.assertTrue(self.s[0].tupla()[0].startswith("(ver hoja 29"))

    def test_cuenta_los_modulos_del_plano(self):
        self.assertEqual(extraer_pdf.contar_modulos(ARROYITO), (2, 1))

    def test_nombres_repetidos_se_completan_a_mano_sin_falso_faltante(self):
        manual = [(f"-K{i}", x.nombre) for i, x in enumerate(self.s)]  # bornes de prueba, no son datos reales
        hs = extraer_pdf.comparar_con_pdf(manual, self.s, "Señales")
        self.assertEqual([h.codigo for h in hs if h.gravedad == "BLOQUEANTE"], [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
