import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import generador
import perfiles
from modelo import NA, Campo, Funcion, Nivel, Proyecto, Senal, TipoPunto

EJEMPLO = Path(r"\\192.168.15.120\PasantiasMM\Sofware listado\Ejemplos\ETAP-0722-ET-CT-MC-LI-6209-1-Lista señales - CAO.xlsx")


def alarma(texto, **kw):
    return Senal(funcion=Funcion.ALARMAS, observaciones=texto, **kw)


def proyecto(senales, offsets=None, numero="03", codigo="3", prefijo="303LC"):
    campo = Campo(numero, "LAT Loma Campana Campo 303", prefijo, "SEL-2241-132kV", senales)
    return Proyecto(perfil_id="EPEN", niveles=[Nivel("132KV", codigo, [campo])],
                    offsets_iniciales=offsets if offsets is not None else {"DI": 200, "AI": 200, "DO": 300})


class TestGenerador(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = perfiles.cargar_perfil("EPEN")

    def test_alarmas_tag_offset_estados(self):
        proy = proyecto([alarma("Seccionador 329SA03 Falta Tensión Auxiliar"),
                         alarma("Seccionador 329SA03 Maniobra Incompleta")])
        generador.generar(proy, self.p)
        a, b = proy.niveles[0].campos[0].senales
        self.assertEqual((a.tag_scada, b.tag_scada), ("303.001", "303.011"))
        self.assertEqual((a.offset, b.offset), (200, 201))
        self.assertEqual((a.s0, a.s1, a.s2, a.s3), ("NORMAL", "ACTUO", NA, NA))
        self.assertIs(a.tipo_punto, TipoPunto.DI)
        self.assertEqual(a.controlador, "SEL-2241-132kV")
        self.assertEqual(a.tag_hmi, "Seccionador_329SA03_Falta_Tension_Auxiliar")
        self.assertEqual(a.desc_hmi, "303LC Seccionador 329SA03 Falta Tension Auxiliar")
        self.assertEqual(a.unidad, NA)

    def test_orden_por_funcion(self):
        med = Senal(funcion=Funcion.MEDICION, medicion_codigo="AU", observaciones="Tensión fase R", s2=0, s3=3276.7)
        res = Senal(funcion=Funcion.RESERVA)
        sen = Senal(funcion=Funcion.SENALIZACION, estado_id="sen_ab_ce", observaciones="Seccionador X Abierto")
        proy = proyecto([res, med, alarma("Falta tensión"), sen])
        generador.generar(proy, self.p)
        funciones = [s.funcion for s in proy.niveles[0].campos[0].senales if not s.segunda_fila]
        self.assertEqual(funciones, [Funcion.ALARMAS, Funcion.SENALIZACION, Funcion.MEDICION, Funcion.RESERVA])

    def test_doble_bit_con_comando(self):
        sen = Senal(funcion=Funcion.SENALIZACION, estado_id="sen_ab_ce", par="SEC 329SA03",
                    observaciones="Seccionador 329SA03 Abierto", obs_segunda_fila="Seccionador 329SA03 Cerrado")
        cmd = Senal(funcion=Funcion.COMANDO, estado_id="com_ab_ce", par="SEC 329SA03",
                    observaciones="Seccionador 329SA03 Abrir/Cerrar")
        proy = proyecto([cmd, alarma("a"), alarma("b"), alarma("c"), sen])
        avisos = generador.generar(proy, self.p)
        filas = proy.niveles[0].campos[0].senales
        self.assertEqual([s.funcion.value for s in filas],
                         ["ALARMAS"] * 3 + ["SEÑALIZACION", "SEÑALIZACION", "COMANDO"])
        s1, s2, c = filas[3], filas[4], filas[5]
        self.assertEqual((s1.tag_scada, s1.offset), ("303.032C", 203))
        self.assertTrue(s2.segunda_fila)
        self.assertEqual((s2.offset, s2.tag_scada, s2.desc_hmi, s2.s0, s2.observaciones),
                         (204, "", "", "", "Seccionador 329SA03 Cerrado"))
        self.assertEqual((c.tag_scada, c.offset), ("303.032C", 203))
        self.assertIs(c.tipo_punto, TipoPunto.DO)
        self.assertEqual((s1.s0, s1.s1, s1.s2, s1.s3), ("error_0", "AB", "CE", "error_1"))
        self.assertFalse([a for a in avisos if "2ª fila" in a])

    def test_senalizacion_sin_comando_no_lleva_C(self):
        sen = Senal(funcion=Funcion.SENALIZACION, estado_id="sen_loc_rem", par="x", observaciones="Interruptor L/R")
        proy = proyecto([sen])
        generador.generar(proy, self.p)
        self.assertEqual(proy.niveles[0].campos[0].senales[0].tag_scada, "303.002")

    def test_comando_suelto_usa_contador_DO(self):
        cmd = Senal(funcion=Funcion.COMANDO, estado_id="com_conect_desconec", observaciones="Desconectar RBC")
        proy = proyecto([cmd])
        generador.generar(proy, self.p)
        c = proy.niveles[0].campos[0].senales[0]
        self.assertEqual((c.tag_scada, c.offset), ("303.001C", 300))

    def test_mediciones(self):
        def med(codigo, texto, unidad=NA):
            return Senal(funcion=Funcion.MEDICION, medicion_codigo=codigo, observaciones=texto,
                         unidad=unidad, s2=-3276.8, s3=3276.7)
        proy = proyecto([med("AU", "Tensión R"), med("AR", "Corriente R"), med("AS", "Potencia aparente", "MVA"),
                         med("AFP", "cos fi")])
        avisos = generador.generar(proy, self.p)
        au, ar, mva, afp = proy.niveles[0].campos[0].senales
        self.assertEqual([x.tag_scada for x in (au, ar, mva, afp)],
                         ["303.01AU", "303.02AR", "303.03AS", "303.04AFP"])
        self.assertEqual([x.offset for x in (au, ar, mva, afp)], [200, 201, 202, 203])
        self.assertEqual((au.s0, au.s1, au.unidad, au.tipo_punto), (0, 32767, "KV", TipoPunto.AI))
        self.assertEqual((ar.s0, ar.unidad), (-32768, "A"))
        self.assertEqual(mva.unidad, "MVA")
        self.assertEqual(afp.unidad, NA)
        self.assertEqual([a for a in avisos if "MIN EU" in a], [])

    def test_medicion_sin_eu_avisa(self):
        proy = proyecto([Senal(funcion=Funcion.MEDICION, medicion_codigo="AP", observaciones="P activa")])
        avisos = generador.generar(proy, self.p)
        self.assertTrue(any("MIN EU" in a for a in avisos))

    def test_reserva(self):
        proy = proyecto([alarma("a"), Senal(funcion=Funcion.RESERVA), Senal(funcion=Funcion.RESERVA)])
        generador.generar(proy, self.p)
        _, r1, r2 = proy.niveles[0].campos[0].senales
        self.assertEqual((r1.tag_scada, r1.tag_hmi, r1.desc_hmi, r1.desc_scada, r1.observaciones),
                         (NA, NA, "RESERVA", "RESERVA", "RESERVA"))
        self.assertEqual((r1.offset, r2.offset, r1.s0, r1.unidad), (201, 202, NA, NA))
        self.assertIs(r1.tipo_punto, TipoPunto.DI)

    def test_offset_continuo_entre_campos(self):
        c1 = Campo("03", "", "303LC", "", [alarma("a"), alarma("b")])
        c2 = Campo("02", "", "302TP1", "", [alarma("c")])
        proy = Proyecto("EPEN", niveles=[Nivel("132KV", "3", [c1, c2])], offsets_iniciales={"DI": 10})
        generador.generar(proy, self.p, variable_inicial={"02": 10})
        self.assertEqual([s.offset for s in c1.senales + c2.senales], [10, 11, 12])
        self.assertEqual([s.tag_scada for s in c1.senales + c2.senales], ["303.001", "303.011", "302.101"])

    def test_falta_offset_inicial(self):
        proy = proyecto([alarma("a")], offsets={})
        with self.assertRaises(generador.ErrorGeneracion):
            generador.generar(proy, self.p)

    def test_respeta_fijos(self):
        a = alarma("Falla X", tag_scada="303.781", offset=284, desc_scada="MI DESC",
                   fijos=["tag_scada", "offset", "desc_scada"])
        b = alarma("Falla Y")
        proy = proyecto([a, b])
        generador.generar(proy, self.p)
        self.assertEqual((a.tag_scada, a.offset, a.desc_scada), ("303.781", 284, "MI DESC"))
        self.assertEqual((b.tag_scada, b.offset), ("303.001", 285))  # el contador sigue después del fijo

    def test_idempotente(self):
        sen = Senal(funcion=Funcion.SENALIZACION, estado_id="sen_ab_ce", par="p", observaciones="Sec Abierto",
                    obs_segunda_fila="Sec Cerrado")
        cmd = Senal(funcion=Funcion.COMANDO, estado_id="com_ab_ce", par="p", observaciones="Sec Abrir/Cerrar")
        proy = proyecto([alarma("a"), sen, cmd])
        generador.generar(proy, self.p)
        primera = copy.deepcopy(proy.niveles[0].campos[0].senales)
        generador.generar(proy, self.p)
        self.assertEqual(proy.niveles[0].campos[0].senales, primera)
        self.assertEqual(len(primera), 4)

    def test_desc_scada_larga_avisa(self):
        proy = proyecto([alarma("Seccionador 329SA03 Falta Tensión Auxiliar")])
        avisos = generador.generar(proy, self.p)
        self.assertEqual(proy.niveles[0].campos[0].senales[0].desc_scada, "")
        self.assertTrue(any("DESC. SCADA" in a for a in avisos))
        corta = proyecto([alarma("SEC BA F/Uaux")])
        generador.generar(corta, self.p)
        self.assertEqual(corta.niveles[0].campos[0].senales[0].desc_scada, "303LC SEC BA F/Uaux")

    def test_roundtrip_json_con_campos_nuevos(self):
        sen = Senal(funcion=Funcion.SENALIZACION, estado_id="sen_ab_ce", par="p", obs_segunda_fila="x")
        proy = proyecto([sen])
        generador.generar(proy, self.p)
        self.assertEqual(Proyecto.from_dict(proy.to_dict()), proy)

    def test_helpers_hmi(self):
        self.assertEqual(generador.tag_hmi_desde("Prot.Ppal Loma Campana - Falla Interna"),
                         "ProtPpal_Loma_Campana_Falla_Interna")
        self.assertEqual(generador.tag_hmi_desde("MK03 - Falta Uca Calefaccion/Iluminacion/Tomas"),
                         "MK03_Falta_Uca_Calefaccion_Iluminacion_Tomas")
        self.assertEqual(generador.desc_hmi_desde("303LC", "Campo 03 Señalización"), "303LC Campo 03 Senalizacion")


@unittest.skipUnless(EJEMPLO.exists(), "ejemplo ETAP no disponible")
class TestContraEjemplo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            import openpyxl
        except ImportError:
            raise unittest.SkipTest("openpyxl no instalado")
        cls.p = perfiles.cargar_perfil("EPEN")
        ws = openpyxl.load_workbook(EJEMPLO, read_only=True, data_only=True)["EPEN"]
        cls.filas = list(ws.iter_rows(min_row=6, values_only=True))

    def test_hmi_se_deriva_de_la_descripcion(self):
        n = ok = 0
        for r in self.filas:
            tag_hmi, desc_hmi = r[5], r[6]
            if not (tag_hmi and desc_hmi) or tag_hmi == "N/A":
                continue
            resto = str(desc_hmi).partition(" ")[2]
            n += 1
            ok += generador.tag_hmi_desde(resto) == str(tag_hmi)
        # Es solo una propuesta: ~58 % de los TAG HMI del ejemplo coinciden. El resto son nombres de punto
        # del relé (ej. ARRANQUE_PROT_PPAL_FASE_R) que no se pueden deducir; se cargan a mano (fijos).
        self.assertGreater(n, 400)
        self.assertGreaterEqual(ok / n, 0.5, f"TAG HMI coincide en {ok} de {n}")

    def test_mediciones_rango_y_unidad(self):
        """RAW (K, L) y UNITS que genera el perfil, contra las 93 mediciones AI del ejemplo."""
        n = 0
        for r in self.filas:
            tag = r[7]
            if r[15] != "AI" or not tag:
                continue
            d = generador.tags.parsear_tag(self.p, str(tag))
            # Solo campos numéricos: en SACA el rango RAW de tensión/corriente es el inverso (ver PREGUNTAS.md)
            if not d or not d["medicion"] or d["nivel"] is None or d["campo"] in ("SACA", "SACC"):
                continue
            s = Senal(funcion=Funcion.MEDICION, medicion_codigo=d["medicion"],
                      unidad=r[14] if r[14] in ("MVA", "A", "Mvar", "MW", "KV", "Hz") else NA,
                      observaciones="x", s2=0, s3=0)
            c = Campo("03", "", "303LC", "", [s])
            proy = Proyecto("EPEN", niveles=[Nivel("132KV", "3", [c])], offsets_iniciales={"AI": 0})
            generador.generar(proy, self.p)
            n += 1
            with self.subTest(tag=tag):
                self.assertEqual((str(s.s0), str(s.s1)), (str(r[10]), str(r[11])))
                if d["medicion"] != "IP":  # el ejemplo escribe KV en IP: parece un error de carga
                    self.assertEqual(s.unidad, r[14])
        self.assertGreater(n, 30)


if __name__ == "__main__":
    unittest.main()
