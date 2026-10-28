"""Perfiles de cliente: cada cliente es una carpeta perfiles/<id>/ con archivos JSON.

El generador, el validador y el escritor de Excel leen siempre el perfil activo;
no hay reglas de un cliente escritas en el código.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

from modelo import Funcion

RAIZ = Path(__file__).parent / "perfiles"
ARCHIVOS = ("perfil",)
CLAVES_PERFIL = ("id", "nombre", "cliente", "hojas", "columnas", "orden_funciones", "largos")


class PerfilInvalido(ValueError):
    pass


@dataclass
class Perfil:
    carpeta: Path
    datos: dict            # perfil.json

    @property
    def id(self) -> str:
        return self.datos["id"]

    @property
    def nombre(self) -> str:
        return self.datos["nombre"]

    @property
    def columnas(self) -> list[dict]:
        return self.datos["columnas"]

    @property
    def columnas_activas(self) -> list[dict]:
        return [c for c in self.columnas if c.get("activa", True)]

    @property
    def orden_funciones(self) -> list[str]:
        return self.datos["orden_funciones"]

    def largo_max(self, campo: str) -> Optional[int]:
        return self.datos["largos"].get(campo)


def listar_perfiles(raiz: Path = RAIZ) -> list[str]:
    if not raiz.is_dir():
        return []
    return sorted(p.name for p in raiz.iterdir() if (p / "perfil.json").is_file())


def _leer(carpeta: Path, nombre: str) -> dict:
    ruta = carpeta / f"{nombre}.json"
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise PerfilInvalido(f"falta {ruta.name} en {carpeta}") from None
    except json.JSONDecodeError as e:
        raise PerfilInvalido(f"{ruta.name} no es JSON válido: {e}") from None


def cargar_perfil(perfil_id: str, raiz: Path = RAIZ, validar_perfil: bool = True) -> Perfil:
    carpeta = raiz / perfil_id
    if not carpeta.is_dir():
        raise PerfilInvalido(f"no existe el perfil '{perfil_id}' (disponibles: {listar_perfiles(raiz)})")
    perfil = Perfil(carpeta, *(_leer(carpeta, n) for n in ARCHIVOS))
    if validar_perfil:
        problemas = validar(perfil)
        if problemas:
            raise PerfilInvalido(f"perfil '{perfil_id}' inválido:\n- " + "\n- ".join(problemas))
    return perfil


def validar(perfil: Perfil) -> list[str]:
    """Devuelve la lista de problemas encontrados (vacía si el perfil es consistente)."""
    p: list[str] = []
    d = perfil.datos
    for k in CLAVES_PERFIL:
        if k not in d:
            p.append(f"perfil.json: falta la clave '{k}'")
    if p:
        return p
    if d["id"] != perfil.carpeta.name:
        p.append(f"perfil.json: id '{d['id']}' no coincide con la carpeta '{perfil.carpeta.name}'")

    funciones_validas = {f.value for f in Funcion}
    orden = d["orden_funciones"]
    if len(set(orden)) != len(orden):
        p.append("orden_funciones tiene valores repetidos")
    for f in orden:
        if f not in funciones_validas:
            p.append(f"orden_funciones: función desconocida '{f}'")

    claves, letras = set(), set()
    for c in d["columnas"]:
        for k in ("clave", "letra", "titulo"):
            if k not in c:
                p.append(f"columna sin '{k}': {c}")
        if c.get("clave") in claves:
            p.append(f"columna repetida: {c.get('clave')}")
        if c.get("letra") in letras:
            p.append(f"letra de columna repetida: {c.get('letra')}")
        claves.add(c.get("clave"))
        letras.add(c.get("letra"))

    for k, v in d["largos"].items():
        if v is not None and (not isinstance(v, int) or v <= 0):
            p.append(f"largos.{k} debe ser un entero positivo o null")
    return p


def duplicar_perfil(origen: str, nuevo_id: str, nombre: Optional[str] = None,
                    raiz: Path = RAIZ) -> Path:
    """Copia un perfil para empezar un cliente nuevo desde las reglas de otro."""
    if not nuevo_id or any(ch in nuevo_id for ch in '\\/:*?"<>|'):
        raise PerfilInvalido(f"id de perfil no válido: '{nuevo_id}'")
    destino = raiz / nuevo_id
    if destino.exists():
        raise PerfilInvalido(f"ya existe el perfil '{nuevo_id}'")
    cargar_perfil(origen, raiz)  # falla si el origen es inválido
    shutil.copytree(raiz / origen, destino)
    ruta = destino / "perfil.json"
    datos = json.loads(ruta.read_text(encoding="utf-8"))
    datos["id"] = nuevo_id
    datos["nombre"] = nombre or nuevo_id
    datos["cliente"] = nombre or nuevo_id
    ruta.write_text(json.dumps(datos, ensure_ascii=False, indent=2), encoding="utf-8")
    return destino
