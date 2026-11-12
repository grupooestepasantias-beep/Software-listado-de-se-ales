"""Correcciones a mano, guardar/abrir proyecto y exportación con carátula."""
import tempfile
import unittest
from pathlib import Path

import openpyxl

import desde_pdf
import libro
from modelo import Caratula

PDF = Path(__file__).resolve().parents[2] / "Ejemplos" / "ETAP-0325-ET-CT-PL-EF-6402_1.pdf"


@unittest.skipUnless(PDF.exists(), "falta el PDF de ejemplo")
class TestProyecto(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = libro.Libro()
        cls.L.agregar_pdf(PDF)
        cls.L.calcular()

    def setUp(self):
        self.L.datos.ediciones = {}

    def _fila(self, funcion="SEÑALIZACION"):
        proyecto, _, _ = self.L.proyecto()
        claves = desde_pdf.claves_de(proyecto)
        senales = [s for nv in proyecto.niveles for c in nv.campos for s in c.senales]
        i = next(i for i, s in enumerate(senales) if s.funcion.value == funcion and s.desc_scada)
        return claves[i], senales[i]

    def test_las_claves_de_fila_no_se_repiten(self):
        proyecto, _, _ = self.L.proyecto()
        claves = desde_pdf.claves_de(proyecto)
        self.assertEqual(len(claves), len(set(claves)))

    def test_correccion_a_mano_y_deshacer(self):
        clave, original = self._fila()
        self.L.editar(clave, "desc", "MI DESCRIPCION")
        self.L.editar(clave, "placa", "A9.9")
        _, nueva = self._fila()
        self.assertEqual((nueva.desc_scada, nueva.placa), ("MI DESCRIPCION", "A9.9"))
        self.L.deshacer_edicion(clave, "desc")
        self.L.deshacer_edicion(clave, "placa")
        _, vuelta = self._fila()
        self.assertEqual((vuelta.desc_scada, vuelta.placa), (original.desc_scada, original.placa))
        self.assertEqual(self.L.datos.ediciones, {})

    def test_la_correccion_sobrevive_a_recalcular(self):
        clave, _ = self._fila()
        self.L.editar(clave, "obs", "OBSERVACION PROPIA")
        self.L.calcular()
        _, s = self._fila()
        self.assertEqual(s.observaciones, "OBSERVACION PROPIA")

    def test_guardar_y_abrir_deja_todo_igual(self):
        clave, _ = self._fila()
        self.L.editar(clave, "desc", "GUARDADA")
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "p.json"
            self.L.guardar(ruta, Caratula(obra="OBRA X"))
            otro = libro.Libro()
            caratula, faltan = otro.abrir(ruta)
        self.assertEqual((faltan, caratula["obra"]), ([], "OBRA X"))
        self.assertEqual(otro.datos.ediciones, self.L.datos.ediciones)
        self.assertEqual([(f.tag, f.offset) for f in otro.filas], [(f.tag, f.offset) for f in self.L.filas])

    def test_abrir_avisa_de_un_pdf_que_ya_no_esta(self):
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "p.json"
            self.L.guardar(ruta)
            texto = ruta.read_text(encoding="utf-8").replace(str(PDF).replace("\\", "\\\\"), str(Path(t) / "no_esta.pdf").replace("\\", "\\\\"))
            ruta.write_text(texto, encoding="utf-8")
            otro = libro.Libro()
            _, faltan = otro.abrir(ruta)
        self.assertEqual(len(faltan), 1)
        self.assertEqual(otro.campos, [])

    def test_exportar_con_y_sin_caratula(self):
        with tempfile.TemporaryDirectory() as t:
            sin, con = Path(t) / "sin.xlsx", Path(t) / "con.xlsx"
            self.L.exportar(sin)
            self.L.exportar(con, Caratula(obra="OBRA X", titulo="LISTADO"))
            hojas_sin = openpyxl.load_workbook(sin).sheetnames
            wb = openpyxl.load_workbook(con)
        self.assertEqual(hojas_sin, ["EPEN"])
        self.assertEqual(len(wb.sheetnames), 2)
        ws = wb["EPEN"]
        self.assertTrue(ws.cell(6, 8).value)                  # el listado quedó en su hoja, con datos desde la fila 6
        self.assertEqual(ws.cell(6, 1).value, 1)              # ITEM
        self.assertIsNone(ws.cell(6, 16).value)               # el apartado UTR (P en adelante) no se exporta
        self.assertIsNone(ws.cell(6, 23).value)

    def test_una_descripcion_corregida_ya_no_sale_en_amarillo(self):
        proyecto, marcas, _ = self.L.proyecto()
        claves = desde_pdf.claves_de(proyecto)
        i = next((i for i, m in enumerate(marcas) if m), None)
        if i is None:
            self.skipTest("no hay descripciones en amarillo en este PDF")
        self.L.editar(claves[i], "desc", "ARREGLADA")
        _, marcas2, _ = self.L.proyecto()
        self.assertFalse(self.L.marcas(proyecto, marcas2)[i])


if __name__ == "__main__":
    unittest.main()
