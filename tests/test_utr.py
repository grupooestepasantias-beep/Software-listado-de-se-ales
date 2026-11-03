"""UTR (columnas P, S, T): tipo, placa y entrada/salida leídas del plano de ingeniería."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pdf_plano  # noqa: E402
import perfiles  # noqa: E402
from modelo import NA, Funcion, TipoPunto  # noqa: E402

PLANO = Path(__file__).resolve().parent.parent.parent / "Ejemplos" / "ETAP-0325-ET-CT-PL-EF-6402_1.pdf"
try:
    import pymupdf
except ImportError:  # pragma: no cover
    pymupdf = None
try:
    import tkinter as tk
except ImportError:  # pragma: no cover
    tk = None

PASO, X0 = 12.06, 649.4


def modulo(rotulos: dict[int, str], x0: float = X0, ruido: float = 0.0):
    """Módulo de 32 bornes dibujado como el plano: borne k en x0 - (k-1)·paso, con 2,4 pasos de hueco entre bloques.
    rotulos = {borne: texto}; los bornes sin texto quedan sin etiqueta (como el borne 16 del módulo de salidas)."""
    orden = []
    for k in sorted(rotulos):
        d = (k - 1) + (2.4 if k > 16 else 0)
        orden.append((x0 - d * PASO + ruido * (k % 3 - 1), 100.0, rotulos[k]))
    return orden


def entradas_digitales() -> dict[int, str]:
    negativos = {10, 12, 14, 16, 26, 28, 30, 32}
    return {k: ("Negativo 48 VCC" if k in negativos else f"Señal del borne {k}") for k in range(1, 33)}


class TestNumeracion(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.cfg = pdf_plano.cargar_config(perfiles.cargar_perfil("EPEN"))

    def numerar(self, rotulos, **kw):
        return pdf_plano._numerar_modulo(modulo(rotulos, **kw), X0, PASO, self.cfg)

    def test_entradas_no_cuentan_los_bornes_negativos(self):
        tipo, nums, aviso = self.numerar(entradas_digitales())
        self.assertEqual((tipo, aviso), ("DI", ""))
        por_borne = dict(zip(sorted(entradas_digitales()), nums))
        self.assertEqual(por_borne[1], 1)
        self.assertEqual(por_borne[9], 9)
        self.assertEqual(por_borne[10], None)       # Negativo
        self.assertEqual(por_borne[11], 10)
        self.assertEqual(por_borne[17], 13)
        self.assertEqual(por_borne[21], 17)         # el borne 21 es DI17 (el ejemplo del plano 6402)
        self.assertEqual(por_borne[22], 18)
        self.assertEqual(por_borne[31], 24)         # 24 entradas en total
        self.assertEqual(max(n for n in nums if n), 24)

    def test_salidas_el_numero_es_la_mitad_del_borne_par(self):
        rotulos = {k: ("Positivo 110 Vcc" if k % 2 else "Reserva") for k in range(1, 33) if k != 16}  # falta el borne 16
        rotulos[18], rotulos[20] = "Interruptor 25204 Apertura", "Interruptor 25204 Cierre"
        tipo, nums, aviso = self.numerar(rotulos)
        por_borne = dict(zip(sorted(rotulos), nums))
        self.assertEqual((tipo, aviso), ("DO", ""))
        self.assertEqual((por_borne[2], por_borne[14]), (1, 7))
        self.assertEqual((por_borne[18], por_borne[20]), (9, 10))
        self.assertEqual(por_borne[32], 16)
        self.assertIsNone(por_borne[17])

    def test_aguanta_el_ruido_de_las_posiciones(self):
        tipo, nums, aviso = self.numerar(entradas_digitales(), ruido=2.0)
        self.assertEqual(aviso, "")
        self.assertEqual(sorted(n for n in nums if n), list(range(1, 25)))

    def test_si_la_geometria_no_cierra_numera_por_orden_y_avisa(self):
        rotulos = entradas_digitales()
        rotulos[10] = "Señal rara"                  # una señal donde el plano tiene un borne negativo
        tipo, nums, aviso = self.numerar(rotulos)
        self.assertIn("por orden", aviso)
        self.assertEqual([n for n in nums if n][:3], [1, 2, 3])

    def test_modulo_analogico_no_tiene_entradas_digitales(self):
        tipo, nums, _ = pdf_plano._numerar_modulo(
            [(X0 - i * PASO, 0.0, t) for i, t in enumerate(["Arrollamiento 132 KV 0-150º C"] + ["Reserva"] * 7)],
            X0, PASO, self.cfg)
        self.assertEqual((tipo, set(nums)), ("AI", {None}))

    def test_paso_entre_bornes(self):
        self.assertAlmostEqual(pdf_plano._paso_de([modulo(entradas_digitales())]), PASO, delta=0.3)


class TestSenales(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.perfil = perfiles.cargar_perfil("EPEN")
        cls.cfg = pdf_plano.cargar_config(cls.perfil)

    def test_doble_bit_lleva_la_entrada_de_cada_estado(self):
        textos = ["Seccionador 229SL04 Cerrado", "Seccionador 229SL04 Abierto", "Seccionador 229SL04 Local",
                  "Seccionador 229SL04 Remoto"]
        r = pdf_plano._senales_de_banda(textos, self.cfg, 29, numeros=[17, 18, 19, 20], tipo="DI", modulo=0)
        # la 1ª fila es el 1er estado (Abierto, Local): su entrada es la de ESE rótulo, no la de su posición
        self.assertEqual([(s.columnas[0], s.entradas) for s in r],
                         [("Seccionador 229SL04 Abierto", [18, 17]), ("Seccionador 229SL04 Local", [19, 20])])
        self.assertTrue(all(s.tipo == "DI" and s.modulo == 0 for s in r))

    def test_la_alimentacion_no_ocupa_entrada(self):
        r = pdf_plano._senales_de_banda(["Negativo 48 VCC", "Reserva", "Falla X Algo"], self.cfg, 1,
                                        numeros=[None, 5, 6], tipo="DI")
        self.assertEqual([(s.funcion, s.entradas) for s in r], [(Funcion.RESERVA, [5]), (Funcion.ALARMAS, [6])])

    def test_comando_de_dos_bornes_va_como_par(self):
        r = pdf_plano._senales_de_banda(["Positivo 110 Vcc", "Interruptor 25204 Apertura", "Positivo 110 Vcc",
                                         "Interruptor 25204 Cierre"], self.cfg, 29, numeros=[None, 9, None, 10], tipo="DO")
        self.assertEqual((r[0].funcion, r[0].entradas), (Funcion.COMANDO, [9, 10]))

    def test_expandir_placas(self):
        f = pdf_plano.expandir_placas
        self.assertEqual(f("A4.2", 3), ["A4.2", "A4.3", "A4.4"])
        self.assertEqual(f("A4.2, A5.1", 3), ["A4.2", "A5.1", "A5.2"])
        self.assertEqual(f("", 3), [])
        self.assertEqual(f("A4.2", 1), ["A4.2"])
        self.assertEqual(f("X", 2), ["X", "X"])           # sin número no se puede seguir: se repite

    def armar(self, destinos):
        sen = pdf_plano._senales_de_banda(
            ["Seccionador 229SL04 Cerrado", "Seccionador 229SL04 Abierto", "Reserva", "Falla X Algo"], self.cfg, 5,
            numeros=[17, 18, 19, 20], tipo="DI", modulo=0)
        sen += pdf_plano._senales_de_banda(
            ["Positivo 110 Vcc", "Interruptor 25204 Apertura", "Positivo 110 Vcc", "Interruptor 25204 Cierre"],
            self.cfg, 5, numeros=[None, 9, None, 10], tipo="DO", modulo=1)
        pg = pdf_plano.PaginaLeida(5, "33KV", "04", sen, modulos=[pdf_plano.ModuloLeido("DI", 4),
                                                                   pdf_plano.ModuloLeido("DO", 1)])
        return pdf_plano.a_niveles([pg], self.perfil, destinos=destinos)

    def test_a_niveles_completa_tipo_placa_y_entrada(self):
        niv = self.armar({5: ("33KV", "04", "", "", "LC", "", False, "A4.2")})
        filas = {s.desc_hmi or s.funcion.value + str(i): s for i, s in enumerate(niv[0].campos[0].senales)}
        por_desc = {s.desc_hmi: s for s in niv[0].campos[0].senales if s.desc_hmi}
        doble = por_desc["204LC Seccionador 229SL04 Abierto/Cerrado"]
        self.assertEqual((doble.tipo_punto, doble.placa, doble.entrada), (TipoPunto.DI, "A4.2", "18"))
        i = niv[0].campos[0].senales.index(doble)
        seg = niv[0].campos[0].senales[i + 1]
        self.assertEqual((seg.segunda_fila, seg.tipo_punto, seg.placa, seg.entrada), (True, TipoPunto.DI, "A4.2", "17"))
        falla = por_desc["204LC Falla X Algo"]
        self.assertEqual((falla.placa, falla.entrada), ("A4.2", "20"))
        cmd = por_desc["204LC Interruptor 25204 Apertura/Cierre"]
        self.assertEqual((cmd.tipo_punto, cmd.placa, cmd.entrada), (TipoPunto.DO, "A4.3", "9/10"))   # 2º módulo: A4.3
        reserva = niv[-1].campos[0].senales[0]
        self.assertEqual((niv[-1].nombre, reserva.tipo_punto, reserva.placa, reserva.entrada), ("RESERVAS", TipoPunto.DI, "A4.2", "19"))

    def test_sin_placas_queda_la_entrada_y_la_placa_en_na(self):
        niv = self.armar({5: ("33KV", "04", "", "", "LC", "", False, "")})
        falla = next(s for s in niv[0].campos[0].senales if s.desc_hmi.endswith("Falla X Algo"))
        self.assertEqual((falla.placa, falla.entrada, falla.tipo_punto), (NA, "20", TipoPunto.DI))

    def test_mediciones_y_lo_demas_quedan_en_na(self):
        pg = pdf_plano.PaginaLeida(5, "33KV", "04", pdf_plano._senales_de_banda(["Falla X Algo"], self.cfg, 5),
                                   mediciones=True)
        niv = pdf_plano.a_niveles([pg], self.perfil)
        med = [s for s in niv[0].campos[0].senales if s.funcion == Funcion.MEDICION]
        self.assertTrue(med and all((s.placa, s.entrada, s.tipo_punto) == (NA, NA, None) for s in med))


@unittest.skipUnless(pymupdf and PLANO.exists(), "falta pymupdf o el plano de ejemplo")
class TestPlanoReal(unittest.TestCase):
    """Página 29 del plano 6402: módulos A4.2 (24 DI), A4.3 (24 DI) y A4.4 (16 DO), medidos contra el dibujo."""

    @classmethod
    def setUpClass(cls):
        cls.perfil = perfiles.cargar_perfil("EPEN")
        cls.pg = pdf_plano.leer_plano(PLANO, cls.perfil, solo_paginas={29})[0]

    def por_texto(self):
        return {s.texto: s for s in self.pg.senales if not s.es_reserva}

    def test_tres_modulos_sin_avisos(self):
        self.assertEqual([(m.tipo, m.aviso) for m in self.pg.modulos], [("DI", ""), ("DI", ""), ("DO", "")])

    def test_las_entradas_del_ejemplo_del_usuario(self):
        s = self.por_texto()
        # DI17 y DI18 (los círculos del plano) son Cerrado y Abierto del seccionador 229SL04; los bornes 21 y 22 NO
        self.assertEqual(s["Seccionador 229SL04 Abierto/Cerrado"].entradas, [18, 17])
        self.assertEqual(s["Seccionador 229SL04 Local/Remoto"].entradas, [19, 20])
        self.assertEqual(s["Interruptor 25204 Abierto/Cerrado"].entradas, [2, 1])
        self.assertEqual(s["Seccionador 229SB04 Abierto/Cerrado"].entradas, [10, 9])    # el borne 10 es Negativo: no cuenta

    def test_salidas(self):
        s = self.por_texto()
        self.assertEqual(s["Interruptor 25204 Apertura/Cierre"].entradas, [9, 10])
        self.assertEqual(s["Seccionador 229SB04 Apertura/Cierre"].entradas, [11, 12])
        self.assertEqual(s["Seccionador 229SL04 Apertura/Cierre"].entradas, [13, 14])

    def test_cada_modulo_numera_sus_24_entradas_sin_repetir(self):
        for mod in (0, 1):
            nums = sorted(n for ls in self.pg.senales if ls.modulo == mod for n in ls.entradas)
            self.assertEqual(nums, list(range(1, 25)), f"módulo {mod}")

    def test_listado_completo_con_placas(self):
        niv = pdf_plano.a_niveles([self.pg], self.perfil, {29: ("33KV", "04", "", "", "LC", "", False, "A4.2")})
        por = {s.desc_hmi: s for n in niv for c in n.campos for s in c.senales if s.desc_hmi}
        s = por["204LC Seccionador 229SL04 Abierto/Cerrado"]
        self.assertEqual((s.tipo_punto, s.placa, s.entrada), (TipoPunto.DI, "A4.2", "18"))
        self.assertEqual(por["204LC Campo 04 33KV QC4 ACTUADA"].placa, "A4.3")          # 2º módulo
        self.assertEqual(por["204LC Seccionador 229SB04 Apertura/Cierre"].placa, "A4.4")  # 3º módulo, salidas


@unittest.skipIf(tk is None, "sin tkinter")
class TestVentana(unittest.TestCase):
    def setUp(self):
        from app import principal
        try:
            self.app = principal.App()
        except tk.TclError:
            self.skipTest("sin pantalla")
        self.app.withdraw()
        self.addCleanup(self.app.destroy)

    def _campo(self, con_utr=True):
        from modelo import Campo, Nivel, Senal
        c = Campo(numero="04", descripcion="Campo 04", prefijo="204LC", controlador="SEL-2241-33kV", senales=[
            Senal(funcion=Funcion.ALARMAS, tag_hmi="A", desc_hmi="204LC Falla X Algo",
                  tipo_punto=TipoPunto.DI if con_utr else None, placa="A4.2" if con_utr else NA,
                  entrada="20" if con_utr else NA)])
        self.app.niveles[:] = [Nivel("33KV", "2", [c])]
        self.app.refrescar()
        return c

    def test_las_columnas_p_s_t_aparecen_solo_si_hay_datos(self):
        self._campo(con_utr=False)
        self.assertEqual(len(self.app.arbol["columns"]), 7)
        c = self._campo(con_utr=True)
        self.assertEqual(list(self.app.arbol["columns"])[-3:], ["tipo_punto", "placa", "entrada"])
        v = self.app.arbol.item(self.app.arbol.get_children()[0], "values")
        self.assertEqual(tuple(str(x) for x in v[-3:]), ("DI", "A4.2", "20"))

    def test_editar_tipo_placa_y_entrada(self):
        c = self._campo()
        n, s = self.app.niveles[0], c.senales[0]
        self.app._asignar(n, c, s, "placa", "A5.1")
        self.app._asignar(n, c, s, "entrada", "7")
        self.app._asignar(n, c, s, "tipo_punto", "do")
        self.assertEqual((s.placa, s.entrada, s.tipo_punto), ("A5.1", "7", TipoPunto.DO))
        self.app._asignar(n, c, s, "placa", "")
        self.assertEqual(s.placa, NA)
        with self.assertRaises(ValueError):
            self.app._asignar(n, c, s, "tipo_punto", "XX")

    def test_exporta_hasta_la_columna_t(self):
        from openpyxl import load_workbook
        from tkinter import filedialog, messagebox
        self._campo()
        mensajes = []
        messagebox.showinfo = lambda *a, **k: mensajes.append(a)
        messagebox.showerror = lambda *a, **k: mensajes.append(a)
        with tempfile.TemporaryDirectory() as t:
            ruta = Path(t) / "x.xlsx"
            filedialog.asksaveasfilename = lambda **k: str(ruta)
            self.app.exportar()
            self.assertEqual(mensajes[-1][0], "Exportado")
            self.assertIn("UTR P-S-T", mensajes[-1][1])
            ws = load_workbook(ruta)["EPEN"]
            self.assertEqual(ws.max_column, 20)                                  # A..T
            self.assertEqual((ws["P6"].value, ws["S6"].value, ws["T6"].value), ("DI", "A4.2", "20"))
            self.assertIsNone(ws["Q6"].value)                                    # PROTOCOLO: no se completa


if __name__ == "__main__":
    unittest.main()
