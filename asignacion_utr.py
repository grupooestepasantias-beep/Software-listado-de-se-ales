"""Asignación de PLACA ENTRADA / ENTRADA (tarea 3.1).

Los módulos (placa, tipo, cantidad de entradas) salen del plano de ingeniería y los carga el usuario en
Proyecto.modulos. Las señales digitales los consumen en orden de hoja:
- DI: una entrada por fila (la 2ª fila de un doble bit y las reservas también ocupan una).
- DO: un comando de doble bit ocupa un par consecutivo ("1/2"); de 1 bit, una sola salida ("1").
- Analógicas: PLACA y ENTRADA = N/A (como en el ejemplo ETAP).
Lo marcado en Senal.fijos ("placa" o "entrada") no se toca y sus entradas se saltean.
PENDIENTE: en el ejemplo el orden físico no siempre es correlativo (2,1 / 3,4 / 9,8); esos casos se corrigen a mano.
"""
from __future__ import annotations

from generador import TIPO_POR_FUNCION
from modelo import NA, Modulo, Proyecto, Senal
from perfiles import Perfil


def _entradas_de(texto: str) -> list[int]:
    try:
        return [int(x) for x in str(texto).split("/")]
    except ValueError:
        return []


class _Cola:
    """Entradas libres de los módulos de un tipo, en orden."""

    def __init__(self, modulos: list[Modulo], usadas: set[tuple[str, int]]):
        self.modulos, self.usadas = modulos, usadas
        self.i = 0
        self.sig = modulos[0].desde if modulos else 0

    def _libre(self, m: Modulo, n: int) -> bool:
        return all((m.placa, self.sig + k) not in self.usadas for k in range(n))

    def tomar(self, n: int = 1):
        """Devuelve (placa, [entradas]) o None si ya no hay lugar."""
        while self.i < len(self.modulos):
            m = self.modulos[self.i]
            if self.sig + n - 1 > m.desde + m.entradas - 1:
                self.i += 1
                if self.i < len(self.modulos):
                    self.sig = self.modulos[self.i].desde
                continue
            if not self._libre(m, n):
                self.sig += 1
                continue
            res = (m.placa, [self.sig + k for k in range(n)])
            self.sig += n
            return res
        return None


def asignar_placas(proyecto: Proyecto, perfil: Perfil) -> list[str]:
    """Completa placa/entrada de las señales digitales. Devuelve avisos."""
    avisos: list[str] = []
    senales = [(n, c, s) for n in proyecto.niveles for c in n.campos for s in c.senales]

    usadas: set[tuple[str, int]] = set()
    for _, _, s in senales:  # entradas ya fijadas a mano
        if "placa" in s.fijos and "entrada" in s.fijos:
            usadas.update((s.placa, e) for e in _entradas_de(s.entrada))

    colas = {t: _Cola([m for m in proyecto.modulos if m.tipo == t], usadas) for t in ("DI", "DO")}
    agotado: set[str] = set()

    for n, c, s in senales:
        tipo = (s.tipo_punto or TIPO_POR_FUNCION[s.funcion]).value
        if tipo not in ("DI", "DO"):
            if "placa" not in s.fijos:
                s.placa = NA
            if "entrada" not in s.fijos:
                s.entrada = NA
            continue
        if "placa" in s.fijos and "entrada" in s.fijos:
            continue
        cuantos = 2 if (tipo == "DO" and _bits(perfil, s) == 2) else 1
        toma = colas[tipo].tomar(cuantos)
        if toma is None:
            if tipo not in agotado:
                agotado.add(tipo)
                avisos.append(f"{n.nombre} / campo {c.numero}: no hay más módulos {tipo} con entradas libres; "
                              f"agregá otro módulo {tipo} o cargá placa/entrada a mano")
            continue
        placa, entradas = toma
        s.placa = placa
        s.entrada = "/".join(str(e) for e in entradas)
    return avisos


def _bits(perfil: Perfil, s: Senal) -> int:
    if s.estado_id:
        try:
            return perfil.estado(s.estado_id)["bits"]
        except KeyError:
            pass
    return 2
