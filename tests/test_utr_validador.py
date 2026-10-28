import copy
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import asignacion_utr
import generador
import perfiles
import validador
from modelo import NA, Campo, Funcion, Modulo, Nivel, Proyecto, Senal, TipoPunto


def alarma(t, **kw):
    return Senal(funcion=Funcion.ALARMAS, observaciones=t, **kw)


def proyecto(senales, modulos=None):
    campo = Campo("03", "LAT", "303LC", "SEL", senales)
    return Proyecto("EPEN", niveles=[Nivel("132KV", "3", [campo])],
                    offsets_iniciales={"DI": 200, "AI": 200, "DO": 300},
                    modulos=modulos if modulos is not None else [])


def completo():
    """Proyecto chico, generado y asignado, sin problemas."""
    sen = Senal(funcion=Funcion.SENALIZACION, estado_id="sen_ab_ce", par="SEC", observaciones="SEC BA Abierto",
                obs_segunda_fila="SEC BA Cerrado", desc_scada="303LC SEC BA")
    cmd = Senal(funcion=Funcion.COMANDO, estado_id="com_ab_ce", par="SEC", observaciones="SEC BA Abrir/Cerrar")
    med = Senal(funcion=Funcion.MEDICION, medicion_codigo="AU", observaciones="V R", s2=0, s3=3276.7,
                desc_scada="303LC V F/R")
    proy = proyecto([alarma("F/Uaux", desc_scada="303LC F/Uaux"), sen, cmd, med,
                     Senal(funcion=Funcion.RESERVA)],
                    [Modulo("A3.4", "DI", 8), Modulo("A3.7", "DO", 4)])
    p = perfiles.cargar_perfil("EPEN")
    generador.generar(proy, p)
    asignacion_utr.asignar_placas(proy, p)
    return proy, p


class TestAsignacion(unittest.TestCase):
    def test_asigna_en_orden(self):
        proy, _ = completo()
        s = proy.niveles[0].campos[0].senales
        # alarma, sen, 2ª fila, cmd, medición, reserva
        self.assertEqual([(x.placa, x.entrada) for x in s],
                         [("A3.4", "1"), ("A3.4", "2"), ("A3.4", "3"), ("A3.7", "1/2"), (NA, NA), ("A3.4", "4")])

    def test_modulos_en_secuencia_y_agotado(self):
        p = perfiles.cargar_perfil("EPEN")
        proy = proyecto([alarma(f"a{i}") for i in range(5)], [Modulo("A1", "DI", 2), Modulo("A2", "DI", 2, desde=5)])
        avisos = asignacion_utr.asignar_placas(proy, p)
        s = proy.niveles[0].campos[0].senales
        self.assertEqual([(x.placa, x.entrada) for x in s[:4]],
                         [("A1", "1"), ("A1", "2"), ("A2", "5"), ("A2", "6")])
        self.assertEqual(s[4].placa, "N/A")
        self.assertEqual(len(avisos), 1)
        self.assertIn("no hay más módulos DI", avisos[0])

    def test_respeta_fijos_y_salta_entradas_usadas(self):
        p = perfiles.cargar_perfil("EPEN")
        fija = alarma("fija", placa="A1", entrada="2", fijos=["placa", "entrada"])
        proy = proyecto([alarma("a"), fija, alarma("b")], [Modulo("A1", "DI", 4)])
        asignacion_utr.asignar_placas(proy, p)
        self.assertEqual([x.entrada for x in proy.niveles[0].campos[0].senales], ["1", "2", "3"])

    def test_comando_un_bit(self):
        p = perfiles.cargar_perfil("EPEN")
        cmd = Senal(funcion=Funcion.COMANDO, estado_id="com_conect_desconec", observaciones="x")
        proy = proyecto([cmd, Senal(funcion=Funcion.COMANDO, estado_id="com_ab_ce", observaciones="y")],
                        [Modulo("A3.7", "DO", 10)])
        asignacion_utr.asignar_placas(proy, p)
        self.assertEqual([x.entrada for x in proy.niveles[0].campos[0].senales], ["1", "2/3"])

    def test_json_con_modulos(self):
        proy, _ = completo()
        self.assertEqual(Proyecto.from_dict(proy.to_dict()), proy)


class TestValidador(unittest.TestCase):
    def mensajes(self, proy, p, gravedad=None):
        return [str(x) for x in validador.validar_proyecto(proy, p) if gravedad in (None, x.gravedad)]

    def test_proyecto_correcto(self):
        proy, p = completo()
        self.assertEqual(self.mensajes(proy, p, "error"), [])

    def test_estado_mal_escrito(self):
        proy, p = completo()
        proy.niveles[0].campos[0].senales[1].s0 = "ERR_0"
        self.assertTrue(any("¿'error_0'?" in m for m in self.mensajes(proy, p, "error")))

    def test_unidad_y_digital(self):
        proy, p = completo()
        s = proy.niveles[0].campos[0].senales
        s[4].unidad = "kV"
        s[0].unidad = "KV"
        m = "\n".join(self.mensajes(proy, p, "error"))
        self.assertIn("¿'KV'?", m)
        self.assertIn("señal digital lleva UNITS N/A", m)

    def test_duplicados(self):
        proy, p = completo()
        s = proy.niveles[0].campos[0].senales
        s[0].tag_scada = "303.012C"            # igual al de la señalización (no es comando): repetido
        s[0].offset = s[2].offset              # offset repetido
        s[0].placa, s[0].entrada = s[1].placa, s[1].entrada
        m = "\n".join(self.mensajes(proy, p, "error"))
        self.assertIn("tag repetido", m)
        self.assertIn("OFFSET", m)
        self.assertIn("usada en 2 filas", m)

    def test_comando_comparte_tag_sin_error(self):
        proy, p = completo()
        m = "\n".join(self.mensajes(proy, p))
        self.assertNotIn("repetido", m)

    def test_falta_segunda_fila_y_orden(self):
        proy, p = completo()
        campo = proy.niveles[0].campos[0]
        campo.senales = [x for x in campo.senales if not x.segunda_fila]
        self.assertTrue(any("sin 2ª fila" in m for m in self.mensajes(proy, p, "error")))
        proy2, p = completo()
        s = proy2.niveles[0].campos[0].senales
        s[0], s[3] = s[3], s[0]  # comando antes que la alarma
        self.assertTrue(any("fuera de orden" in m for m in self.mensajes(proy2, p, "error")))

    def test_espacios_sobrantes_y_tipo(self):
        proy, p = completo()
        s = proy.niveles[0].campos[0].senales
        s[0].desc_scada = "303LC F/Uaux "
        s[4].tipo_punto = TipoPunto.DI  # la medición
        m = "\n".join(self.mensajes(proy, p, "error"))
        self.assertIn("espacios o tabulaciones", m)
        self.assertIn("MEDICION no puede ser DI", m)

    def test_comando_doble_bit_una_salida(self):
        proy, p = completo()
        proy.niveles[0].campos[0].senales[3].entrada = "1"
        self.assertTrue(any("dos salidas" in m for m in self.mensajes(proy, p, "error")))

    def test_no_modifica(self):
        proy, p = completo()
        antes = copy.deepcopy(proy)
        validador.validar_proyecto(proy, p)
        self.assertEqual(proy, antes)


@unittest.skipUnless(Path(r"\\192.168.15.120\PasantiasMM\Sofware listado\Ejemplos").exists(), "sin ejemplo")
class TestEjemploEtap(unittest.TestCase):
    def test_detecta_inconsistencias_reales(self):
        try:
            import openpyxl  # noqa: F401
            import ejemplo_etap
        except ImportError:
            self.skipTest("openpyxl no instalado")
        p = perfiles.cargar_perfil("EPEN")
        probs = validador.validar_proyecto(ejemplo_etap.proyecto_desde_ejemplo(), p)
        texto = "\n".join(str(x) for x in probs)
        # Inconsistencias que el ejemplo ETAP tiene de verdad:
        self.assertIn("OFFSET 284 repetido", texto)             # una alarma y una reserva con el mismo offset
        self.assertIn("entrada A3.5.15 (DI) usada en 2 filas", texto)
        self.assertIn("DESC. SCADA repetida '303LC DISP GRL PPAL'", texto)
        self.assertIn("espacios o tabulaciones sobrantes", texto)
        self.assertIn("'MARCHA' no es un estado del perfil", texto)  # el PDF dice PAR/ARR
        self.assertIn("tag no estándar", texto)


if __name__ == "__main__":
    unittest.main()
