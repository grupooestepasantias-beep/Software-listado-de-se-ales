import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import hmi

VOCAB = json.loads((Path(__file__).resolve().parent.parent / "plantillas/EPEN/lectura_plano.json").read_text(encoding="utf-8"))


class TestHmi(unittest.TestCase):
    def test_descripcion_lo_mas_completa_posible(self):
        casos = {
            "Secc. 229SL04 Falta Tensión Auxiliar F Motriz": "204AP Seccionador 229SL04 Falta Tension Auxiliar Fuerza Motriz",
            "Interruptor 25204 Falta Ten. de Comando": "204AP Interruptor 25204 Falta Tension de Comando",
            "Prot. Campo 04 33 KV Falla Interna": "204AP Proteccion Campo 04 33 KV Falla Interna",
            "Seccionador 229SB04 Abierto/Cerrado": "204AP Seccionador 229SB04 Abierto/Cerrado",
            "Campo 04 33Kv Tensión Señalización OK": "204AP Campo 04 33Kv Tension Senalizacion OK",
        }
        for texto, esperado in casos.items():
            self.assertEqual(hmi.desc_hmi_desde("204AP", texto, VOCAB), esperado)

    def test_tag_es_la_descripcion_abreviada(self):
        casos = {
            "Secc. 229SL04 Falta Tensión Auxiliar F Motriz": "Seccionador_229SL04_F_Tension_Aux_Fza_Motriz",
            "Interruptor 25204 Falta Ten. de Comando": "Interruptor_25204_F_Tension_de_Comando",
            "Prot. Campo 04 33 KV Falla Interna": "Prot_Campo_04_33_KV_Falla_Interna",
            "Seccionador 229SB04 Abierto/Cerrado": "Seccionador_229SB04_Abierto_Cerrado",
        }
        for texto, esperado in casos.items():
            self.assertEqual(hmi.tag_hmi_desde(texto, VOCAB), esperado)

    def test_no_expande_palabras_que_solo_empiezan_igual(self):
        # "Ten" no debe tocar "Tension", ni "Prot" a "Protocolo"
        self.assertEqual(hmi.completar("Falta Tension Protocolo", VOCAB), "Falta Tension Protocolo")

    def test_sin_vocabulario_solo_limpia(self):
        self.assertEqual(hmi.tag_hmi_desde("Falta Tensión Aux."), "Falta_Tension_Aux")


if __name__ == "__main__":
    unittest.main()
