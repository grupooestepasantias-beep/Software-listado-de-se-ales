"""Placas de módulo dibujadas (sin texto), leídas con OCR (placas.py). Sin OCR instalado se prueban con lecturas simuladas."""
import unittest
from types import SimpleNamespace

import ocr
import placas


def pagina():
    return SimpleNamespace(number=41, parent=SimpleNamespace(name="USRE-0821_r3.pdf"))


def caja(x, texto, conf=0.99):
    return {"x": x, "y": 10, "w": 100, "h": 30, "texto": texto, "conf": conf}


class TestPlacas(unittest.TestCase):
    def setUp(self):
        self._disp, self._leer = ocr.disponible, ocr.leer_hoja
        ocr.disponible = lambda: True

    def tearDown(self):
        ocr.disponible, ocr.leer_hoja = self._disp, self._leer

    def leer(self, cajas):
        ocr.leer_hoja = lambda *a, **k: {"cajas": cajas}
        return placas.por_ocr(pagina(), 4)

    def test_limpia_el_uno_leido_como_i(self):
        self.assertEqual(placas._limpiar("UTRI.1 .1"), "UTR1.1.1")
        self.assertEqual(placas._limpiar("utr1.1.l"), "UTR1.1.1")

    def test_una_placa_por_modulo_de_izquierda_a_derecha(self):
        cajas = [caja(1500, "UTR1.1.3"), caja(300, "UTR1.1.1"), caja(900, "UTR1.1.2"), caja(2100, "UTR1.1.4"), caja(50, "Campo 01")]
        self.assertEqual(self.leer(cajas), ["UTR1.1.1", "UTR1.1.2", "UTR1.1.3", "UTR1.1.4"])

    def test_si_no_coincide_la_cantidad_no_se_adivina(self):
        self.assertEqual(self.leer([caja(300, "UTR1.1.1"), caja(900, "UTR1.1.2")]), [])

    def test_una_placa_leida_dos_veces_no_cuenta_doble(self):
        cajas = [caja(300, "UTR1.1.1"), caja(310, "UTR1.1.1"), caja(900, "UTR1.1.2"), caja(1500, "UTR1.1.3"), caja(2100, "UTR1.1.4")]
        self.assertEqual(len(self.leer(cajas)), 4)

    def test_lecturas_poco_confiables_se_descartan(self):
        self.assertEqual(self.leer([caja(300, "UTR1.1.1", 0.3), caja(900, "UTR1.1.2"), caja(1500, "UTR1.1.3"), caja(2100, "UTR1.1.4")]), [])

    def test_sin_ocr_devuelve_vacio(self):
        ocr.disponible = lambda: False
        self.assertEqual(placas.por_ocr(pagina(), 4), [])


if __name__ == "__main__":
    unittest.main()
