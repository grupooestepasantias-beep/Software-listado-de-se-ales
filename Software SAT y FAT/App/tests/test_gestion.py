"""Versiones, registro, proyectos, validación de entradas, datos incompletos y manejo de errores."""
import json
import os
import shutil
import sys
import tempfile
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

import datos_prueba as D
import generador_sat as g
import gestion
import validador
import word_tools


def paquete(*args, **kw):
    """Los datos de prueba son ficticios: no hay PDF contra los que contrastar."""
    kw.setdefault("respaldo_pdf", False)
    return g.generar_paquete(*args, **kw)


class Temporal(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix="sat_gestion_")
        self.addCleanup(shutil.rmtree, self.tmp, True)

    def generar_sat(self, **cambios):
        return g.generar(dict(D.DATOS, **cambios), D.DOCUMENTOS, D.COMPONENTES, self.tmp, tipo="SAT")


class Versiones(Temporal):
    def test_regenerar_no_pisa_el_documento_anterior(self):
        ruta = self.generar_sat(FECHA="01/11/2026")
        hash1 = gestion.sha256(ruta)
        self.generar_sat(FECHA="02/11/2026")
        versiones = gestion.listar_versiones(ruta)
        self.assertEqual(len(versiones), 1)
        self.assertEqual(gestion.sha256(versiones[0][0]), hash1, "la versión archivada es la original, sin cambios")
        self.assertNotEqual(gestion.sha256(ruta), hash1)

    def test_varias_regeneraciones_conservan_todas_las_versiones(self):
        for dia in range(1, 5):
            ruta = self.generar_sat(FECHA=f"0{dia}/11/2026")
        self.assertEqual(len(gestion.listar_versiones(ruta)), 3)

    def test_restaurar_vuelve_a_la_version_elegida_y_no_pierde_la_actual(self):
        ruta = self.generar_sat(FECHA="01/11/2026")
        hash_vieja = gestion.sha256(ruta)
        self.generar_sat(FECHA="02/11/2026")
        hash_nueva = gestion.sha256(ruta)
        vieja = gestion.listar_versiones(ruta)[0][0]
        gestion.restaurar_version(vieja, ruta)
        self.assertEqual(gestion.sha256(ruta), hash_vieja)
        self.assertIn(hash_nueva, [gestion.sha256(v) for v, _ in gestion.listar_versiones(ruta)])

    def test_no_quedan_archivos_temporales(self):
        self.generar_sat()
        self.generar_sat()
        sobrantes = [f for f in os.listdir(self.tmp) if f.startswith("~tmp_")]
        self.assertEqual(sobrantes, [])

    def test_si_falla_el_guardado_el_documento_anterior_queda_intacto(self):
        ruta = self.generar_sat()
        hash1 = gestion.sha256(ruta)

        class Roto:
            def save(self, destino):
                open(destino, "wb").write(b"a medias")
                raise OSError("disco lleno (simulado)")
        with self.assertRaises(OSError):
            gestion.guardar_docx_seguro(Roto(), ruta)
        self.assertEqual(gestion.sha256(ruta), hash1)
        self.assertEqual(gestion.listar_versiones(ruta), [])
        self.assertEqual([f for f in os.listdir(self.tmp) if f.startswith("~tmp_")], [])

    def test_los_originales_de_referencia_nunca_se_modifican(self):
        origen = os.path.join(self.tmp, "origen")
        os.makedirs(origen)
        with open(os.path.join(origen, "plano.pdf"), "wb") as f:
            f.write(b"%PDF-1.4 prueba")
        antes = gestion.sha256(os.path.join(origen, "plano.pdf"))
        g.generar(D.DATOS, D.DOCUMENTOS, D.COMPONENTES, os.path.join(self.tmp, "salida"), tipo="SAT")
        self.assertEqual(gestion.sha256(os.path.join(origen, "plano.pdf")), antes)


class Registro(Temporal):
    def test_cada_paquete_queda_registrado_con_huella(self):
        r = paquete(D.DATOS, D.DOCUMENTOS, D.COMPONENTES, D.TERMICAS, D.SENALES, D.COMANDOS, self.tmp,
                              incluir=("SAT",), pdf=False)
        lineas = gestion.leer_registro(self.tmp)
        self.assertEqual(len(lineas), 1)
        x = lineas[0]
        self.assertEqual((x["accion"], x["usuario"] != "", x["incluir"]), ("generar_paquete", True, ["SAT"]))
        self.assertEqual(x["archivos"][0]["sha256"], gestion.sha256(r["archivos"][0]))
        self.assertIn(x["estado"], ("LISTO PARA ENTREGAR", "NO LISTO PARA ENTREGAR"))

    def test_un_registro_dañado_no_rompe_la_lectura(self):
        gestion.registrar(self.tmp, "a")
        with open(os.path.join(self.tmp, gestion.REGISTRO), "a", encoding="utf-8") as f:
            f.write("{esto no es json\n")
        gestion.registrar(self.tmp, "b")
        self.assertEqual([x["accion"] for x in gestion.leer_registro(self.tmp)], ["a", "b"])


class Proyectos(Temporal):
    def estado(self):
        return {"datos": D.DATOS, "documentos": D.DOCUMENTOS, "componentes": D.COMPONENTES, "termicas": D.TERMICAS,
                "senales": D.SENALES, "comandos": D.COMANDOS}

    def test_guardar_y_cargar_conserva_todo(self):
        ruta = os.path.join(self.tmp, "p.json")
        gestion.guardar_proyecto(ruta, self.estado())
        e = gestion.cargar_proyecto(ruta)
        self.assertEqual(e["datos"]["NOMBRE"], "Estación Prueba")
        self.assertEqual(len(e["senales"]), len(D.SENALES))
        self.assertEqual(e["version"], gestion.VERSION_PROYECTO)

    def test_guardar_de_nuevo_archiva_el_proyecto_anterior(self):
        ruta = os.path.join(self.tmp, "p.json")
        gestion.guardar_proyecto(ruta, self.estado())
        gestion.guardar_proyecto(ruta, self.estado())
        self.assertEqual(len(gestion.listar_versiones(ruta)), 1)

    def test_archivo_que_no_es_un_proyecto_se_rechaza(self):
        ruta = os.path.join(self.tmp, "x.json")
        json.dump({"otra": "cosa"}, open(ruta, "w"))
        with self.assertRaises(ValueError):
            gestion.cargar_proyecto(ruta)

    def test_proyecto_de_una_version_mas_nueva_se_rechaza(self):
        ruta = os.path.join(self.tmp, "x.json")
        json.dump({"version": 99, "datos": {}}, open(ruta, "w"))
        with self.assertRaises(ValueError):
            gestion.cargar_proyecto(ruta)

    def test_json_corrupto_da_error_claro(self):
        ruta = os.path.join(self.tmp, "x.json")
        open(ruta, "w").write("{{{")
        with self.assertRaises(ValueError):  # json.JSONDecodeError es ValueError
            gestion.cargar_proyecto(ruta)


class EntradasYArchivos(Temporal):
    def errores(self, **cambios):
        return {c for c, _ in gestion.validar_entradas(dict(D.DATOS, **cambios))}

    def test_datos_correctos(self):
        self.assertEqual(self.errores(), set())

    def test_campos_obligatorios(self):
        for campo in ("CLIENTE", "NRO_OBRA", "OBRA", "UBICACION", "TIPO_TABLERO", "NOMBRE", "FECHA", "REVISION"):
            self.assertIn(campo, self.errores(**{campo: "  "}), campo)

    def test_fecha(self):
        for mala in ("2026-11-02", "31/02/2026", "02/13/2026", "hoy", "2/11/26"):
            self.assertIn("FECHA", self.errores(FECHA=mala), mala)
        self.assertNotIn("FECHA", self.errores(FECHA="29/02/2028"))

    def test_revision(self):
        for mala in ("A B", "rA!", "ABCD"):
            self.assertIn("REVISION", self.errores(REVISION=mala), mala)
        for buena in ("A", "B", "C2", "10"):
            self.assertNotIn("REVISION", self.errores(REVISION=buena), buena)

    def test_nombre_con_caracteres_de_ruta(self):
        for malo in ("A/B", "A\\B", 'A"B', "A:B", "A*B", "A?B", "A<B", "A|B"):
            self.assertIn("NOMBRE", self.errores(NOMBRE=malo), malo)

    def test_no_se_admiten_llaves_ni_caracteres_de_control(self):
        self.assertIn("OBRA", self.errores(OBRA="Obra {{X}}"))
        self.assertIn("OBRA", self.errores(OBRA="Obra\x07"))

    def test_largo_maximo(self):
        self.assertIn("NOMBRE", self.errores(NOMBRE="x" * 61))
        self.assertNotIn("NOMBRE", self.errores(NOMBRE="x" * 60))

    def test_nombre_de_archivo_seguro(self):
        self.assertEqual(gestion.nombre_archivo_seguro('a/b:c*d?"e<f>g|h'), "a-b-c-d--e-f-g-h")
        self.assertEqual(gestion.nombre_archivo_seguro("  .. "), "sin_nombre")

    def test_validar_pdf(self):
        ok = os.path.join(self.tmp, "ok.pdf")
        open(ok, "wb").write(b"%PDF-1.7\n...")
        self.assertEqual(gestion.validar_pdf(ok), "")
        falso = os.path.join(self.tmp, "falso.pdf")
        open(falso, "wb").write(b"MZ esto es un ejecutable")
        self.assertIn("PDF", gestion.validar_pdf(falso))
        vacio = os.path.join(self.tmp, "vacio.pdf")
        open(vacio, "wb").close()
        self.assertIn("vacío", gestion.validar_pdf(vacio))
        self.assertIn("no existe", gestion.validar_pdf(os.path.join(self.tmp, "nada.pdf")))
        otro = os.path.join(self.tmp, "x.exe")
        open(otro, "wb").write(b"%PDF")
        self.assertIn("no es un PDF", gestion.validar_pdf(otro))


class DatosIncompletosYErrores(Temporal):
    def test_con_datos_obligatorios_vacios_no_se_genera_nada(self):
        with self.assertRaises(g.DatosIncompletos) as cm:
            paquete(D.DATOS, [], [], [], [], [], self.tmp, incluir=g.CANONICOS)
        self.assertEqual(os.listdir(self.tmp), [])
        self.assertTrue(cm.exception.hallazgos)
        self.assertTrue(all(h.gravedad in (validador.BLOQUEANTE, validador.ADVERTENCIA) for h in cm.exception.hallazgos))

    def test_con_entradas_invalidas_se_rechaza(self):
        with self.assertRaises(ValueError) as cm:
            paquete(dict(D.DATOS, FECHA="mañana"), D.DOCUMENTOS, D.COMPONENTES, D.TERMICAS, D.SENALES,
                              D.COMANDOS, self.tmp)
        self.assertIn("dd/mm/aaaa", str(cm.exception))
        self.assertEqual(os.listdir(self.tmp), [])

    def test_sin_documentos_elegidos(self):
        with self.assertRaises(ValueError):
            paquete(D.DATOS, D.DOCUMENTOS, D.COMPONENTES, D.TERMICAS, D.SENALES, D.COMANDOS, self.tmp, incluir=())

    def test_solo_anexos_no_pide_componentes(self):
        r = paquete(D.DATOS, D.DOCUMENTOS, [], D.TERMICAS, D.SENALES, D.COMANDOS, self.tmp, incluir=("A1", "A2"))
        self.assertEqual(len(r["archivos"]), 2)

    def test_documento_abierto_en_otra_aplicacion_da_error_y_no_corrompe(self):
        ruta = g.generar(D.DATOS, D.DOCUMENTOS, D.COMPONENTES, self.tmp, tipo="SAT")
        hash1 = gestion.sha256(ruta)
        with open(ruta, "rb"):  # en Windows, mover un archivo abierto falla
            try:
                g.generar(dict(D.DATOS, FECHA="03/11/2026"), D.DOCUMENTOS, D.COMPONENTES, self.tmp, tipo="SAT")
                bloqueado = False
            except OSError:
                bloqueado = True
        if bloqueado:
            self.assertEqual(gestion.sha256(ruta), hash1)
        self.assertEqual([f for f in os.listdir(self.tmp) if f.startswith("~tmp_")], [])

    def test_word_no_disponible_o_con_error_no_rompe_la_generacion(self):
        resultado = word_tools.actualizar([os.path.join(self.tmp, "no_existe.docx")])
        self.assertEqual(len(resultado), 1)
        self.assertFalse(resultado[0]["ok"])
        self.assertTrue(resultado[0]["error"])

    def test_sin_word_el_paquete_igual_se_genera_y_avisa(self):
        original = word_tools.word_disponible
        word_tools.word_disponible = lambda: False
        try:
            r = paquete(D.DATOS, D.DOCUMENTOS, D.COMPONENTES, D.TERMICAS, D.SENALES, D.COMANDOS, self.tmp,
                                  incluir=("SAT",))
        finally:
            word_tools.word_disponible = original
        self.assertEqual(len(r["archivos"]), 1)
        codigos = {h.codigo for h in r["informe"].hallazgos}
        self.assertIn("W01", codigos)
        self.assertIn("I02", codigos)
        self.assertEqual(r["estado"], "NO LISTO PARA ENTREGAR", "un índice sin actualizar no puede darse por terminado")


class Interfaz(unittest.TestCase):
    def test_la_ventana_abre_y_los_controles_existen(self):
        try:
            import app
            a = app.App()
        except Exception as e:  # sin entorno gráfico
            self.skipTest(f"sin entorno gráfico: {e}")
        try:
            a.update()
            self.assertEqual(a._seleccion(), ("FAT", "FAT_A1", "FAT_A2"))
            a._preset(g.CANONICOS)
            self.assertEqual(a._seleccion(), g.CANONICOS)
            a.t_refs.agregar(("a.pdf", "d"))
            self.assertEqual(a.t_refs.filas(), [("a.pdf", "d")])
            estado = a._estado_proyecto()
            self.assertEqual(set(estado), {"datos", "documentos", "componentes", "termicas", "senales", "comandos",
                                           "opciones", "carpeta_salida", "pdf_anexo", "pdfs"})
            a._cargar_estado(estado)
        finally:
            a.destroy()


if __name__ == "__main__":
    unittest.main(verbosity=2)
