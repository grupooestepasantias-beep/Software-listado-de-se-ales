"""Servicios auxiliares: reparto de las alarmas del TDCI en SAA (alterna) y SAC (continua)."""
import json
import tempfile
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

import libro

TDCI = (Path(__file__).resolve().parents[3] / "senillosa" / "TDCI" / "3-Funcional"
        / "USRE-01-19-SET-Ct-PL-Ad-0808_r4.pdf")


# Las 27 respuestas del usuario del 2026-11-16 (hoja 18 del TDCI). Los tests usan estas y no el archivo del perfil,
# que el usuario puede ir ampliando o corrigiendo en «Datos…» sin que se rompan.
_SAA = ["Alimentación trans.Potencia TPO1 (RBC)", "Tablero seccional de shelter", "iluminación Playa",
        'Iluminación columna a "P"', "Falta tensión señaliza. gral.", "Falta tensión iluminación emergencia",
        "Falta tensión Tab TCOM"]
_SAC = ["Alimentación Cargador de baterias", "Alimentaciòn de inversor", "Alimentación tableros",
        "Alimentación reconectadores", "Alarma intruso", "Alarma incendio", "Alarma movimiento",
        "Falta alimentación inversor", "Falta tensión comando 33 KV", "Falta tensión comando 13,2 KV",
        "Falta tensión fuerza motriz 33 KV", "Falta tensión fuerza motriz 13,2 KV", "Falta tensión general alarmas",
        "Falta tensión tableros Med y Prot.", "Falta tensión Power Injector 1", "Falta tensión Power Injector 2",
        "Falta tensión exploración 33 KV", "Falta tensión exploración 13,2 kv", "Falta tensión alimentación MGEAC",
        "Falta tensión exploración MGEAC"]
MEMORIA_TDCI = {**{libro.clave_sa(t): "SAA" for t in _SAA}, **{libro.clave_sa(t): "SAC" for t in _SAC}}


def _libro(memoria=None, tmp=None):
    """Libro con el TDCI cargado. `memoria` reemplaza lo que el perfil recuerda (por defecto, las 27 respuestas del
    usuario); nunca se escribe el archivo real."""
    memoria = MEMORIA_TDCI if memoria is None else memoria
    ruta = Path(tmp or tempfile.mkdtemp()) / "servicios_auxiliares.json"
    with mock.patch.object(libro.Libro, "_memoria_sa_ruta", return_value=ruta):
        L = libro.Libro()
    L.memoria_sa = dict(memoria)
    L.agregar_pdf(TDCI)
    L._ruta_memoria_prueba = ruta
    return L


def _por_campo(L):
    return {c.clave: [s for s in c.senales if not s.reserva] for c in L.campos}


@unittest.skipUnless(TDCI.exists(), "falta el PDF del TDCI")
class TestRepartoSa(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.L = _libro()

    def test_hay_dos_campos_y_se_reparten_las_39_alarmas(self):
        por = _por_campo(self.L)
        self.assertEqual(set(por) & {"SAA", "SAC"}, {"SAA", "SAC"})
        self.assertEqual((len(por["SAA"]), len(por["SAC"])), (11, 28))

    def test_de_donde_sale_cada_asignacion(self):
        fuentes = Counter(x["fuente"] for x in self.L.servicios_auxiliares())
        self.assertEqual(fuentes, Counter({"memoria": 27, "rótulo": 12}))
        self.assertTrue(all(x["campo"] for x in self.L.servicios_auxiliares()))

    def test_las_respuestas_del_usuario(self):
        campo = {x["texto"]: x["campo"] for x in self.L.servicios_auxiliares()}
        self.assertEqual(campo["Tablero seccional de shelter"], "SAA")          # es una térmica de alterna
        self.assertEqual(campo["Alimentación Cargador de baterias"], "SAC")     # cargadores: siempre continua
        self.assertEqual(campo["Falta tensión Power Injector 1"], "SAC")
        self.assertEqual(campo["Falta tensión Tab TCOM"], "SAA")
        self.assertEqual(campo["Alarma intruso"], "SAC")

    def test_lo_que_dice_el_rotulo_manda_cuando_no_hay_respuesta(self):
        L = _libro(memoria={})
        campo = {x["texto"]: (x["campo"], x["fuente"]) for x in L.servicios_auxiliares()}
        self.assertEqual(campo["Interruptor Ppal 380Vca Abierto"], ("SAA", "rótulo"))
        self.assertEqual(campo["Falta tensión barra 48 Vcc"], ("SAC", "rótulo"))

    def test_las_reservas_quedan_en_saa(self):
        reservas = {c.clave: sum(1 for s in c.senales if s.reserva) for c in self.L.campos}
        self.assertGreater(reservas["SAA"], 0)
        self.assertEqual(reservas["SAC"], 0)

    def test_los_tags_van_con_el_campo_y_no_se_repiten(self):
        self.L.calcular()
        tags = [f.tag for f in self.L.filas if f.tag and f.tag != "N/A"]
        self.assertTrue(any(t.startswith("SAA.") for t in tags) and any(t.startswith("SAC.") for t in tags))
        self.assertEqual(len(tags), len(set(tags)))


@unittest.skipUnless(TDCI.exists(), "falta el PDF del TDCI")
class TestPreguntaSoloLoQueNoSabe(unittest.TestCase):
    def test_sin_memoria_las_dudosas_quedan_sin_asignar_y_en_saa(self):
        L = _libro(memoria={})
        sin = [x for x in L.servicios_auxiliares() if x["campo"] is None]
        self.assertEqual(len(sin), 27)
        por = _por_campo(L)
        self.assertEqual(len(por["SAC"]), 8)                                    # solo los que dicen Vcc
        self.assertEqual(len(por["SAA"]), 31)                                   # 4 Vca + 27 sin asignar

    def test_asignar_mueve_la_alarma_y_pide_recalcular(self):
        L = _libro(memoria={})
        L.calcular()
        clave = next(x["clave"] for x in L.servicios_auxiliares() if x["campo"] is None)
        L.asignar_sa({clave: "SAC"}, recordar=False)
        self.assertEqual(len(_por_campo(L)["SAC"]), 9)
        self.assertEqual(L.hechos, [])
        self.assertFalse(L._ruta_memoria_prueba.exists())                       # recordar=False no escribe la memoria

    def test_recordar_guarda_la_respuesta_para_los_proximos_proyectos(self):
        L = _libro(memoria={})
        clave = next(x["clave"] for x in L.servicios_auxiliares() if x["campo"] is None)
        with mock.patch.object(libro.Libro, "_memoria_sa_ruta", return_value=L._ruta_memoria_prueba):
            L.asignar_sa({clave: "SAC"}, recordar=True)
            otro = libro.Libro()
        self.assertEqual(json.loads(L._ruta_memoria_prueba.read_text(encoding="utf-8"))["decisiones"], {clave: "SAC"})
        self.assertEqual(otro.memoria_sa, {clave: "SAC"})

    def test_el_proyecto_guardado_conserva_el_reparto(self):
        L = _libro(memoria={})
        clave = next(x["clave"] for x in L.servicios_auxiliares() if x["campo"] is None)
        L.asignar_sa({clave: "SAC"}, recordar=False)
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "p.json"
            L.guardar(ruta)
            otro = libro.Libro()                                                # abre con la memoria del perfil
            otro.memoria_sa = {}
            otro.abrir(ruta)
        self.assertEqual({x["clave"]: x["campo"] for x in otro.servicios_auxiliares()}[clave], "SAC")


if __name__ == "__main__":
    unittest.main()
