"""Etapa 3: validaciones (avisos celestes y rosas). Informan; no modifican la base."""
import tempfile
import unittest
from pathlib import Path

import openpyxl

import avisos
import formatos
import libro
import perfiles
from avisos import CELESTE, ROSA
from avisos import excel as aviso_excel
from avisos.reglas import cargar_config
from base import ProyectoDB, SenalBase

PERFIL = perfiles.cargar_perfil("EPEN")
CFG = cargar_config(PERFIL)
PDF_6402 = Path(__file__).resolve().parents[2] / "Ejemplos" / "ETAP-0325-ET-CT-PL-EF-6402_1.pdf"


def db_de(*senales: SenalBase) -> ProyectoDB:
    db = ProyectoDB()
    for i, b in enumerate(senales, 1):
        b.id = b.id or i
        if b.item is None and not b.es_hueco:
            b.item = i
        db.senales.append(b)
    return db


def sb(**kw) -> SenalBase:
    base = dict(funcion="ALARMAS", nivel="13,2KV", campo="03", controlador="SEL-2241-13,2kV", tag_hmi="X", desc_hmi="X",
                tag_scada="103.101", offset=100, desc_scada="103 ALGO", s0="NORMAL", s1="ACTUO")
    base.update(kw)
    return SenalBase(**base)


def codigos(db, gravedad=None, **kw):
    return [a.codigo for a in avisos.validar(db, cfg=CFG, **kw) if gravedad in (None, a.gravedad)]


class TestCelestes(unittest.TestCase):
    def test_tag_scada_repetido(self):
        db = db_de(sb(tag_hmi="A"), sb(tag_hmi="B", offset=101))
        self.assertEqual(codigos(db, CELESTE).count("TAG_SCADA_DUPLICADO"), 1)

    def test_una_senal_y_su_comando_comparten_tag(self):
        db = db_de(sb(funcion="SEÑALIZACION", tag_scada="103.222C", offset=5, tag_hmi="A"),
                   sb(funcion="COMANDO", tag_scada="103.222C", offset=5, tag_hmi="B"))
        self.assertNotIn("TAG_SCADA_DUPLICADO", codigos(db))
        self.assertNotIn("OFFSET_REPETIDO", codigos(db))

    def test_dos_comandos_con_el_mismo_tag_si_se_marcan(self):
        db = db_de(sb(funcion="COMANDO", tag_scada="103.222C", tag_hmi="A"),
                   sb(funcion="COMANDO", tag_scada="103.222C", offset=101, tag_hmi="B"))
        self.assertIn("TAG_SCADA_DUPLICADO", codigos(db))

    def test_reservas_y_vacios_no_cuentan_como_repetidos(self):
        db = db_de(sb(tag_scada="N/A", tag_hmi="N/A", es_reserva=True, funcion="RESERVA"),
                   sb(tag_scada="N/A", tag_hmi="N/A", offset=101, es_reserva=True, funcion="RESERVA"),
                   sb(tag_scada="", tag_hmi="", offset=102, es_hueco=True))
        c = codigos(db)
        self.assertNotIn("TAG_SCADA_DUPLICADO", c)
        self.assertNotIn("TAG_HMI_DUPLICADO", c)

    def test_tag_hmi_repetido(self):
        db = db_de(sb(tag_scada="103.101"), sb(tag_scada="103.111", offset=101))
        self.assertIn("TAG_HMI_DUPLICADO", codigos(db, CELESTE))

    def test_offset_repetido_entre_dos_digitales(self):
        db = db_de(sb(tag_hmi="A"), sb(tag_hmi="B", tag_scada="103.111"))
        self.assertIn("OFFSET_REPETIDO", codigos(db, CELESTE))

    def test_offset_repetido_valido_digital_y_medicion(self):
        db = db_de(sb(tag_hmi="A"), sb(funcion="MEDICION", tag_hmi="B", tag_scada="103.01AU", offset=100,
                                       min_raw=0, max_raw=32767, min_eu=0, max_eu=327.67, unidad="KV", s0=None, s1=None))
        self.assertNotIn("OFFSET_REPETIDO", codigos(db))

    def test_offset_repetido_entre_dos_mediciones(self):
        m = dict(funcion="MEDICION", offset=7, min_raw=0, max_raw=32767, min_eu=0, max_eu=327.67, unidad="KV", s0=None, s1=None)
        db = db_de(sb(tag_hmi="A", tag_scada="103.01AU", **m), sb(tag_hmi="B", tag_scada="103.02AV", **m))
        self.assertIn("OFFSET_REPETIDO", codigos(db, CELESTE))

    def test_las_filas_libres_no_cuentan_en_los_offsets(self):
        db = db_de(sb(tag_hmi="A"), sb(tag_scada="", tag_hmi="", offset=100, es_hueco=True, desc_scada="", desc_hmi=""))
        self.assertNotIn("OFFSET_REPETIDO", codigos(db))

    def test_item_repetido(self):
        db = db_de(sb(tag_hmi="A", item=4), sb(tag_hmi="B", tag_scada="103.111", offset=101, item=4))
        self.assertIn("ITEM_REPETIDO", codigos(db, CELESTE))

    def test_formato_del_tag_segun_las_reglas(self):
        buenos = ["103.101", "103.222C", "TP1.101", "SAA.201", "SAC.351", "101.01AU", "104.08AFP", "105.13IP"]
        for t in buenos:
            f = "MEDICION" if t[-1:].isalpha() and not t.endswith("C") else "ALARMAS"
            db = db_de(sb(tag_scada=t, funcion=f, min_raw=0, max_raw=1, min_eu=0, max_eu=1, unidad="A"))
            self.assertNotIn("TAG_FUERA_DE_FORMATO", codigos(db), t)
        for t in ["103101", "XX.101", "SACA.101", "103.1", "103.101X", "10.101"]:
            db = db_de(sb(tag_scada=t))
            self.assertIn("TAG_FUERA_DE_FORMATO", codigos(db, CELESTE), t)

    def test_un_comando_sin_c_final_esta_mal(self):
        self.assertIn("TAG_FUERA_DE_FORMATO", codigos(db_de(sb(funcion="COMANDO", tag_scada="103.222"))))

    def test_desc_scada_de_mas_de_20_caracteres(self):
        self.assertIn("DESC_SCADA_LARGA", codigos(db_de(sb(desc_scada="x" * 21)), CELESTE))
        self.assertNotIn("DESC_SCADA_LARGA", codigos(db_de(sb(desc_scada="x" * 20))))

    def test_controlador_de_otra_tension(self):
        self.assertIn("CONTROLADOR_OTRA_TENSION", codigos(db_de(sb(controlador="SEL-2241-33kV")), CELESTE))
        self.assertNotIn("CONTROLADOR_OTRA_TENSION", codigos(db_de(sb(controlador="SEL-2241-13,2kV"))))
        self.assertNotIn("CONTROLADOR_OTRA_TENSION", codigos(db_de(sb(controlador="15203_MED"))))      # no nombra tensión
        self.assertNotIn("CONTROLADOR_OTRA_TENSION", codigos(db_de(sb(controlador="SEL-2241-DCI"))))

    def test_escala_invertida(self):
        m = dict(funcion="MEDICION", tag_scada="103.01AU", min_raw=10, max_raw=5, min_eu=0, max_eu=1, unidad="KV", s0=None, s1=None)
        self.assertIn("ESCALA_INVERTIDA", codigos(db_de(sb(**m)), CELESTE))


class TestRosas(unittest.TestCase):
    def test_desc_scada_sin_resolver(self):
        self.assertIn("DESC_SCADA_SIN_RESOLVER", codigos(db_de(sb(sin_resolver=True)), ROSA))

    def test_falta_informacion(self):
        av = [a for a in avisos.validar(db_de(sb(tag_scada="", offset=None)), cfg=CFG) if a.codigo == "FALTA_INFORMACION"]
        self.assertEqual(len(av), 1)
        self.assertIn("tag_scada", av[0].mensaje)
        self.assertIn("offset", av[0].mensaje)

    def test_una_medicion_con_la_escala_incompleta(self):
        m = dict(funcion="MEDICION", tag_scada="103.01AU", min_raw=0, max_raw=None, min_eu=0, max_eu=1, unidad="", s0=None, s1=None)
        av = [a for a in avisos.validar(db_de(sb(**m)), cfg=CFG) if a.codigo == "FALTA_INFORMACION"]
        self.assertIn("max_raw", av[0].mensaje)
        self.assertIn("unidad", av[0].mensaje)

    def test_las_reservas_y_la_segunda_fila_no_piden_datos(self):
        db = db_de(sb(es_reserva=True, funcion="RESERVA", tag_scada="N/A", tag_hmi="N/A", desc_hmi="", s0="N/A", s1="N/A"),
                   sb(segunda_fila=True, tag_scada="", tag_hmi="", desc_hmi="", desc_scada="", s0=None, s1=None, offset=101))
        self.assertNotIn("FALTA_INFORMACION", codigos(db))

    def test_tag_hmi_y_desc_hmi_con_distinto_equipo(self):
        db = db_de(sb(tag_hmi="Interruptor_25201_Alarma", desc_hmi="Interruptor 25204 Alarma"))
        self.assertIn("TAG_Y_DESC_HMI", codigos(db, ROSA))
        db = db_de(sb(tag_hmi="Interruptor_25201_Alarma", desc_hmi="Interruptor 25201 Alarma"))
        self.assertNotIn("TAG_Y_DESC_HMI", codigos(db))

    def test_el_conexionado_incompleto_solo_se_pide_con_el_formato_completo(self):
        db = db_de(sb())
        self.assertNotIn("CONEXIONADO_INCOMPLETO", codigos(db))
        self.assertIn("CONEXIONADO_INCOMPLETO", codigos(db, ROSA, pide_conexionado=True))
        completo = sb(tablero="TC2-01", bornera_tablero="X1.1", borne_tablero="71")
        self.assertNotIn("CONEXIONADO_INCOMPLETO", codigos(db_de(completo), pide_conexionado=True))

    def test_los_avisos_de_lectura_se_muestran(self):
        av = avisos.validar(db_de(sb()), cfg=CFG, avisos_de_lectura=["Campo 01: el nivel no figura en el cajetín."])
        self.assertIn(("LECTURA", ROSA), [(a.codigo, a.gravedad) for a in av])


class TestGenerales(unittest.TestCase):
    def test_validar_no_modifica_la_base_y_pone_los_celestes_primero(self):
        db = db_de(sb(tag_hmi="A", sin_resolver=True), sb(tag_hmi="B", offset=101, desc_scada="x" * 25, tag_scada="103.111"))
        antes = db.a_dict()
        av = avisos.validar(db, cfg=CFG)
        self.assertEqual(db.a_dict(), antes)
        self.assertEqual(av[0].gravedad, CELESTE)
        self.assertEqual({a.gravedad for a in av}, {CELESTE, ROSA})

    def test_un_aviso_dice_donde_esta(self):
        db = db_de(sb(hoja=42, archivo="plano.pdf", campo="03", item=17, desc_scada="x" * 25))
        a = next(a for a in avisos.validar(db, cfg=CFG) if a.codigo == "DESC_SCADA_LARGA")
        self.assertEqual((a.item, a.hoja, a.campo), (17, 42, "03"))
        self.assertIn("hoja 42", a.donde)
        self.assertIn("ITEM 17", a.donde)

    def test_agregar_una_regla_nueva_no_toca_el_resto(self):
        def regla_de_prueba(ctx):
            return [avisos.Aviso(ROSA, "PRUEBA", "hola")]
        avisos.REGLAS.append(regla_de_prueba)
        try:
            self.assertIn("PRUEBA", codigos(db_de(sb())))
        finally:
            avisos.REGLAS.remove(regla_de_prueba)


@unittest.skipUnless(PDF_6402.exists(), "falta el PDF de ejemplo")
class TestConElPlanoReal(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = libro.Libro()
        cls.L.agregar_pdf(PDF_6402)
        cls.L.calcular()
        cls.db = cls.L.base()

    def test_lo_que_arma_la_app_no_contradice_ninguna_regla(self):
        celestes = [a for a in avisos.validar(self.db, PERFIL, avisos_de_lectura=self.L.avisos) if a.gravedad == CELESTE]
        self.assertEqual(celestes, [], [a.mensaje for a in celestes])

    def test_un_dato_corregido_a_mano_que_rompe_una_regla_se_avisa_pero_no_se_cambia(self):
        import desde_pdf
        proyecto, _, _ = self.L.proyecto()
        clave = next(c for c, (_, s) in zip(desde_pdf.claves_de(proyecto),
                                            ((None, s) for nv in proyecto.niveles for ca in nv.campos for s in ca.senales))
                     if s.tag_scada not in ("", "N/A", None))
        self.L.editar(clave, "desc", "UNA DESCRIPCION MUY LARGA DE VERDAD")
        try:
            db = self.L.base()
            av = avisos.validar(db, PERFIL)
            self.assertIn("DESC_SCADA_LARGA", [a.codigo for a in av if a.gravedad == CELESTE])
            self.assertIn("UNA DESCRIPCION MUY LARGA DE VERDAD", [b.desc_scada for b in db.senales])   # no la tocó
        finally:
            self.L.deshacer_edicion(clave, "desc")

    def test_la_verificacion_del_excel_detecta_una_celda_cambiada(self):
        formato = formatos.cargar("reducido")
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "x.xlsx"
            self.L.exportar_formato("reducido", ruta, db=self.db)
            self.assertEqual(aviso_excel.verificar(self.db, formato, ruta), [])
            wb = openpyxl.load_workbook(ruta)
            ws = wb[formato.hoja]
            ws["H6"] = "999.999"                                             # alguien cambió un TAG SCADA a mano en el Excel
            wb.save(ruta)
            av = aviso_excel.verificar(self.db, formato, ruta)
        self.assertEqual([a.codigo for a in av], ["EXCEL_DISTINTO_DE_LA_BASE"])
        self.assertEqual(av[0].gravedad, CELESTE)
        self.assertIn("H6", av[0].mensaje)


if __name__ == "__main__":
    unittest.main()
