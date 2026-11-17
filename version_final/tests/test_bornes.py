"""Bornera y borne leídos de las tablas de bornes dibujadas en el plano (OCR).

Las hojas de prueba son lecturas OCR reales (tests/datos) de USRE-01-19-SET-Ct-PL-Ad-0811_rev4.pdf (campo 201 de Senillosa,
33 kV), hojas 52, 53 y 56; no hace falta tener el OCR instalado para correr estos tests."""
import json
import unittest
from pathlib import Path

import bornes
from bornes import FilaBorne

DATOS = Path(__file__).parent / "datos"


def tabla(n):
    d = json.loads((DATOS / f"ocr_F0811_h{n}.json").read_text(encoding="utf-8"))
    return d, bornes.leer_tabla(d)


class TestLeerTabla(unittest.TestCase):
    def test_reconoce_la_hoja_de_tabla(self):
        d, _ = tabla(53)
        self.assertTrue(bornes.es_hoja_de_tabla(d["cajas"]))
        self.assertFalse(bornes.es_hoja_de_tabla([{"texto": "CAJETIN"}, {"texto": "SALIDAS"}]))

    def test_filas_de_la_bornera_x11(self):
        _, filas = tabla(53)
        por_borne = {(f.bornera, f.borne): f for f in filas}
        self.assertEqual(por_borne[("X1.1", 61)].descripcion, "Int. 252 / 01 Cerrado")
        self.assertEqual(por_borne[("X1.1", 71)].descripcion, "Int. 252 / 01 Resorte Descarg.")
        self.assertEqual(por_borne[("X1.1", 73)].descripcion, "TV-Llave Termomag. Abiert")

    def test_la_descripcion_de_dos_renglones_se_une_a_su_borne(self):
        _, filas = tabla(53)
        d = {f.borne: f.descripcion for f in filas if f.bornera == "X1.1"}
        self.assertEqual(d[65], "Seccionador 289 / 01 Cerrado")      # el primer renglón queda sobre el borne y el segundo debajo
        self.assertEqual(d[67], "Seccionador 289 / 01 en Local")

    def test_cada_mitad_de_la_hoja_tiene_su_bornera(self):
        _, filas = tabla(53)
        self.assertEqual({f.bornera for f in filas}, {"X1.1", "X2"})

    def test_el_titulo_pegado_se_separa_de_la_bornera(self):
        _, filas = tabla(56)
        self.assertIn("XT.1", {f.bornera for f in filas})
        self.assertNotIn("XT.1ALARMASTRANSFORMADOR", {f.bornera for f in filas})

    def test_la_bobina_del_rele_se_lee(self):
        _, filas = tabla(53)
        self.assertEqual({f.bobina for f in filas if f.bornera == "X1.1" and f.borne in (61, 62, 71)}, {"A1"})
        _, f52 = tabla(52)
        self.assertEqual({f.bobina for f in f52 if f.bornera == "X1.1" and f.borne in (24, 25, 26)}, {"A2"})


class TestEmparejar(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.filas = tabla(52)[1] + tabla(53)[1]

    def test_palabras_igualan_el_codigo_y_las_abreviaturas(self):
        self.assertEqual(bornes.palabras("Interruptor 252 / 01 Cerrado"), ["interruptor", "25201", "cerrado"])
        self.assertEqual(bornes.palabras("Int. 252 / 01 Resorte Descarg."), ["interruptor", "25201", "resorte", "descargado"])

    def test_parecido(self):
        self.assertGreaterEqual(bornes.parecido("Interruptor 252 / 01 Resorte descargado", "Int. 252 / 01 Resorte Descarg."), 0.9)
        self.assertEqual(bornes.parecido("Interruptor 252 / 01 Cerrado", "Int. 289 / 01 Cerrado"), 0.0)     # otro equipo
        self.assertLess(bornes.parecido("Interruptor 252 / 01 Abierto", "Int. 252 / 01 Cerrado"), bornes.UMBRAL)

    def test_cada_estado_de_una_senal_doble_va_a_su_borne(self):
        h = bornes.asignar(["Interruptor 252 / 01 Abierto", "Interruptor 252 / 01 Cerrado"], self.filas)
        self.assertEqual((h["Interruptor 252 / 01 Cerrado"].bornera, h["Interruptor 252 / 01 Cerrado"].borne), ("X1.1", 61))
        self.assertEqual((h["Interruptor 252 / 01 Abierto"].bornera, h["Interruptor 252 / 01 Abierto"].borne), ("X1.1", 62))

    def test_como_el_excel_oficial_de_senillosa(self):
        """El oficial (campo 201) pone estos bornes en X1.1."""
        esperado = {"Interruptor 252 / 01 en Local": 63, "Interruptor 252 / 01 en Remoto": 64,
                    "Interruptor 252 / 01 Resorte descargado": 71, "Seccionador 289 / 01 Cerrado": 65,
                    "Seccionador 289 / 01 en Local": 67, "Seccionador 289 / 01 en Remoto": 68}
        h = bornes.asignar(list(esperado), self.filas)
        self.assertEqual({e: (x.bornera, x.borne) for e, x in h.items()}, {e: ("X1.1", n) for e, n in esperado.items()})

    def test_si_hay_dos_filas_vale_la_de_la_bobina_a1(self):
        # «Interruptor 252 / 01 Cerrado» está en el borne 24 (A2, el común) y en el 61 (A1, la señal)
        h = bornes.buscar("Interruptor 252 / 01 Cerrado", self.filas)
        self.assertEqual(h.borne, 61)
        self.assertFalse(h.dudoso)

    def test_sin_fila_parecida_no_se_inventa(self):
        self.assertIsNone(bornes.buscar("Falla interna Prot. Principal", self.filas))
        self.assertIsNone(bornes.buscar("Reserva", self.filas))
        self.assertIsNone(bornes.buscar("", self.filas))

    def test_empate_entre_filas_iguales_queda_dudoso(self):
        filas = [FilaBorne("X1", 1, "Alarma general", 1), FilaBorne("X1", 2, "Alarma general", 1)]
        h = bornes.buscar("Alarma general", filas)
        self.assertEqual((h.borne, h.alternativas), (1, (("X1", 2),)))
        self.assertTrue(h.dudoso)

    def test_ida_y_vuelta_a_json(self):
        self.assertEqual(bornes.de_dicts(json.loads(json.dumps(bornes.a_dicts(self.filas)))), self.filas)


if __name__ == "__main__":
    unittest.main()
