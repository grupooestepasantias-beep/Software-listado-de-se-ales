"""Señal central del listado: UN solo registro con todos los datos de una fila, para todos los formatos de salida.

Cada formato de Excel (completo, reducido…) toma de acá las columnas que necesita; elegir un formato nunca borra datos.
Lo que no corresponde a una señal queda vacío ("" o None): no se inventan datos.

`origen` dice de dónde salió cada dato, para que recalcular no pise lo corregido a mano:
    "pdf"    leído del plano (rótulo, módulo, placa, entrada…)
    "regla"  calculado con las reglas del perfil (TAG, OFFSET, estados, descripción SCADA…)
    "manual" escrito o corregido por el usuario
Un dato sin entrada en `origen` está vacío.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Optional, Union

PDF, REGLA, MANUAL = "pdf", "regla", "manual"
Valor = Union[str, int, float, None]

# Campos de la señal que son datos (no de estructura) y la fuente por defecto de cada uno cuando tienen valor.
FUENTE_POR_DEFECTO = {
    "controlador": REGLA, "tag_hmi": PDF, "desc_hmi": PDF, "tag_scada": REGLA, "offset": REGLA, "desc_scada": REGLA,
    "s0": REGLA, "s1": REGLA, "s2": REGLA, "s3": REGLA,
    "min_raw": REGLA, "max_raw": REGLA, "min_eu": REGLA, "max_eu": REGLA, "unidad": REGLA,
    "tipo_senal": PDF, "tablero": REGLA, "placa": PDF, "entrada": PDF, "bornera_tablero": PDF, "borne_tablero": PDF,
    "bornera_equipo": REGLA, "borne_equipo": REGLA, "indice_dnp": PDF, "observaciones": PDF,
}


@dataclass
class SenalBase:
    # --- identificación y ubicación en la hoja
    id: int = 0                       # número de orden estable dentro del proyecto
    item: Optional[int] = None        # ITEM (columna A); las filas libres no llevan
    grupo_nivel: int = 0              # bloque de NIVEL al que pertenece (las reservas forman bloques aparte)
    grupo_campo: int = 0              # bloque de campo
    nivel: str = ""                   # "13,2KV"
    nivel_codigo: str = ""            # dígito del TAG para ese nivel ("1", "2", "3")
    campo: str = ""                   # "01", "TP1", "SAA"
    descripcion_campo: str = ""       # columna DESCRIP
    campo_prefijo: str = ""           # prefijo de las descripciones del campo (ej. "101")
    funcion: str = ""                 # ALARMAS, SEÑALIZACION, COMANDO, MEDICION, RESERVA
    # --- HMI
    controlador: str = ""
    tag_hmi: str = ""
    desc_hmi: str = ""
    # --- SCADA
    tag_scada: str = ""
    offset: Optional[int] = None
    desc_scada: str = ""
    # --- estados (digitales) o escalas (mediciones)
    s0: Valor = None
    s1: Valor = None
    s2: Valor = None
    s3: Valor = None
    min_raw: Valor = None
    max_raw: Valor = None
    min_eu: Valor = None
    max_eu: Valor = None
    unidad: str = ""
    # --- conexionado
    tipo_senal: str = ""              # DI, DO, AI, AO
    tablero: str = ""
    placa: str = ""
    entrada: str = ""
    bornera_tablero: str = ""
    borne_tablero: str = ""
    bornera_equipo: str = ""
    borne_equipo: str = ""
    indice_dnp: Valor = None          # INDICE DNP CCO: solo una columna; queda vacía hasta que el usuario defina qué es
    observaciones: str = ""
    # --- estado de la fila
    segunda_fila: bool = False        # 2.ª fila de una señal de doble bit
    es_reserva: bool = False
    es_hueco: bool = False            # fila libre (solo OFFSET) para ampliaciones
    sin_resolver: bool = False        # DESC. SCADA que no entró en 20 caracteres con las abreviaturas
    hoja: Optional[int] = None        # hoja del PDF de donde salió
    archivo: str = ""                 # PDF de donde salió
    origen: dict[str, str] = field(default_factory=dict)

    # ------------------------------------------------------------ origen
    def poner(self, nombre: str, valor, fuente: str) -> None:
        """Asigna un dato y anota su fuente (una fuente MANUAL no se degrada a otra sin que el usuario lo pida)."""
        setattr(self, nombre, valor)
        if valor in (None, ""):
            self.origen.pop(nombre, None)
        elif self.origen.get(nombre) != MANUAL or fuente == MANUAL:
            self.origen[nombre] = fuente

    def fuente_de(self, nombre: str) -> str:
        return self.origen.get(nombre, "")

    def completar_origen(self) -> None:
        """Anota la fuente por defecto de los datos con valor que todavía no la tienen."""
        for nombre, fuente in FUENTE_POR_DEFECTO.items():
            if getattr(self, nombre) not in (None, "") and nombre not in self.origen:
                self.origen[nombre] = fuente

    # ------------------------------------------------------------ guardar y cargar
    def a_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def de_dict(cls, d: dict) -> "SenalBase":
        validos = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**validos)
