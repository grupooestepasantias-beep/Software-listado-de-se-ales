"""Bornera y borne leídos de las hojas de CABLEADO del plano (cableado.py).

Las hojas de prueba son lecturas OCR reales (tests/datos) de USRE-01-19-SET-Ct-PL-Ad-0811_rev4.pdf, hojas 11, 12 y 20
(campo 201 de Senillosa, 33 kV): se guardaron solo el encabezado y la fila de bornes, con las líneas verticales de las
celdas del encabezado. No hace falta tener el OCR instalado."""
import json
import unittest
from pathlib import Path

import bornes
import cableado

DATOS = Path(__file__).parent / "datos"


def hoja(n):
    d = json.loads((DATOS / f"cableado_F0811_h{n}.json").read_text(encoding="utf-8"))
    return cableado.analizar_hoja(d["cajas"], d["bordes"], d["ancho"], d["alto"], n)


class TestLimpiarNombre(unittest.TestCase):
    def test_ceros_por_oes_y_palabras_pegadas(self):
        self.assertEqual(cableado.limpiar_nombre("INTERRUPT0R252/01"), "INTERRUPTOR 252/01")
        self.assertEqual(cableado.limpiar_nombre("SECCI0NAD0R289/01 EN L0CAL"), "SECCIONADOR 289/01 EN LOCAL")
        self.assertEqual(cableado.limpiar_nombre("252/01CERRADO"), "252/01 CERRADO")

    def test_no_toca_los_nombres_normales(self):
        self.assertEqual(cableado.limpiar_nombre("Parada de emergencia"), "Parada de emergencia")
        self.assertEqual(cableado.limpiar_nombre("289T/01 ABIERTO"), "289T/01 ABIERTO")


class TestHojasDeCableado(unittest.TestCase):
    def test_hoja_11_bornes_61_a_70_de_la_x11(self):
        """Los bornes que el Excel oficial pone en X1.1 para el campo 201."""
        filas = {f.borne: f for f in hoja(11)}
        self.assertEqual(sorted(filas), list(range(61, 71)))
        self.assertTrue(all(f.bornera == "X1.1" for f in filas.values()))
        self.assertEqual(filas[61].descripcion, "INTERRUPTOR 252/01 CERRADO")
        self.assertEqual(filas[62].descripcion, "INTERRUPTOR 252/01 ABIERTO")
        self.assertEqual(filas[63].descripcion, "INTERRUPTOR 252/01 EN LOCAL")
        self.assertEqual(filas[68].descripcion, "SECCIONADOR 289/01 EN REMOTO")
        self.assertEqual(filas[70].descripcion, "SECCIONADOR 289T/01 ABIERTO")

    def test_hoja_12_incluye_el_resorte_descargado(self):
        filas = {f.borne: f.descripcion for f in hoja(12)}
        self.assertEqual(filas[71], "INTERRUPTOR 252/01 RESORTE DESCARGADO")
        self.assertEqual(sorted(filas), [71, 72, 73])

    def test_el_titulo_del_grupo_no_se_mezcla_con_los_nombres(self):
        self.assertFalse([f for f in hoja(11) if "PLAYA" in f.descripcion or "SENALIZACIONES" in f.descripcion])

    def test_no_se_leen_los_cables_al_comun_de_la_bobina(self):
        """«-X1.1» sin dos puntos (bornes 24-28, el común A2) no es la fila de la señal."""
        self.assertFalse([f for f in hoja(11) + hoja(12) if f.borne < 61])

    def test_dos_bornes_bajo_una_misma_celda_y_celdas_de_distinto_ancho(self):
        """Hoja 20: «Subir Tap» (31), «Bajar Tap» (32, 33), «Parada de emergencia» (34, 35)."""
        filas = [(f.bornera, f.borne, f.descripcion) for f in hoja(20)]
        self.assertEqual(filas, [("XT.1", 31, "Subir Tap"), ("XT.1", 32, "Bajar Tap"), ("XT.1", 33, "Bajar Tap"),
                                 ("XT.1", 34, "Parada de emergencia"), ("XT.1", 35, "Parada de emergencia")])
        self.assertNotIn("COMANDO RBC", " ".join(f.descripcion for f in hoja(20)))      # título de grupo


class TestEmparejarConBuscar(unittest.TestCase):
    """Las filas del cableado se usan con `bornes.buscar` sin cambiar nada."""

    @classmethod
    def setUpClass(cls):
        cls.filas = hoja(11) + hoja(12) + hoja(20)

    def test_como_el_excel_oficial_de_senillosa(self):
        esperado = {"Interruptor 252 / 01 Cerrado": 61, "Interruptor 252 / 01 Abierto": 62,
                    "Interruptor 252 / 01 en Local": 63, "Interruptor 252 / 01 en Remoto": 64,
                    "Seccionador 289 / 01 Cerrado": 65, "Seccionador 289 / 01 en Local": 67,
                    "Seccionador 289 / 01 en Remoto": 68, "Interruptor 252 / 01 Resorte descargado": 71}
        h = bornes.asignar(list(esperado), self.filas)
        self.assertEqual({e: (x.bornera, x.borne) for e, x in h.items()}, {e: ("X1.1", n) for e, n in esperado.items()})

    def test_comandos_del_regulador(self):
        h = bornes.asignar(["Subir Tap", "Parada de emergencia"], self.filas)
        self.assertEqual((h["Subir Tap"].bornera, h["Subir Tap"].borne), ("XT.1", 31))
        self.assertEqual(h["Parada de emergencia"].borne, 34)
        self.assertTrue(h["Parada de emergencia"].dudoso)       # dos bornes en la misma celda: la primera, y el otro queda de alternativa


class TestSinOcr(unittest.TestCase):
    def test_leer_cableado_sin_ocr_no_falla(self):
        original = cableado.disponible
        cableado.disponible = lambda: False
        try:
            self.assertEqual(cableado.leer_cableado("no_existe.pdf"), [])
        finally:
            cableado.disponible = original


if __name__ == "__main__":
    unittest.main()
