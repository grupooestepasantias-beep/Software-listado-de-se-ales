"""Catálogo de controladores / dispositivos de campo (SEL-2240 Axion y RTAC, Schneider Saitel DP).

catalogo/controladores.json trae el listado base (con la fuente de cada modelo); los modelos que el
usuario agrega se guardan aparte en catalogo/controladores_propios.json para no perderlos al actualizar la base.
"""
from __future__ import annotations

import json
from pathlib import Path

RAIZ = Path(__file__).parent / "catalogo"
BASE = RAIZ / "controladores.json"
PROPIOS = RAIZ / "controladores_propios.json"
MARCA_PROPIA = "Propio"


def _leer(ruta: Path) -> dict:
    return json.loads(ruta.read_text(encoding="utf-8")) if ruta.is_file() else {}


def cargar(base: Path = BASE, propios: Path = PROPIOS) -> dict:
    """{'entradas': [...], 'sitios': {...}, 'consultado': 'AAAA-MM-DD', 'nota': str}; los propios van marcados."""
    doc = _leer(base)
    entradas = list(doc.get("entradas", []))
    entradas += [dict(e, propio=True) for e in _leer(propios).get("entradas", [])]
    return {"entradas": entradas, "sitios": doc.get("sitios", {}), "consultado": doc.get("consultado", ""),
            "nota": doc.get("_nota", "")}


def marcas(entradas: list[dict]) -> list[str]:
    return sorted({e["marca"] for e in entradas})


def categorias(entradas: list[dict], marca: str = "") -> list[str]:
    return sorted({e["categoria"] for e in entradas if not marca or e["marca"] == marca})


def filtrar(entradas: list[dict], marca: str = "", categoria: str = "", texto: str = "") -> list[dict]:
    """Filtra por marca, categoría y texto (en modelo, familia, categoría o descripción; sin mayúsculas)."""
    t = texto.strip().lower()
    return [e for e in entradas
            if (not marca or e["marca"] == marca) and (not categoria or e["categoria"] == categoria)
            and (not t or t in " ".join((e["modelo"], e["familia"], e["categoria"], e["descripcion"])).lower())]


def valores_desplegable(entradas: list[dict]) -> list[str]:
    """Modelos para un desplegable (sin repetir), en el orden marca → familia → categoría → modelo."""
    vistos, out = set(), []
    for e in sorted(entradas, key=lambda e: (e["marca"], e["familia"], e["categoria"])):
        if e["modelo"] not in vistos:
            vistos.add(e["modelo"])
            out.append(e["modelo"])
    return out


def lleva_tension(modelo: str, entradas: list[dict]) -> bool:
    """Los controladores (RTAC, CPU) llevan la tensión del nivel al final (SEL-2241-33kV); los módulos de E/S no."""
    return any(e["modelo"] == modelo and e["categoria"].startswith("Controlador") for e in entradas)


def agregar_propio(modelo: str, descripcion: str = "", marca: str = MARCA_PROPIA, familia: str = "",
                   categoria: str = "Otro", ruta: Path = PROPIOS) -> dict:
    """Guarda un modelo del usuario (no repite un modelo ya cargado de la misma marca)."""
    modelo = modelo.strip()
    if not modelo:
        raise ValueError("Escribí el modelo.")
    doc = _leer(ruta) or {"entradas": []}
    if any(e["modelo"].lower() == modelo.lower() and e["marca"] == marca for e in doc["entradas"]):
        raise ValueError(f"'{modelo}' ya está en tus modelos propios.")
    entrada = {"marca": marca.strip() or MARCA_PROPIA, "familia": familia.strip(), "categoria": categoria.strip() or "Otro",
               "modelo": modelo, "descripcion": descripcion.strip(), "fuente": "cargado por el usuario"}
    doc["entradas"].append(entrada)
    ruta.parent.mkdir(parents=True, exist_ok=True)
    ruta.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return entrada
