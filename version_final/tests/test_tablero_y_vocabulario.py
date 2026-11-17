"""Tablero por campo (conexionado, etapa 4 acotada) y vocabulario de la DESC. SCADA."""
import tempfile
import unittest
from pathlib import Path

import openpyxl

import descripcion as d
import libro

PM = Path(__file__).resolve().parents[3]
TCONTROL = PM / "senillosa" / "TCONTROL 13,2kV" / "3-Funcional" / "USRE-01-19-SET-Ct-PL-Ad-0821_r3.pdf"
TDCI = PM / "senillosa" / "TDCI" / "3-Funcional" / "USRE-01-19-SET-Ct-PL-Ad-0808_r4.pdf"
PDF_6402 = Path(__file__).resolve().parents[2] / "Ejemplos" / "ETAP-0325-ET-CT-PL-EF-6402_1.pdf"


class TestDescScada(unittest.TestCase):
    """Abreviaturas ampliadas con las Reglas y con cómo abrevia el Excel oficial de Senillosa."""

    def casos(self, prefijo, esperados):
        for texto, esperado in esperados.items():
            self.assertEqual(d.descripcion_scada(prefijo, texto), (esperado, True), texto)

    def test_alarmas_del_campo(self):
        self.casos("103", {
            "Falla protección de cuba cable": "103 F/PROT CUBA CAB",
            "Disparo protección de cuba cable": "103 DISP P/CUBA CAB",
            "Tensiones interrumpidas": "103 U INTERR",
            "TV- Llave termomagnética abierta": "103 TV LLAVE TM AB",
            "Campo 03 mando en Telecontrol/en Distancia": "103 LLAVE T/D",
            "Habilita recierre": "103 HAB RECIERRE",
            "Señalización protección grupo A": "103 SENAL PROT G/A",
            "Señalización protección grupo B": "103 SENAL PROT G/B"})

    def test_servicios_auxiliares_como_el_excel_oficial(self):
        self.casos("SAC", {"Interruptor Ppal. 110Vcc Abierto": "SAC INT 110VCC AB",       # oficial: SACC INT 110VCC AB
                           "Falta tensión interruptor ppal. 48Vcc": "SAC F/U INT 48VCC",    # oficial: SACC F/U INT 48VCC
                           "Falta tensión barra 24 Vcc": "SAC F/U BAR 24VCC"})              # oficial: … F/U BAR …VCC

    def test_la_proteccion_de_trafo_tp1(self):
        self.casos("TP1", {"PROTECCION PRINCIPAL DISPARO GENERAL": "TP1 PP DISP GRL",       # oficial: PP DISP GRL
                           "PROTECCION RESPALDO DISPARO GENERAL": "TP1 PR DISP GRL"})       # oficial: PR DISP GRL

    def test_en_un_campo_especial_la_tension_del_rotulo_distingue_las_alarmas(self):
        a = d.descripcion_scada("SAC", "Falta tensión comando 33 KV")[0]
        b = d.descripcion_scada("SAC", "Falta tensión comando 13,2 KV")[0]
        self.assertEqual((a, b), ("SAC F/U CMDO 33", "SAC F/U CMDO 13"))
        self.assertNotEqual(a, b)

    def test_en_un_campo_numerado_la_tension_no_va_en_la_descripcion(self):
        self.assertEqual(d.descripcion_scada("204", "Falta tensión comando 33 KV")[0], "204 F/U CMDO")

    def test_siempre_en_mayuscula_y_de_20_caracteres_como_maximo(self):
        for texto in ["Una descripcion larguisima que no entra de ninguna manera en veinte caracteres", "x"]:
            r, _ = d.descripcion_scada("101", texto)
            self.assertEqual((r, len(r) <= 20), (r.upper(), True))


@unittest.skipUnless(TCONTROL.exists() and TDCI.exists(), "faltan los PDF de Senillosa")
class TestSenillosa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = libro.Libro()
        cls.L.agregar_pdf(TCONTROL)
        cls.L.agregar_pdf(TDCI)
        cls.L.calcular()
        cls.db = cls.L.base()

    def test_casi_todas_las_descripciones_se_resuelven(self):
        con_desc = [b for b in self.db.senales if b.desc_scada and not b.es_hueco]
        sin = [b for b in con_desc if b.sin_resolver]
        self.assertLessEqual(len(sin), 5, [b.desc_scada for b in sin])         # antes eran 85 de 247

    def test_no_quedan_descripciones_repetidas_entre_senales(self):
        vistas = {}
        for b in self.db.senales:
            if b.desc_scada and not (b.es_reserva or b.segunda_fila or b.funcion == "COMANDO" or b.es_hueco):
                vistas.setdefault(b.desc_scada, []).append(b.id)
        self.assertEqual({k: v for k, v in vistas.items() if len(v) > 1}, {})

    def test_el_tablero_de_cada_campo(self):
        por_campo = {}
        for b in self.db.senales:
            if not b.es_hueco:
                por_campo.setdefault(b.campo, set()).add(b.tablero)
        self.assertEqual(por_campo["01"], {"TC1-01"})
        self.assertEqual(por_campo["03"], {"TC1-03"})
        self.assertEqual(por_campo["05"], {"TC1-05"})
        self.assertEqual(por_campo["SAA"], {"TDCI"})
        self.assertEqual(por_campo["SAC"], {"TDCI"})

    def test_los_huecos_no_llevan_tablero(self):
        self.assertTrue(all(b.tablero == "" for b in self.db.senales if b.es_hueco))

    def test_lo_que_escribe_el_usuario_manda_sobre_el_tablero_deducido(self):
        self.L.datos.tablero["103"] = "TC1-03A"
        try:
            tabs = {b.tablero for b in self.L.base().senales if b.campo == "03" and not b.es_hueco}
            self.assertEqual(tabs, {"TC1-03A"})
            self.assertEqual(self.L.tablero_defecto(next(c for c in self.L.campos if c.clave == "103")), "TC1-03")
        finally:
            self.L.datos.tablero.pop("103")

    def test_el_tablero_sale_en_la_columna_R_del_formato_completo(self):
        with tempfile.TemporaryDirectory() as t:
            self.L.exportar_formato("completo", Path(t) / "x.xlsx", db=self.db)
            ws = openpyxl.load_workbook(Path(t) / "x.xlsx").active
        valores = {ws.cell(r, 18).value for r in range(5, ws.max_row + 1)} - {None}
        self.assertTrue({"TC1-03", "TDCI"} <= valores, valores)


@unittest.skipUnless(PDF_6402.exists(), "falta el PDF de ejemplo")
class TestEtap(unittest.TestCase):
    def test_el_tablero_de_los_campos_del_etap_sigue_la_misma_convencion(self):
        L = libro.Libro()
        L.agregar_pdf(PDF_6402)
        L.calcular()
        tabs = {b.tablero for b in L.base().senales if not b.es_hueco and b.campo == "04"}
        self.assertEqual(tabs, {"TC2-04"})                                       # el cajetín del plano dice TC2-04


if __name__ == "__main__":
    unittest.main()
