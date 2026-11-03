"""Carga y validacion de las reglas de redaccion de un cliente (perfiles/<cliente>/redaccion.json).

Nada de EPEN esta en el codigo: tildes, unidad de tension, terminos, errores conocidos, largos y
patrones protegidos salen de ese archivo. Un cliente nuevo = otro redaccion.json."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

MODOS_TILDES = ("quitar", "agregar", "no_tocar")


class ReglasInvalidas(ValueError):
    pass


@dataclass
class Reglas:
    datos: dict
    carpeta: Path
    patrones: list = field(default_factory=list)   # patrones protegidos ya compilados

    @property
    def hoja(self) -> str:
        return self.datos["hoja"]

    @property
    def primera_fila(self) -> int:
        return self.datos["primera_fila"]

    @property
    def col(self) -> dict:
        return self.datos["columnas"]

    @property
    def columnas_texto(self) -> list[str]:
        return self.datos["columnas_texto"]

    @property
    def intactos(self) -> set[str]:
        return set(self.datos.get("valores_intactos", []))

    @property
    def modo_tildes(self) -> str:
        return self.datos.get("tildes", {}).get("modo", "no_tocar")

    def largo(self, letra: str):
        return self.datos.get("largos", {}).get(letra)


def validar(datos: dict) -> list[str]:
    problemas = []
    for k in ("hoja", "primera_fila", "columnas", "columnas_texto"):
        if k not in datos:
            problemas.append(f"falta '{k}'")
    if problemas:
        return problemas
    protegidas = {datos["columnas"].get(k) for k in ("tag_hmi", "tag_scada", "offset", "funcion", "nivel")}
    cruce = protegidas & set(datos["columnas_texto"])
    if cruce:
        problemas.append(f"columnas de identificadores marcadas como texto: {sorted(cruce)}")
    if datos.get("tildes", {}).get("modo", "no_tocar") not in MODOS_TILDES:
        problemas.append(f"tildes.modo debe ser uno de {MODOS_TILDES}")
    for p in datos.get("patrones_protegidos", []):
        try:
            re.compile(p)
        except re.error as e:
            problemas.append(f"patron protegido invalido {p!r}: {e}")
    for t in datos.get("terminos", []):
        if not t.get("buscar") or "poner" not in t:
            problemas.append(f"termino incompleto: {t}")
    return problemas


def cargar(perfil_carpeta) -> Reglas:
    """`perfil_carpeta`: carpeta del perfil (Perfil.carpeta) o su ruta."""
    carpeta = Path(perfil_carpeta)
    ruta = carpeta / "redaccion.json"
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise ReglasInvalidas(f"falta {ruta}") from None
    except json.JSONDecodeError as e:
        raise ReglasInvalidas(f"{ruta.name} no es JSON valido: {e}") from None
    problemas = validar(datos)
    if problemas:
        raise ReglasInvalidas(f"{ruta.name} invalido:\n- " + "\n- ".join(problemas))
    return Reglas(datos, carpeta, [re.compile(p) for p in datos.get("patrones_protegidos", [])])
