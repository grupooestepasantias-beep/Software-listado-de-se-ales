import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import descripciones as dsc
import perfiles
from modelo import Campo, Funcion, Nivel, Proyecto, Senal, TipoPunto


class TestDescripciones(unittest.TestCase):
    def setUp(self):
        self.perfil = perfiles.cargar_perfil("EPEN")
        self.tmp = tempfile.TemporaryDirectory()
        self.base = Path(self.tmp.name)
        for f in ("reglas_descripcion.json",):  # la memoria del usuario de la prueba empieza vacía
            shutil.copy(Path(dsc.RAIZ_PLANTILLAS) / "EPEN" / f, self.base / f)

    def tearDown(self):
        self.tmp.cleanup()

    def proyecto(self, *senales):
        return Proyecto(perfil_id="EPEN", niveles=[Nivel("33KV", "2", [Campo("04", prefijo="204AP", senales=list(senales))])])

    def alarma(self, texto):
        return Senal(funcion=Funcion.ALARMAS, tipo_punto=TipoPunto.DI, observaciones=texto)

    def senal(self, texto, estado_id):
        e = self.perfil.estado(estado_id)
        return Senal(funcion=Funcion.SENALIZACION, tipo_punto=TipoPunto.DI, observaciones=texto,
                     estado_id=estado_id, s1=e["s1"], s2=e["s2"])

    def aplicar(self, p, reglas=None):
        return dsc.aplicar(p, self.perfil, reglas or dsc.Reglas(self.perfil, self.base))

    def test_analizar(self):
        sin = {"secc": "seccionador"}
        self.assertEqual(dsc.analizar("Secc. 229SL04 Falta Tensión Auxiliar", sin),
                         ("seccionador", "SL", "falta tension auxiliar"))
        self.assertEqual(dsc.analizar("Interruptor 25204 Resorte Descargado", sin),
                         ("interruptor", "", "resorte descargado"))
        self.assertEqual(dsc.analizar("Campo 04 33KV QF4 ACTUADA", sin)[0], "")

    def test_reglas_del_pdf(self):
        s1 = self.alarma("Seccionador 229SA04 Falta Tensión Auxiliar")
        s2 = self.senal("Interruptor 25204 Abierto/Cerrado", "sen_ab_ce")
        s3 = self.alarma("Interruptor 25204 Disparo")
        inf, _ = self.aplicar(self.proyecto(s1, s2, s3))
        self.assertEqual((s1.desc_scada, s2.desc_scada, s3.desc_scada), ("204AP SEC BA F/Uaux", "204AP INT", "204AP INT DIS"))
        self.assertEqual((inf.por_reglas, inf.pendientes), (3, []))
        self.assertIn("desc_scada", s1.fijos)

    def test_pregunta_lo_que_no_define_el_pdf_y_lo_recuerda(self):
        s = self.alarma("Seccionador 229SZ04 Falta Tensión Auxiliar")  # SZ no figura en las reglas
        inf, reglas = self.aplicar(self.proyecto(s))
        self.assertEqual([(p.tipo, p.clave) for p in inf.pendientes], [("equipo", "seccionador|SZ")])
        self.assertEqual(s.desc_scada, "")
        inf.pendientes[0].respuesta = "SEC Z"
        reglas.recordar(inf.pendientes[0])
        reglas.guardar_memoria()
        inf2, _ = self.aplicar(self.proyecto(s), dsc.Reglas(self.perfil, self.base))  # memoria releída del disco
        self.assertEqual((s.desc_scada, inf2.pendientes, inf2.por_memoria), ("204AP SEC Z F/Uaux", [], 1))

    def test_estado_distinto_de_abierto_cerrado_se_pregunta(self):
        s = self.senal("Interruptor 25204 Manual/Automático", "sen_man_aut")
        inf, _ = self.aplicar(self.proyecto(s))
        p = inf.pendientes[0]
        self.assertEqual((p.tipo, p.clave, p.borrador), ("estado", "sen_man_aut", "M/A"))

    def test_frase_parcialmente_conocida_solo_pregunta_el_resto(self):
        s = self.alarma("Interruptor 25204 Falta Tensión Auxiliar SSAA")
        inf, reglas = self.aplicar(self.proyecto(s))
        self.assertEqual([(p.tipo, p.clave) for p in inf.pendientes], [("frase", "ssaa")])
        inf.pendientes[0].respuesta = "SSAA"
        reglas.recordar(inf.pendientes[0])
        inf2, _ = self.aplicar(self.proyecto(s), reglas)
        # con espacios serían 21: se pegan las partes como en el ejemplo de los lineamientos (301LAVALINTF/UAUX)
        self.assertEqual((s.desc_scada, inf2.pendientes), ("204APINTF/Uaux SSAA", []))

    def test_el_comando_no_se_duplica_con_su_senalizacion(self):
        sen = self.senal("Interruptor 25204 Abierto/Cerrado", "sen_ab_ce")
        e = self.perfil.estado("com_ab_ce")
        com = Senal(funcion=Funcion.COMANDO, tipo_punto=TipoPunto.DO, observaciones="Interruptor 25204 Cierre/Apertura",
                    estado_id="com_ab_ce", s1=e["s1"], s2=e["s2"])
        inf, _ = self.aplicar(self.proyecto(sen, com))
        self.assertEqual((sen.desc_scada, com.desc_scada, inf.pendientes), ("204AP INT", "", []))

    def test_texto_sin_equipo_se_pregunta_completo(self):
        s = self.alarma("Campo 04 33KV QF4 ACTUADA")
        inf, _ = self.aplicar(self.proyecto(s))
        self.assertEqual(inf.pendientes[0].tipo, "texto")

    def test_frase_larga_o_repetida_pide_abreviatura_propia(self):
        a = self.alarma("Interruptor 25204 Disparo")
        b = self.alarma("Interruptor 25205 Disparo")  # mismo texto normalizado: se llamarían igual
        inf, _ = self.aplicar(self.proyecto(a, b))
        self.assertEqual((a.desc_scada, b.desc_scada), ("", ""))
        self.assertEqual({p.tipo for p in inf.pendientes}, {"largo"})

    def test_prefijo_largo_no_entra(self):
        s = self.alarma("Seccionador 229SA04 Falta Tensión Auxiliar")
        p = Proyecto(perfil_id="EPEN", niveles=[Nivel("33KV", "2", [Campo("04", prefijo="204LARGOPREF", senales=[s])])])
        inf, _ = self.aplicar(p)
        self.assertEqual(s.desc_scada, "")
        self.assertEqual(inf.pendientes[0].tipo, "largo")


if __name__ == "__main__":
    unittest.main()
