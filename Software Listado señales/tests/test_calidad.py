"""Paso de calidad: reglas de redaccion, comparacion con la referencia por TAG, validaciones y archivo final."""
import copy
import csv
import sys
import tempfile
import unittest
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import excel_writer  # noqa: E402
import perfiles  # noqa: E402
from calidad import mejorar_archivo, referencia  # noqa: E402
from calidad.libro import corregir, leer_filas  # noqa: E402
from calidad.reglas import Reglas, ReglasInvalidas, cargar, validar as validar_reglas  # noqa: E402
from calidad.texto import normalizar  # noqa: E402
from modelo import Campo, Caratula, Funcion, Nivel, Proyecto, Senal  # noqa: E402

PERFIL = perfiles.cargar_perfil("EPEN")
REGLAS = cargar(PERFIL.carpeta)


def con_reglas(**cambios) -> Reglas:
    d = copy.deepcopy(REGLAS.datos)
    for k, v in cambios.items():
        if isinstance(v, dict) and isinstance(d.get(k), dict):
            d[k].update(v)
        else:
            d[k] = v
    return Reglas(d, REGLAS.carpeta, REGLAS.patrones)


def norm(texto, letra="G", nivel="33KV", reglas=REGLAS):
    return normalizar(texto, letra, reglas, nivel)


class TestTexto(unittest.TestCase):
    def test_tildes_se_quitan_como_en_el_etap(self):
        self.assertEqual(norm("Tensión de Señalización").final, "Tension de Senalizacion")

    def test_tildes_modo_agregar(self):
        r = con_reglas(tildes={"modo": "agregar"})
        self.assertEqual(norm("Falta Tension Auxiliar", reglas=r).final, "Falta Tensión Auxiliar")
        self.assertEqual(norm("PROTECCION SENALIZACION", reglas=r).final, "PROTECCIÓN SEÑALIZACIÓN")
        # una abreviatura o un codigo no es una palabra del diccionario
        self.assertEqual(norm("204te SEC BB Tension F/U", reglas=r).final, "204te SEC BB Tensión F/U")

    def test_tildes_modo_no_tocar(self):
        r = con_reglas(tildes={"modo": "no_tocar"})
        self.assertEqual(norm("Tensión Proteccion", reglas=r).final, "Tensión Proteccion")

    def test_espacios_y_separadores(self):
        self.assertEqual(norm("  204te   Seccionador  229SB04 ").final, "204te Seccionador 229SB04")
        self.assertEqual(norm("204te 2TV04- Falta Vca Med 1").final, "204te 2TV04 - Falta Vca Med 1")
        self.assertEqual(norm("C. Conjunto TI/TV Campo04 Falta").final, "C. Conjunto TI/TV Campo 04 Falta")

    def test_unidad_de_tension_uniforme(self):
        for original, esperado in (("33KV", "33kV"), ("33Kv", "33kV"), ("33 KV", "33kV"), ("6.6KV", "6,6kV"),
                                   ("6,6kV", "6,6kV"), ("132kv", "132kV"), ("13.2 kV", "13,2kV")):
            self.assertEqual(norm(f"Campo 04 {original} Falta").final, f"Campo 04 {esperado} Falta", original)

    def test_reserva_con_nivel(self):
        self.assertEqual(norm("RESERVA 6.6KV Campo 06", nivel="6,6KV").final, "RESERVA 6,6kV Campo 06")
        self.assertEqual(norm("RESERVA 132KV Campo 05", nivel="132KV").final, "RESERVA 132kV Campo 05")

    def test_valores_que_no_se_tocan(self):
        for v in ("N/A", "RESERVA", "=LEN(A2)"):
            r = norm(v)
            self.assertEqual((r.final, r.pasos, r.dudas), (v, [], []))

    def test_codigos_y_tags_se_conservan(self):
        t = "204te Seccionador 229SB04 TC3-03 25204 2TV04 QC4 A3.4 Falta"
        self.assertEqual(norm(t).final, t)
        # un codigo con 'kv' pegado no se confunde con una tension
        self.assertEqual(norm("Interruptor 25204 33kV").final, "Interruptor 25204 33kV")

    def test_abreviaturas_validas_no_cambian(self):
        for t in ("204te INT F/U FM", "204te SEC BB L/R", "305tr PPAL TC1 05 33", "204te LLAVE T/D", "306 PUE/AB", "cos fi", "P Activa"):
            self.assertEqual(norm(t, "J").final, t, t)

    def test_siglas(self):
        self.assertEqual(norm("204te SEC BB Ssaa", "J").final, "204te SEC BB SSAA")
        self.assertEqual(norm("204te TC1 F/U Y ok", "J").final, "204te TC1 F/U Y OK")
        self.assertEqual(norm("Tension Senalizacion OK").final, "Tension Senalizacion OK")
        # 'ok' dentro de otra palabra no es la sigla
        self.assertEqual(norm("Bloque Stoke").final, "Bloque Stoke")

    def test_errores_conocidos_conservan_mayusculas(self):
        self.assertEqual(norm("Falta Tencion Secionador").final, "Falta Tension Seccionador")
        self.assertEqual(norm("TENCION SECIONADOR").final, "TENSION SECCIONADOR")

    def test_numero_de_nivel_sin_unidad(self):
        completa = norm("Proteccion Campo 04 33 Falta Tension", nivel="33KV")
        self.assertEqual(completa.final, "Proteccion Campo 04 33kV Falta Tension")
        self.assertEqual(completa.pasos[0].confianza, "media")
        # el nivel de la fila no lo confirma: no se supone
        dudosa = norm("Proteccion Campo 05 33 Falta Tension", nivel="132KV")
        self.assertEqual(dudosa.final, "Proteccion Campo 05 33 Falta Tension")
        self.assertEqual([d.tipo for d in dudosa.dudas], ["tension_sin_unidad"])
        # un numero que no es un nivel (numero de campo) no se toca ni se pregunta
        self.assertEqual(norm("Campo 04 05 Falta", nivel="33KV").dudas, [])

    def test_texto_con_otro_nivel_queda_para_revision(self):
        r = norm("Campo 05 33KV QC5 ACTUADA", nivel="132KV")
        self.assertEqual(r.final, "Campo 05 33kV QC5 ACTUADA")     # solo se unifica la unidad
        self.assertEqual([d.tipo for d in r.dudas], ["nivel_distinto"])

    def test_palabra_repetida_se_informa_no_se_corrige(self):
        r = norm("204te PPAL INT INT", "J")
        self.assertEqual(r.final, "204te PPAL INT INT")
        self.assertEqual([d.tipo for d in r.dudas], ["palabra_repetida"])

    def test_largo_scada_nunca_se_excede(self):
        # 20 caracteres exactos; la correccion (quitar tildes) no lo agranda, y una que lo agrande se descarta
        r = con_reglas(terminos=[{"buscar": "SEC", "poner": "SECCION", "columnas": ["J"], "regla": "prueba"}])
        res = norm("204te SEC BB F/U FM", "J", reglas=r)
        self.assertEqual(res.final, "204te SEC BB F/U FM")
        self.assertEqual([d.tipo for d in res.dudas], ["excede_largo"])
        self.assertEqual(res.pasos, [])

    def test_no_se_vacia_una_descripcion(self):
        r = con_reglas(errores_conocidos={"x": ""}, tildes={"modo": "no_tocar"})
        self.assertTrue(norm("hola", reglas=r).final)

    def test_idempotente(self):
        for t in ("  Campo04 33Kv  Tensión- Falta  Ssaa ok ", "RESERVA 6.6KV Campo 06", "2TV04- Falta Vca Med 1"):
            una = norm(t).final
            self.assertEqual(norm(una).final, una)
            self.assertEqual(norm(una).pasos, [])

    def test_cada_paso_se_registra(self):
        r = norm("  Campo04 33Kv ")
        self.assertEqual(r.final, "Campo 04 33kV")
        self.assertEqual({p.regla for p in r.pasos}, {"espacios", "campo_pegado", "tension_unidad"})
        self.assertTrue(all(p.motivo and p.confianza for p in r.pasos))


class TestReglas(unittest.TestCase):
    def test_perfil_epen_valido(self):
        self.assertEqual(validar_reglas(REGLAS.datos), [])
        self.assertEqual(REGLAS.largo("J"), PERFIL.largo_max("desc_scada"))

    def test_no_se_puede_declarar_texto_una_columna_de_identificadores(self):
        d = copy.deepcopy(REGLAS.datos)
        d["columnas_texto"].append("H")
        self.assertTrue(any("identificadores" in p for p in validar_reglas(d)))

    def test_falta_el_archivo(self):
        with tempfile.TemporaryDirectory() as t, self.assertRaises(ReglasInvalidas):
            cargar(t)


def proyecto_sucio() -> Proyecto:
    car = Caratula(cliente="ENTE", obra="LAT 132 kV PRUEBA", titulo="ETAP - LISTADO DE SEÑALES",
                   numero_documento="ETAP-0722-ET-CT-MC-LI-6209", archivo_magnetico="ETAP-0722-ET-CT-MC-LI-6209", revision="1")
    mk = lambda f, th, dh, ts, off, ds, **kw: Senal(f, tag_hmi=th, desc_hmi=dh, tag_scada=ts, offset=off, desc_scada=ds, **kw)
    a = Campo("04", "ACOMETIDAS", "204te", senales=[
        mk(Funcion.ALARMAS, "Seccionador_229SB04_Falta_Ssaa", "204te Seccionador 229SB04 Falta Tension Auxiliar Ssaa", "204.151", 205, "204te SEC BB Ssaa"),
        mk(Funcion.ALARMAS, "Campo_04_33KV_Falta_110Vcc", "204te CAMPO 04 33Kv Falta 110Vcc", "204.231", 206, "204te TC1 INT 110VCC"),
        mk(Funcion.ALARMAS, "2TV04_Falta_Vca", "204te 2TV04- Falta Vca Med 1", "204.191", 207, "204te 2TV0 INT med 1"),
        mk(Funcion.SENALIZACION, "Interruptor_25204_Ab_Ce", "204te Interruptor 25204 Abierto/Cerrado", "204.322C", 208, "204te INT"),
    ])
    b = Campo("TP1", "TRAFO", "302TP1", senales=[
        mk(Funcion.ALARMAS, "RES", "RESERVA 33KV Campo TP1", "N/A", None, "RESERVA", es_reserva=True),
    ])
    return Proyecto("EPEN", caratula=car, niveles=[Nivel("33KV", "2", [a, b])])


class TestArchivo(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dir = tempfile.TemporaryDirectory()
        cls.entrada = Path(cls.dir.name) / "listado.xlsx"
        excel_writer.escribir_xlsx(proyecto_sucio(), PERFIL, cls.entrada, hasta_columna="O")
        cls.informe = mejorar_archivo(cls.entrada, ref=None)

    @classmethod
    def tearDownClass(cls):
        cls.dir.cleanup()

    def test_no_pisa_la_entrada_y_deja_los_tres_archivos(self):
        salida = Path(self.informe.salida)
        self.assertEqual(salida.name, "listado_final.xlsx")
        for p in (salida, Path(self.informe.ruta_md), Path(self.informe.ruta_csv)):
            self.assertTrue(p.is_file(), p)
        ws = openpyxl.load_workbook(self.entrada)["EPEN"]
        self.assertIn("33Kv", " ".join(str(c.value) for c in ws["G"]))          # la entrada sigue como estaba

    def test_corrige_solo_texto(self):
        ws = openpyxl.load_workbook(self.informe.salida)["EPEN"]
        self.assertEqual(ws["G6"].value, "204te Seccionador 229SB04 Falta Tension Auxiliar SSAA")
        self.assertEqual(ws["J6"].value, "204te SEC BB SSAA")
        self.assertEqual(ws["G7"].value, "204te CAMPO 04 33kV Falta 110Vcc")
        self.assertEqual(ws["G8"].value, "204te 2TV04 - Falta Vca Med 1")
        for fila in range(6, 11):
            self.assertEqual(ws[f"I{fila}"].value, openpyxl.load_workbook(self.entrada)["EPEN"][f"I{fila}"].value)
        self.assertIn("RESERVA 33kV Campo TP1", [c.value for c in ws["G"]])
        self.assertIn("RESERVA", [c.value for c in ws["J"]])

    def test_aprobado_y_sin_bloqueantes(self):
        self.assertTrue(self.informe.aprobado, [c.detalle for c in self.informe.bloqueantes])
        codigos = {c.codigo for c in self.informe.chequeos}
        for esperado in ("libro_abre", "identificadores_intactos", "filas_conservadas", "sin_duplicados_nuevos",
                         "segunda_pasada_estable", "formato_conservado[EPEN]", "formato_conservado[Caratula]"):
            self.assertIn(esperado, codigos)

    def test_encabezado_y_pie_como_el_etap(self):
        ws = openpyxl.load_workbook(self.informe.salida)["EPEN"]
        self.assertEqual(ws.oddHeader.center.text, "LAT 132 kV PRUEBA\nETAP - LISTADO DE SEÑALES")
        self.assertEqual(ws.oddFooter.left.text, "ETAP-0722-ET-CT-MC-LI-6209-r1")
        self.assertEqual(ws.oddFooter.center.text, "&P+1 de &N+1")

    def test_registro_de_cambios_auditable(self):
        with open(self.informe.ruta_csv, encoding="utf-8-sig", newline="") as f:
            filas = list(csv.DictReader(f, delimiter=";"))
        aplicados = [f for f in filas if f["estado"] == "aplicado" and f["tipo"] != "presentacion"]
        self.assertTrue(aplicados)
        for f in aplicados:
            self.assertTrue(f["hoja"] and f["celda"] and f["regla"] and f["confianza"] and f["motivo"], f)
            self.assertNotEqual(f["texto_original"], f["texto_final"])
        j6 = [f for f in aplicados if f["celda"] == "J6"]
        self.assertEqual(j6[0]["tag"], "204.151")
        self.assertEqual(j6[0]["texto_original"], "204te SEC BB Ssaa")
        self.assertEqual(j6[0]["texto_final"], "204te SEC BB SSAA")

    def test_informe_refleja_el_resultado_real(self):
        md = Path(self.informe.ruta_md).read_text(encoding="utf-8")
        self.assertIn(f"| Celdas corregidas | {self.informe.celdas_cambiadas()} |", md)
        self.assertIn("APROBADO", md)
        self.assertIn("No se uso un archivo de referencia", md)

    def test_segunda_generacion_no_cambia_nada(self):
        otra = Path(self.dir.name) / "segunda.xlsx"
        inf2 = mejorar_archivo(self.informe.salida, otra, ref=None, escribir_informe=False)
        self.assertEqual([c for c in inf2.cambios if c.tipo != "presentacion"], [])
        self.assertEqual(inf2.presentacion, [])
        a, b = openpyxl.load_workbook(self.informe.salida), openpyxl.load_workbook(otra)
        for nombre in a.sheetnames:
            self.assertEqual([[c.value for c in r] for r in a[nombre].iter_rows()],
                             [[c.value for c in r] for r in b[nombre].iter_rows()])

    def test_los_pendientes_no_se_corrigen_solos(self):
        # el campo se llama TP1 en el nivel 33KV: nada que adivinar; el unico texto con nivel distinto queda sin tocar
        sucio = proyecto_sucio()
        sucio.niveles[0].campos[0].senales[1].desc_hmi = "204te CAMPO 04 132KV Falta 110Vcc"
        ruta = Path(self.dir.name) / "nivel.xlsx"
        excel_writer.escribir_xlsx(sucio, PERFIL, ruta, hasta_columna="O")
        inf = mejorar_archivo(ruta, ref=None, escribir_informe=False)
        self.assertIn("nivel_distinto", [p.tipo for p in inf.pendientes])
        ws = openpyxl.load_workbook(inf.salida)["EPEN"]
        self.assertEqual(ws["G7"].value, "204te CAMPO 04 132kV Falta 110Vcc")

    def test_no_se_pierde_ninguna_fila(self):
        a = leer_filas(openpyxl.load_workbook(self.entrada)["EPEN"], REGLAS)
        b = leer_filas(openpyxl.load_workbook(self.informe.salida)["EPEN"], REGLAS)
        self.assertEqual([(f.fila, f.tag, f.funcion) for f in a], [(f.fila, f.tag, f.funcion) for f in b])


class TestReferencia(unittest.TestCase):
    """La referencia vincula solo por TAG exacto + funcion + campo; nunca por fila ni por parecido."""

    def hoja(self, filas):
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "EPEN"
        for i, (nivel, funcion, th, g, ts, j) in enumerate(filas, start=6):
            ws[f"B{i}"], ws[f"E{i}"], ws[f"F{i}"], ws[f"G{i}"], ws[f"H{i}"], ws[f"J{i}"] = nivel, funcion, th, g, ts, j
        return ws

    def comparar(self, mias, suyas):
        ws, ref = self.hoja(mias), self.hoja(suyas)
        return ws, referencia.comparar(ws, leer_filas(ws, REGLAS), referencia.indexar(ref, REGLAS), REGLAS)

    def test_mismo_tag_y_solo_estilo_adopta_el_texto_aprobado(self):
        ws, (res, cambios, pend) = self.comparar(
            [("33KV", "ALARMAS", "a", "204te Falta TENSION de Comando", "204.121", "204te INT F/U CMDO")],
            [("33KV", "ALARMAS", "a", "204te Falta Tension de Comando", "204.121", "204te INT F/U CMDO")])
        self.assertEqual((res.vinculadas, res.adoptadas, res.coinciden), (1, 1, 1))
        self.assertEqual(ws["G6"].value, "204te Falta Tension de Comando")
        self.assertEqual(cambios[0].regla, "texto_aprobado_de_referencia")
        self.assertEqual(pend, [])

    def test_diferencia_funcional_no_se_copia(self):
        ws, (res, cambios, pend) = self.comparar(
            [("33KV", "ALARMAS", "a", "204te Falta Tension de Comando", "204.121", "204te INT F/U CMDO")],
            [("33KV", "ALARMAS", "a", "204te Falta Fuerza Motriz", "204.121", "204te INT F/U FM")])
        self.assertEqual(res.vinculadas, 1)
        self.assertEqual(cambios, [])
        self.assertEqual(ws["G6"].value, "204te Falta Tension de Comando")
        self.assertEqual({p.tipo for p in pend}, {"difiere_de_referencia"})

    def test_mismo_tag_en_otro_campo_es_ambiguo(self):
        _, (res, cambios, pend) = self.comparar(
            [("33KV", "ALARMAS", "a", "204te Falta Tension", "204.121", "204te F/U")],
            [("132KV", "ALARMAS", "a", "303LC Falta Tension", "204.121", "303LC F/U")])
        self.assertEqual((res.vinculadas, len(res.ambiguas)), (0, 1))
        self.assertEqual(cambios, [])
        self.assertEqual(pend[0].tipo, "referencia_ambigua")

    def test_varios_candidatos_es_ambiguo(self):
        _, (res, _, _) = self.comparar(
            [("33KV", "ALARMAS", "a", "204te X", "204.121", "204te X")],
            [("33KV", "ALARMAS", "a", "204te X", "204.121", "204te X"), ("33KV", "ALARMAS", "b", "204te Y", "204.121", "204te Y")])
        self.assertEqual(len(res.ambiguas), 1)

    def test_na_y_senales_sin_tag_no_se_comparan(self):
        _, (res, _, _) = self.comparar([("33KV", "ALARMAS", "", "RESERVA", "N/A", "RESERVA")], [("33KV", "ALARMAS", "", "RESERVA", "N/A", "RESERVA")])
        self.assertEqual((res.examinadas, res.vinculadas), (0, 0))

    def test_la_misma_funcion_distingue_senal_y_comando(self):
        _, (res, _, _) = self.comparar(
            [("33KV", "COMANDO", "a", "204te INT Apertura/Cierre", "204.322C", "204te INT")],
            [("33KV", "SEÑALIZACION", "a", "204te INT Abierto/Cerrado", "204.322C", "204te INT")])
        self.assertEqual((res.vinculadas, len(res.sin_referencia)), (0, 1))

    @unittest.skipUnless((PERFIL.carpeta.parents[2] / REGLAS.datos["referencia"]["archivo"]).is_file(), "falta el ETAP de Ejemplos")
    def test_el_etap_real_contra_si_mismo_coincide_entero(self):
        ruta = PERFIL.carpeta.parents[2] / REGLAS.datos["referencia"]["archivo"]
        ws = openpyxl.load_workbook(ruta)["EPEN"]
        res, cambios, _ = referencia.comparar(ws, leer_filas(ws, REGLAS), referencia.indexar(ws, REGLAS), REGLAS)
        self.assertEqual(cambios, [])
        self.assertEqual(res.difieren, [])
        self.assertGreater(res.coinciden, 100)
        self.assertTrue(referencia.auditar(ws, REGLAS))        # la referencia tiene defectos propios y se informan


class TestSobreElETAP(unittest.TestCase):
    """El ETAP terminado, pasado por el paso de calidad, no pierde datos ni formato."""
    RUTA = PERFIL.carpeta.parents[2] / REGLAS.datos["referencia"]["archivo"]

    @unittest.skipUnless(RUTA.is_file(), "falta el ETAP de Ejemplos")
    def test_no_rompe_el_etap(self):
        with tempfile.TemporaryDirectory() as t:
            inf = mejorar_archivo(self.RUTA, Path(t) / "etap_final.xlsx", ref=None)
            self.assertTrue(inf.aprobado, [c.detalle for c in inf.bloqueantes])
            self.assertEqual(inf.examinadas > 1000, True)
            # solo cambios de redaccion segura: ninguna regla toca tags ni offsets (lo comprueba el validador)
            self.assertNotIn("presentacion", {c.tipo for c in inf.cambios})   # ya trae encabezado y pie


if __name__ == "__main__":
    unittest.main()
