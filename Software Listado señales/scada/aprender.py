"""Aprende el glosario de abreviaturas (DESC. SCADA) de un listado terminado y lo guarda en el perfil.

    python -m scada.aprender            # EPEN: aprende del ETAP -> perfiles/EPEN/glosario.json

Las respuestas que el usuario ya dio (glosario.usuario) se conservan. Para sumar otro listado del cliente, pasar su
.xlsx: python -m scada.aprender otro_listado.xlsx  (mismo formato columnas A-W del ETAP).
"""
from __future__ import annotations

import sys
from pathlib import Path

from . import descripcion, ejemplos
from . import perfil as scada_perfil


def main(perfil_id: str = "EPEN", extra: list[Path] = ()) -> descripcion.Glosario:
    perfil = scada_perfil.cargar(perfil_id)
    filas = ejemplos.etap()
    for ruta in extra:  # otros listados del mismo cliente, mismo formato que el ETAP
        ejemplos.ETAP = Path(ruta)
        filas += ejemplos.etap()
    nuevo = descripcion.aprender(filas, perfil)
    previo = descripcion.Glosario.cargar(perfil.ruta_glosario)
    nuevo.usuario = previo.usuario  # no se pierde lo que el usuario ya contestó
    nuevo.guardar(perfil.ruta_glosario)
    return nuevo


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    g = main(extra=[Path(a) for a in sys.argv[1:]])
    print(f"glosario guardado: frases={len(g.texto)} equipo+frase={len(g.frase)} protecciones={len(g.rele)} "
          f"palabras={len(g.palabra)} pegadas={len(g.pegado)}")
