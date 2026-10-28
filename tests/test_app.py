import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import excel_writer
import perfiles
from app import validacion as v

try:
    import tkinter as tk
except ImportError:
    tk = None


def _datos_ok() -> dict:
    d = v.datos_vacios()
    d.update(cliente="EPEN", obra="LAT 132 kV", titulo="ETAP - LISTADO DE SEÑALES",
             numero_documento="ETAP-0722-ET-CT-MC-LI-6209", item_inicial="1",
             offsets={"DI": "200", "AI": "200", "DO": "0", "AO": "0"},
             referencias=[("ETAP-0722-ET-CT-PL-EF-6106", "Esquema"), ("", "")],
             revisiones=[{"rev": "0", "fecha": "21/04/2025", "descripcion": "APC", "proyecto": "DV",
                          "revisor": "GG", "aprobador": "ME"}])
    return d


class TestValidacion(unittest.TestCase):
    def test_formulario_valido(self):
        self.assertEqual(v.validar(_datos_ok(), 14, 4, 20), [])

    def test_nada_es_obligatorio_por_ahora(self):
        d = v.datos_vacios()  # ITEM arranca en 1; la carátula y los OFFSET (SCADA) se completan después
        self.assertEqual(v.validar(d, 14, 4, 20), [])
        d["item_inicial"] = ""  # vacío tampoco bloquea: se toma 1
        self.assertEqual(v.validar(d, 14, 4, 20), [])
        self.assertEqual(v.a_proyecto(d, "EPEN").item_inicial, 1)

    def test_item_no_numerico_o_negativo(self):
        d = _datos_ok()
        d["item_inicial"] = "-3"
        self.assertTrue(any("ITEM" in m for m in v.validar(d, 14, 4, 20)))
        d["item_inicial"] = "abc"
        self.assertTrue(any("ITEM" in m for m in v.validar(d, 14, 4, 20)))

    def test_largo_documento(self):
        d = _datos_ok()
        d["numero_documento"] = "ETAP-0722"  # más corto: permitido
        self.assertEqual(v.validar(d, 14, 4, 20), [])
        d["numero_documento"] = "ETAP-0722-ET-CT-MC-LI-62099"  # 21 caracteres sin guiones
        self.assertTrue(any("Número de documento" in m for m in v.validar(d, 14, 4, 20)))

    def test_limites_y_filas_vacias(self):
        d = _datos_ok()
        d["referencias"] = [(f"P{i}", "x") for i in range(15)]
        self.assertTrue(any("referencias" in m for m in v.validar(d, 14, 4, 20)))
        d["referencias"] = [("", ""), ("", "")]  # filas vacías no cuentan
        self.assertEqual(v.validar(d, 14, 4, 20), [])

    def test_ida_y_vuelta_proyecto(self):
        p = v.a_proyecto(_datos_ok(), "EPEN")
        self.assertEqual(p.item_inicial, 1)
        self.assertEqual(p.offsets_iniciales["DI"], 200)
        self.assertEqual(len(p.caratula.referencias), 1)
        d2 = v.desde_proyecto(p)
        self.assertEqual(d2["numero_documento"], "ETAP-0722-ET-CT-MC-LI-6209")
        self.assertEqual(d2["revisiones"][0]["rev"], "0")
        with tempfile.TemporaryDirectory() as t:
            p.guardar(Path(t) / "p.json")
            from modelo import Proyecto
            self.assertEqual(Proyecto.cargar(Path(t) / "p.json").to_dict(), p.to_dict())

    def test_exporta_excel_desde_formulario(self):
        perfil = perfiles.cargar_perfil("EPEN")
        p = v.a_proyecto(_datos_ok(), "EPEN")
        try:
            from openpyxl import load_workbook
        except ImportError:
            self.skipTest("falta openpyxl")
        with tempfile.TemporaryDirectory() as t:
            ruta = excel_writer.escribir_xlsx(p, perfil, Path(t) / "x.xlsx")
            ws = load_workbook(ruta)["Caratula"]
            self.assertEqual(ws["C34"].value, "LAT 132 kV")
            self.assertEqual(ws["D44"].value, "E")


@unittest.skipIf(tk is None, "sin tkinter")
class TestVentana(unittest.TestCase):
    """La ventana nueva: tabla A-G, edición de celdas, mover/borrar bloques y exportar solo A-G."""

    def setUp(self):
        from app.principal import App
        try:
            self.app = App()
        except tk.TclError:
            self.skipTest("sin pantalla")
        self.app.withdraw()

    def tearDown(self):
        self.app.destroy()

    def _campo(self):
        from modelo import Campo, Funcion, Nivel, Senal
        c = Campo(numero="04", descripcion="Campo 04", controlador="SEL-2241-33kV", senales=[
            Senal(funcion=Funcion.ALARMAS, tag_hmi="A", desc_hmi="204 A", controlador="SEL-2241-33kV"),
            Senal(funcion=Funcion.SENALIZACION, tag_hmi="B", desc_hmi="204 B"),
            Senal(funcion=Funcion.SENALIZACION, segunda_fila=True),
            Senal(funcion=Funcion.COMANDO, tag_hmi="C")])
        self.app.niveles[:] = [Nivel("33KV", "2", [c])]
        self.app.refrescar()
        return c

    def test_siete_columnas_y_celdas_combinadas(self):
        self._campo()
        self.assertEqual(list(self.app.arbol["columns"]), ["item", "nivel", "descrip", "controlador", "funcion", "tag_hmi", "desc_hmi"])
        filas = [self.app.arbol.item(i, "values") for i in self.app.arbol.get_children()]
        self.assertEqual([str(f[0]) for f in filas], ["1", "2", "3", "4"])
        self.assertEqual((filas[0][1], filas[0][2], filas[1][1], filas[1][2]), ("33KV", "Campo 04", "", ""))

    def test_item_inicial_renumera(self):
        self._campo()
        self.app.item.set("100")
        filas = [str(self.app.arbol.item(i, "values")[0]) for i in self.app.arbol.get_children()]
        self.assertEqual(filas, ["100", "101", "102", "103"])

    def test_editar_celdas_y_grupos(self):
        from modelo import Funcion
        c = self._campo()
        nivel = self.app.niveles[0]
        self.app._asignar(nivel, c, c.senales[0], "nivel", "132KV")
        self.assertEqual((nivel.nombre, nivel.codigo), ("132KV", "3"))
        self.app._asignar(nivel, c, c.senales[0], "descrip", "LAT Loma Campana")
        self.app._asignar(nivel, c, c.senales[0], "funcion", "reserva")
        self.assertEqual((c.descripcion, c.senales[0].funcion, c.senales[0].es_reserva),
                         ("LAT Loma Campana", Funcion.RESERVA, True))
        with self.assertRaises(ValueError):
            self.app._asignar(nivel, c, c.senales[0], "funcion", "otra cosa")

    def test_doble_bit_se_mueve_y_se_borra_como_bloque(self):
        from tkinter import messagebox
        c = self._campo()
        ids = list(self.app.arbol.get_children())
        self.app.arbol.selection_set(ids[1])
        self.app.mover(1)
        self.assertEqual([s.tag_hmi for s in c.senales], ["A", "C", "B", ""])
        messagebox.askyesno = lambda *a, **k: True
        self.app.arbol.selection_set(list(self.app.arbol.get_children())[2])  # la señal B
        self.app.borrar()
        self.assertEqual([s.tag_hmi for s in c.senales], ["A", "C"])

    def test_agregar_fila_despues_del_bloque(self):
        c = self._campo()
        self.app.arbol.selection_set(list(self.app.arbol.get_children())[1])
        self.app.agregar_fila()
        self.assertEqual(len(c.senales), 5)
        self.assertEqual((c.senales[3].controlador, c.senales[3].segunda_fila), ("SEL-2241-33kV", False))

    def test_exportar_solo_a_g(self):
        try:
            from openpyxl import load_workbook
        except ImportError:
            self.skipTest("falta openpyxl")
        from tkinter import filedialog, messagebox
        self._campo()
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "x.xlsx"
            filedialog.asksaveasfilename = lambda **k: str(ruta)
            mensajes = []
            messagebox.showinfo = lambda *a, **k: mensajes.append(a)
            messagebox.showerror = lambda *a, **k: mensajes.append(a)
            self.app.exportar()
            self.assertEqual([m[0] for m in mensajes], ["Exportado"])
            ws = load_workbook(ruta)["EPEN"]
            self.assertEqual(ws.max_column, 7)
            self.assertEqual((ws["A6"].value, ws["B6"].value, ws["C6"].value, ws["F6"].value, ws["G6"].value),
                             (1, "33KV", "Campo 04", "A", "204 A"))


if __name__ == "__main__":
    unittest.main()
