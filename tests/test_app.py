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

    def test_obligatorios_y_numeracion(self):
        d = v.datos_vacios()
        msgs = "\n".join(v.validar(d, 14, 4, 20))
        for esperado in ("ITEM inicial", "OFFSET inicial DI"):  # la carátula no es obligatoria por ahora
            self.assertIn(esperado, msgs)
        self.assertNotIn("cliente", msgs)

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
class TestGui(unittest.TestCase):
    def test_formulario_ida_y_vuelta(self):
        from app.principal import App
        try:
            app = App()
        except tk.TclError:
            self.skipTest("sin pantalla")
        app.withdraw()
        try:
            perfil = perfiles.cargar_perfil("EPEN")
            app.mostrar_formulario(perfil, None)
            f = app._actual
            self.assertEqual((f.max_ref, f.max_rev, f.largo_doc), (14, 4, 20))
            f._cargar(_datos_ok())
            d = f.datos()
            self.assertEqual(v.validar(d, f.max_ref, f.max_rev, f.largo_doc), [])
            self.assertEqual(len(f.refs.filas), 2)
            f.refs.quitar()
            self.assertEqual(len(f.refs.valores()), 1)
            from app.principal import DialogoAbreviaturas
            import descripciones
            pend = [descripciones.Pendiente("equipo", "seccionador|SL", "Abreviatura de «Seccionador SL»", "x", "SL", 14)]
            dlg = DialogoAbreviaturas(app, pend, 20)
            dlg.vars[0].set("SL")
            dlg._aceptar()  # cierra la ventana y deja la respuesta en el pendiente
            self.assertEqual(pend[0].respuesta, "SL")
            app.mostrar_inicio()
        finally:
            app.destroy()


if __name__ == "__main__":
    unittest.main()
