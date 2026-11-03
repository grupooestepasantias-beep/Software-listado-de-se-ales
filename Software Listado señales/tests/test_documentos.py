"""Corpus documental: filas, índice, cajetín y comparación de rótulos (con cajas sintéticas: no hace falta OCR)."""
import unittest

import documentos
from documentos import Caja, PaginaDoc


def caja(x, y, t):
    return Caja(x, y, len(t) * 5, 8, t)


class TestIndice(unittest.TestCase):
    def test_el_indice_de_dos_columnas_se_lee_por_hoja(self):
        cajas = [caja(50, 100, "HOJA"), caja(80, 100, "01"), caja(110, 100, "CARATULA"),
                 caja(400, 101, "HOJA"), caja(430, 101, "74"), caja(460, 101, "LISTA DE SENALES Y ALARMAS"),
                 caja(50, 120, "HOJA 11"), caja(110, 120, "CAMPO 01 13,2kV-TENSIONES"),
                 caja(400, 120, "HOJA 82"), caja(460, 120, "TABLAS DE BORNES")]
        pg = PaginaDoc("a.pdf", 2, cajas, "ocr", es_indice=True)
        self.assertEqual(documentos.leer_indice([pg]),
                         {1: "CARATULA", 74: "LISTA DE SENALES Y ALARMAS", 11: "CAMPO 01 13,2kV-TENSIONES",
                          82: "TABLAS DE BORNES"})

    def test_el_cajetin_da_hoja_y_titulo(self):
        cajas = [caja(10, 500, "OBRA: NUEVA SUB"), caja(200, 501, "TITULO:"), caja(250, 500, "TCONTROL 13,2kV - ÍNDICE"),
                 caja(400, 500, "DOCUMENTO Nº:"), caja(210, 520, "HOJA: 74 DE 92")]
        self.assertEqual(documentos._cajetin(cajas), ("74", "TCONTROL 13,2kV - ÍNDICE"))

    def test_las_cajas_se_agrupan_en_renglones(self):
        f = documentos.filas([caja(300, 50, "B"), caja(10, 52, "A"), caja(10, 90, "C")])
        self.assertEqual([[c.texto for c in r] for r in f], [["A", "B"], ["C"]])


class TestComparacion(unittest.TestCase):
    def test_el_ocr_confunde_o_con_cero_pero_se_reconoce(self):
        self.assertEqual(documentos.clave_ocr("Seccionador 189/01 CERRAD0"),
                         documentos.clave_ocr("Seccionador 189/01 cerrado"))
        self.assertEqual(documentos.clave_ocr("EN L0CAL"), documentos.clave_ocr("en local"))

    def test_los_numeros_no_se_tocan(self):
        self.assertEqual(documentos.clave_ocr("Reconectador 152/05"), "RECONECTADOR 152/05")
        self.assertEqual(documentos.clave_ocr("Común negativo 48 Vcc"), "COMUN NEGATIVO 48 VCC")


if __name__ == "__main__":
    unittest.main()
