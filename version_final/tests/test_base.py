"""Etapa 1: la base central (SenalBase + ProyectoDB) y que el Excel desde la base sea idéntico al de siempre."""
import json
import tempfile
import unittest
from pathlib import Path

import openpyxl

import desde_pdf
import libro
from base import MANUAL, PDF, REGLA, ProyectoDB, SenalBase
from modelo import Caratula

PDF_6402 = Path(__file__).resolve().parents[2] / "Ejemplos" / "ETAP-0325-ET-CT-PL-EF-6402_1.pdf"
TCONTROL = (Path(__file__).resolve().parents[3] / "senillosa" / "TCONTROL 13,2kV" / "3-Funcional"
            / "USRE-01-19-SET-Ct-PL-Ad-0821_r3.pdf")


class TestSenalBase(unittest.TestCase):
    def test_ida_y_vuelta_por_dict(self):
        b = SenalBase(id=3, funcion="ALARMAS", tag_scada="101.101", offset=325, s0="NORMAL", origen={"tag_scada": REGLA})
        self.assertEqual(SenalBase.de_dict(b.a_dict()), b)

    def test_lo_que_no_se_conoce_queda_vacio(self):
        b = SenalBase()
        for nombre in ("tablero", "bornera_tablero", "borne_tablero", "bornera_equipo", "borne_equipo", "indice_dnp"):
            self.assertIn(getattr(b, nombre), ("", None), nombre)

    def test_lo_manual_no_se_degrada_a_regla(self):
        b = SenalBase()
        b.poner("desc_scada", "MIA", MANUAL)
        b.poner("desc_scada", "OTRA", REGLA)
        self.assertEqual(b.fuente_de("desc_scada"), MANUAL)
        b.poner("desc_scada", "", REGLA)                               # vaciar el dato borra también su fuente
        self.assertEqual(b.fuente_de("desc_scada"), "")

    def test_una_version_mas_nueva_se_rechaza(self):
        with self.assertRaises(ValueError):
            ProyectoDB.de_dict({"version": 99})


def _celdas(ws):
    return [[ws.cell(r, c).value for c in range(1, ws.max_column + 1)] for r in range(1, ws.max_row + 1)]


def _relleno_j(ws):
    return [ws.cell(r, 10).fill.fgColor.rgb for r in range(1, ws.max_row + 1)]


@unittest.skipUnless(PDF_6402.exists(), "falta el PDF de ejemplo")
class TestBaseDesdeElPlano(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = libro.Libro()
        cls.L.agregar_pdf(PDF_6402)
        cls.L.calcular()
        cls.db = cls.L.base()

    def test_tiene_una_senal_base_por_fila(self):
        proyecto, _, _ = self.L.proyecto()
        total = sum(len(c.senales) for nv in proyecto.niveles for c in nv.campos)
        self.assertEqual(len(self.db.senales), total)
        self.assertEqual([b.id for b in self.db.senales], list(range(1, total + 1)))

    def test_el_proyecto_de_vuelta_es_igual(self):
        proyecto, marcas, huecos = self.L.proyecto()
        marcas = self.L.marcas(proyecto, marcas)
        p2, m2, h2 = self.db.a_proyecto()
        self.assertEqual(p2.to_dict(), proyecto.to_dict())
        self.assertEqual((m2, h2), (marcas, huecos))

    def test_el_excel_desde_la_base_es_identico(self):
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t) / "directo.xlsx", Path(t) / "base.xlsx"
            n1 = self.L.exportar(a)
            n2 = self.L.exportar_base(self.db, b)
            wa, wb = openpyxl.load_workbook(a).active, openpyxl.load_workbook(b).active
            self.assertEqual(n1, n2)
            self.assertEqual(_celdas(wa), _celdas(wb))
            self.assertEqual(_relleno_j(wa), _relleno_j(wb))
            self.assertEqual(sorted(map(str, wa.merged_cells.ranges)), sorted(map(str, wb.merged_cells.ranges)))

    def test_guardar_y_cargar_la_base(self):
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "base.json"
            self.db.guardar(ruta)
            otra = ProyectoDB.cargar(ruta)
        self.assertEqual(otra.a_dict(), self.db.a_dict())

    def test_mediciones_con_escalas_y_estados_sin_ellas(self):
        med = [b for b in self.db.senales if b.funcion == "MEDICION" and not b.es_hueco]
        dig = [b for b in self.db.senales if b.funcion in ("ALARMAS", "SEÑALIZACION") and b.tag_scada not in ("", "N/A")]
        self.assertTrue(med and dig)
        self.assertTrue(all(b.min_raw is not None and b.max_eu is not None and b.s0 is None for b in med))
        self.assertTrue(all(b.s0 is not None and b.min_raw is None for b in dig))

    def test_cada_senal_sabe_de_que_hoja_y_pdf_salio(self):
        leidas = [b for b in self.db.senales if not b.es_hueco and b.funcion in ("ALARMAS", "SEÑALIZACION")
                  and not b.es_reserva and not b.segunda_fila]
        self.assertTrue(all(b.hoja and b.archivo.endswith(".pdf") for b in leidas))

    def test_origen_de_los_datos(self):
        b = next(x for x in self.db.senales if x.tag_scada not in ("", "N/A") and x.funcion == "ALARMAS")
        self.assertEqual((b.fuente_de("tag_scada"), b.fuente_de("offset"), b.fuente_de("tag_hmi")), (REGLA, REGLA, PDF))
        self.assertEqual(b.fuente_de("tablero"), "")                    # lo que no hay no tiene fuente

    def test_el_indice_dnp_es_el_offset_y_el_conexionado_nuevo_queda_vacio(self):
        self.assertTrue(all(b.indice_dnp == b.offset for b in self.db.senales))
        self.assertTrue(any(b.indice_dnp is not None for b in self.db.senales))
        self.assertEqual(self.db.senales[0].fuente_de("indice_dnp"), REGLA)
        self.assertTrue(all(not b.tablero and not b.borne_equipo and not b.bornera_tablero for b in self.db.senales))

    def test_el_indice_dnp_sigue_al_offset_corregido_a_mano(self):
        proyecto, _, _ = self.L.proyecto()
        clave = desde_pdf.claves_de(proyecto)[0]
        self.L.editar(clave, "offset", "999")
        try:
            b = self.L.base().senales[0]
            self.assertEqual((b.offset, b.indice_dnp), (999, 999))
        finally:
            self.L.deshacer_edicion(clave, "offset")

    def test_lo_corregido_a_mano_figura_como_manual(self):
        proyecto, _, _ = self.L.proyecto()
        clave = desde_pdf.claves_de(proyecto)[0]
        self.L.editar(clave, "desc", "MI DESCRIPCION")
        try:
            db = self.L.base()
            self.assertEqual(db.senales[0].desc_scada, "MI DESCRIPCION")
            self.assertEqual(db.senales[0].fuente_de("desc_scada"), MANUAL)
            self.assertEqual([(b.id, n) for b, n in db.con_fuente(MANUAL)], [(1, "desc_scada")])
        finally:
            self.L.deshacer_edicion(clave, "desc")

    def test_el_proyecto_guardado_es_version_2_y_abre_tambien_el_viejo(self):
        with tempfile.TemporaryDirectory() as t:
            nuevo, viejo = Path(t) / "v2.json", Path(t) / "v1.json"
            self.L.guardar(nuevo, Caratula(obra="OBRA X"))
            d = json.loads(nuevo.read_text(encoding="utf-8"))
            self.assertEqual(d["version"], 2)
            self.assertEqual(len(d["base"]["senales"]), len(self.db.senales))
            d.pop("base")                                              # un proyecto como los de la versión 1
            d["version"] = 1
            viejo.write_text(json.dumps(d), encoding="utf-8")
            otro = libro.Libro()
            caratula, faltan = otro.abrir(viejo)
        self.assertEqual((faltan, caratula["obra"], len(otro.filas)), ([], "OBRA X", len(self.L.filas)))


@unittest.skipUnless(TCONTROL.exists(), "falta el PDF de Senillosa")
class TestBaseUsre(unittest.TestCase):
    def test_el_excel_del_estilo_usre_tambien_sale_identico(self):
        L = libro.Libro()
        L.agregar_pdf(TCONTROL)
        L.calcular()
        with tempfile.TemporaryDirectory() as t:
            a, b = Path(t) / "directo.xlsx", Path(t) / "base.xlsx"
            L.exportar(a)
            L.exportar_base(L.base(), b)
            self.assertEqual(_celdas(openpyxl.load_workbook(a).active), _celdas(openpyxl.load_workbook(b).active))


if __name__ == "__main__":
    unittest.main()
