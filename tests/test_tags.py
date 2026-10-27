import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import perfiles
import tags
from modelo import Funcion, Senal, TipoPunto

EJEMPLO = Path(r"\\192.168.15.120\PasantiasMM\Sofware listado\Ejemplos\ETAP-0722-ET-CT-MC-LI-6209-1-Lista señales - CAO.xlsx")


class TestTags(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = perfiles.cargar_perfil("EPEN")

    def test_construir(self):
        p = self.p
        self.assertEqual(tags.construir_tag(p, nivel="3", campo="03", variable=0, bits=1), "303.001")
        self.assertEqual(tags.construir_tag(p, nivel="3", campo="03", variable=63, bits=2, comando=True), "303.632C")
        self.assertEqual(tags.construir_tag(p, nivel="3", campo="03", variable=1, medicion="AU"), "303.01AU")
        self.assertEqual(tags.construir_tag(p, campo="TP1", variable=43, bits=1), "TP1.431")
        self.assertEqual(tags.construir_tag(p, nivel="3", campo="03", variable=2, medicion="AFP"), "303.02AFP")

    def test_construir_errores(self):
        p = self.p
        with self.assertRaises(ValueError):
            tags.construir_tag(p, nivel="3", campo="03", variable=100, bits=1)
        with self.assertRaises(ValueError):
            tags.construir_tag(p, nivel="3", campo="03", variable=1, bits=3)
        with self.assertRaises(ValueError):
            tags.construir_tag(p, nivel="3", campo="3", variable=1, bits=1)
        with self.assertRaises(ValueError):
            tags.construir_tag(p, nivel="3", campo="03", variable=1, medicion="ZZ")
        with self.assertRaises(ValueError):
            tags.construir_tag(p, nivel="3", campo="03", variable=1, bits=1, medicion="AU")

    def test_parsear(self):
        p = self.p
        self.assertEqual(tags.parsear_tag(p, "303.632C"),
                         {"nivel": "3", "campo": "03", "variable": 63, "bits": 2, "comando": True, "medicion": None})
        self.assertEqual(tags.parsear_tag(p, "303.02AFP")["medicion"], "AFP")
        self.assertEqual(tags.parsear_tag(p, "TP1.431")["campo"], "TP1")
        for malo in ("SACC.01V48", "UTR02T_132", "N/A", "", "303.63", "303.633"):
            self.assertIsNone(tags.parsear_tag(p, malo), malo)

    def test_proxima_variable_y_desc(self):
        p = self.p
        self.assertEqual(tags.proxima_variable(p, {0, 1, 2, 4}), 3)
        self.assertEqual(tags.proxima_variable(p, {10, 11}, desde=10), 12)
        with self.assertRaises(ValueError):
            tags.proxima_variable(p, set(range(100)))
        self.assertEqual(tags.construir_desc_scada(p, "303LC", "SEC BA F/Uaux"), "303LC SEC BA F/Uaux")
        with self.assertRaises(ValueError):
            tags.construir_desc_scada(p, "303LC", "TEXTO DEMASIADO LARGO PARA SCADA")

    def test_validar_tag(self):
        p = self.p
        ok = Senal(funcion=Funcion.COMANDO, tipo_punto=TipoPunto.DO, tag_scada="303.632C", desc_scada="303LC SEC BA")
        self.assertEqual(tags.validar_tag(p, ok), [])
        sin_c = Senal(funcion=Funcion.COMANDO, tag_scada="303.632")
        self.assertIn("debe terminar en C", tags.validar_tag(p, sin_c)[0])
        med = Senal(funcion=Funcion.MEDICION, tag_scada="303.001")
        self.assertIn("código de medición", tags.validar_tag(p, med)[0])
        ext = Senal(funcion=Funcion.MEDICION, tag_scada="SACC.01V48")
        self.assertIn("no estándar", tags.validar_tag(p, ext)[0])
        res = Senal(funcion=Funcion.RESERVA, tag_scada="N/A")
        self.assertEqual(tags.validar_tag(p, res), [])
        larga = Senal(funcion=Funcion.ALARMAS, tag_scada="303.001", desc_scada="x" * 21)
        self.assertIn("máx. 20", tags.validar_tag(p, larga)[0])

    @unittest.skipUnless(EJEMPLO.exists(), "ejemplo ETAP no disponible")
    def test_contra_ejemplo_etap(self):
        try:
            import openpyxl
        except ImportError:
            self.skipTest("openpyxl no instalado")
        ws = openpyxl.load_workbook(EJEMPLO, read_only=True, data_only=True)["EPEN"]
        estandar = no_estandar = 0
        for fila in ws.iter_rows(min_row=6, values_only=True):
            tag = fila[7]
            if tag is None:
                continue
            d = tags.parsear_tag(self.p, str(tag))
            if d is None:
                if str(tag).strip() != tags.NO_APLICA:  # las reservas llevan N/A
                    no_estandar += 1
                continue
            estandar += 1
            rearmado = tags.construir_tag(
                self.p, campo=d["campo"], variable=d["variable"], nivel=d["nivel"],
                bits=d["bits"], comando=d["comando"], medicion=d["medicion"])
            self.assertEqual(rearmado, str(tag).strip())
        # 482 estándar; 11 no estándar (TP1.01APOS, TP1.02AIMTA, SACC.01V48..06I110, UTR02T_132..UTR06T_SSAA)
        self.assertGreaterEqual(estandar, 482)
        self.assertLessEqual(no_estandar, 11)


if __name__ == "__main__":
    unittest.main()
