"""Correcciones del usuario que la app recuerda (TAG HMI y DESC. HMI por rótulo del plano).

Cuando el usuario corrige a mano el TAG o la DESC. HMI de una señal leída de un plano, se guarda la corrección con el
rótulo original como clave (plantillas/<id>/correcciones_usuario.json). En las próximas cargas, el mismo rótulo sale
con lo que el usuario escribió. Es una memoria exacta: no inventa nada para rótulos que nunca vio.

El prefijo del campo (ej. '204LC') se guarda como '{p}', así la corrección sirve en cualquier campo.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Optional

from hmi import sin_acentos

RAIZ_PLANTILLAS = Path(__file__).parent / "plantillas"
CAMPOS = ("tag_hmi", "desc_hmi")


def _ruta(perfil_id: str) -> Path:
    return RAIZ_PLANTILLAS / perfil_id / "correcciones_usuario.json"


def clave(rotulo: str) -> str:
    """Rótulo normalizado: sin tildes, minúsculas y espacios simples."""
    return " ".join(sin_acentos(rotulo).lower().split())


def cargar(perfil_id: str) -> dict[str, dict[str, str]]:
    try:
        d = json.loads(_ruta(perfil_id).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return d.get("rotulos", {}) if isinstance(d, dict) else {}


def guardar(perfil_id: str, rotulo: str, campo: str, valor: str, prefijo: str = "") -> None:
    """Recuerda que, para ese rótulo, `campo` (tag_hmi/desc_hmi) vale `valor`. Un valor vacío olvida la corrección."""
    if campo not in CAMPOS or not clave(rotulo):
        return
    datos = cargar(perfil_id)
    entrada = datos.setdefault(clave(rotulo), {})
    if valor.strip():
        entrada[campo] = valor.replace(prefijo, "{p}", 1) if prefijo and valor.startswith(prefijo) else valor
    else:
        entrada.pop(campo, None)
    if not entrada:
        datos.pop(clave(rotulo), None)
    ruta = _ruta(perfil_id)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_suffix(".tmp")
    tmp.write_text(json.dumps({"rotulos": datos}, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    tmp.replace(ruta)


def aplicar(correcciones: dict, rotulo: str, prefijo: str) -> dict[str, str]:
    """{campo: valor} corregido para ese rótulo (con el prefijo del campo ya puesto); {} si no hay nada aprendido."""
    e = correcciones.get(clave(rotulo), {})
    return {c: e[c].replace("{p}", prefijo) for c in CAMPOS if c in e}


def rotulo_de(observaciones: str) -> Optional[str]:
    """El rótulo original que la app dejó anotado en la fila ('plano.pdf p.42 | rótulo: ... | leído')."""
    m = re.search(r"rótulo: (.*?)(?: \| |$)", observaciones)
    return m.group(1) if m else None
