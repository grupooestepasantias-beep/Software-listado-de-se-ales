"""Numeración del SCADA: TAG (columna H) y OFFSET (columna I) del listado de señales.

Solo lógica, sin interfaz ni lectura de PDF. Reglas (respuestas del usuario, 2026-11-05):

* TAG digital:   {prefijo}.{VV}{bits}[C]   VV = variable de 2 dígitos, bits = 1 (simple) o 2 (doble),
                 C = la señal tiene comando. Reserva: "N/A".
* VV:            el usuario indica el número inicial de CADA campo; sigue de a 1 y no se repite dentro del campo.
* OFFSET digital: por campo, en este orden: alarmas, 10 libres, señales, 10 libres, y el campo siguiente.
                 Los libres salen como filas (Fila.hueco) solo con OFFSET, para futuras ampliaciones.
                 Una señal doble ocupa 2 offsets. Una reserva ocupa su lugar (offset) pero no consume variable.
* COMANDO:       se detecta por el tag: si termina en C, su offset es el mismo de la señal (no hay otro contador).
* MEDICION:      después de todos los campos; contador propio (analógicas): {prefijo}.{NN}{código}.
"""
from __future__ import annotations

from dataclasses import dataclass, field

ALARMAS, SENALIZACION, COMANDO, MEDICION, RESERVA = "ALARMAS", "SEÑALIZACION", "COMANDO", "MEDICION", "RESERVA"

HUECO = 10  # offsets libres entre secciones

# Juego de medición del ETAP (código del TAG según LINEAMIENTOS, página 2), en su orden.
MEDICIONES_ETAP = ("AU", "AV", "AW", "AR", "AS", "AT", "AF", "AFP", "AP", "AS", "AQ", "VP", "IP")


class ErrorNumeracion(ValueError):
    pass


@dataclass
class Senal:
    funcion: str                 # ALARMAS o SEÑALIZACION (el COMANDO se deduce del tag terminado en C)
    texto: str = ""
    doble: bool = False          # 2 bits (dos offsets)
    dos_estados: bool = False    # dos estados en UNA sola entrada («en local»): tag de 2 bits pero una fila y un offset
    comando: bool = False        # tiene comando asociado -> el tag termina en C
    reserva: bool = False        # conexión hecha pero sin uso -> tag "N/A"
    pares: tuple[str, ...] = ()  # rótulos del PDF (1 o 2): sirven para elegir los estados
    origen: object = None        # LecturaSenal del PDF (para el controlador y las columnas A-G)
    origen_comando: object = None  # LecturaSenal del comando asociado, si lo hay


@dataclass
class Campo:
    prefijo: str                 # "303", "101", "TP1", "SACA"… (nivel+campo, o el campo especial solo)
    variable_inicial: int        # lo define el usuario por campo
    senales: list[Senal] = field(default_factory=list)
    mediciones: tuple[str, ...] = ()        # códigos de medición (ver MEDICIONES_ETAP); () = sin mediciones
    saltar_medicion: tuple[int, ...] = ()   # números NN que el campo no usa (ej. 4 en 132 kV)
    nivel: str = ""              # tensión con la que se numera (la del PDF o la que corrigió el usuario)
    nivel_pdf: str = ""          # "33KV" tal como figura en el cajetín del PDF
    clave: str = ""              # identifica al campo aunque cambie su prefijo (nivel+campo originales)
    descripcion_base: str = ""   # texto del cajetín, sin el «Campo 204» del final
    paginas: list[int] = field(default_factory=list)      # hojas del PDF de donde salió
    inferidos: list[str] = field(default_factory=list)    # datos que el cajetín no trae y se dedujeron (nivel, campo)
    archivos: list[str] = field(default_factory=list)     # PDF de donde salió
    numero: str = ""             # "04", o un campo especial como "TP1" (el que se usa para numerar)
    numero_pdf: str = ""         # el que figura en el PDF (vacío si no lo trae)
    descripcion: str = ""        # texto del cajetín (ej. "ACOMETIDAS TRAFO Y ACOPLE")
    controlador: str = ""        # controlador por defecto del campo


@dataclass
class Fila:
    campo: str
    funcion: str
    tag: str
    offset: int
    senal: Senal | None = None
    codigo: str = ""             # solo mediciones
    extra: bool = False          # segunda fila de una señal doble (sin tag, offset siguiente)
    hueco: bool = False          # offset reservado para ampliaciones: fila sin tag ni descripción


def _tag_digital(prefijo: str, variable: int, s: Senal) -> str:
    if s.reserva:
        return "N/A"
    if not 0 <= variable <= 99:
        raise ErrorNumeracion(f"El campo {prefijo} se pasó de 99 variables (llegó a {variable}).")
    return f"{prefijo}.{variable:02d}{2 if s.doble or s.dos_estados else 1}{'C' if s.comando else ''}"


def _seccion(campo: Campo, funcion: str, offset: int, variable: int) -> tuple[list[Fila], int, int]:
    filas: list[Fila] = []
    for s in (x for x in campo.senales if x.funcion == funcion):
        tag = _tag_digital(campo.prefijo, variable, s)
        filas.append(Fila(campo.prefijo, funcion, tag, offset, s))
        offset += 1
        if s.doble:
            filas.append(Fila(campo.prefijo, funcion, "", offset, s, extra=True))
            offset += 1
        if not s.reserva:
            variable += 1
    return filas, offset, variable


def _hueco(campo: str, funcion: str, offset: int, cantidad: int) -> list[Fila]:
    return [Fila(campo, funcion, "", offset + i, extra=True, hueco=True) for i in range(cantidad)]


def numerar(campos: list[Campo], offset_inicial: int, offset_inicial_medicion: int,
            hueco: int = HUECO, hueco_medicion: int = HUECO) -> list[Fila]:
    """Filas en el orden del Excel: por campo ALARMAS y SEÑALIZACION, luego todos los COMANDO, luego MEDICION."""
    prefijos = [c.prefijo for c in campos]
    if len(set(prefijos)) != len(prefijos):
        raise ErrorNumeracion("Hay campos repetidos: " + ", ".join(sorted({p for p in prefijos if prefijos.count(p) > 1})))
    for c in campos:
        n = sum(1 for x in c.senales if not x.reserva)        # cada señal (y cada comando sin señal) usa un número
        if n > 100:
            raise ErrorNumeracion(f"El campo {c.prefijo} tiene {n} señales y la variable solo admite 100 números (00 a 99).")
        if c.variable_inicial + n > 100:
            raise ErrorNumeracion(
                f"El campo {c.prefijo} tiene {n} señales y cada una usa un número de variable (00 a 99). Empezando en "
                f"{c.variable_inicial} llegaría a {c.variable_inicial + n - 1}: poné una variable inicial de {100 - n} o menos.")
    salida: list[Fila] = []
    offset = offset_inicial
    for c in campos:
        variable = c.variable_inicial
        alarmas, offset, variable = _seccion(c, ALARMAS, offset, variable)
        libres_a = _hueco(c.prefijo, ALARMAS, offset, hueco)
        offset += hueco
        senales, offset, variable = _seccion(c, SENALIZACION, offset, variable)
        libres_s = _hueco(c.prefijo, SENALIZACION, offset, hueco)
        offset += hueco
        salida += alarmas + libres_a + senales + libres_s
    # Comandos: se deducen del tag; mismo offset que la señal.
    for f in [f for f in salida if f.tag.endswith("C") and not f.extra]:
        salida.append(Fila(f.campo, COMANDO, f.tag, f.offset, f.senal))
    # Mediciones: contador propio, después de todo lo digital.
    offset = offset_inicial_medicion
    ultimo = max((i for i, c in enumerate(campos) if c.mediciones), default=-1)
    for i, c in enumerate(campos):
        if not c.mediciones:
            continue
        nn = 0
        for codigo in c.mediciones:
            nn += 1
            while nn in c.saltar_medicion:
                nn += 1
            salida.append(Fila(c.prefijo, MEDICION, f"{c.prefijo}.{nn:02d}{codigo}", offset, codigo=codigo))
            offset += 1
        if i != ultimo:
            salida += _hueco(c.prefijo, MEDICION, offset, hueco_medicion)
            offset += hueco_medicion
    return salida
