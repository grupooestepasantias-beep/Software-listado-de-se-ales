import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import perfiles
from modelo import Campo, Caratula, Funcion, Nivel, Proyecto, Referencia, Revision, Senal, TipoPunto


class TestPerfiles(unittest.TestCase):
    def test_epen_carga_y_valida(self):
        p = perfiles.cargar_perfil("EPEN")
        self.assertEqual(perfiles.validar(p), [])
        self.assertEqual(p.orden_funciones, ["ALARMAS", "SEÑALIZACION", "COMANDO", "MEDICION"])
        self.assertEqual(p.largo_max("desc_scada"), 20)
        self.assertEqual([c["letra"] for c in p.columnas][0], "A")
        self.assertEqual(p.columnas[-1]["letra"], "W")
        inactivas = {c["clave"] for c in p.columnas if not c["activa"]}
        self.assertEqual(inactivas, {"protocolo", "pos_dnp", "bornera", "borne"})

    def test_estados_y_sufijos(self):
        p = perfiles.cargar_perfil("EPEN")
        e = p.estado("sen_ab_ce")
        self.assertEqual((e["s0"], e["s1"], e["s2"], e["s3"]), ("error_0", "AB", "CE", "error_1"))
        self.assertTrue(all(x["tipo_punto"] == "DO" for x in p.estados_para("COMANDO")))
        self.assertEqual(len(p.sufijos("AS")), 2)  # corriente fase S y potencia aparente
        with self.assertRaises(KeyError):
            p.estado("no_existe")

    def test_perfil_inexistente(self):
        with self.assertRaises(perfiles.PerfilInvalido):
            perfiles.cargar_perfil("NO_EXISTE")

    def test_duplicar_perfil(self):
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            import shutil
            shutil.copytree(perfiles.RAIZ / "EPEN", raiz / "EPEN")
            destino = perfiles.duplicar_perfil("EPEN", "OTRO", "Cliente Otro", raiz)
            self.assertTrue((destino / "estados.json").is_file())
            nuevo = perfiles.cargar_perfil("OTRO", raiz)
            self.assertEqual(nuevo.nombre, "Cliente Otro")
            self.assertEqual(sorted(perfiles.listar_perfiles(raiz)), ["EPEN", "OTRO"])
            with self.assertRaises(perfiles.PerfilInvalido):
                perfiles.duplicar_perfil("EPEN", "OTRO", raiz=raiz)

    def test_validar_detecta_errores(self):
        p = perfiles.cargar_perfil("EPEN")
        p.datos["orden_funciones"] = ["ALARMAS", "ALARMAS", "XYZ"]
        p.datos["columnas"].append(dict(p.columnas[0]))
        problemas = "\n".join(perfiles.validar(p))
        self.assertIn("repetidos", problemas)
        self.assertIn("XYZ", problemas)
        self.assertIn("columna repetida", problemas)


class TestModelo(unittest.TestCase):
    def _proyecto(self) -> Proyecto:
        senal = Senal(funcion=Funcion.SENALIZACION, tipo_punto=TipoPunto.DI,
                      tag_scada="303.632C", offset=263, s0="error_0", s1="AB", s2="CE", s3="error_1",
                      estado_id="sen_ab_ce", fijos=["desc_scada"])
        return Proyecto(
            perfil_id="EPEN",
            caratula=Caratula(cliente="ENTE", obra="LAT", referencias=[Referencia("ETAP-1", "Plano")],
                              revisiones=[Revision(rev="0", fecha="21/04/2025")]),
            niveles=[Nivel("132KV", "3", [Campo("03", "LAT Loma Campana Campo 303", "303LC", "SEL-2241-132kV", [senal])])],
            offsets_iniciales={"DI": 200, "AI": 200},
        )

    def test_roundtrip_json(self):
        proy = self._proyecto()
        with tempfile.TemporaryDirectory() as tmp:
            ruta = Path(tmp) / "p.json"
            proy.guardar(ruta)
            json.loads(ruta.read_text(encoding="utf-8"))
            otro = Proyecto.cargar(ruta)
        self.assertEqual(proy, otro)
        s = otro.todas_las_senales()[0]
        self.assertIs(s.funcion, Funcion.SENALIZACION)
        self.assertIs(s.tipo_punto, TipoPunto.DI)

    def test_tipo_punto(self):
        self.assertTrue(TipoPunto.AI.es_analogico)
        self.assertTrue(TipoPunto.DO.es_salida)
        self.assertFalse(TipoPunto.DI.es_salida)


if __name__ == "__main__":
    unittest.main()
