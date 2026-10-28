import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import excel_writer
import pdf_plano
import perfiles
from modelo import Caratula, Funcion, Proyecto, TipoPunto

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

    def banda(self, textos):
        return pdf_plano._senales_de_banda(textos, self.cfg, 1, 1)

    def test_ignora_alimentacion_y_marca_reservas(self):
        r = self.banda(["Negativo 48 VCC", "Reserva", "Positivo 110 Vcc", "Reserva"])
        self.assertEqual([s.funcion for s in r], [Funcion.RESERVA, Funcion.RESERVA])
        self.assertTrue(all(s.es_reserva for s in r))

    def test_pares_de_doble_bit(self):
        r = self.banda(["Seccionador 229SL04 Remoto", "Seccionador 229SL04 Local",
                        "Seccionador 229SL04 Abierto", "Seccionador 229SL04 Cerrado"])
        self.assertEqual([(s.funcion, s.estado_id) for s in r],
                         [(Funcion.SENALIZACION, "sen_loc_rem"), (Funcion.SENALIZACION, "sen_ab_ce")])
        self.assertEqual(r[1].texto, "Seccionador 229SL04 Abierto/Cerrado")

    def test_no_empareja_equipos_distintos(self):
        r = self.banda(["Seccionador 229SL04 Abierto", "Seccionador 229SB04 Cerrado"])
        self.assertEqual(len(r), 2)
        self.assertTrue(all(s.funcion == Funcion.ALARMAS for s in r))

    def test_banda_de_salidas_son_comandos_do(self):
        r = self.banda(["Positivo 110 Vcc", "Seccionador 229SL04 Cierre", "Positivo 110 Vcc",
                        "Seccionador 229SL04 Apertura", "Reserva"])
        self.assertEqual([(s.funcion, s.tipo_punto) for s in r],
                         [(Funcion.COMANDO, TipoPunto.DO), (Funcion.RESERVA, TipoPunto.DO)])

    def test_niveles_ordenados_por_funcion_y_estados_del_perfil(self):
        lecturas = (self.banda(["Reserva", "Campo 04 Falla X", "Eq 1 Abierto", "Eq 1 Cerrado"])
                    + pdf_plano_salida(self))
        pg = pdf_plano.PaginaLeida(5, "33KV", "04", lecturas)
        niv = pdf_plano.a_niveles([pg], self.perfil, {5: ("33KV", "04", "Campo 04")})
        c = niv[0].campos[0]
        self.assertEqual(c.descripcion, "Campo 04")
        self.assertEqual([s.funcion for s in c.senales],
                         [Funcion.ALARMAS, Funcion.SENALIZACION, Funcion.COMANDO])
        self.assertEqual((c.senales[1].s1, c.senales[1].s2), ("AB", "CE"))
        # las reservas van todas juntas al final de la hoja, con el campo en la descripción
        self.assertEqual(len(niv), 2)
        self.assertEqual(niv[-1].nombre, "RESERVAS")
        self.assertEqual([s.observaciones for s in niv[-1].campos[0].senales], ["Reserva Campo 04 DI"])

    def test_codigo_de_nivel_por_tension(self):
        esperado = {"132KV": "3", "66KV": "3", "33KV": "2", "13,2KV": "1", "13KV": "1", "6.6KV": "1",
                    "6,6 kV": "1", "SSAA": ""}
        for nombre, cod in esperado.items():
            self.assertEqual(pdf_plano.codigo_nivel(nombre, self.cfg), cod, nombre)

    def test_prefijo_controlador_y_generador(self):
        import generador
        pg = pdf_plano.PaginaLeida(5, "33KV", "04", self.banda(["Eq 1 Falla X", "Eq 1 Abierto", "Eq 1 Cerrado"]))
        niv = pdf_plano.a_niveles([pg], self.perfil, {5: ("33KV", "04", "Campo 04", "SEL-2241")}, lugar="LC")
        self.assertEqual((niv[0].codigo, niv[0].campos[0].prefijo, niv[0].campos[0].controlador),
                         ("2", "204LC", "SEL-2241"))
        p = Proyecto(perfil_id="EPEN", niveles=niv, item_inicial=1, offsets_iniciales={"DI": 200})
        generador.generar(p, self.perfil)
        tags = [s.tag_scada for s in p.todas_las_senales() if s.tag_scada]
        self.assertTrue(all(t.startswith("204.") for t in tags), tags)
        self.assertEqual(p.todas_las_senales()[0].offset, 200)

    def test_reservas_de_varios_niveles_en_un_solo_bloque(self):
        a = pdf_plano.PaginaLeida(1, "33KV", "04", self.banda(["Reserva", "Eq 1 Falla"]))
        b = pdf_plano.PaginaLeida(2, "132KV", "04", self.banda(["Reserva", "Eq 2 Falla"]))
        niv = pdf_plano.a_niveles([a, b], self.perfil)
        self.assertEqual([n.nombre for n in niv], ["33KV", "132KV", "RESERVAS"])
        self.assertEqual([s.observaciones for s in niv[-1].campos[0].senales],
                         ["Reserva 33KV Campo 04 DI", "Reserva 132KV Campo 04 DI"])


def pdf_plano_salida(t):
    return pdf_plano._senales_de_banda(["Eq 1 Cierre", "Eq 1 Apertura"], t.cfg, 5, 2)


@unittest.skipUnless(pymupdf and PLANO.exists(), "falta pymupdf o el plano de ejemplo")
class TestPlanoReal(unittest.TestCase):
    def test_pagina_29_y_exportar(self):
        perfil = perfiles.cargar_perfil("EPEN")
        paginas = pdf_plano.leer_plano(PLANO, perfil, solo_paginas={29})
        self.assertEqual(len(paginas), 1)
        pg = paginas[0]
        self.assertEqual((pg.nivel, pg.campo), ("33KV", "04"))
        textos = [s.texto for s in pg.senales]
        self.assertIn("Seccionador 229SL04 Abierto/Cerrado", textos)
        self.assertIn("Interruptor 25204 Cierre/Apertura", textos)
        self.assertFalse(any("Positivo" in t or "Negativo" in t for t in textos))
        n_do = [s for s in pg.senales if s.tipo_punto == TipoPunto.DO and not s.es_reserva]
        self.assertEqual(len(n_do), 3)  # 3 comandos (SL04, SB04, interruptor)

        p = Proyecto(perfil_id="EPEN", caratula=Caratula(cliente="X"),
                     niveles=pdf_plano.a_niveles(paginas, perfil))
        try:
            from openpyxl import load_workbook
        except ImportError:
            self.skipTest("falta openpyxl")
        with tempfile.TemporaryDirectory() as t:
            ruta = excel_writer.escribir_xlsx(p, perfil, Path(t) / "s.xlsx")
            ws = load_workbook(ruta)["EPEN"]
            n = len(p.todas_las_senales())
            self.assertEqual(ws.cell(5 + n, 1).value, n)  # ITEM correlativo hasta la última fila
            self.assertEqual(ws["B6"].value, "33KV")


if __name__ == "__main__":
    unittest.main()
