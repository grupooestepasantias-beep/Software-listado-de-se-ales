"""Estilo USRE (listado de Senillosa hecho a mano) frente al ETAP."""
import tempfile
import unittest
from pathlib import Path

import openpyxl

import estados as est
import estilo
import libro
import numeracion as num

TCONTROL = (Path(__file__).resolve().parents[3] / "senillosa" / "TCONTROL 13,2kV" / "3-Funcional"
            / "USRE-01-19-SET-Ct-PL-Ad-0821_r3.pdf")


class TestTextos(unittest.TestCase):
    def test_detecta_el_estilo_por_el_nombre_del_pdf(self):
        self.assertEqual(estilo.detectar(["USRE-01-19-SET-Ct-PL-Ad-0821_r3.pdf"]), estilo.USRE)
        self.assertEqual(estilo.detectar(["ETAP-0325-ET-CT-PL-EF-6402_1.pdf"]), estilo.ETAP)

    def test_codigo_de_equipo_sin_barra(self):
        self.assertEqual(estilo.sin_barra("Reconectador 152/01 alarma general"), "Reconectador 15201 alarma general")
        self.assertEqual(estilo.sin_barra("Seccionador 189/01 falta tension"), "Seccionador 18901 falta tension")

    def test_titulo(self):
        self.assertEqual(estilo.titulo("Falta tension de alimentacion"), "Falta Tension de Alimentacion")
        self.assertEqual(estilo.titulo("Proteccion grupo a"), "Proteccion Grupo A")
        self.assertEqual(estilo.titulo("Llave TM en tablero"), "Llave TM en Tablero")

    def test_partir_pares(self):
        self.assertEqual(estilo.partir_par("Reconectador 152/01 Abierto", "Reconectador 152/01 Cerrado"),
                         ("Reconectador 152/01", "Abierto", "Cerrado"))
        self.assertEqual(estilo.partir_par("Reconectador 152/01 en local", "Reconectador 152/01 en remoto"),
                         ("Reconectador 152/01", "en local", "en remoto"))
        self.assertEqual(estilo.partir_par("Apertura reconectador 152/01", "Cierre reconectador 152/01"),
                         ("reconectador 152/01", "Apertura", "Cierre"))
        self.assertEqual(estilo.texto_doble("Reconectador 152/01 en local", "Reconectador 152/01 en remoto"),
                         "Reconectador 152/01 En local/En remoto")

    def test_estados_usre(self):
        ab = num.Senal(num.SENALIZACION, "x", doble=True, pares=("Seccionador 18901 Abierto", "Seccionador 18901 Cerrado"))
        self.assertEqual(est.estados(ab, None, estilo.USRE), ["err_0", "ABIERTO", "CERRADO", "err_1", "N/A"])
        una = num.Senal(num.SENALIZACION, "x", dos_estados=True,
                        pares=("Seccionador 18901 en remoto", "Seccionador 18901 en local"))
        self.assertEqual(est.estados(una, None, estilo.USRE), ["REMOTO", "LOCAL", "N/A", "N/A", "N/A"])
        self.assertEqual(est.estados(num.Senal(num.ALARMAS, "Seccionador 18901 Falta Tension"), None, estilo.USRE)[1], "FALTA")
        self.assertEqual(est.estados(num.Senal(num.ALARMAS, "Falla filtro serie"), None, estilo.USRE)[1], "FALLA")
        self.assertEqual(est.estados(num.Senal(num.ALARMAS, "Alarma general"), None, estilo.USRE)[1], "ACTUO")
        cmd = est.estados(ab, None, estilo.USRE, ("Reconectador 152/01 Apertura", "Reconectador 152/01 Cierre"))
        self.assertEqual(cmd[:2], ["ABRIR", "CERRAR"])

    def test_el_estilo_etap_no_cambia(self):
        ab = num.Senal(num.SENALIZACION, "x", doble=True, pares=("Seccionador 18901 Abierto", "Seccionador 18901 Cerrado"))
        self.assertEqual(est.estados(ab), ["error_0", "AB", "CE", "error_1", "N/A"])


@unittest.skipUnless(TCONTROL.exists(), "falta el PDF de Senillosa")
class TestSenillosa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = libro.Libro()
        cls.L.agregar_pdf(TCONTROL)
        cls.L.calcular()
        with tempfile.TemporaryDirectory() as t:
            cls.L.exportar(Path(t) / "x.xlsx")
            ws = openpyxl.load_workbook(Path(t) / "x.xlsx").active
        cls.filas = [[ws.cell(r, c).value for c in range(1, 16)] for r in range(6, ws.max_row + 1)]

    def test_se_detecta_usre_y_las_variables_empiezan_en_10(self):
        self.assertEqual(self.L.datos.estilo, estilo.USRE)
        primero = next(f for f in self.filas if f[7])
        self.assertTrue(primero[7].endswith(".101"))

    def test_senal_doble_con_un_solo_tag_hmi_y_segunda_fila_vacia(self):
        i = next(i for i, f in enumerate(self.filas) if f[5] == "Reconectador_15201_Abierto_Cerrado")
        self.assertEqual(self.filas[i][6], "Reconectador 15201 Abierto/Cerrado")
        self.assertEqual(self.filas[i][10:14], ["err_0", "ABIERTO", "CERRADO", "err_1"])
        seg = self.filas[i + 1]
        self.assertEqual((seg[5], seg[6], seg[7]), (None, None, None))
        self.assertEqual(seg[8], self.filas[i][8] + 1)               # ocupa el offset siguiente

    def test_en_local_con_una_sola_entrada_es_una_fila(self):
        i = next(i for i, f in enumerate(self.filas) if f[5] and f[5].startswith("Reconectador_15201_En_Local"))
        self.assertTrue(self.filas[i][7].endswith("2"))               # tag de 2 bits
        self.assertEqual(self.filas[i + 1][8], self.filas[i][8] + 1)  # …pero un solo offset
        self.assertTrue(self.filas[i + 1][5])                         # la fila siguiente ya es otra señal

    def test_mediciones_en_los_campos_de_control(self):
        medidas = [f for f in self.filas if f[3] and f[3].startswith("SATEC")]
        self.assertEqual(len(medidas), 13 * 4)                       # 4 campos de control (101, 103, 104, 105)

    def test_el_codigo_de_equipo_va_sin_barra(self):
        textos = " ".join(str(f[5]) + str(f[6]) for f in self.filas)
        self.assertNotIn("152/01", textos)


if __name__ == "__main__":
    unittest.main()
