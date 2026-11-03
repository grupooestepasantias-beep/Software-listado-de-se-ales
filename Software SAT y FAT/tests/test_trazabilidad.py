"""El generador no deja pasar datos sin respaldo en los PDF. Usa los planos reales de La Paz solo como lectura."""
import csv
import os
import shutil
import sys
import tempfile
import unittest
import zipfile

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import docx

import extraer_pdf
import generador_sat as g
import validador

ING = r"\\192.168.15.120\PasantiasMM\la paz\Ing"
EF = os.path.join(ING, "ET-LP-0205-ET-CT-PL-EF-1006_rC.pdf")
TP = os.path.join(ING, "ET-LP-0205-ET-CT-PL-TP-1006_rC.pdf")
CONFIRMA_PORTADA = {("PDF06", os.path.basename(TP))}


@unittest.skipUnless(os.path.exists(EF) and os.path.exists(TP), "no hay acceso a los planos de La Paz")
class Respaldo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.pdfs = {os.path.basename(EF): EF, os.path.basename(TP): TP}
        cls.datos = dict(CLIENTE="EDESTE", NRO_OBRA="205", OBRA="205-EDESTE_Reemplazo RTUs", UBICACION="La Paz, Mendoza",
                         TIPO_TABLERO="Tablero de Control", NOMBRE="La Paz", FECHA_FAT="20/10/2026", FECHA_SAT="02/11/2026",
                         REVISION="A")
        cls.docs = [(n, g.deducir_descripcion(n, "Tablero de Control", "66/13,2 KV")) for n in cls.pdfs]
        cls.comps = [("RTAC SEL 2241", "")] + [("MÓDULO DI SEL 2244-2", "")] * 10 + [("MÓDULO DO SEL 2244-3", "")] * 5
        s, c, _ = extraer_pdf.extraer_senales(EF)
        cls.senales = [("-Q1" if n == "Falla Alimentación General" else b, n) for b, n in s]  # borne que el plano no da
        cls.comandos = c
        cls.termicas = extraer_pdf.aplicar_sugerencias(extraer_pdf.extraer_termicas(EF, TP))

    def revisar(self, incluir=("FAT_A1", "FAT_A2"), **cambios):
        a = dict(datos=self.datos, documentos=self.docs, componentes=self.comps, termicas=self.termicas,
                 senales=self.senales, comandos=self.comandos, pdfs=self.pdfs, confirmados=CONFIRMA_PORTADA)
        a.update(cambios)
        return g.revisar_previos(a["datos"], a["documentos"], a["componentes"], a["termicas"], a["senales"], a["comandos"],
                                 incluir, a["pdfs"], True, a["confirmados"])

    def bloqueantes(self, hs):
        return {h.codigo for h in hs if h.gravedad == validador.BLOQUEANTE}

    def test_datos_correctos_no_tienen_bloqueantes(self):
        self.assertEqual(self.bloqueantes(self.revisar()), set())

    def test_la_portada_inconsistente_del_plano_se_detecta_y_se_puede_confirmar(self):
        hs = self.revisar(confirmados=set())
        h = next(h for h in hs if h.codigo == "PDF06")
        self.assertTrue(h.confirmable and h.gravedad == validador.BLOQUEANTE)
        self.assertIn("NUEVA CALIFORNIA", h.descripcion)

    def test_nombre_de_senal_distinto_al_plano_bloquea(self):
        s = list(self.senales)
        s[0] = (s[0][0], s[0][1] + " modificada")
        self.assertIn("R10", self.bloqueantes(self.revisar(senales=s)))

    def test_senal_inventada_bloquea(self):
        self.assertIn("R11", self.bloqueantes(self.revisar(senales=self.senales + [("-XFI9/1", "Señal inventada")])))

    def test_senal_faltante_bloquea(self):
        self.assertIn("R13", self.bloqueantes(self.revisar(senales=self.senales[:-1])))

    def test_comando_inventado_bloquea(self):
        self.assertIn("R11", self.bloqueantes(self.revisar(comandos=self.comandos + [("XF99-1", "Comando inventado")])))

    def test_termica_sin_respaldo_o_faltante_bloquea(self):
        self.assertIn("R20", self.bloqueantes(self.revisar(termicas=self.termicas + [("220 VCA", "Inventada", "Q999")])))
        self.assertIn("R21", self.bloqueantes(self.revisar(termicas=self.termicas[1:])))

    def test_tension_que_contradice_al_plano_bloquea(self):
        t = [(("220 VCA" if q == "Q1" else gr), d, q) for gr, d, q in self.termicas]  # el plano dice 110 VCC
        self.assertIn("R22", self.bloqueantes(self.revisar(termicas=t)))

    def test_termicas_sin_tension_o_descripcion_bloquean_hasta_completarlas(self):
        crudas = extraer_pdf.extraer_termicas(EF, TP)
        self.assertIn("D09", self.bloqueantes(self.revisar(termicas=crudas)))

    def test_senal_sin_borne_bloquea_hasta_completarla(self):
        crudas = extraer_pdf.extraer_senales(EF)[0]
        self.assertIn("D08", self.bloqueantes(self.revisar(senales=crudas)))

    def test_documento_de_referencia_sin_pdf_cargado_bloquea(self):
        self.assertIn("D10", self.bloqueantes(self.revisar(pdfs={})))

    def test_obra_o_estacion_equivocada_bloquea(self):
        self.assertIn("PDF07", {h.codigo for h in self.revisar(datos=dict(self.datos, NRO_OBRA="999"))})
        self.assertIn("PDF05", {h.codigo for h in self.revisar(datos=dict(self.datos, NOMBRE="Santa Rosa"))})

    def test_revisiones_incompatibles_entre_planos(self):
        with tempfile.TemporaryDirectory() as tmp:
            tp_b = shutil.copy(TP, os.path.join(tmp, "ET-LP-0205-ET-CT-PL-TP-1006_rB.pdf"))
            pdfs = {os.path.basename(EF): EF, os.path.basename(tp_b): tp_b}
            hs = extraer_pdf.validar_planos(list(pdfs.values()), self.datos)
        self.assertIn("PDF03", {h.codigo for h in hs})

    def test_no_se_genera_nada_si_hay_pendientes(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(g.DatosIncompletos):
                g.generar_paquete(self.datos, self.docs, self.comps, extraer_pdf.extraer_termicas(EF, TP), self.senales,
                                  self.comandos, tmp, pdfs=self.pdfs, confirmados=CONFIRMA_PORTADA)
            self.assertEqual(os.listdir(tmp), [])


@unittest.skipUnless(os.path.exists(EF) and os.path.exists(TP), "no hay acceso a los planos de La Paz")
class PaqueteReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        b = Respaldo
        b.setUpClass()
        cls.tmp = tempfile.mkdtemp(prefix="sat_real_")
        cls.r = g.generar_paquete(b.datos, b.docs, b.comps, b.termicas, b.senales, b.comandos, cls.tmp,
                                  pdfs=b.pdfs, confirmados=CONFIRMA_PORTADA)
        cls.b = b

    @classmethod
    def tearDownClass(cls):
        shutil.rmtree(cls.tmp, ignore_errors=True)

    def test_listo_para_entregar(self):
        self.assertEqual(self.r["estado"], "LISTO PARA ENTREGAR", self.r["informe"].a_texto())

    def test_seis_word_seis_pdf_y_zip_con_todo(self):
        self.assertEqual(len(self.r["archivos"]), 4)  # SAT (un solo archivo) + FAT con sus 2 anexos
        self.assertEqual(len(self.r["pdfs"]), 4)
        nombres = set(zipfile.ZipFile(self.r["zip"]).namelist())
        for a in self.r["archivos"] + self.r["pdfs"] + [self.r["trazabilidad"]]:
            self.assertIn(os.path.basename(a), nombres)
        self.assertFalse(os.path.basename(self.r["zip"]).startswith("BORRADOR"))

    def test_nombres_con_cliente_obra_tablero_y_tipo(self):
        for a in self.r["archivos"]:
            n = os.path.basename(a)
            self.assertTrue(n.startswith("EDESTE - Obra 205 - Tablero de Control La Paz - Protocolo "), n)
            self.assertRegex(n, r"Protocolo (SAT - rA|FAT - rA( - Anexo [12])?)\.docx$")

    def test_sat_y_fat_son_independientes_y_cada_uno_lleva_su_fecha(self):
        for a in self.r["archivos"]:
            d = validador.Doc(a)
            fam = d.tipo.split("_")[0]
            self.assertEqual(d.portada["fecha"], "02/11/2026" if fam == "SAT" else "20/10/2026", a)
            self.assertEqual(d.portada["ubicacion"], "La Paz, Mendoza")
            txt = d.texto_completo()
            self.assertNotRegex(txt, r"\bFAT\b" if fam == "SAT" else r"\bSAT\b")

    def test_las_213_senales_y_28_comandos_coinciden_con_el_plano(self):
        d = validador.Doc(next(a for a in self.r["archivos"] if a.endswith("Protocolo FAT - rA - Anexo 2.docx")))
        filas = [f for f in validador._filas(d.tabla("senales")) if f[0].startswith(("-XFI", "-Q"))]
        self.assertEqual(len(filas), 213)
        self.assertEqual([(f[0], f[1]) for f in filas], self.b.senales)
        cmd = [f for t in (validador._anidadas(d.tabla("comandos")) or [d.tabla("comandos")]) for f in validador._filas(t) if f[0].startswith("XF")]
        self.assertEqual(len(cmd), 28)

    def test_anexo_1_es_un_procedimiento_ordenado(self):
        d = validador.Doc(next(a for a in self.r["archivos"] if a.endswith("Protocolo FAT - rA - Anexo 1.docx")))
        filas = validador._filas(d.tabla("energizado"))
        self.assertEqual(filas[0], ["Paso", "Circuito (térmica)", "Tensión esperada", "Tensión medida",
                                    "Indicaciones observadas", "Resultado"])
        self.assertEqual([f[0] for f in filas[1:]], [str(i) for i in range(1, 9)])
        titulos = [t for t, _, _ in d.parrafos]
        for s in ("Condiciones previas", "Secuencia de energización", "Criterio de aceptación"):
            self.assertIn(s, titulos)

    def test_trazabilidad_registra_origen_de_cada_dato(self):
        with open(self.r["trazabilidad"], encoding="utf-8-sig") as f:
            filas = list(csv.reader(f, delimiter=";"))[1:]
        self.assertEqual(len(filas), 213 + 28 + 8)
        manuales = [f for f in filas if "MANUAL" in f[9] or "a mano" in f[9]]
        self.assertTrue(any(f[2] == "Falla Alimentación General" and "a mano" in f[9] for f in manuales))
        self.assertTrue(all(f[6] for f in filas if f[0] == "Señal DI" and "a mano" not in f[9]))

    def test_word_editable_abre_con_python_docx(self):
        for a in self.r["archivos"]:
            self.assertGreater(len(docx.Document(a).paragraphs), 10)


if __name__ == "__main__":
    unittest.main(verbosity=2)
