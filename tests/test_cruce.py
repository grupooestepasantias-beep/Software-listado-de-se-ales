"""Cruce EF ↔ listas de señales, señales de tablero e índice sin la palabra HOJA (cajas sintéticas: sin OCR)."""
import unittest
from types import SimpleNamespace

import cruce
import documentos
import pdf_plano
from documentos import Caja, Documento, PaginaDoc
from modelo import Funcion


def caja(x, y, t):
    return Caja(x, y, len(t) * 5, 8, t)


def pagina_lista(n, hoja, columnas, modulo="Entradas Digitales"):
    """columnas: [(nombre, relé, borne)]; una columna cada 100 pt, como en las hojas LISTA DE SEÑALES Y ALARMAS."""
    cajas = [caja(50, 40, "LISTA DE SEÑALES Y ALARMAS")]
    def c(cx, y, t):          # centrada en la columna, como en el plano
        return caja(cx - len(t) * 2.5, y, t)

    for i, (nombre, rele, borne) in enumerate(columnas):
        cx = 100 + 100 * i
        cajas += [c(cx, 80 + 6 * (i % 2), nombre), c(cx, 400, "UTR1.1.1"), c(cx, 412, "SEL 2244"), c(cx, 424, modulo)]
        cajas += [c(cx, y, t) for y, t in ((200, rele), (215, borne)) if t]
    return PaginaDoc("a.pdf", n, cajas, "ocr", hoja=hoja, titulo="LISTA DE SEÑALES Y ALARMAS",
                     seccion="LISTA DE SEÑALES Y ALARMAS")


def doc(*paginas):
    d = Documento("a.pdf", "a.pdf")
    d.paginas = list(paginas)
    return d


def ls(*columnas, reserva=False):
    return SimpleNamespace(columnas=list(columnas), es_reserva=reserva, verificacion="")


def ef(pagina, campo, *senales):
    return SimpleNamespace(archivo="b.pdf", pagina=pagina, campo=campo, nivel="13,2KV", senales=list(senales))


COLUMNAS = [("RECONECTADOR 152/01 ABIERT0", "-KR4.1", "14-D-1"), ("SECCIONADOR 189/01 FALTA TENSION", "-KS6.1", "14-B-1"),
            ("TENSIONES INTERRUMPIDAS", "-KV1.1", "14-B-1"), ("CAMPO 01 MANDO EN TELECONTROL", "-KR9.1", "15-D-1"),
            ("SENALIZACION PROT. GRUPO A -XDI.1: 1Q", "-KR1.1", "15-D-1"), ("SENALIZACION PROT. GRUPO B", "-KR2.1", "15-D-1")]


class TestCruce(unittest.TestCase):
    def setUp(self):
        self.d = doc(pagina_lista(44, "74", COLUMNAS))

    def test_la_lista_se_lee_por_columnas(self):
        celdas = cruce.celdas_de_lista(self.d.paginas[0])
        self.assertEqual(len(celdas), 6)
        self.assertEqual((celdas[0].rele, celdas[0].borne, celdas[0].codigos), ("-KR4.1", "14-D-1", ("152/01",)))

    def test_verificada_distinta_sin_respaldo_y_recuperada(self):
        senales = [ls("Reconectador 152/01 abierto"), ls("Seccionador 189/01 falta tensión"),
                   ls("Disparo de nada 152/01"), ls("Señalización protección grupo A"),
                   ls("Campo 01 mando en Telecontrol")]
        inf = cruce.verificar([ef(42, "01", *senales)], [self.d])
        estados = {v.rotulo: v.estado for v in inf.verificaciones}
        self.assertEqual(estados["Reconectador 152/01 abierto"], "verificada")      # O/0 del OCR
        self.assertEqual(estados["Seccionador 189/01 falta tensión"], "verificada")
        self.assertEqual(estados["Señalización protección grupo A"], "verificada")  # abreviatura y referencia XDI
        self.assertEqual(estados["Campo 01 mando en Telecontrol"], "verificada")
        self.assertEqual(estados["Disparo de nada 152/01"], "sin_respaldo")
        self.assertTrue(all(v.celda.origen for v in inf.verificaciones if v.celda))
        # lo que está en la lista y no en el EF queda aparte, con su origen
        sobran = {c.texto for c in inf.recuperadas}
        self.assertIn("TENSIONES INTERRUMPIDAS", sobran)
        self.assertIn("SENALIZACION PROT. GRUPO B", sobran)

    def test_grupo_a_y_grupo_b_no_se_confunden(self):
        inf = cruce.verificar([ef(42, "01", ls("Señalización protección grupo B"))], [self.d])
        self.assertIn("GRUPO B", inf.verificaciones[0].celda.texto)

    def test_sin_hoja_de_lista_nada_se_verifica_ni_se_inventa(self):
        inf = cruce.verificar([ef(42, "01", ls("Reconectador 152/01 abierto"))], [doc()])
        self.assertTrue(inf.sin_lista)
        self.assertEqual(inf.verificaciones[0].estado, "sin_respaldo")
        self.assertEqual(inf.recuperadas, [])

    def test_una_lista_de_otro_campo_no_respalda(self):
        inf = cruce.verificar([ef(42, "03", ls("Campo 03 mando en Telecontrol"))], [self.d])
        self.assertNotEqual(inf.verificaciones[0].estado, "verificada")

    def test_los_comandos_se_buscan_entre_las_salidas(self):
        salidas = [("Apertura RECONECTADOR 152/01", "", ""), ("Cierre RECONECTADOR 152/01", "", "")] + \
                  [(f"Otra salida {i}", "", "") for i in range(5)]
        entradas = [("SENALIZACION PROT. GRUPO A", "", "")] + [(f"Otra entrada {i}", "", "") for i in range(6)]
        d = doc(pagina_lista(44, "74", salidas, modulo="Salidas Digitales"), pagina_lista(45, "75", entradas))
        inf = cruce.verificar([ef(43, "01", ls("Apertura reconectador 152/01"), ls("Comando protección grupo A"))], [d])
        estados = [v.estado for v in inf.verificaciones]
        self.assertEqual(estados, ["verificada", "sin_respaldo"])


class TestTablero(unittest.TestCase):
    def pagina(self):
        nombres = ["Reserva", "Alimentacion", "Falta de tension", "Interruptor ppal"]
        cajas = [caja(500, 45, "ENTRADAS DIGITALES")]
        for i, n in enumerate(nombres):
            x = 120 + 110 * i
            cajas += [caja(x, 68, n), caja(x, 295, f"X4/{9 + i}"), caja(x, 528, f"DI{9 + i}")]
        cajas += [caja(230, 79, "de inversor"), caja(340, 79, "barra 380/220Vca"), caja(450, 79, "220 Vca seg. abierto"),
                  caja(120, 394, "110"), caja(132, 394, "1,5mm2/Ce")]
        return PaginaDoc("t.pdf", 10, cajas, "ocr", hoja="10", titulo="ENTRADAS DIGITALES - ALARMAS")

    def test_el_nombre_de_cada_columna_se_arma_con_sus_renglones(self):
        celdas = cruce.senales_de_tablero(self.pagina())
        self.assertEqual([c.texto for c in celdas],
                         ["Reserva", "Alimentacion de inversor", "Falta de tension barra 380/220Vca",
                          "Interruptor ppal 220 Vca seg. abierto"])
        self.assertEqual((celdas[0].modulo, celdas[0].borne), ("DI9", "X4/9"))
        self.assertEqual(len(celdas), 4)

    def test_las_hojas_de_tablero_no_leidas_por_el_ef_van_al_informe(self):
        inf = cruce.verificar([], [doc(self.pagina())])
        self.assertEqual(len(inf.tableros), 4)
        self.assertIn("de reserva", inf.resumen())

    def test_una_hoja_que_el_ef_ya_leyo_no_se_repite(self):
        pg = SimpleNamespace(archivo="t.pdf", pagina=10, campo="", nivel="", senales=[])
        self.assertEqual(cruce.verificar([pg], [doc(self.pagina())]).tableros, [])


class TestIndiceSinPalabraHoja(unittest.TestCase):
    def test_hoja_detalle_revision(self):
        cajas = [caja(195, 101, "HOJA"), caja(362, 108, "DETALLE"), caja(547, 108, "REVISION"),
                 caja(606, 101, "HOJA"), caja(783, 108, "DETALLE"),
                 caja(196, 133, "01"), caja(244, 133, "PORTADA"),
                 caja(195, 151, "02"), caja(239, 151, "INDICE DE CONTENIDO"),
                 caja(195, 275, "09"), caja(249, 275, "SENALES DIGITALES"), caja(560, 275, "0"),
                 caja(606, 133, "12"), caja(650, 133, "SENALES DIGITALES")]
        pg = PaginaDoc("a.pdf", 2, cajas, "ocr", es_indice=True)
        self.assertEqual(documentos.leer_indice([pg]),
                         {1: "PORTADA", 2: "INDICE DE CONTENIDO", 9: "SENALES DIGITALES", 12: "SENALES DIGITALES"})


class TestPartirPorCampo(unittest.TestCase):
    def test_un_modulo_con_dos_campos_se_corta_donde_cambia(self):
        textos = ["Cierre reconectador 152/01", "Apertura reconectador 152/01", "Comando protección grupo A",
                  "Cierre reconectador 152/03", "Apertura reconectador 152/03", "Comando protección grupo A"]
        senales = [pdf_plano.LecturaSenal(42, Funcion.ALARMAS, t, columnas=[t], modulo=0) for t in textos]
        partes = pdf_plano._partir_por_campo(senales, [object()])
        self.assertEqual([p[0] for p in partes], ["01", "03"])
        self.assertEqual([len(p[1]) for p in partes], [3, 3])


if __name__ == "__main__":
    unittest.main()
