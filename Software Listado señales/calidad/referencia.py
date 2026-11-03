"""Comparacion con el listado terminado (referencia) por identificador estable, nunca por fila ni parecido.

Una senal se vincula solo si el TAG SCADA coincide EXACTO, la FUNCION coincide, hay un unico candidato y el
campo (primer termino de DESC. HMI) es el mismo. Con eso la equivalencia esta confirmada:
  - mismo texto -> coincide
  - mismo texto salvo mayusculas/tildes/espacios -> se adopta el texto aprobado de la referencia (estilo)
  - texto distinto -> diferencia funcional: NO se copia, queda en el informe
Mismo TAG con otro campo, o varios candidatos -> ambigua: se informa, no se corrige."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from .libro import Cambio, Fila, Pendiente, leer_filas
from .reglas import Reglas
from .texto import sin_tildes

NO_TAG = {"", "N/A", "n/a"}


def _plegar(t: str) -> str:
    return re.sub(r"\s+", " ", sin_tildes(t)).strip().casefold()


@dataclass
class Resumen:
    examinadas: int = 0
    vinculadas: int = 0
    coinciden: int = 0
    adoptadas: int = 0
    difieren: list = field(default_factory=list)      # (fila, tag, columna, texto, referencia)
    ambiguas: list = field(default_factory=list)      # (fila, tag, motivo)
    sin_referencia: list = field(default_factory=list)  # (fila, tag)


def indexar(ws, reglas: Reglas) -> dict:
    idx: dict = defaultdict(list)
    for f in leer_filas(ws, reglas):
        if f.tag_scada not in NO_TAG:
            idx[(f.tag_scada, f.funcion)].append(f)
    return idx


def comparar(ws, filas: list[Fila], idx_ref: dict, reglas: Reglas) -> tuple[Resumen, list[Cambio], list[Pendiente]]:
    res, cambios, pend = Resumen(), [], []
    c = reglas.col
    for f in filas:
        if f.tag_scada in NO_TAG:
            continue
        res.examinadas += 1
        cands = idx_ref.get((f.tag_scada, f.funcion), [])
        if not cands:
            res.sin_referencia.append((f.fila, f.tag_scada))
            continue
        if len(cands) > 1 or cands[0].prefijo.casefold() != f.prefijo.casefold():
            motivo = "varios candidatos en la referencia" if len(cands) > 1 else \
                f"mismo TAG pero otro campo ({f.prefijo!r} vs {cands[0].prefijo!r} en la referencia)"
            res.ambiguas.append((f.fila, f.tag_scada, motivo))
            pend.append(Pendiente(ws.title, f"{c['tag_scada']}{f.fila}", f.tag_scada, f.desc_hmi, "referencia_ambigua", motivo))
            continue
        ref = cands[0]
        res.vinculadas += 1
        igual = True
        for letra, mio, suyo in ((c["desc_hmi"], f.desc_hmi, ref.desc_hmi), (c["desc_scada"], f.desc_scada, ref.desc_scada)):
            if mio == suyo:
                continue
            if _plegar(mio) == _plegar(suyo):
                limite = reglas.largo(letra)
                if limite and len(suyo) > limite:
                    continue
                ws[f"{letra}{f.fila}"].value = suyo
                cambios.append(Cambio(ws.title, f"{letra}{f.fila}", f.tag_scada, letra, mio, suyo, "referencia",
                                      "texto_aprobado_de_referencia", mio, suyo, "alta",
                                      f"TAG {f.tag_scada} vinculado; difiere solo en mayusculas/tildes/espacios"))
                res.adoptadas += 1
            else:
                igual = False
                res.difieren.append((f.fila, f.tag_scada, letra, mio, suyo))
                pend.append(Pendiente(ws.title, f"{letra}{f.fila}", f.tag_scada, mio, "difiere_de_referencia",
                                      f"la referencia dice {suyo!r}: diferencia que puede ser funcional", suyo))
        res.coinciden += igual
    return res, cambios, pend


def auditar(ws, reglas: Reglas) -> list[str]:
    """Hallazgos sobre la propia referencia: sirve de modelo de calidad pero no se asume perfecta."""
    c = reglas.col
    filas = leer_filas(ws, reglas)
    out = []
    raros = [f"{l}{r}" for r in range(reglas.primera_fila, ws.max_row + 1) for l in reglas.columnas_texto
             if isinstance(ws[f"{l}{r}"].value, str) and (ws[f"{l}{r}"].value != ws[f"{l}{r}"].value.strip()
                                                           or "  " in ws[f"{l}{r}"].value)]
    if raros:
        out.append(f"{len(raros)} celdas de texto con espacios sobrantes o dobles (ej. {', '.join(raros[:4])})")
    kv = Counter()
    for r in range(reglas.primera_fila, ws.max_row + 1):
        for l in reglas.columnas_texto:
            v = ws[f"{l}{r}"].value
            if isinstance(v, str):
                for m in re.findall(r"\d+(?:[.,]\d+)?\s*[kK][vV]", v):
                    kv[m] += 1
    if len({k.replace(" ", "") for k in kv} ) != len({k.replace(" ", "").lower() for k in kv}):
        out.append("la unidad de tension se escribe de varias formas: " + ", ".join(f"{k} x{n}" for k, n in kv.most_common(6)))
    rep = Counter((f.tag_scada, f.funcion) for f in filas if f.tag_scada not in NO_TAG)
    dup = [k for k, n in rep.items() if n > 1]
    if dup:
        out.append(f"{len(dup)} pares (TAG SCADA, FUNCION) repetidos (ej. {dup[0][0]} / {dup[0][1]})")
    lim = reglas.largo(c["desc_scada"])
    if lim:
        largos = [f for f in filas if len(f.desc_scada) > lim]
        if largos:
            out.append(f"{len(largos)} DESC. SCADA de mas de {lim} caracteres (ej. fila {largos[0].fila})")
    return out
