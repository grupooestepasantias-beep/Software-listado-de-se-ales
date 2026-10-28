import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import excel_writer
import pdf_plano
import perfiles
from modelo import Funcion, Proyecto

PLANO = Path(r"\\192.168.15.120\PasantiasMM\Sofware listado\Ejemplos\ETAP-0325-ET-CT-PL-EF-6402_1.pdf")

try:
    import pymupdf  # noqa: F401
except ImportError:
    pymupdf = None


class TestClasificacion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.perfil = perfiles.cargar_perfil("EPEN")
        cls.cfg = pdf_plano.cargar_config(cls.perfil)

    def banda(self, textos, pagina=1):
        return pdf_plano._senales_de_banda(textos, self.cfg, pagina)

    def test_ignora_alimentacion_y_marca_reservas(self):
        r = self.banda(["Negativo 48 VCC", "Reserva", "Positivo 110 Vcc", "Reserva"])
        self.assertEqual([s.funcion for s in r], [Funcion.RESERVA, Funcion.RESERVA])

    def test_pares_de_doble_bit_en_orden_de_estados(self):
        r = self.banda(["Seccionador 229SL04 Cerrado", "Seccionador 229SL04 Abierto",
                        "Seccionador 229SL04 Remoto", "Seccionador 229SL04 Local"])
        self.assertEqual([s.funcion for s in r], [Funcion.SENALIZACION, Funcion.SENALIZACION])
        # la 1ª fila es el 1er estado (Abierto / Local), aunque en el plano figure después
        self.assertEqual(r[0].columnas, ["Seccionador 229SL04 Abierto", "Seccionador 229SL04 Cerrado"])
        self.assertEqual(r[0].texto, "Seccionador 229SL04 Abierto/Cerrado")
        self.assertEqual(r[1].columnas[0], "Seccionador 229SL04 Local")

    def test_no_empareja_equipos_distintos(self):
        r = self.banda(["Seccionador 229SL04 Abierto", "Seccionador 229SB04 Cerrado"])
        self.assertEqual(len(r), 2)
        self.assertTrue(all(s.funcion == Funcion.ALARMAS for s in r))

    def test_banda_de_salidas_son_comandos(self):
        r = self.banda(["Positivo 110 Vcc", "Seccionador 229SL04 Cierre", "Positivo 110 Vcc",
                        "Seccionador 229SL04 Apertura", "Reserva", "Interruptor 25204 Cierre"])
        self.assertEqual([s.funcion for s in r], [Funcion.COMANDO, Funcion.RESERVA, Funcion.COMANDO])
        self.assertEqual(r[0].columnas[0], "Seccionador 229SL04 Apertura")

    def test_codigo_de_nivel_por_tension(self):
        esperado = {"132KV": "3", "66KV": "3", "33KV": "2", "13,2KV": "1", "13KV": "1", "6.6KV": "1",
                    "6,6 kV": "1", "SSAA": ""}
        for nombre, cod in esperado.items():
            self.assertEqual(pdf_plano.codigo_nivel(nombre, self.cfg), cod, nombre)

    def test_controlador_por_defecto(self):
        self.assertEqual(pdf_plano.controlador_por_defecto("33KV", self.cfg), "SEL-2241-33kV")
        self.assertEqual(pdf_plano.controlador_por_defecto("132 KV", self.cfg), "SEL-2241-132kV")
        self.assertEqual(pdf_plano.controlador_por_defecto("6.6KV", self.cfg), "SEL-2241-6,6kV")  # coma, como el ETAP

    def test_la_tension_del_controlador_sigue_al_nivel(self):
        f = pdf_plano.con_tension_del_nivel
        self.assertEqual(f("SEL-2241-33kV", "132KV"), "SEL-2241-132kV")
        self.assertEqual(f("SEL-2241-132kV", "6,6KV"), "SEL-2241-6,6kV")
        self.assertEqual(f("SCHNEIDER P142_C04", "132KV"), "SCHNEIDER P142_C04")  # un relé no lleva tensión
        self.assertEqual(f("SEL-3555", "132KV"), "SEL-3555")
        self.assertEqual(f("SEL-2241-33kV", "RESERVAS"), "SEL-2241-33kV")  # nivel sin tensión: no cambia

    def test_las_senales_de_proteccion_llevan_el_rele_del_campo(self):
        niv = self.armar(["Prot. Campo 04 33 KV Falla Interna", "Interruptor 25204 Falta Fuerza Motriz",
                          "Campo 04 33KV Falla Multimedidor", "2TV04- Falta Vca Prot"],
                         destinos={5: ("33KV", "04", "", "", "AP", "SCHNEIDER P142_C04")})
        por = {s.desc_hmi: s.controlador for s in niv[0].campos[0].senales}
        self.assertEqual(por["204AP Proteccion Campo 04 33 KV Falla Interna"], "SCHNEIDER P142_C04")
        self.assertEqual(por["204AP Interruptor 25204 Falta Fuerza Motriz"], "SEL-2241-33kV")
        self.assertEqual(por["204AP Campo 04 33KV Falla Multimedidor"], "SEL-2241-33kV")
        self.assertEqual(por["204AP 2TV04- Falta Vca Proteccion"], "SEL-2241-33kV")  # 'Prot' no está al comienzo

    def armar(self, textos, **kw):
        return pdf_plano.a_niveles([pdf_plano.PaginaLeida(5, "33KV", "04", self.banda(textos, 5))], self.perfil, **kw)

    def test_filas_a_g(self):
        niv = self.armar(["Seccionador 229SL04 Cerrado", "Seccionador 229SL04 Abierto", "Reserva",
                          "Interruptor 25204 Falta Fuerza Motriz"], destinos={5: ("33KV", "04", "Campo 04", "", "AP")})
        c = niv[0].campos[0]
        self.assertEqual((niv[0].nombre, niv[0].codigo, c.descripcion, c.prefijo, c.controlador),
                         ("33KV", "2", "Campo 04", "204AP", "SEL-2241-33kV"))
        a, s1, s2 = c.senales  # alarma primero (orden fijo), luego la señalización con sus 2 filas
        self.assertEqual((a.funcion, a.controlador, a.tag_hmi, a.desc_hmi),
                         (Funcion.ALARMAS, "SEL-2241-33kV", "Interruptor_25204_F_Fza_Motriz",
                          "204AP Interruptor 25204 Falta Fuerza Motriz"))
        self.assertEqual((s1.tag_hmi, s1.desc_hmi), ("Seccionador_229SL04_Abierto_Cerrado",
                                                      "204AP Seccionador 229SL04 Abierto/Cerrado"))
        self.assertEqual((s2.segunda_fila, s2.funcion, s2.controlador, s2.tag_hmi, s2.desc_hmi),
                         (True, Funcion.SENALIZACION, "SEL-2241-33kV", "", ""))

    def test_reservas_juntas_al_final_con_el_campo_en_la_descripcion(self):
        a = pdf_plano.PaginaLeida(1, "33KV", "04", self.banda(["Reserva", "Eq 1 Falla"], 1))
        b = pdf_plano.PaginaLeida(2, "132KV", "04", self.banda(["Reserva", "Eq 2 Falla"], 2))
        niv = pdf_plano.a_niveles([a, b], self.perfil)
        self.assertEqual([n.nombre for n in niv], ["33KV", "132KV", "RESERVAS"])
        r = niv[-1].campos[0].senales
        self.assertEqual([(s.tag_hmi, s.desc_hmi) for s in r],
                         [("N/A", "RESERVA 33KV Campo 04"), ("N/A", "RESERVA 132KV Campo 04")])


@unittest.skipUnless(pymupdf and PLANO.exists(), "falta pymupdf o el plano de ejemplo")
class TestPlanoReal(unittest.TestCase):
    def test_pagina_29_y_exportar_a_g(self):
        perfil = perfiles.cargar_perfil("EPEN")
        paginas = pdf_plano.leer_plano(PLANO, perfil, solo_paginas={29})
        self.assertEqual(len(paginas), 1)
        pg = paginas[0]
        self.assertEqual((pg.nivel, pg.campo), ("33KV", "04"))
        textos = [s.texto for s in pg.senales]
        self.assertIn("Seccionador 229SL04 Abierto/Cerrado", textos)
        self.assertIn("Interruptor 25204 Apertura/Cierre", textos)
        self.assertFalse(any("Positivo" in t or "Negativo" in t for t in textos))
        self.assertEqual(sum(s.funcion == Funcion.COMANDO for s in pg.senales), 3)

        niv = pdf_plano.a_niveles(paginas, perfil)
        p = Proyecto(perfil_id="EPEN", niveles=niv, item_inicial=1)
        try:
            from openpyxl import load_workbook
        except ImportError:
            self.skipTest("falta openpyxl")
        with tempfile.TemporaryDirectory() as t:
            ruta = excel_writer.escribir_xlsx(p, perfil, Path(t) / "s.xlsx", incluir_caratula=False,
                                              hasta_columna="G")
            wb = load_workbook(ruta)
            self.assertEqual(wb.sheetnames, ["EPEN"])
            ws = wb["EPEN"]
            n = len(p.todas_las_senales())
            self.assertEqual(ws.cell(5 + n, 1).value, n)  # ITEM correlativo hasta la última fila
            self.assertEqual((ws["B6"].value, ws["D6"].value, ws["E6"].value),
                             ("33KV", "SEL-2241-33kV", "ALARMAS"))
            self.assertEqual(ws.max_column, 7)  # solo A-G
            self.assertEqual(ws.auto_filter.ref, f"A5:G{5 + n}")
            self.assertEqual(ws.print_area, f"'EPEN'!$A$1:$G${5 + n}")


if __name__ == "__main__":
    unittest.main()
