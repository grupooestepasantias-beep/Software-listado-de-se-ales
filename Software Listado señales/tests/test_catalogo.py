import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import catalogo


class TestCatalogo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.doc = catalogo.cargar(propios=Path(tempfile.gettempdir()) / "no_existe_propios.json")
        cls.e = cls.doc["entradas"]

    def test_trae_las_dos_marcas_con_su_fuente(self):
        self.assertEqual(catalogo.marcas(self.e), ["SEL (Schweitzer Engineering Laboratories)", "Schneider Electric"])
        self.assertTrue(all(x["fuente"].startswith("http") for x in self.e))
        self.assertEqual(set(self.doc["sitios"]), set(catalogo.marcas(self.e)))
        self.assertEqual(self.doc["consultado"], "2026-10-29")

    def test_modelos_clave(self):
        modelos = {x["modelo"] for x in self.e}
        for m in ("SEL-2241", "SEL-2241-2", "SEL-2244-2", "SEL-2244-3", "SEL-2245-4", "SEL-3555",
                  "SM_CPU866e", "SM_DI32", "SM_DO16R", "SM_AI16", "SM_PS40"):
            self.assertIn(m, modelos)
        self.assertEqual(len(modelos), len(self.e))  # sin repetidos

    def test_filtros(self):
        sel = catalogo.marcas(self.e)[0]
        solo_sel = catalogo.filtrar(self.e, marca=sel)
        self.assertTrue(solo_sel and all(x["marca"] == sel for x in solo_sel))
        di = catalogo.filtrar(self.e, categoria="Entradas digitales")
        self.assertEqual({x["modelo"] for x in di}, {"SEL-2244-2", "SEL-2244-4", "SM_DI32"})
        self.assertEqual([x["modelo"] for x in catalogo.filtrar(self.e, texto="2244-5")], ["SEL-2244-5"])
        self.assertIn("SM_CPU866e", {x["modelo"] for x in catalogo.filtrar(self.e, texto="alto rendimiento")})
        self.assertEqual(catalogo.filtrar(self.e, texto="zzzz"), [])
        self.assertIn("Entradas digitales", catalogo.categorias(self.e, "Schneider Electric"))

    def test_desplegable_y_tension(self):
        valores = catalogo.valores_desplegable(self.e)
        self.assertEqual(len(valores), len(set(valores)))
        self.assertEqual(valores[0][:3], "SEL")  # primero la marca SEL, luego Schneider
        self.assertIn("SM_AI8AO4", valores)
        for m in ("SEL-2241", "SEL-3555", "SM_CPU866e"):
            self.assertTrue(catalogo.lleva_tension(m, self.e), m)
        for m in ("SEL-2244-2", "SM_DI32", "SEL-2242", "no existe"):
            self.assertFalse(catalogo.lleva_tension(m, self.e), m)

    def test_modelos_propios_se_guardan_aparte_y_no_se_repiten(self):
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "propios.json"
            catalogo.agregar_propio("ACME-1", "Un equipo", ruta=ruta)
            with self.assertRaises(ValueError):
                catalogo.agregar_propio("acme-1", ruta=ruta)
            with self.assertRaises(ValueError):
                catalogo.agregar_propio("  ", ruta=ruta)
            doc = catalogo.cargar(propios=ruta)
            propios = [x for x in doc["entradas"] if x.get("propio")]
            self.assertEqual([(x["modelo"], x["marca"]) for x in propios], [("ACME-1", "Propio")])
            self.assertEqual(len(doc["entradas"]), len(self.e) + 1)


if __name__ == "__main__":
    unittest.main()
