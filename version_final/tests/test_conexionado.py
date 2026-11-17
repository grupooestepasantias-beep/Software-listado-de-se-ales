"""Bornera y borne de EQUIPO aprendidos de un listado oficial (conexionado.py + herramientas/aprender_conexionado.py)."""
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl

import conexionado
from conexionado import Conexionado, Regla

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "herramientas"))
import aprender_conexionado  # noqa: E402

OFICIAL = Path(r"\\192.168.15.101\Archivos\PasantiasMM\senillosa\USRE-0119-SET-C-T-LI-Ls-0744_rD_DV_2.xlsx")


class TestClave(unittest.TestCase):
    def test_el_codigo_de_equipo_no_cuenta(self):
        a = conexionado.clave_de("Interruptor 252 / 01 Abierto")
        self.assertEqual(a, "interruptor # abierto")
        self.assertEqual(a, conexionado.clave_de("Interruptor 25201 Abierto"))
        self.assertEqual(conexionado.clave_de("Seccionador 28T901 Cerrado"), "seccionador #t cerrado")    # puesta a tierra: otra cosa
        self.assertEqual(conexionado.clave_de("Cuchilla Tierra 229T / 01 Cerrado"), "cuchilla tierra #t cerrado")

    def test_reconectador_es_interruptor_y_apertura_es_abrir(self):
        self.assertEqual(conexionado.clave_de("Reconectador 152/01 abierto"), "interruptor # abierto")
        self.assertEqual(conexionado.clave_de("Interruptor 252/01 Apertura/Cierre"), "interruptor # abrir/cerrar")

    def test_sin_tildes_ni_signos(self):
        self.assertEqual(conexionado.clave_de("Seccionador 289/01 Falta Tensión"), "seccionador # falta tension")

    def test_tipo_de_campo(self):
        self.assertEqual(conexionado.tipo_de_campo("Entrada TR01 Campo 101"), "entrada")
        self.assertEqual(conexionado.tipo_de_campo("LM1 Campo 103"), "lm")
        self.assertEqual(conexionado.tipo_de_campo("TR01 Lado 33KV"), "tr")
        self.assertEqual(conexionado.tipo_de_campo(""), "")


def tabla():
    return Conexionado([
        Regla("interruptor # abierto", "33KV", "tr", "-XP1", "2", "x", "Interruptor 25201 Abierto"),
        Regla("seccionador # cerrado", "13,2KV", "entrada", "L0", "41", "x", "Seccionador 18901 Cerrado"),
        Regla("seccionador # cerrado", "13,2KV", "lm", "L0", "2", "x", "Seccionador 18903 Cerrado"),
        Regla("proteccion grupo a", "13,2KV", "lm", "1XP{c}", "19", "x", "Proteccion Grupo A"),
        Regla("seccionador # falta tension", "33KV", "tr", "L0", "1", "x", "Seccionador 28901 Falta Tension"),
        Regla("falla interna prot principal", "33KV", "tr", "2XP1", "3", "x", "Falla Interna Prot. Principal"),
        Regla("falla interna prot respaldo", "33KV", "tr", "2XP1", "33", "x", "Falla Interna Prot. Respaldo"),
    ])


class TestBuscar(unittest.TestCase):
    def test_coincidencia_exacta_en_el_nivel(self):
        self.assertEqual(tabla().buscar("Interruptor 252 / 01 Abierto", "33KV", "TR01"), ("-XP1", "2"))

    def test_otro_nivel_no_se_completa(self):
        self.assertEqual(tabla().buscar("Interruptor 252 / 01 Abierto", "13,2KV", "TR01"), ("", ""))

    def test_el_tipo_de_campo_desambigua(self):
        t = tabla()
        self.assertEqual(t.buscar("Seccionador 189/01 Cerrado", "13,2KV", "Entrada TR01"), ("L0", "41"))
        self.assertEqual(t.buscar("Seccionador 189/03 Cerrado", "13,2KV", "LM1"), ("L0", "2"))

    def test_si_no_se_sabe_el_tipo_y_hay_dos_valores_no_se_elige(self):
        self.assertEqual(tabla().buscar("Seccionador 189/03 Cerrado", "13,2KV", "Campo 103"), ("", ""))

    def test_plantilla_con_el_numero_de_campo(self):
        t = tabla()
        self.assertEqual(t.buscar("Proteccion Grupo A", "13,2KV", "LM1", "103"), ("1XP3", "19"))
        self.assertEqual(t.buscar("Proteccion Grupo A", "13,2KV", "LM3", "105"), ("1XP5", "19"))
        self.assertEqual(t.buscar("Proteccion Grupo A", "13,2KV", "LM1", ""), ("", ""))     # sin número de campo no se arma

    def test_por_parecido_y_con_errores_de_tipeo_del_plano(self):
        self.assertEqual(tabla().buscar("Seccionado 289 / 01 Falta Tensión", "33KV", "TR01"), ("L0", "1"))

    def test_dos_reglas_parecidas_no_se_confunden(self):
        t = tabla()
        self.assertEqual(t.buscar("Falla interna Prot. Principal", "33KV", "TR01"), ("2XP1", "3"))
        self.assertEqual(t.buscar("Falla interna Prot. Respaldo", "33KV", "TR01"), ("2XP1", "33"))

    def test_lo_desconocido_queda_vacio(self):
        t = tabla()
        self.assertEqual(t.buscar("Transf. TP01 Nivel RBC", "33KV", "TR01"), ("", ""))
        self.assertEqual(t.buscar("", "33KV", ""), ("", ""))
        self.assertEqual(Conexionado().buscar("Interruptor 252 / 01 Abierto", "33KV"), ("", ""))

    def test_guardar_y_cargar(self):
        with tempfile.TemporaryDirectory() as d:
            tabla().guardar(d)
            self.assertEqual(len(Conexionado.cargar(d)), len(tabla()))
            self.assertEqual(Conexionado.cargar(d).buscar("Interruptor 252 / 01 Abierto", "33KV", "TR01"), ("-XP1", "2"))


def excel_de_prueba(ruta):
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "EPEN"
    ws.append([""])
    ws.append(["ITEM", "NIVEL", "DESCRIP", "BORNERA EQUIPO", "N* DE BORNE EQUIPO", "DESCRIPCION / OBSERVAC"])
    ws.append([""])
    ws.append([""])
    ws.append([1, "13,2KV", "Entrada TR01 Campo 101", "L0", "41", "Seccionador 18901 Cerrado"])
    ws.append([2, None, None, "1XP1", "22", "Proteccion Grupo A"])
    ws.append([3, None, "LM1 Campo 103", "L0", "2", "Seccionador 18903 Cerrado"])
    ws.append([4, None, None, "1XP3", "19", "Proteccion Grupo A"])
    ws.append([5, None, "LM2 Campo 104", "L0", "2", "Seccionador 18904 Cerrado"])
    ws.append([6, None, None, "1XP4", "19", "Proteccion Grupo A"])
    ws.append([7, None, None, None, None, "Sin conexionado"])
    wb.save(ruta)


class TestAprender(unittest.TestCase):
    def test_aprende_de_un_listado_y_detecta_la_plantilla_por_campo(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "oficial.xlsx"
            excel_de_prueba(ruta)
            reglas, conflictos = aprender_conexionado.aprender(ruta)
            t = Conexionado(reglas)
            self.assertEqual(t.buscar("Seccionador 18901 Cerrado", "13,2KV", "Entrada TR01"), ("L0", "41"))
            self.assertEqual(t.buscar("Seccionador 18903 Cerrado", "13,2KV", "LM1"), ("L0", "2"))
            self.assertEqual(t.buscar("Proteccion Grupo A", "13,2KV", "LM1", "103"), ("1XP3", "19"))
            self.assertEqual(t.buscar("Proteccion Grupo A", "13,2KV", "LM2", "104"), ("1XP4", "19"))
            self.assertEqual(t.buscar("Proteccion Grupo A", "13,2KV", "Entrada TR01", "101"), ("1XP1", "22"))
            self.assertEqual(conflictos, [])

    def test_encuentra_las_columnas_por_su_titulo(self):
        with tempfile.TemporaryDirectory() as d:
            ruta = Path(d) / "oficial.xlsx"
            excel_de_prueba(ruta)
            wb = openpyxl.load_workbook(ruta)
            wb.active.insert_cols(1, 2)                      # las columnas cambian de letra: no debe importar
            wb.save(ruta)
            reglas, _ = aprender_conexionado.aprender(ruta)
            self.assertGreaterEqual(len(reglas), 4)


@unittest.skipUnless(OFICIAL.exists(), "no hay acceso al listado oficial de Senillosa")
class TestListadoOficialDeSenillosa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.reglas, cls.conflictos = aprender_conexionado.aprender(OFICIAL)
        cls.t = Conexionado(cls.reglas)

    def test_interruptor_y_seccionador_de_33kv(self):
        self.assertEqual(self.t.buscar("Interruptor 252 / 01 Cerrado", "33KV", "TR01 Lado 33KV Campo 2"), ("-XP1", "4"))
        self.assertEqual(self.t.buscar("Seccionador 289 / 01 Abierto", "33KV", "TR01 Lado 33KV Campo 2"), ("L0", "43"))

    def test_los_campos_de_13kv_se_distinguen_por_tipo(self):
        self.assertEqual(self.t.buscar("Reconectador 152/01 abierto", "13,2KV", "Entrada TR01"), ("IOM-XP1", "12"))
        self.assertEqual(self.t.buscar("Reconectador 152/03 abierto", "13,2KV", "LM1"), ("IOM-XP1", "NA1"))

    def test_las_protecciones_de_las_lineas_usan_el_numero_de_campo(self):
        self.assertEqual(self.t.buscar("Proteccion Grupo A", "13,2KV", "LM2", "104"), ("1XP4", "19"))

    def test_no_hay_reglas_que_se_contradigan(self):
        self.assertEqual(self.conflictos, [])


if __name__ == "__main__":
    unittest.main()
