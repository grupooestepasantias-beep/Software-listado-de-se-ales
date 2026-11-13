"""Formatos de salida del Excel (etapa 2 del generador nuevo).

Un formato es un archivo `formatos/<id>.json` que dice qué campo de la base va en cada columna y de qué plantilla
(`plantillas/…`) salen los títulos, combinaciones, anchos, estilos, filtro e impresión. Elegir un formato nunca
borra datos de la base: solo decide qué se exporta. Para sumar una columna o un formato nuevo se edita el JSON,
no el programa.

El resultado siempre es un .xlsx común, que se puede abrir y editar a mano.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).parent
BASE = RAIZ.parent

# Campos que un formato puede pedir (valor de cada columna). `estado0..3` son S0..S3 en una señal digital y
# MIN RAW / MAX RAW / MIN EU / MAX EU en una medición.
CAMPOS = ("item", "nivel", "descrip", "controlador", "funcion", "tag_hmi", "desc_hmi", "tag_scada", "offset", "desc_scada",
          "estado0", "estado1", "estado2", "estado3", "unidad", "tipo_senal", "tablero", "placa", "entrada",
          "bornera_tablero", "borne_tablero", "bornera_equipo", "borne_equipo", "indice_dnp", "observaciones")


class FormatoInvalido(ValueError):
    pass


@dataclass
class Formato:
    id: str
    nombre: str
    plantilla: dict                 # plantilla del listado (extraída de un Excel de ejemplo)
    hoja: str
    primera_fila_datos: int
    ultima_columna: str
    columnas: list[dict]            # [{"letra": "A", "campo": "item"}, …]; campo null = columna vacía

    @property
    def letra_de(self) -> dict[str, str]:
        return {c["campo"]: c["letra"] for c in self.columnas if c["campo"]}


def _leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8"))


def cargar(id_formato: str) -> Formato:
    ruta = RAIZ / f"{id_formato}.json"
    if not ruta.is_file():
        raise FormatoInvalido(f"No existe el formato «{id_formato}». Disponibles: {', '.join(ids())}")
    d = _leer(ruta)
    plantilla = _leer(BASE / d["plantilla"])["listado"]
    desconocidos = [c["campo"] for c in d["columnas"] if c["campo"] and c["campo"] not in CAMPOS]
    if desconocidos:
        raise FormatoInvalido(f"El formato {id_formato} pide campos que no existen: {', '.join(desconocidos)}")
    return Formato(d["id"], d["nombre"], plantilla, d["hoja"], d["primera_fila_datos"], d["ultima_columna"], d["columnas"])


def ids() -> list[str]:
    return sorted(p.stem for p in RAIZ.glob("*.json"))


def disponibles() -> list[Formato]:
    return [cargar(i) for i in ids()]
