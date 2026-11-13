"""Base central de un proyecto: la lista de señales (SenalBase) más lo necesario para volver a generar el Excel.

Etapa 1 del generador nuevo. De acá salen todos los formatos de Excel (etapa 2) y sobre ella trabajan las validaciones
(etapa 3). Hoy se llena desde la cadena de siempre (PDF -> numeración -> filas) con `Libro.base()`, y se puede volver
a un `Proyecto` del escritor con `a_proyecto()`: el Excel que sale es idéntico al de la exportación directa.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from modelo import Campo, Funcion, Nivel, Proyecto, Senal, TipoPunto

from .senal import MANUAL, SenalBase

VERSION = 2

# atributo de modelo.Senal -> campo de SenalBase (los que se llaman distinto)
_RENOMBRE = {"tipo_punto": "tipo_senal"}
_ESCALAS = {"s0": "min_raw", "s1": "max_raw", "s2": "min_eu", "s3": "max_eu"}


def _valido(tipo) -> bool:
    return tipo in ("DI", "DO", "AI", "AO")


@dataclass
class ProyectoDB:
    perfil_id: str = "EPEN"
    estilo: str = ""
    item_inicial: int = 1
    pdfs: list[str] = field(default_factory=list)
    datos: dict = field(default_factory=dict)          # lo que se le preguntó al usuario (variables, offsets, placas…)
    caratula: dict | None = None
    senales: list[SenalBase] = field(default_factory=list)

    # ------------------------------------------------------------ desde / hacia el Proyecto del escritor
    @classmethod
    def desde_proyecto(cls, proyecto: Proyecto, marcas: list[bool], huecos: list[bool], claves: list[str],
                       ediciones: dict | None = None, **resto) -> "ProyectoDB":
        db = cls(perfil_id=proyecto.perfil_id, item_inicial=proyecto.item_inicial, **resto)
        item = proyecto.item_inicial
        i = 0
        gc = -1                                                    # bloque de campo: crece en cada campo de cada nivel
        for gn, nv in enumerate(proyecto.niveles):
            for c in nv.campos:
                gc += 1
                for s in c.senales:
                    es_medicion = s.funcion == Funcion.MEDICION
                    b = SenalBase(
                        id=i + 1, grupo_nivel=gn, grupo_campo=gc, nivel=nv.nombre,
                        nivel_codigo=nv.codigo, campo=c.numero, descripcion_campo=c.descripcion, campo_prefijo=c.prefijo,
                        funcion=s.funcion.value, controlador=s.controlador, tag_hmi=s.tag_hmi, desc_hmi=s.desc_hmi,
                        tag_scada=s.tag_scada, offset=s.offset, desc_scada=s.desc_scada, unidad=s.unidad,
                        tipo_senal=s.tipo_punto.value if s.tipo_punto else "", placa=s.placa, entrada=s.entrada,
                        observaciones=s.observaciones, segunda_fila=s.segunda_fila, es_reserva=s.es_reserva,
                        es_hueco=huecos[i], sin_resolver=marcas[i], hoja=s.hoja, archivo=s.archivo)
                    for viejo, nuevo in _ESCALAS.items():          # K-N: estados o escalas según la función
                        setattr(b, nuevo if es_medicion else viejo, getattr(s, viejo))
                    b.indice_dnp = s.offset                        # regla del usuario (2026-11-13): índice DNP = OFFSET
                    if not huecos[i]:
                        b.item, item = item, item + 1
                    b.completar_origen()
                    db.senales.append(b)
                    i += 1
        db._marcar_ediciones(claves, ediciones or {})
        return db

    def _marcar_ediciones(self, claves: list[str], ediciones: dict) -> None:
        import desde_pdf                                           # evita el import circular al cargar el paquete
        for clave, b in zip(claves, self.senales):
            for col in ediciones.get(clave, {}):
                attr = desde_pdf.EDITABLES.get(col)
                if attr is None:
                    continue
                nombre = _RENOMBRE.get(attr, attr)
                if b.funcion == Funcion.MEDICION.value:
                    nombre = _ESCALAS.get(nombre, nombre)
                b.origen[nombre] = MANUAL

    def a_proyecto(self) -> tuple[Proyecto, list[bool], list[bool]]:
        """(Proyecto, marcas «sin resolver», filas libres): lo mismo que arma `desde_pdf.a_proyecto`."""
        proyecto = Proyecto(self.perfil_id, item_inicial=self.item_inicial)
        nivel = campo = None
        gn = gc = None
        for b in self.senales:
            if nivel is None or b.grupo_nivel != gn:
                nivel = Nivel(nombre=b.nivel, codigo=b.nivel_codigo)
                proyecto.niveles.append(nivel)
                gn, campo, gc = b.grupo_nivel, None, None
            if campo is None or b.grupo_campo != gc:
                campo = Campo(numero=b.campo, descripcion=b.descripcion_campo, prefijo=b.campo_prefijo)
                nivel.campos.append(campo)
                gc = b.grupo_campo
            es_medicion = b.funcion == Funcion.MEDICION.value
            s = Senal(funcion=Funcion(b.funcion), controlador=b.controlador, tag_hmi=b.tag_hmi, desc_hmi=b.desc_hmi,
                      tag_scada=b.tag_scada, offset=b.offset, desc_scada=b.desc_scada, unidad=b.unidad,
                      tipo_punto=TipoPunto(b.tipo_senal) if _valido(b.tipo_senal) else None, placa=b.placa,
                      entrada=b.entrada, observaciones=b.observaciones, segunda_fila=b.segunda_fila,
                      es_reserva=b.es_reserva, hoja=b.hoja, archivo=b.archivo)
            for viejo, nuevo in _ESCALAS.items():
                setattr(s, viejo, getattr(b, nuevo if es_medicion else viejo))
            campo.senales.append(s)
        return proyecto, [b.sin_resolver for b in self.senales], [b.es_hueco for b in self.senales]

    # ------------------------------------------------------------ consultas
    def filas(self) -> list[SenalBase]:
        """Las señales reales (sin las filas libres)."""
        return [b for b in self.senales if not b.es_hueco]

    def con_fuente(self, fuente: str) -> list[tuple[SenalBase, str]]:
        """(señal, dato) de todos los datos que tienen esa fuente (ej. MANUAL)."""
        return [(b, n) for b in self.senales for n, f in b.origen.items() if f == fuente]

    # ------------------------------------------------------------ guardar y cargar
    def a_dict(self) -> dict:
        return {"version": VERSION, "perfil_id": self.perfil_id, "estilo": self.estilo, "item_inicial": self.item_inicial,
                "pdfs": self.pdfs, "datos": self.datos, "caratula": self.caratula,
                "senales": [b.a_dict() for b in self.senales]}

    @classmethod
    def de_dict(cls, d: dict) -> "ProyectoDB":
        if d.get("version", 1) > VERSION:
            raise ValueError(f"El proyecto es de una versión más nueva ({d['version']}) que la que sabe leer esta app.")
        return cls(perfil_id=d.get("perfil_id", "EPEN"), estilo=d.get("estilo", ""), item_inicial=d.get("item_inicial", 1),
                   pdfs=list(d.get("pdfs", [])), datos=dict(d.get("datos", {})), caratula=d.get("caratula"),
                   senales=[SenalBase.de_dict(x) for x in d.get("senales", [])])

    def guardar(self, ruta) -> None:
        Path(ruta).write_text(json.dumps(self.a_dict(), ensure_ascii=False, indent=1), encoding="utf-8")

    @classmethod
    def cargar(cls, ruta) -> "ProyectoDB":
        return cls.de_dict(json.loads(Path(ruta).read_text(encoding="utf-8")))
