"""Etapa 2: formatos de salida (completo y reducido) desde la misma base."""
import copy
import tempfile
import unittest
from pathlib import Path

import openpyxl
from openpyxl.utils import get_column_letter

import formatos
import libro
from formatos.escritor import escribir
from modelo import Caratula

PDF_6402 = Path(__file__).resolve().parents[2] / "Ejemplos" / "ETAP-0325-ET-CT-PL-EF-6402_1.pdf"
OFICIAL = Path(__file__).resolve().parents[3] / "senillosa" / "USRE-0119-SET-C-T-LI-Ls-0744_rD_DV_2.xlsx"


class TestFormatos(unittest.TestCase):
    def test_los_formatos_disponibles(self):
        self.assertEqual(formatos.ids(), ["completo", "reducido"])
        completo = formatos.cargar("completo")
        self.assertEqual([c["letra"] for c in completo.columnas], [get_column_letter(i) for i in range(1, 29)])
        self.assertEqual(formatos.cargar("reducido").ultima_columna, "O")

    def test_un_formato_con_un_campo_inexistente_se_rechaza(self):
        with self.assertRaises(formatos.FormatoInvalido):
            formatos.cargar("no_existe")


def _celdas(ws, hasta):
    return [[ws.cell(r, c).value for c in range(1, hasta + 1)] for r in range(1, ws.max_row + 1)]


@unittest.skipUnless(PDF_6402.exists(), "falta el PDF de ejemplo")
class TestSalidas(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = libro.Libro()
        cls.L.agregar_pdf(PDF_6402)
        cls.L.calcular()
        cls.db = cls.L.base()
        cls.dir = tempfile.TemporaryDirectory()
        d = Path(cls.dir.name)
        cls.L.exportar(d / "directo.xlsx")
        cls.n_red = cls.L.exportar_formato("reducido", d / "reducido.xlsx", db=cls.db)
        cls.n_com = cls.L.exportar_formato("completo", d / "completo.xlsx", db=cls.db)
        cls.directo = openpyxl.load_workbook(d / "directo.xlsx").active
        cls.red = openpyxl.load_workbook(d / "reducido.xlsx").active
        cls.com = openpyxl.load_workbook(d / "completo.xlsx").active

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_el_reducido_es_identico_al_excel_de_siempre(self):
        a, b = self.directo, self.red
        self.assertEqual(_celdas(a, 15), _celdas(b, 15))
        self.assertEqual(sorted(map(str, a.merged_cells.ranges)), sorted(map(str, b.merged_cells.ranges)))
        self.assertEqual([a.cell(r, 10).fill.fgColor.rgb for r in range(1, a.max_row + 1)],
                         [b.cell(r, 10).fill.fgColor.rgb for r in range(1, b.max_row + 1)])
        self.assertEqual({k: v.width for k, v in a.column_dimensions.items() if k <= "O" and len(k) == 1},
                         {k: v.width for k, v in b.column_dimensions.items() if k <= "O" and len(k) == 1})
        self.assertEqual([a.row_dimensions[r].height for r in range(1, 12)], [b.row_dimensions[r].height for r in range(1, 12)])
        self.assertEqual((a.auto_filter.ref, a.print_area, a.print_title_rows), (b.auto_filter.ref, b.print_area, b.print_title_rows))
        self.assertEqual((a.page_setup.orientation, a.page_setup.paperSize), (b.page_setup.orientation, b.page_setup.paperSize))
        self.assertEqual(len(a.conditional_formatting), len(b.conditional_formatting))
        self.assertEqual(self.n_red, self.L.exportar(Path(self.dir.name) / "otra.xlsx"))

    def test_el_completo_tiene_los_titulos_y_el_formato_del_oficial(self):
        if not OFICIAL.exists():
            self.skipTest("falta el Excel oficial")
        of = openpyxl.load_workbook(OFICIAL)["EPEN"]
        c = self.com
        self.assertEqual(_celdas(c, 28)[:4], _celdas(of, 28)[:4])                         # títulos, 4 filas
        self.assertEqual(sorted(str(m) for m in c.merged_cells.ranges if m.min_row <= 4),
                         sorted(str(m) for m in of.merged_cells.ranges if m.min_row <= 4))
        self.assertEqual({k: of.column_dimensions[k].width for k in map(get_column_letter, range(1, 29))
                          if of.column_dimensions[k].width},
                         {k: c.column_dimensions[k].width for k in map(get_column_letter, range(1, 29))
                          if of.column_dimensions[k].width})
        self.assertEqual([of.row_dimensions[r].height for r in range(1, 5)], [c.row_dimensions[r].height for r in range(1, 5)])
        self.assertEqual((c.print_title_rows, c.page_setup.orientation), (of.print_title_rows, of.page_setup.orientation))
        self.assertEqual(c["A2"].font.b, of["A2"].font.b)
        self.assertEqual(c["F3"].fill.fgColor.rgb, of["F3"].fill.fgColor.rgb)

    def test_el_completo_lleva_los_mismos_datos_que_el_reducido(self):
        # reducido: A-O = item, nivel, descrip, ctl, funcion, tag hmi, desc hmi, tag, offset, desc scada, estados, unidad
        # completo: lo mismo con la columna G (EXTERNAL NAME) vacía, así que desde la H todo corre una columna
        red = [[self.red.cell(r, c).value for c in range(1, 16)] for r in range(6, self.red.max_row + 1)]
        com = [[self.com.cell(r, c).value for c in range(1, 17)] for r in range(5, self.com.max_row + 1)]
        self.assertEqual(len(red), len(com))
        self.assertEqual([f[:6] for f in red], [f[:6] for f in com])
        self.assertEqual([f[6:15] for f in red], [f[7:16] for f in com])

    def test_externalname_vacio_conexionado_vacio_y_dnp_igual_al_offset(self):
        c = self.com
        filas = range(5, c.max_row + 1)
        self.assertTrue(all(c.cell(r, 7).value is None for r in filas))                   # G: EXTERNAL NAME
        for letra in ("R", "V", "W", "Y", "Z"):                                           # tablero, bornera, borne
            self.assertTrue(all(c[f"{letra}{r}"].value is None for r in filas), letra)
        self.assertEqual([c.cell(r, 27).value for r in filas], [c.cell(r, 10).value for r in filas])   # AA = J
        self.assertTrue(any(c.cell(r, 27).value is not None for r in filas))

    def test_el_completo_no_fija_paneles(self):
        self.assertIsNone(self.com.freeze_panes)

    def test_el_completo_marca_el_amarillo_en_la_desc_scada(self):
        self.assertEqual(self.n_com, self.n_red)
        amarillas = [r for r in range(5, self.com.max_row + 1) if self.com.cell(r, 11).fill.fgColor.rgb == "00FFFF00"]
        self.assertEqual(len(amarillas), self.n_com)

    def test_agregar_o_reordenar_columnas_no_requiere_tocar_el_programa(self):
        f = copy.deepcopy(formatos.cargar("reducido"))
        f.columnas = [{"letra": "A", "campo": "tag_scada"}, {"letra": "B", "campo": "offset"},
                      {"letra": "C", "campo": "indice_dnp"}]
        f.ultima_columna = "C"
        with tempfile.TemporaryDirectory() as t:
            escribir(self.db, f, Path(t) / "x.xlsx", self.L.perfil)
            ws = openpyxl.load_workbook(Path(t) / "x.xlsx").active
        primera = next(b for b in self.db.senales if b.tag_scada not in ("", "N/A") and not b.es_hueco)
        valores = [[ws.cell(r, c).value for c in (1, 2, 3)] for r in range(6, ws.max_row + 1)]
        self.assertIn([primera.tag_scada, primera.offset, primera.indice_dnp], valores)

    def test_con_caratula_el_libro_lleva_dos_hojas_en_cualquier_formato(self):
        for fid in ("reducido", "completo"):
            with tempfile.TemporaryDirectory() as t:
                self.L.exportar_formato(fid, Path(t) / "x.xlsx", Caratula(obra="OBRA X"), db=self.db)
                self.assertEqual(openpyxl.load_workbook(Path(t) / "x.xlsx").sheetnames, ["Caratula", "EPEN"], fid)

    def test_elegir_formato_no_cambia_la_base(self):
        antes = self.db.a_dict()
        self.L.exportar_formato("reducido", Path(self.dir.name) / "a.xlsx", db=self.db)
        self.L.exportar_formato("completo", Path(self.dir.name) / "b.xlsx", db=self.db)
        self.assertEqual(self.db.a_dict(), antes)


if __name__ == "__main__":
    unittest.main()
