"""Informe de calidad (Markdown) y registro de cambios (CSV) de una corrida."""
from __future__ import annotations

import csv
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from .libro import Cambio, Pendiente
from .referencia import Resumen
from .validar import ADVERTENCIA, BLOQUEANTE, RECOMENDACION, Chequeo

ROTULO = {BLOQUEANTE: "BLOQUEANTE", ADVERTENCIA: "ADVERTENCIA", RECOMENDACION: "RECOMENDACION"}
LIMITES = [
    "No hay corrector ortografico general instalado: solo se detectan los errores del diccionario configurado "
    "(perfiles/<cliente>/redaccion.json -> errores_conocidos y tildes.diccionario). Una falta de ortografia que no este "
    "en el diccionario no se detecta.",
    "La comparacion con la referencia solo vincula senales con el mismo TAG SCADA, la misma FUNCION, un unico candidato y el "
    "mismo campo. Dos proyectos distintos casi no comparten TAG, asi que la cantidad de vinculos puede ser baja o cero.",
    "Los nombres de TAG, offsets, estados, unidades y demas identificadores no se corrigen nunca; si estan mal hay que corregirlos en la fuente.",
]


@dataclass
class Informe:
    entrada: str
    salida: str
    referencia: str = ""
    examinadas: int = 0
    cambios: list = field(default_factory=list)
    pendientes: list = field(default_factory=list)
    resumen_ref: Resumen | None = None
    hallazgos_ref: list = field(default_factory=list)
    chequeos: list = field(default_factory=list)
    presentacion: list = field(default_factory=list)
    modo_tildes: str = ""
    ruta_md: str = ""
    ruta_csv: str = ""

    @property
    def bloqueantes(self) -> list[Chequeo]:
        return [c for c in self.chequeos if c.nivel == BLOQUEANTE and not c.ok]

    @property
    def aprobado(self) -> bool:
        return not self.bloqueantes

    def celdas_cambiadas(self) -> int:
        return len({(c.hoja, c.celda) for c in self.cambios if c.tipo != "presentacion"})

    def resumen_corto(self) -> str:
        return (f"{self.examinadas} descripciones examinadas, {self.celdas_cambiadas()} corregidas, "
                f"{len(self.pendientes)} para revisar, {len(self.bloqueantes)} errores bloqueantes")

    # ------------------------------------------------------------------ markdown
    def a_markdown(self) -> str:
        L = ["# Informe de calidad del listado", "",
             f"- Fecha: {datetime.now():%Y-%m-%d %H:%M}",
             f"- Entrada: `{self.entrada}`", f"- Salida: `{self.salida}`",
             f"- Referencia: `{self.referencia or 'no se uso'}`",
             f"- Tildes: modo `{self.modo_tildes}`",
             f"- **Resultado: {'APROBADO sin errores bloqueantes' if self.aprobado else 'CON ERRORES BLOQUEANTES'}** "
             f"({self.resumen_corto()})", ""]
        por_tipo = Counter(c.tipo for c in self.cambios)
        por_regla = Counter(c.regla.split(":")[0] for c in self.cambios if c.tipo != "presentacion")
        L += ["## 1. Resumen", "", "| Concepto | Cantidad |", "|---|---|",
              f"| Descripciones examinadas (DESCRIP, DESC. HMI, DESC. SCADA) | {self.examinadas} |",
              f"| Celdas corregidas | {self.celdas_cambiadas()} |",
              f"| Correcciones ortograficas | {por_tipo.get('ortografia', 0)} |",
              f"| Normalizaciones de nomenclatura / siglas | {por_tipo.get('nomenclatura', 0)} |",
              f"| Normalizaciones de formato (unidad kV, separadores, espacios) | {por_tipo.get('formato', 0) + por_tipo.get('espacios', 0)} |",
              f"| Tildes ({self.modo_tildes}) | {por_tipo.get('tildes', 0)} |",
              f"| Textos adoptados de la referencia | {por_tipo.get('referencia', 0)} |",
              f"| Casos que requieren aprobacion humana | {len(self.pendientes)} |", ""]
        if por_regla:
            L += ["Reglas aplicadas: " + ", ".join(f"`{k}` x{v}" for k, v in por_regla.most_common()), ""]

        L += ["## 2. Validaciones", "", "| Nivel | Chequeo | Resultado | Detalle |", "|---|---|---|---|"]
        orden = {BLOQUEANTE: 0, ADVERTENCIA: 1, RECOMENDACION: 2}
        for c in sorted(self.chequeos, key=lambda c: (orden[c.nivel], c.ok)):
            L.append(f"| {ROTULO[c.nivel]} | {c.codigo} | {'OK' if c.ok else 'FALLA'} | {c.detalle.replace('|', '/')} |")
        ok = sum(c.ok for c in self.chequeos)
        L += ["", f"Superadas: {ok} — Fallidas: {len(self.chequeos) - ok}.", ""]

        L += ["## 3. Comparacion con la referencia", ""]
        r = self.resumen_ref
        if r is None:
            L += ["No se uso un archivo de referencia.", ""]
        else:
            L += [f"- Senales con TAG SCADA examinadas: {r.examinadas}",
                  f"- Vinculadas de forma inequivoca (mismo TAG, FUNCION y campo): {r.vinculadas}",
                  f"- Con texto coincidente: {r.coinciden}; texto adoptado de la referencia (solo estilo): {r.adoptadas}",
                  f"- Con diferencia posiblemente funcional (no se copio): {len(r.difieren)}",
                  f"- Ambiguas (mismo TAG en otro campo o varios candidatos): {len(r.ambiguas)}",
                  f"- Sin vinculo con la referencia: {len(r.sin_referencia)}", ""]
            if r.vinculadas == 0:
                L += ["> Ninguna senal comparte TAG con la referencia (son campos distintos): no hay nada que verificar contra ella, "
                      "y por eso no se copio ningun texto. Las correcciones salen solo de las reglas.", ""]
            if self.hallazgos_ref:
                L += ["**Hallazgos en el propio archivo de referencia** (no se replican):", ""] + [f"- {h}" for h in self.hallazgos_ref] + [""]

        L += ["## 4. Para revision humana", ""]
        if not self.pendientes:
            L += ["Sin casos pendientes.", ""]
        else:
            L += ["Por tipo: " + ", ".join(f"`{k}` x{v}" for k, v in Counter(p.tipo for p in self.pendientes).most_common()), "",
                  "| Celda | TAG | Tipo | Detalle | Texto |", "|---|---|---|---|---|"]
            for p in self.pendientes[:200]:
                L.append(f"| {p.hoja}!{p.celda} | {p.tag} | {p.tipo} | {p.detalle.replace('|', '/')} | {p.texto.replace('|', '/')} |")
            if len(self.pendientes) > 200:
                L.append(f"| ... | | | {len(self.pendientes) - 200} mas en el CSV | |")
            L.append("")

        L += ["## 5. Presentacion", ""]
        L += [f"- Completado: {', '.join(self.presentacion)}" if self.presentacion else "- Sin cambios de presentacion (ya estaba completa o faltan datos en la caratula)", ""]

        L += ["## 6. Limites de este informe", ""] + [f"- {x}" for x in LIMITES]
        L += ["", "## 7. Registro de cambios", "",
              f"El detalle celda por celda (hoja, celda, TAG, texto original y corregido, tipo, regla, confianza y motivo) esta en `{Path(self.ruta_csv).name}`.", ""]
        return "\n".join(L)

    def a_csv(self, destino: Path) -> None:
        with open(destino, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f, delimiter=";")
            w.writerow(["estado", "hoja", "celda", "tag", "columna", "texto_original", "texto_final", "tipo", "regla",
                        "antes_de_la_regla", "despues_de_la_regla", "confianza", "motivo"])
            for c in self.cambios:
                w.writerow(["aplicado", c.hoja, c.celda, c.tag, c.columna, c.original, c.final, c.tipo, c.regla,
                            c.antes, c.despues, c.confianza, c.motivo])
            for p in self.pendientes:
                w.writerow(["revisar", p.hoja, p.celda, p.tag, "", p.texto, p.propuesta, p.tipo, "", "", "", "", p.detalle])

    def escribir(self, base: Path) -> None:
        self.ruta_md = str(base.with_name(base.stem + "_informe_calidad.md"))
        self.ruta_csv = str(base.with_name(base.stem + "_cambios.csv"))
        Path(self.ruta_md).write_text(self.a_markdown(), encoding="utf-8")
        self.a_csv(Path(self.ruta_csv))
