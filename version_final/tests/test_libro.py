import unittest
from pathlib import Path

import desde_pdf
import libro
import numeracion as num

PDF = Path(__file__).resolve().parents[2] / "Ejemplos" / "ETAP-0325-ET-CT-PL-EF-6402_1.pdf"


def campo(prefijo, med=False):
    return num.Campo(prefijo, 10, [num.Senal(num.ALARMAS, "Interruptor 1 Resorte Descargado"),
                                   num.Senal(num.SENALIZACION, "Interruptor 1 Abierto/Cerrado", doble=True, comando=True,
                                             pares=("Interruptor 1 Abierto", "Interruptor 1 Cerrado"))],
                    mediciones=num.MEDICIONES_ETAP[:2] if med else (), clave=prefijo, numero=prefijo[1:], numero_pdf=prefijo[1:],
                    nivel_pdf="6,6KV", nivel="6,6KV")


class TestLibro(unittest.TestCase):
    def test_agregar_mantiene_lo_hecho_y_sigue_a_continuacion(self):
        L = libro.Libro()
        L.campos = [campo("101", True), campo("102", True)]
        L.calcular()
        antes = [(f.campo, f.tag, f.offset) for f in L.filas]
        L.campos.append(campo("103", True))
        L.datos.variable_inicial["103"] = 40
        L.calcular(agregar=True)
        self.assertEqual([(f.campo, f.tag, f.offset) for f in L.filas][:len(antes)], antes)
        nuevas = [f for f in L.filas[len(antes):] if f.campo == "103" and not f.hueco]
        self.assertTrue(nuevas[0].tag.startswith("103.40"))
        previos = [f.offset for f in L.filas[:len(antes)] if f.funcion != num.MEDICION]
        self.assertGreater(nuevas[0].offset, max(previos))
        self.assertEqual(L.pendientes(), [])

    def test_la_tension_define_el_primer_digito_y_cada_campo_su_variable(self):
        L = libro.Libro()
        L.campos = [campo("101"), campo("102")]
        L.datos.nivel["101"] = "33KV"                     # 33 kV -> 2
        L.datos.variable_inicial.update({"101": 5, "102": 30})
        L.calcular()
        tags = [f.tag for f in L.filas if f.tag and not f.hueco and f.funcion != "COMANDO"]
        self.assertEqual(tags[:2], ["201.051", "201.062C"])      # campo 01 de 33 kV, desde la variable 05
        self.assertTrue([t for t in tags if t.startswith("102.30")])  # campo 02 de 6,6 kV, desde la 30

    def test_recalcular_todo_renumera(self):
        L = libro.Libro()
        L.campos = [campo("101"), campo("102")]
        L.calcular()
        L.datos.offset_digital = 500
        L.calcular()
        self.assertEqual(min(f.offset for f in L.filas), 500)

    @unittest.skipUnless(PDF.exists(), "falta el PDF de ejemplo")
    def test_un_pdf_dos_veces_no_duplica_campos(self):
        L = libro.Libro()
        nuevos, repetidos = L.agregar_pdf(PDF)
        self.assertEqual((nuevos, repetidos), (["204", "205", "206"], []))
        self.assertEqual(L.agregar_pdf(PDF), ([], ["204", "205", "206"]))

    @unittest.skipUnless(PDF.exists(), "falta el PDF de ejemplo")
    def test_exporta_un_excel_con_h_a_o(self):
        import tempfile

        import openpyxl
        L = libro.Libro()
        L.agregar_pdf(PDF)
        L.calcular()
        with tempfile.TemporaryDirectory() as t:
            L.exportar(Path(t) / "x.xlsx")
            ws = openpyxl.load_workbook(Path(t) / "x.xlsx").active
        self.assertEqual(ws["H6"].value, "204.101")           # variable inicial 10 por defecto
        self.assertEqual(ws["I6"].value, 200)
        self.assertEqual(ws["A6"].value, 1)
        self.assertEqual(ws["B6"].value, "33KV")
        self.assertEqual(ws["D6"].value, "SEL-2241-33kV")
        self.assertTrue(ws["F6"].value)
        self.assertEqual(ws["E6"].value, "ALARMAS")
        self.assertEqual(ws["K6"].value, "NORMAL")


TDCI = Path(__file__).resolve().parents[3] / "EDESTE" / "TDCI" / "3-Funcional" / "USRE-01-19-SET-Ct-PL-Ad-0808_r4.pdf"


class TestColumnasUtr(unittest.TestCase):
    """Bloque UTR de la hoja: TIPO DE SEÑAL (P), PLACA (S), ENTRADA (T) y DESCRIPCION / OBSERVACIONES (W)."""

    @unittest.skipUnless(PDF.exists(), "falta el PDF de ejemplo")
    @unittest.skipUnless(desde_pdf.MOSTRAR_UTR, "el apartado UTR no se exporta (desde_pdf.MOSTRAR_UTR = False)")
    def test_senales_dobles_comandos_y_mediciones(self):
        import tempfile

        import openpyxl
        L = libro.Libro()
        L.agregar_pdf(PDF)
        L.calcular()
        with tempfile.TemporaryDirectory() as t:
            L.exportar(Path(t) / "x.xlsx")
            ws = openpyxl.load_workbook(Path(t) / "x.xlsx").active
        fila = {}
        fn = None
        for r in range(6, ws.max_row + 1):
            fn = ws.cell(r, 5).value or fn
            obs = ws.cell(r, 23).value
            if obs and ("Interruptor 25204" in obs or "TENSION CAMPO 04 33kV FASE R" in obs) and (fn, obs) not in fila:
                fila[(fn, obs)] = (ws.cell(r, 16).value, ws.cell(r, 19).value, ws.cell(r, 20).value)
        # cada estado de una señal doble lleva la entrada de su propio borne
        self.assertEqual(fila[("SEÑALIZACION", "Interruptor 25204 Abierto")][::2], ("DI", "2"))
        self.assertEqual(fila[("SEÑALIZACION", "Interruptor 25204 Cerrado")][::2], ("DI", "1"))
        # comando de dos salidas: 'a/b'; el plano no trae la placa: queda vacía (la app la pregunta)
        self.assertEqual(fila[("COMANDO", "Interruptor 25204 Apertura/Cierre")], ("DO", None, "9/10"))
        # medición del multimedidor: AI, sin placa ni entrada
        self.assertEqual(fila[("MEDICION", "TENSION CAMPO 04 33kV FASE R")], ("AI", "N/A", "N/A"))

    @unittest.skipUnless(TDCI.exists(), "falta el PDF del TDCI")
    def test_la_placa_sale_del_plano_y_se_puede_cambiar(self):
        L = libro.Libro()
        L.agregar_pdf(TDCI)
        self.assertEqual([m["placa_pdf"] for m in L.modulos()], ["A1.4", "A1.5", "A1.6"])
        L.datos.placas[L.modulos()[0]["clave"]] = "A9.9"          # lo que escribe el usuario manda sobre el plano
        L.calcular()
        proyecto, _, _ = L.proyecto()
        placas = [s.placa for nv in proyecto.niveles for c in nv.campos for s in c.senales if s.placa]
        self.assertEqual((placas[0], placas[-1]), ("A9.9", "A1.6"))

    @unittest.skipUnless(PDF.exists(), "falta el PDF de ejemplo")
    def test_reservas_al_final_separadas_por_nivel_y_campo(self):
        L = libro.Libro()
        L.agregar_pdf(PDF)
        L.calcular()
        proyecto, _, _ = L.proyecto()
        finales = proyecto.niveles[-1]
        self.assertEqual(finales.nombre, "33KV")                   # el nivel va en su primera fila, no en un bloque "RESERVAS"
        self.assertTrue(all(c.descripcion for c in finales.campos))
        self.assertTrue(all(s.es_reserva and s.observaciones == "RESERVA" for c in finales.campos for s in c.senales))


if __name__ == "__main__":
    unittest.main()
