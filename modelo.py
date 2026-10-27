"""Modelo de datos del listado de señales.

No contiene reglas de ningún cliente: tags, estados, largos y orden de columnas
viven en perfiles/<cliente>/ (ver perfiles.py). Aquí solo se describe la forma
de los datos y cómo se guardan/cargan como JSON.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional, Union

NA = "N/A"

Valor = Union[str, int, float, None]


class TipoPunto(str, Enum):
    DI = "DI"  # entrada digital
    AI = "AI"  # entrada analógica
    DO = "DO"  # salida digital
    AO = "AO"  # salida analógica

    @property
    def es_analogico(self) -> bool:
        return self in (TipoPunto.AI, TipoPunto.AO)

    @property
    def es_salida(self) -> bool:
        return self in (TipoPunto.DO, TipoPunto.AO)


class Funcion(str, Enum):
    ALARMAS = "ALARMAS"
    SENALIZACION = "SEÑALIZACION"
    COMANDO = "COMANDO"
    MEDICION = "MEDICION"
    RESERVA = "RESERVA"


@dataclass
class Referencia:
    codigo: str = ""
    descripcion: str = ""


@dataclass
class Revision:
    rev: str = ""
    fecha: str = ""
    descripcion: str = ""
    proyecto: str = ""
    revisor: str = ""
    aprobador: str = ""


@dataclass
class Caratula:
    cliente: str = ""
    obra: str = ""
    lugar: str = ""
    departamento: str = ""
    expediente: str = ""
    titulo: str = ""
    numero_documento: str = ""
    proyecto: str = ""
    dibujo: str = ""
    aprobo: str = ""
    archivo_magnetico: str = ""
    escala: str = "N/A"
    revision: str = ""
    fecha: str = ""
    referencias: list[Referencia] = field(default_factory=list)
    revisiones: list[Revision] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict) -> "Caratula":
        d = dict(d)
        d["referencias"] = [Referencia(**r) for r in d.get("referencias", [])]
        d["revisiones"] = [Revision(**r) for r in d.get("revisiones", [])]
        return cls(**d)


@dataclass
class Senal:
    funcion: Funcion
    tipo_punto: Optional[TipoPunto] = None
    controlador: str = ""
    tag_hmi: str = ""
    desc_hmi: str = ""
    tag_scada: str = ""
    offset: Optional[int] = None
    desc_scada: str = ""
    # Columnas K-N: estados S0-S3 (digitales) o MIN RAW / MAX RAW / MIN EU / MAX EU (analógicas)
    s0: Valor = NA
    s1: Valor = NA
    s2: Valor = NA
    s3: Valor = NA
    unidad: str = NA
    placa: str = NA
    entrada: str = NA
    observaciones: str = ""
    # Datos de apoyo para el generador (no son columnas del Excel)
    estado_id: Optional[str] = None       # id en estados.json del perfil
    medicion_codigo: Optional[str] = None  # sufijo de medición (AR, AU, AP...)
    es_reserva: bool = False
    fijos: list[str] = field(default_factory=list)  # campos editados a mano: el generador no los pisa

    @classmethod
    def from_dict(cls, d: dict) -> "Senal":
        d = dict(d)
        d["funcion"] = Funcion(d["funcion"])
        if d.get("tipo_punto"):
            d["tipo_punto"] = TipoPunto(d["tipo_punto"])
        return cls(**d)


@dataclass
class Campo:
    numero: str                 # "01", "03", "TP1", "SAC"... (definido por el plano de ingeniería)
    descripcion: str = ""       # columna DESCRIP
    prefijo: str = ""           # prefijo de DESC. SCADA / DESC. HMI (ej. "303LC")
    controlador: str = ""       # controlador por defecto del campo
    senales: list[Senal] = field(default_factory=list)


@dataclass
class Nivel:
    nombre: str                 # columna NIVEL (ej. "132KV")
    codigo: str = ""            # dígito/código que entra en el tag (ej. "3")
    campos: list[Campo] = field(default_factory=list)


@dataclass
class Proyecto:
    perfil_id: str
    caratula: Caratula = field(default_factory=Caratula)
    niveles: list[Nivel] = field(default_factory=list)
    # El software siempre pregunta desde qué número arrancar; un contador por tipo de punto.
    item_inicial: int = 1
    offsets_iniciales: dict[str, int] = field(default_factory=dict)

    def todas_las_senales(self) -> list[Senal]:
        return [s for n in self.niveles for c in n.campos for s in c.senales]

    def to_dict(self) -> dict:
        return json.loads(json.dumps(asdict(self), ensure_ascii=False))

    @classmethod
    def from_dict(cls, d: dict) -> "Proyecto":
        niveles = [
            Nivel(
                nombre=n["nombre"],
                codigo=n.get("codigo", ""),
                campos=[
                    Campo(
                        numero=c["numero"],
                        descripcion=c.get("descripcion", ""),
                        prefijo=c.get("prefijo", ""),
                        controlador=c.get("controlador", ""),
                        senales=[Senal.from_dict(s) for s in c.get("senales", [])],
                    )
                    for c in n.get("campos", [])
                ],
            )
            for n in d.get("niveles", [])
        ]
        return cls(
            perfil_id=d["perfil_id"],
            caratula=Caratula.from_dict(d.get("caratula", {})),
            niveles=niveles,
            item_inicial=d.get("item_inicial", 1),
            offsets_iniciales=dict(d.get("offsets_iniciales", {})),
        )

    def guardar(self, ruta: Union[str, Path]) -> None:
        Path(ruta).write_text(
            json.dumps(self.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8"
        )

    @classmethod
    def cargar(cls, ruta: Union[str, Path]) -> "Proyecto":
        return cls.from_dict(json.loads(Path(ruta).read_text(encoding="utf-8")))
