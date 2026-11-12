import unittest

import estados as est
import numeracion as num


class TestEstados(unittest.TestCase):
    def test_alarma_y_simple(self):
        self.assertEqual(est.estados(num.Senal(num.ALARMAS)), ["NORMAL", "ACTUO", "N/A", "N/A", "N/A"])
        self.assertEqual(est.estados(num.Senal(num.SENALIZACION))[:2], ["NORMAL", "OPERO"])

    def test_dobles_segun_los_rotulos_del_pdf(self):
        d = lambda *p: num.Senal(num.SENALIZACION, doble=True, pares=p)  # noqa: E731
        self.assertEqual(est.estados(d("Interruptor 1 Abierto", "Interruptor 1 Cerrado"))[:4], ["error_0", "AB", "CE", "error_1"])
        self.assertEqual(est.estados(d("Secc. Local", "Secc. Remoto"))[1:3], ["LOC", "REM"])
        self.assertEqual(est.estados(d("Llave Tele/Distancia en D", "Llave Tele/Distancia en T"))[1:3], ["DIST", "TELE"])

    def test_reserva_todo_na(self):
        self.assertEqual(est.estados(num.Senal(num.ALARMAS, reserva=True)), ["N/A"] * 5)

    def test_rango_default_y_elegido(self):
        self.assertEqual(est.rango(0), [0, 32767, 0, 327.67, "KV"])
        self.assertEqual(est.rango(3, {3: {"min_raw": -32768, "max_raw": 32767, "min_eu": -3276.8, "max_eu": 3276.7}})[0:2], [-32768, 32767])

    def test_numero_con_coma(self):
        self.assertEqual(est.numero("327,67"), 327.67)
        self.assertEqual(est.numero("32767"), 32767)


if __name__ == "__main__":
    unittest.main()
