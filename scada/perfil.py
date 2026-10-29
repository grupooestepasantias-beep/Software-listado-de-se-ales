"""Perfil SCADA de un cliente: perfiles/<id>/scada.json (+ glosario.json con las abreviaturas aprendidas)."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent / "perfiles"
CLAVES = ("id", "largo_desc_scada", "orden_funciones", "tag", "offsets", "estados", "mediciones", "desc_scada")


class PerfilInvalido(ValueError):
    pass


@dataclass
class PerfilScada:
    carpeta: Path
    datos: dict

    @property
    def id(self) -> str:
        return self.datos["id"]

    @property
    def maximo(self) -> int:
        return self.datos["largo_desc_scada"]

    @property
    def tag(self) -> dict:
        return self.datos["tag"]

    @property
    def offsets(self) -> dict:
        return self.datos["offsets"]

    @property
    def estados(self) -> dict:
        return self.datos["estados"]

    @property
    def mediciones(self) -> dict:
        return self.datos["mediciones"]

    @property
    def desc(self) -> dict:
        return self.datos["desc_scada"]

    @property
    def ruta_glosario(self) -> Path:
        return self.carpeta / "glosario.json"

    def familia(self, familia_id: str) -> dict:
        for f in self.estados["familias"]:
            if f["id"] == familia_id:
                return f
        raise KeyError(familia_id)


def listar(raiz: Path = RAIZ) -> list[str]:
    return sorted(p.name for p in raiz.iterdir() if (p / "scada.json").is_file()) if raiz.is_dir() else []


def cargar(perfil_id: str, raiz: Path = RAIZ) -> PerfilScada:
    carpeta = raiz / perfil_id
    ruta = carpeta / "scada.json"
    if not ruta.is_file():
        raise PerfilInvalido(f"no existe el perfil SCADA '{perfil_id}' (hay: {listar(raiz)})")
    try:
        datos = json.loads(ruta.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise PerfilInvalido(f"{ruta.name} no es JSON válido: {e}") from None
    perfil = PerfilScada(carpeta, datos)
    problemas = validar(perfil)
    if problemas:
        raise PerfilInvalido(f"perfil SCADA '{perfil_id}' inválido:\n- " + "\n- ".join(problemas))
    return perfil


def _regex_ok(p: list[str], donde: str, ids: list[str]) -> None:
    for rx in p:
        try:
            re.compile(rx)
        except re.error as e:
            ids.append(f"{donde}: expresión inválida {rx!r} ({e})")


def validar(perfil: PerfilScada) -> list[str]:
    d, p = perfil.datos, []
    for k in CLAVES:
        if k not in d:
            p.append(f"falta la clave '{k}'")
    if p:
        return p
    if d["id"] != perfil.carpeta.name:
        p.append(f"id '{d['id']}' no coincide con la carpeta '{perfil.carpeta.name}'")
    if not isinstance(d["largo_desc_scada"], int) or d["largo_desc_scada"] <= 0:
        p.append("largo_desc_scada debe ser un entero positivo")
    ids = set()
    for f in d["estados"]["familias"]:
        if f["id"] in ids:
            p.append(f"estados: familia repetida '{f['id']}'")
        ids.add(f["id"])
        if len(f["s"]) != 4:
            p.append(f"estados: '{f['id']}' necesita 4 valores S0-S3")
        if f["bits"] not in (1, 2):
            p.append(f"estados: '{f['id']}' bits debe ser 1 o 2")
        _regex_ok(f.get("senalizacion", []) + f.get("comando", []), f"estados.{f['id']}", p)
    for k in ("normal", "falla"):
        if len(d["estados"]["alarma"][k]) != 4:
            p.append(f"estados.alarma.{k} necesita 4 valores")
    _regex_ok(d["estados"]["alarma"].get("falla_detectar", []) + d["estados"]["alarma"].get("falla_revisar", []),
              "estados.alarma", p)
    codigos = set()
    for m in d["mediciones"]["juego"]:
        for k in ("patron", "codigo", "unidad", "raw", "factor"):
            if k not in m:
                p.append(f"mediciones: falta '{k}' en {m.get('codigo', m)}")
        if m.get("raw") not in ("signed", "unsigned"):
            p.append(f"mediciones: raw debe ser signed o unsigned en {m.get('codigo')}")
        _regex_ok([m.get("patron", "")], f"mediciones.{m.get('codigo')}", p)
        codigos.add(m.get("codigo"))
    sep = d["offsets"]["separacion_entre_campos"]
    if any(not isinstance(v, int) or v < 0 for v in sep.values()):
        p.append("offsets.separacion_entre_campos: enteros >= 0")
    if d["offsets"].get("comando") not in ("compartido", "propio"):
        p.append("offsets.comando debe ser 'compartido' o 'propio'")
    return p
