import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import diccionario as dic
import perfiles
from modelo import Campo, Funcion, Nivel, Proyecto, Senal, TipoPunto

EJEMPLO = Path(r"\\192.168.15.120\PasantiasMM\Sofware listado\Ejemplos\ETAP-0722-ET-CT-MC-LI-6209-1-Lista señales - CAO.xlsx")


def _proyecto(*textos, prefijo="204AP"):
    senales = [Senal(funcion=Funcion.ALARMAS, tipo_punto=TipoPunto.DI, observaciones=t) for t in textos]
    return Proyecto(perfil_id="EPEN", niveles=[Nivel("33KV", "2", [Campo("04", prefijo=prefijo, senales=senales)])])


class TestDiccionario(unittest.TestCase):
    def setUp(self):
        self.d = dic.Diccionario()
        self.d.agregar(["Seccionador 329SA03 Falta Tensión Auxiliar"], "SEC BA F/Uaux")
        self.d.agregar(["Interruptor 35203 Resorte Descargado"], "INT RES/DESC")

    def test_normaliza_numeros_acentos_y_sinonimos(self):
        self.assertEqual(dic.normalizar("Secc. 229SA04 Falta Tensión"), "seccionador #sa# falta tension")

    def test_exacta_ignora_el_numero_de_campo_y_equipo(self):
        p = _proyecto("Seccionador 229SA04 Falta Tension Auxiliar")
        inf = dic.aplicar(p, self.d)
        s = p.todas_las_senales()[0]
        self.assertEqual((inf.exactas, s.desc_scada, "desc_scada" in s.fijos), (1, "204AP SEC BA F/Uaux", True))

    def test_codigo_de_equipo_distinto_no_se_confunde(self):
        p = _proyecto("Seccionador 229SB04 Falta Tension Auxiliar")  # SB != SA
        inf = dic.aplicar(p, self.d)
        self.assertEqual((inf.exactas, p.todas_las_senales()[0].desc_scada, len(inf.sin_dato)), (0, "", 1))

    def test_no_pisa_lo_ya_cargado_ni_repite_en_el_campo(self):
        p = _proyecto("Interruptor 25204 Resorte Descargado", "Interruptor 25205 Resorte Descargado")
        inf = dic.aplicar(p, self.d)
        self.assertEqual([s.desc_scada for s in p.todas_las_senales()], ["", ""])
        self.assertEqual(len(inf.sin_dato), 2)

    def test_respeta_el_maximo_de_20(self):
        p = _proyecto("Interruptor 25204 Resorte Descargado", prefijo="204AP-LARGO-X")
        inf = dic.aplicar(p, self.d)
        self.assertEqual(p.todas_las_senales()[0].desc_scada, "")
        self.assertEqual(len(inf.sin_dato), 1)


@unittest.skipUnless(EJEMPLO.exists(), "falta el ejemplo ETAP")
class TestDesdeExcel(unittest.TestCase):
    def test_aprende_del_listado_etap(self):
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            self.skipTest("falta openpyxl")
        perfil = perfiles.cargar_perfil("EPEN")
        d = dic.cargar_diccionario(EJEMPLO, perfil)
        self.assertGreater(d.filas_leidas, 300)
        s = d.sugerir("Seccionador 329SA03 Falta Tensión Auxiliar")
        self.assertEqual((s.sufijo, s.exacta), ("SEC BA F/Uaux", True))


if __name__ == "__main__":
    unittest.main()
