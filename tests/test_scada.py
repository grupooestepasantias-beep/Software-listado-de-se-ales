import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scada import descripcion  # noqa: E402
from scada import gen as scada_gen  # noqa: E402
from scada import perfil as scada_perfil  # noqa: E402
from scada import texto as tx  # noqa: E402
from modelo import NA, Campo, Funcion, Nivel, Proyecto, Senal, TipoPunto  # noqa: E402

VACIO = descripcion.Glosario()


def S(funcion, desc, **kw):
    return Senal(funcion=funcion, desc_hmi=desc, **kw)


def alarma(t, pre="303LC"):
    return S(Funcion.ALARMAS, f"{pre} {t}")


def proyecto(senales, *, nivel="132KV", codigo="3", numero="", prefijo="", offsets=None):
    campo = Campo(numero, "LAT", prefijo, "SEL", senales)
    return Proyecto("EPEN", niveles=[Nivel(nivel, codigo, [campo])],
                    offsets_iniciales=offsets if offsets is not None else {"DI": 200, "AI": 200, "DO": 300})


class Base(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.p = scada_perfil.cargar("EPEN")

    def gen(self, proy, **kw):
        return scada_gen.generar_scada(proy, self.p, kw.pop("glosario", VACIO), **kw)

    def filas(self, proy):
        return proy.niveles[0].campos[0].senales


class TestPerfil(Base):
    def test_carga_y_valida(self):
        self.assertEqual(scada_perfil.validar(self.p), [])
        self.assertEqual(self.p.maximo, 20)
        self.assertEqual(scada_perfil.listar(), ["EPEN"])

    def test_detecta_errores(self):
        p = copy.deepcopy(self.p)
        p.datos["estados"]["familias"][0]["senalizacion"] = ["(sin cerrar"]
        p.datos["mediciones"]["juego"][0]["raw"] = "raro"
        p.datos["offsets"]["comando"] = "otro"
        m = "\n".join(scada_perfil.validar(p))
        self.assertIn("expresión inválida", m)
        self.assertIn("raw debe ser", m)
        self.assertIn("compartido", m)
        with self.assertRaises(scada_perfil.PerfilInvalido):
            scada_perfil.cargar("NO_EXISTE")


class TestTagsOffsetsEstados(Base):
    def test_alarmas(self):
        pr = proyecto([alarma("Seccionador 329SA03 Falta Tension Auxiliar"),
                       alarma("Seccionador 329SA03 Maniobra Incompleta"),
                       S(Funcion.ALARMAS, "303LC UTR COMUNICACION CONTROLADOR")])
        self.gen(pr)
        a, b, c = self.filas(pr)
        self.assertEqual((a.tag_scada, b.tag_scada), ("303.001", "303.011"))   # el campo 303 arranca en 00
        self.assertEqual((a.offset, b.offset), (200, 201))
        self.assertEqual((a.s0, a.s1, a.s2, a.s3, a.unidad, a.tipo_punto), ("NORMAL", "ACTUO", NA, NA, NA, TipoPunto.DI))
        self.assertEqual(c.s1, "ACTUO")  # "UTR COMUNICACION" solo es FALLA si el texto EMPIEZA así (sin prefijo)

    def test_otros_campos_arrancan_en_10(self):
        pr = proyecto([alarma("Falta X", pre="204LC")], nivel="33KV", codigo="2")
        self.gen(pr)
        self.assertEqual(self.filas(pr)[0].tag_scada, "204.101")

    def test_campo_especial_sin_nivel(self):
        pr = proyecto([S(Funcion.ALARMAS, "SACC Falta tension 110Vcc")], nivel="SSAA", codigo="")
        self.gen(pr)
        self.assertEqual(self.filas(pr)[0].tag_scada, "SACC.101")

    def test_doble_bit_con_comando(self):
        sen = S(Funcion.SENALIZACION, "303LC Seccionador 329SA03 Abierto/Cerrado")
        seg = Senal(funcion=Funcion.SENALIZACION, segunda_fila=True)
        cmd = S(Funcion.COMANDO, "303LC Seccionador 329SA03 Abrir/Cerrar")
        pr = proyecto([cmd, alarma("X"), seg, sen])      # desordenado a propósito
        self.gen(pr)
        f = self.filas(pr)
        self.assertEqual([x.funcion.value for x in f],
                         ["ALARMAS", "SEÑALIZACION", "SEÑALIZACION", "COMANDO"])
        al, s1, s2, c = f
        self.assertEqual((s1.tag_scada, s1.offset), ("303.012C", 201))
        self.assertTrue(s2.segunda_fila)
        self.assertEqual((s2.offset, s2.tag_scada, s2.s0, s2.unidad), (202, "", "", NA))
        self.assertEqual((c.tag_scada, c.offset, c.tipo_punto), ("303.012C", 201, TipoPunto.DO))
        self.assertEqual((s1.s0, s1.s1, s1.s2, s1.s3), ("error_0", "AB", "CE", "error_1"))
        self.assertEqual(c.s1, "AB")
        self.assertEqual(c.desc_scada, s1.desc_scada)    # el comando copia la descripción de su señalización
        self.assertEqual(s1.desc_scada, "303LC SEC BA")  # reglas: equipo SA -> SEC BA, Abierto/Cerrado sin sufijo

    def test_crea_la_segunda_fila_si_falta(self):
        pr = proyecto([S(Funcion.SENALIZACION, "303LC Interruptor 35203 En Local/En Remoto")])
        self.gen(pr)
        f = self.filas(pr)
        self.assertEqual(len(f), 2)
        self.assertTrue(f[1].segunda_fila)
        self.assertEqual((f[0].s1, f[0].s2, f[0].desc_scada), ("LOC", "REM", "303LC INT L/R"))
        self.assertEqual(f[0].tag_scada, "303.002")      # variable 00, 2 bits, sin comando: no lleva C

    def test_familias_de_estado(self):
        casos = {
            "Llave Telecontrol-Distancia": ("DIST", "TELE"), "Seccionador 329SA03 En Local/En Remoto": ("LOC", "REM"),
            "Interruptor 15201 Extraido/Insertado": ("EX", "IN"), "CBC En Manual/En Automatico": ("MAN", "AUT"),
            "Recierre Deshabilitar/Habilitar": ("SIN", "CON"), "Ventiladores Marcha/Parada": ("PAR", "ARR"),
        }
        for texto, (a, b) in casos.items():
            with self.subTest(texto=texto):
                pr = proyecto([S(Funcion.SENALIZACION, f"303LC {texto}")])
                self.gen(pr)
                s = self.filas(pr)[0]
                self.assertEqual((s.s1, s.s2), (a, b))

    def test_comando_de_1_bit_y_suelto(self):
        pr = proyecto([S(Funcion.COMANDO, "TRAFO1 Desconectar RBC")], codigo="3", prefijo="TRAFO1")
        pr.niveles[0].campos[0].descripcion = "TR01 Campo TP1"
        self.gen(pr)
        c = self.filas(pr)[0]
        self.assertEqual((c.tag_scada, c.offset, c.s0, c.s1, c.s2), ("TP1.101C", 300, "CONECT", "DESCONEC", NA))

    def test_reservas(self):
        pr = proyecto([alarma("a"), Senal(funcion=Funcion.RESERVA, desc_hmi="RESERVA Campo 03", es_reserva=True),
                       Senal(funcion=Funcion.RESERVA, es_reserva=True)])
        self.gen(pr)
        _, r1, r2 = self.filas(pr)
        self.assertEqual((r1.tag_scada, r1.desc_scada, r1.s0, r1.unidad, r1.tipo_punto), (NA, "RESERVA", NA, NA, TipoPunto.DI))
        self.assertEqual((r1.offset, r2.offset), (201, 202))

    def test_separacion_entre_campos(self):
        c1 = Campo("", "Campo 303", "303LC", "", [alarma("a"), alarma("b")])
        c2 = Campo("", "Campo 302", "302TP1", "", [alarma("c", pre="302TP1")])
        pr = Proyecto("EPEN", niveles=[Nivel("132KV", "3", [c1, c2])], offsets_iniciales={"DI": 200, "AI": 200})
        self.gen(pr)
        self.assertEqual([s.offset for s in c1.senales + c2.senales], [200, 201, 212])   # 10 libres entre campos
        self.assertEqual(c2.senales[0].tag_scada, "302.101")

    def test_falta_offset_inicial(self):
        with self.assertRaises(scada_gen.ErrorGeneracion):
            self.gen(proyecto([alarma("a")], offsets={}))

    def test_respeta_fijos_e_idempotente(self):
        a = alarma("Falla X")
        a.tag_scada, a.offset, a.desc_scada, a.fijos = "303.781", 284, "MI DESC", ["tag_scada", "offset", "desc_scada"]
        sen = S(Funcion.SENALIZACION, "303LC Seccionador 329SA03 Abierto/Cerrado")
        pr = proyecto([a, alarma("b"), sen, S(Funcion.COMANDO, "303LC Seccionador 329SA03 Abrir/Cerrar")])
        self.gen(pr)
        f = self.filas(pr)
        self.assertEqual((f[0].tag_scada, f[0].offset, f[0].desc_scada), ("303.781", 284, "MI DESC"))
        self.assertEqual(f[1].offset, 285)                  # el contador sigue después del offset fijo
        primera = copy.deepcopy(pr)
        self.gen(pr)
        self.assertEqual(pr, primera)

    def test_json_roundtrip(self):
        pr = proyecto([alarma("a"), S(Funcion.SENALIZACION, "303LC Interruptor 35203 Abierto/Cerrado")])
        self.gen(pr)
        self.assertEqual(Proyecto.from_dict(pr.to_dict()), pr)


class TestMediciones(Base):
    JUEGO = ["TENSION CAMPO 03 132kV FASE R", "TENSION CAMPO 03 132kV FASE S", "TENSION CAMPO 03 132kV FASE T",
             "CORRIENTE CAMPO 03 132kV FASE R", "CORRIENTE CAMPO 03 132kV FASE S", "CORRIENTE CAMPO 03 132kV FASE T",
             "FRECUENCIA CAMPO 03 132kV", "ANGULO DE FASE TOTAL CAMPO 03 132kV", "POTENCIA ACTIVA CAMPO 03 132kV",
             "POTENCIA APARENTE CAMPO 03 132kV", "POTENCIA REACTIVA CAMPO 03 132kV",
             "TENSION PROMEDIO CAMPO 03 132kV", "CORRIENTE PROMEDIO CAMPO 03 132kV"]

    def test_juego_de_13(self):
        pr = proyecto([S(Funcion.MEDICION, f"303LC {t}") for t in self.JUEGO])
        inf = self.gen(pr)
        f = self.filas(pr)
        self.assertEqual([x.tag_scada for x in f],
                         ["303.01AU", "303.02AV", "303.03AW", "303.05AR", "303.06AS", "303.07AT", "303.08AF",
                          "303.09AFP", "303.10AP", "303.11AS", "303.12AQ", "303.13VP", "303.14IP"])  # la 04 no se usa
        self.assertEqual([x.offset for x in f], list(range(200, 213)))
        self.assertEqual([x.unidad for x in f], ["KV"] * 3 + ["A"] * 3 + ["Hz", NA, "MW", "MVA", "Mvar", "KV", "A"])
        au, ar, af, ap = f[0], f[3], f[6], f[8]
        self.assertEqual((au.s0, au.s1, au.s2, au.s3), (0, 32767, 0, 3276.7))
        self.assertEqual((ar.s0, ar.s1, ar.s2, ar.s3), (-32768, 32767, -3276.8, 3276.7))
        self.assertEqual((af.s2, af.s3), (0, 327.67))
        self.assertEqual((ap.s2, ap.s3), (-3276.8, 3276.7))
        self.assertEqual(f[0].desc_scada, "303LC V F/U")
        self.assertEqual(inf.eu_por_defecto, 13)
        self.assertTrue(all(x.tipo_punto == TipoPunto.AI for x in f))

    def test_servicios_auxiliares_rango_invertido(self):
        pr = proyecto([S(Funcion.MEDICION, "SACA TENSION FASE R"), S(Funcion.MEDICION, "SACA CORRIENTE FASE R")],
                      nivel="SSAA", codigo="")
        self.gen(pr)
        tension, corriente = self.filas(pr)
        self.assertEqual((tension.tag_scada, tension.unidad, tension.s0), ("SACA.01AU", "V", -32768))
        self.assertEqual((corriente.tag_scada, corriente.unidad, corriente.s0), ("SACA.02AR", "A", 0))

    def test_medicion_no_reconocida(self):
        pr = proyecto([S(Funcion.MEDICION, "303LC Temperatura CPU")])
        inf = self.gen(pr)
        self.assertTrue(any("medición no reconocida" in a for a in inf.avisos))
        self.assertEqual(self.filas(pr)[0].tag_scada, "")


class TestDescripcion(Base):
    def test_glosario_y_prioridad_del_usuario(self):
        g = descripcion.Glosario()
        g.texto[tx.clave_exacta("Falta Ucc Comando")] = "F/U CMDO"
        r = descripcion.proponer("303LC", "Falta Ucc Comando", None, self.p, g)
        self.assertEqual((r.desc, r.origen), ("303LC F/U CMDO", "glosario"))
        g.recordar("texto", tx.clave_exacta("Falta Ucc Comando"), "F/U CMNDO")
        r = descripcion.proponer("303LC", "Falta Ucc Comando", None, self.p, g)
        self.assertEqual((r.desc, r.origen), ("303LC F/U CMNDO", "usuario"))

    def test_clave_exacta_antes_que_la_general(self):
        g = descripcion.Glosario()
        g.texto["falta ucc senalizacion #vcc"] = "F/U SENAL"
        g.texto["falta ucc senalizacion 48vcc"] = "F/U SENAL48"
        self.assertEqual(descripcion.proponer("101TP1", "Falta Ucc Senalizacion 48Vcc", None, self.p, g).desc,
                         "101TP1 F/U SENAL48")
        self.assertEqual(descripcion.proponer("101TP1", "Falta Ucc Senalizacion 110Vcc", None, self.p, g).desc,
                         "101TP1 F/U SENAL")

    def test_proteccion_ppal_resp(self):
        g = descripcion.Glosario()
        g.rele["excitacion fase r"] = "EXC F/R"
        self.assertEqual(descripcion.proponer("303LC", "PROT PPAL EXCITACION FASE R", None, self.p, g).desc,
                         "303LC EXC F/R PPAL")
        self.assertEqual(descripcion.proponer("303LC", "PROT RES EXCITACION FASE R", None, self.p, g).desc,
                         "303LC EXC F/R Presp")

    def test_propuesta_siempre_entra_y_va_marcada(self):
        for t in ("Transformador Regulador Bajo Carga Funcion Automatica Descripcion Muy Larga", "Puerta Abierta"):
            r = descripcion.proponer("303LC", t, None, self.p, VACIO)
            self.assertEqual(r.origen, "propuesta")
            self.assertLessEqual(len(r.desc), 20)
            self.assertTrue(r.desc.startswith("303LC "))
        self.assertEqual(descripcion.proponer("303LC", "Puerta Abierta", None, self.p, VACIO, con_propuesta=False).origen,
                         "pendiente")

    def test_reglas_por_texto_sin_equipo(self):
        casos = [("Campo 03 132kV Llave Telecontrol-Distancia", "dist_tele", "303LC LLAVE T/D"),
                 ("Recierre Linea a Loma Campana Deshabilitar/Habilitar", "sin_con", "303LC REC HAB"),
                 ("Trafo TR01 CBC En Manual/En Automatico", "man_aut", "303LC RBC MAN/AUTO")]
        for texto, familia, esperado in casos:
            with self.subTest(texto=texto):
                r = descripcion.proponer("303LC", texto, familia, self.p, VACIO, con_propuesta=False)
                self.assertEqual((r.desc, r.origen), (esperado, "reglas"))

    def test_propuesta_conserva_el_equipo_y_distingue(self):
        a = descripcion.abreviar_por_palabras("204LC", "Seccionador 229SB04 Falta Tension Auxiliar Comando", self.p, VACIO,
                                              frozenset({"comando"}))
        b = descripcion.abreviar_por_palabras("204LC", "Seccionador 229SB04 Falta Tension Auxiliar SSAA", self.p, VACIO,
                                              frozenset({"ssaa"}))
        self.assertTrue(a.startswith("204LC SEC BB"))
        self.assertIn("CMDO", a)
        self.assertNotEqual(a, b)
        self.assertLessEqual(max(len(a), len(b)), 20)

    def test_vocabulario_prioridad(self):
        g = descripcion.Glosario()
        self.assertEqual(descripcion.vocabulario(self.p, g)["comando"], "CMDO")
        g.palabra["comando"] = "COM"
        g.recordar("palabra", "comando", "CMD")
        self.assertEqual(descripcion.vocabulario(self.p, g)["comando"], "CMD")   # usuario > cliente > base

    def test_desambigua_propuestas_repetidas(self):
        pr = proyecto([alarma("Seccionador 229SB04 Falta Tension Auxiliar Fuerza Motriz", "204LC"),
                       alarma("Seccionador 229SB04 Falta Tension Auxiliar Comando", "204LC"),
                       alarma("Seccionador 229SB04 Falta Tension Auxiliar SSAA", "204LC")],
                      nivel="33KV", codigo="2")
        inf = self.gen(pr)
        d = [s.desc_scada for s in self.filas(pr)]
        self.assertEqual(len(set(d)), 3, d)
        self.assertEqual(len(inf.propuestas), 3)
        self.assertFalse([a for a in inf.avisos if "repetida" in a])

    def test_avisa_si_no_logra_distinguir(self):
        pr = proyecto([S(Funcion.COMANDO, "204LC Habilitar recierre"), S(Funcion.COMANDO, "204LC Deshabilitar recierre")],
                      nivel="33KV", codigo="2")
        inf = self.gen(pr)
        self.assertTrue([a for a in inf.avisos if "repetida" in a])

    def test_pegado_cuando_no_entra(self):
        self.assertEqual(descripcion.unir("303LC", "SEC BA", "F/Uaux"), "303LC SEC BA F/Uaux")
        self.assertEqual(descripcion.unir("303LC", "PrtTxTelepPpal", pegado=True), "303LCPrtTxTelepPpal")
        self.assertIsNone(descripcion.unir("303LC", "ABCDEFGHIJKLMNOP"))

    def test_aprender_de_filas(self):
        filas = [dict(funcion="ALARMAS", desc_hmi="303LC Seccionador 329SA03 Falta Tension Auxiliar",
                      desc_scada="303LC SEC BA F/Uaux", tag="303.011") for _ in range(2)]
        filas += [dict(funcion="ALARMAS", desc_hmi="303LC PROT PPAL EXCITACION FASE R",
                       desc_scada="303LC EXC F/R PPAL", tag="303.201")]
        g = descripcion.aprender(filas, self.p)
        self.assertEqual(g.frase["falta tension auxiliar"], "F/Uaux")
        self.assertEqual(g.rele["excitacion fase r"], "EXC F/R")
        r = descripcion.proponer("302TP1", "Seccionador 329SB02 Falta Tension Auxiliar", None, self.p, g)
        self.assertEqual(r.desc, "302TP1 SEC BB F/Uaux")


class TestContraEtap(unittest.TestCase):
    """Protección contra retrocesos: el motor, sin ver H-O, se parece al listado terminado del ETAP."""

    @classmethod
    def setUpClass(cls):
        from scada import ejemplos
        if not ejemplos.ETAP.exists():
            raise unittest.SkipTest("ejemplo ETAP no disponible")
        try:
            import openpyxl  # noqa: F401
        except ImportError:
            raise unittest.SkipTest("openpyxl no instalado")
        from scada import evaluar
        cls.r = evaluar.evaluar()

    def pct(self, c):
        return c.ok / c.n

    def test_estructura_del_tag(self):
        self.assertGreaterEqual(self.pct(self.r["m"]["tag estructura"]), 0.92)

    def test_estados_y_unidades(self):
        for k in ("estados S0", "estados S1", "estados S2", "estados S3"):
            self.assertGreaterEqual(self.pct(self.r["m"][k]), 0.91, k)
        self.assertGreaterEqual(self.pct(self.r["m"]["unidad"]), 0.95)
        self.assertGreaterEqual(self.pct(self.r["m"]["tipo punto"]), 0.99)

    def test_saltos_de_offset(self):
        self.assertGreaterEqual(self.pct(self.r["m"]["salto de offset DI (igual al ejemplo)"]), 0.88)
        self.assertGreaterEqual(self.pct(self.r["m"]["salto de offset AI (igual al ejemplo)"]), 0.94)

    def test_descripcion_scada(self):
        self.assertGreaterEqual(self.pct(self.r["m"]["desc SCADA exacta"]), 0.88)
        cv = self.r["cv"]
        self.assertGreaterEqual(self.pct(cv["  acierto entre las resueltas"]), 0.80)
        self.assertEqual(self.pct(cv["propuesta cabe en 20 caracteres"]), 1.0)


if __name__ == "__main__":
    unittest.main()
