"""Corre todas las pruebas y guarda el resultado en resultado_pruebas.txt.

Uso:  python ejecutar_pruebas.py
Las pruebas que dependen de Microsoft Word o de la carpeta de red se omiten (y se informa) si no están disponibles.
"""
import datetime
import io
import os
import sys
import unittest

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, AQUI)


def main():
    suite = unittest.defaultTestLoader.discover(os.path.join(AQUI, "tests"), pattern="test_*.py", top_level_dir=AQUI)
    flujo = io.StringIO()
    corredor = unittest.TextTestRunner(stream=flujo, verbosity=2)
    resultado = corredor.run(suite)
    texto = flujo.getvalue()
    resumen = (f"\nPRUEBAS: {resultado.testsRun} ejecutadas, {len(resultado.failures)} fallas, "
               f"{len(resultado.errors)} errores, {len(resultado.skipped)} omitidas "
               f"({datetime.datetime.now():%d/%m/%Y %H:%M})\n")
    for prueba, motivo in resultado.skipped:
        resumen += f"  omitida: {prueba.id().split('.', 1)[-1]} - {motivo}\n"
    with open(os.path.join(AQUI, "resultado_pruebas.txt"), "w", encoding="utf-8") as f:
        f.write(texto + resumen)
    print(texto[-3000:] + resumen)
    return 0 if resultado.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
