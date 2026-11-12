import unittest

from numeracion import (ALARMAS, COMANDO, MEDICION, SENALIZACION, Campo, ErrorNumeracion, MEDICIONES_ETAP, Senal, numerar)


def alarma(**k): return Senal(ALARMAS, **k)
def senal(**k): return Senal(SENALIZACION, **k)


class TestNumeracion(unittest.TestCase):
    def campo(self, prefijo="303", inicio=10, **k):
        return Campo(prefijo, inicio, [alarma(), alarma(), senal(doble=True, comando=True), senal(doble=True)], **k)

    def test_tag_y_variable_correlativa_desde_el_inicio_del_usuario(self):
        filas = numerar([self.campo(inicio=10)], 200, 200)
        tags = [f.tag for f in filas if f.tag and f.funcion != COMANDO]
        self.assertEqual(tags, ["303.101", "303.111", "303.122C", "303.132"])

    def test_cada_campo_arranca_en_su_propio_numero(self):
        filas = numerar([self.campo("101", 10), self.campo("102", 20)], 200, 200)
        self.assertEqual([f.tag for f in filas if f.campo == "102" and f.tag][:2], ["102.201", "102.211"])

    def test_offsets_alarmas_hueco_senales_hueco_campo_siguiente(self):
        filas = numerar([self.campo("101"), self.campo("102")], 200, 500)
        o = {(f.campo, f.tag): f.offset for f in filas if f.tag and f.funcion != COMANDO}
        self.assertEqual(o[("101", "101.101")], 200)
        self.assertEqual(o[("101", "101.111")], 201)
        # alarmas ocupan 200-201, 10 libres (202-211), señales desde 212 (dobles: 212-213, 214-215)
        self.assertEqual(o[("101", "101.122C")], 212)
        self.assertEqual(o[("101", "101.132")], 214)
        # 10 libres (216-225) y arranca el campo 102
        self.assertEqual(o[("102", "102.101")], 226)

    def test_la_senal_doble_ocupa_dos_offsets(self):
        filas = [f for f in numerar([self.campo()], 200, 500) if f.funcion == SENALIZACION]
        self.assertEqual([(f.tag, f.offset, f.extra) for f in filas[:3]], [("303.122C", 212, False), ("", 213, True), ("303.132", 214, False)])

    def test_comando_toma_el_offset_de_la_senal_sin_contador_propio(self):
        filas = numerar([self.campo()], 200, 500)
        cmd = [f for f in filas if f.funcion == COMANDO]
        self.assertEqual([(f.tag, f.offset) for f in cmd], [("303.122C", 212)])

    def test_sin_C_no_hay_comando(self):
        filas = numerar([Campo("303", 10, [senal(doble=True)])], 200, 500)
        self.assertFalse([f for f in filas if f.funcion == COMANDO])

    def test_reserva_ocupa_offset_pero_no_variable_y_va_con_na(self):
        c = Campo("303", 10, [alarma(), alarma(reserva=True), alarma()])
        filas = numerar([c], 200, 500)
        self.assertEqual([(f.tag, f.offset) for f in filas if not f.hueco], [("303.101", 200), ("N/A", 201), ("303.111", 202)])

    def test_los_libres_salen_como_filas_con_solo_offset(self):
        filas = numerar([self.campo("101"), self.campo("102")], 200, 500)
        libres = [f for f in filas if f.hueco and f.funcion != MEDICION]
        self.assertEqual(len(libres), 40)                      # 10 tras alarmas + 10 tras señales, por campo
        self.assertEqual([f.offset for f in libres[:10]], list(range(202, 212)))
        self.assertTrue(all(f.tag == "" for f in libres))

    def test_mas_de_99_variables_da_error(self):
        with self.assertRaises(ErrorNumeracion):
            numerar([Campo("303", 98, [alarma(), alarma(), alarma()])], 0, 0)

    def test_el_error_de_99_dice_con_cuanto_se_puede_empezar(self):
        c = Campo("302", 10, [alarma() for _ in range(99)])
        with self.assertRaisesRegex(ErrorNumeracion, "variable inicial de 1 o menos"):
            numerar([c], 0, 0)
        c.variable_inicial = 1
        numerar([c], 0, 0)                                        # 99 señales desde 1 llegan justo a 99

    def test_campos_repetidos_dan_error(self):
        with self.assertRaises(ErrorNumeracion):
            numerar([self.campo("303"), self.campo("303")], 0, 0)

    def test_mediciones_van_al_final_con_contador_propio(self):
        filas = numerar([self.campo("101", mediciones=MEDICIONES_ETAP), self.campo("102", mediciones=("AU", "AV"))], 200, 300)
        med = [f for f in filas if f.funcion == MEDICION]
        med = [f for f in med if not f.hueco]
        self.assertEqual([(f.tag, f.offset) for f in med[:3]], [("101.01AU", 300), ("101.02AV", 301), ("101.03AW", 302)])
        self.assertEqual(med[13].tag, "102.01AU")
        self.assertEqual(med[13].offset, 300 + 13 + 10)

    def test_medicion_salta_el_numero_que_el_campo_no_usa(self):
        filas = numerar([self.campo("303", mediciones=MEDICIONES_ETAP, saltar_medicion=(4,))], 200, 200)
        tags = [f.tag for f in filas if f.funcion == MEDICION and not f.hueco]
        self.assertEqual(tags[2:5], ["303.03AW", "303.05AR", "303.06AS"])


if __name__ == "__main__":
    unittest.main()
