"""Varios PDF en una carga, origen de cada señal y correcciones aprendidas."""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import correcciones
import pdf_plano
import perfiles
from modelo import Funcion

SENILLOSA = Path(r"\\192.168.15.120\PasantiasMM\senillosa")
CONTROL = SENILLOSA / "TCONTROL 13,2kV" / "3-Funcional" / "USRE-01-19-SET-Ct-PL-Ad-0821_r3.pdf"
COMUNICACIONES = SENILLOSA / "TCOM01" / "3-Funcional" / "USRE-01-19-SET-Te-PL-Ad-1042_r0.pdf"


def pagina(archivo, n, textos, nivel="33KV", campo="04"):
    senales = [pdf_plano.LecturaSenal(n, Funcion.ALARMAS, t, False, [t]) for t in textos]
    return pdf_plano.PaginaLeida(n, nivel, campo, senales, archivo=archivo)


class TestVariosPdf(unittest.TestCase):
    def setUp(self):
        self.perfil = perfiles.cargar_perfil("EPEN")
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(correcciones, "RAIZ_PLANTILLAS", Path(tmp.name))
        p.start()
        self.addCleanup(p.stop)

    def test_un_archivo_roto_no_frena_a_los_demas(self):
        with tempfile.TemporaryDirectory() as d:
            malo = Path(d) / "roto.pdf"
            malo.write_bytes(b"no es un pdf")
            pgs, informe = pdf_plano.leer_planos([malo, Path(d) / "no_existe.pdf"], self.perfil)
        self.assertEqual(pgs, [])
        self.assertEqual([f["estado"] for f in informe], ["error", "error"])
        self.assertTrue(all(f["mensaje"] for f in informe))

    @unittest.skipUnless(CONTROL.exists() and COMUNICACIONES.exists(), "faltan los PDF de Senillosa")
    def test_los_planos_de_senillosa(self):
        pgs, informe = pdf_plano.leer_planos([COMUNICACIONES, CONTROL], self.perfil)
        self.assertEqual([f["estado"] for f in informe], ["sin_senales", "ok"])
        self.assertTrue(pgs and all(p.archivo == CONTROL.name for p in pgs))
        self.assertEqual({p.nivel for p in pgs}, {"13,2KV"})   # sale del título "TCONTROL 13,2kV - DETALLE…"
        self.assertTrue(all("nivel" not in p.inferidos for p in pgs))

    def test_la_misma_senal_en_dos_archivos_entra_una_vez(self):
        pgs = [pagina("control.pdf", 5, ["Seccionador 229 Abierto", "Falla cargador"]),
               pagina("proteccion.pdf", 2, ["Seccionador 229 Abierto", "Disparo 51"])]
        niveles = pdf_plano.a_niveles(pgs, self.perfil, {("control.pdf", 5): ("33KV", "04", ""),
                                                          ("proteccion.pdf", 2): ("33KV", "04", "")})
        textos = [s.observaciones for n in niveles for c in n.campos for s in c.senales]
        self.assertEqual(sum("Seccionador 229 Abierto" in t for t in textos), 1)
        self.assertEqual(len(textos), 3)

    def test_cada_senal_dice_de_que_archivo_y_pagina_salio(self):
        pgs = [pagina("a.pdf", 7, ["Falla cargador"]), pagina("b.pdf", 7, ["Falla UPS"], campo="05")]
        niveles = pdf_plano.a_niveles(pgs, self.perfil)
        obs = [s.observaciones for n in niveles for c in n.campos for s in c.senales]
        self.assertIn("a.pdf p.7 | rótulo: Falla cargador | leído", obs)
        self.assertIn("b.pdf p.7 | rótulo: Falla UPS | leído", obs)

    def test_lo_deducido_se_marca_como_inferido(self):
        pg = pagina("a.pdf", 3, ["Falla cargador"])
        pg.inferidos = ["campo"]
        s = pdf_plano.a_niveles([pg], self.perfil)[0].campos[0].senales[0]
        self.assertTrue(s.observaciones.endswith("inferido: campo"))

    def test_las_dos_paginas_con_igual_numero_se_destinan_por_separado(self):
        pgs = [pagina("a.pdf", 1, ["Falla A"]), pagina("b.pdf", 1, ["Falla B"])]
        niveles = pdf_plano.a_niveles(pgs, self.perfil, {("a.pdf", 1): ("33KV", "01", ""), ("b.pdf", 1): ("33KV", "02", "")})
        self.assertEqual([c.numero for c in niveles[0].campos], ["01", "02"])


class TestCorrecciones(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        p = mock.patch.object(correcciones, "RAIZ_PLANTILLAS", Path(tmp.name))
        p.start()
        self.addCleanup(p.stop)
        self.perfil = perfiles.cargar_perfil("EPEN")

    def test_se_guarda_con_el_prefijo_como_marcador(self):
        correcciones.guardar("EPEN", "Falla  Cargador", "desc_hmi", "204LC Falla del Cargador de Baterias", "204LC")
        c = correcciones.cargar("EPEN")
        self.assertEqual(c["falla cargador"]["desc_hmi"], "{p} Falla del Cargador de Baterias")
        self.assertEqual(correcciones.aplicar(c, "FALLA cargador", "205AP")["desc_hmi"], "205AP Falla del Cargador de Baterias")

    def test_un_valor_vacio_olvida_la_correccion(self):
        correcciones.guardar("EPEN", "Falla UPS", "tag_hmi", "UPS_F")
        correcciones.guardar("EPEN", "Falla UPS", "tag_hmi", "")
        self.assertEqual(correcciones.cargar("EPEN"), {})

    def test_la_proxima_carga_usa_la_correccion(self):
        correcciones.guardar("EPEN", "Falla cargador", "tag_hmi", "Cargador_F")
        s = pdf_plano.a_niveles([pagina("a.pdf", 1, ["Falla cargador", "Falla UPS"])], self.perfil)[0].campos[0].senales
        self.assertEqual(s[0].tag_hmi, "Cargador_F")
        self.assertTrue(s[0].observaciones.endswith("corregido por el usuario"))
        self.assertNotEqual(s[1].tag_hmi, "Cargador_F")

    def test_el_rotulo_se_lee_de_las_observaciones(self):
        self.assertEqual(correcciones.rotulo_de("a.pdf p.1 | rótulo: Falla UPS | leído"), "Falla UPS")
        self.assertIsNone(correcciones.rotulo_de("a mano"))


if __name__ == "__main__":
    unittest.main()
