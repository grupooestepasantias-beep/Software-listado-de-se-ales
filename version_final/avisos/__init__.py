"""Avisos del listado (etapa 3): validaciones sobre la base central. Informan; NUNCA modifican un dato.

Dos colores (pedido del usuario):
    CELESTE  la señal contradice una regla (TAG duplicado, OFFSET repetido que no es válido, DESC. SCADA de más de 20
             caracteres, controlador de otra tensión, TAG fuera del formato de las Reglas…)
    ROSA     falta información o hay algo para revisar (sin descripción resuelta, sin escalas, sin conexionado…)

Cada regla es una función en `reglas.py` registrada en REGLAS: sumar una regla nueva no toca el resto.
"""
from __future__ import annotations

from dataclasses import dataclass, field

CELESTE, ROSA = "celeste", "rosa"
COLORES = {CELESTE: "#bfe3ff", ROSA: "#ffd1e6"}
NOMBRES = {CELESTE: "Contradice una regla", ROSA: "Falta información / revisar"}


@dataclass(frozen=True)
class Aviso:
    gravedad: str                 # CELESTE o ROSA
    codigo: str                   # identifica la regla (ej. "TAG_DUPLICADO")
    mensaje: str                  # qué pasó, en palabras
    ids: tuple[int, ...] = ()     # señales de la base (SenalBase.id) a las que se refiere; vacío = aviso general
    campo: str = ""               # campo del listado (ej. "03", "SAA")
    item: int | None = None       # ITEM de la primera señal (columna A)
    hoja: int | None = None       # hoja del PDF de donde salió
    archivo: str = ""             # PDF de donde salió

    @property
    def donde(self) -> str:
        partes = []
        if self.campo:
            partes.append(f"campo {self.campo}")
        if self.item is not None:
            partes.append(f"ITEM {self.item}")
        if self.hoja:
            partes.append(f"hoja {self.hoja} del PDF" + (f" ({self.archivo})" if self.archivo else ""))
        return " · ".join(partes)


from .reglas import REGLAS, validar  # noqa: E402  (después de Aviso, que las reglas usan)

__all__ = ["Aviso", "CELESTE", "ROSA", "COLORES", "NOMBRES", "REGLAS", "validar"]
