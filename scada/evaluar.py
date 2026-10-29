"""Mide el motor SCADA contra el listado terminado del ETAP.

Esconde H-O (tag, offset, descripción SCADA, estados, unidades), regenera con scada.gen a partir de la tabla A-G
y compara fila por fila. Uso, desde la carpeta codigo:
    python -m scada.evaluar         (resumen)
    python -m scada.evaluar -v      (con ejemplos de diferencias)
"""
from __future__ import annotations

import re
import sys
from collections import Counter, OrderedDict, defaultdict

from . import descripcion, ejemplos
from . import gen as scada_gen
from . import perfil as scada_perfil
from . import texto as tx
from modelo import Campo, Funcion, Nivel, Proyecto, Senal

OFFSETS_ETAP = {"DI": 200, "AI": 200, "DO": 263}


def proyecto_desde_filas(filas: list[dict]) -> tuple[Proyecto, dict[int, dict]]:
    """Proyecto con SOLO la tabla A-G (como la entrega la app) y un mapa id(Senal) -> fila real."""
    niveles: OrderedDict[str, Nivel] = OrderedDict()
    campos: dict[tuple[str, str], Campo] = {}
    real: dict[int, dict] = {}
    for f in filas:
        nv = niveles.setdefault(f["nivel"], Nivel(f["nivel"], ""))
        c = campos.get((f["nivel"], f["campo"]))
        if c is None:
            c = campos[(f["nivel"], f["campo"])] = Campo("", f["campo"])
            nv.campos.append(c)
        funcion = Funcion(f["funcion"])
        segunda = funcion == Funcion.SENALIZACION and not f["tag"] and not f["desc_hmi"]
        s = Senal(funcion=funcion, controlador=f["controlador"], tag_hmi=f["tag_hmi"], desc_hmi=f["desc_hmi"],
                  segunda_fila=segunda, es_reserva=funcion == Funcion.RESERVA)
        c.senales.append(s)
        real[id(s)] = f
    return Proyecto("EPEN", niveles=list(niveles.values()), offsets_iniciales=dict(OFFSETS_ETAP)), real


class Cuenta:
    def __init__(self):
        self.ok = self.n = 0
        self.dif: list[tuple] = []

    def add(self, igual: bool, ejemplo: tuple) -> None:
        self.n += 1
        self.ok += igual
        if not igual:
            self.dif.append(ejemplo)

    def __str__(self) -> str:
        return f"{self.ok:4d} / {self.n:<4d} = {100 * self.ok / max(self.n, 1):5.1f} %"


def _num(v):
    try:
        return round(float(v), 2)
    except (TypeError, ValueError):
        return str(v).strip()


def estructura(tag: str) -> str:
    """Tag sin el número de variable: 303.632C -> 303.##2C ; TP1.01AU -> TP1.##AU."""
    return re.sub(r"\.\d{2}", ".##", tag or "")


def evaluar(verboso: bool = False) -> dict:
    perfil = scada_perfil.cargar("EPEN")
    filas = ejemplos.etap()
    proy, real = proyecto_desde_filas(filas)
    glos = descripcion.aprender(filas, perfil)
    inf = scada_gen.generar_scada(proy, perfil, glos)

    m = defaultdict(Cuenta)
    deltas = {t: Cuenta() for t in ("DI", "AI")}
    ultimo: dict[str, tuple[int, int]] = {}
    for nv in proy.niveles:
        for c in nv.campos:
            for s in c.senales:
                f = real.get(id(s))
                if f is None:  # el motor agregó una 2ª fila que el ejemplo no tiene (ej. Recierre en 1 fila)
                    m["filas extra que el motor agregó"].add(False, (c.descripcion[:25], s.desc_hmi))
                    continue
                ref = f["ref"]
                if s.segunda_fila:
                    m["offset (todas las filas)"].add(s.offset == f["offset"], (ref, s.offset, f["offset"]))
                    continue
                es_res = s.funcion == Funcion.RESERVA
                if not es_res or f["tag"] == "N/A":
                    m["tag exacto"].add(s.tag_scada == f["tag"], (ref, s.tag_scada, f["tag"]))
                    m["tag estructura"].add(estructura(s.tag_scada) == estructura(f["tag"]),
                                            (ref, s.tag_scada, f["tag"]))
                m["offset (todas las filas)"].add(s.offset == f["offset"], (ref, s.offset, f["offset"]))
                for k in ("s0", "s1", "s2", "s3"):
                    m["estados " + k.upper()].add(_num(getattr(s, k)) == _num(f[k]),
                                                  (ref, getattr(s, k), f[k], f["desc_hmi"][:40]))
                m["unidad"].add(s.unidad == f["unidad"], (ref, s.unidad, f["unidad"]))
                m["tipo punto"].add((s.tipo_punto.value if s.tipo_punto else "") == f["tipo"],
                                    (ref, s.tipo_punto, f["tipo"]))
                if s.funcion in (Funcion.ALARMAS, Funcion.SENALIZACION, Funcion.COMANDO) and f["desc_scada"]:
                    m["desc SCADA exacta"].add(s.desc_scada == f["desc_scada"], (ref, s.desc_scada, f["desc_scada"]))
                    m["desc SCADA (sin mayúsc.)"].add(s.desc_scada.lower() == f["desc_scada"].lower(),
                                                      (ref, s.desc_scada, f["desc_scada"]))
                    m["desc SCADA resuelta (no vacía)"].add(bool(s.desc_scada), (ref, s.desc_scada, f["desc_scada"]))
                # saltos de offset consecutivos (estructura, sin depender de los huecos del ejemplo)
                t = s.tipo_punto.value if s.tipo_punto else ""
                if t in deltas and s.offset is not None and f["offset"] is not None:
                    if t in ultimo:
                        deltas[t].add(s.offset - ultimo[t][0] == f["offset"] - ultimo[t][1],
                                      (ref, s.offset - ultimo[t][0], f["offset"] - ultimo[t][1]))
                    ultimo[t] = (s.offset, f["offset"])
    for t, c in deltas.items():
        m[f"salto de offset {t} (igual al ejemplo)"] = c

    # ---- descripciones con validación cruzada: el campo evaluado NO está en el aprendizaje
    cv = defaultdict(Cuenta)
    grupos = OrderedDict()
    for f in filas:
        grupos.setdefault((f["nivel"], f["campo"]), []).append(f)
    for (nv, cp), fs in grupos.items():
        otros = [f for k, g in grupos.items() if k != (nv, cp) for f in g]
        g_cv = descripcion.aprender(otros, perfil)
        prefijo = tx.prefijo_comun([f["desc_hmi"] for f in fs])
        for f in fs:
            if f["funcion"] not in ("ALARMAS", "SEÑALIZACION") or not f["desc_scada"] or not f["tag"] \
                    or f["desc_scada"] == "RESERVA" or not f["desc_hmi"]:
                continue
            p, texto = tx.separar_prefijo(f["desc_hmi"])
            r = descripcion.proponer(p, texto, None, perfil, g_cv, con_propuesta=False)
            cv["resuelta por reglas/glosario"].add(bool(r.desc), (f["ref"], r.desc, f["desc_scada"]))
            if r.desc:
                cv["  acierto entre las resueltas"].add(r.desc.lower() == f["desc_scada"].lower(),
                                                       (f["ref"], r.desc, f["desc_scada"], f["desc_hmi"][:45]))
            else:  # lo que quedaría "a completar": ¿qué tan buena es la propuesta por palabras?
                pr = descripcion.proponer(p, texto, None, perfil, g_cv, con_propuesta=True)
                cv["propuesta por palabras (de las no resueltas)"].add(
                    (pr.desc or "").lower() == f["desc_scada"].lower(), (f["ref"], pr.desc, f["desc_scada"]))
                cv["propuesta cabe en 20 caracteres"].add(bool(pr.desc) and len(pr.desc) <= perfil.maximo,
                                                          (f["ref"], pr.desc, f["desc_scada"]))
    return {"m": m, "cv": cv, "inf": inf, "n": len(filas)}


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    verboso = "-v" in sys.argv
    r = evaluar(verboso)
    print(f"Listado ETAP: {r['n']} filas. Se esconde H-O y se regenera desde la tabla A-G.\n")
    for k, c in r["m"].items():
        print(f"{k:42s} {c}")
        if verboso:
            for d in c.dif[:4]:
                print("      ", d)
    print("\nDescripciones SCADA con validación cruzada (se aprende de los OTROS campos):")
    for k, c in r["cv"].items():
        print(f"{k:42s} {c}")
        if verboso:
            for d in c.dif[:6]:
                print("      ", d)
    inf = r["inf"]
    print(f"\nOrigen de las DESC. SCADA generadas: {dict(inf.origen)}  pendientes: {len(inf.pendientes)}")
    print(f"Avisos: {len(inf.avisos)}")
    if verboso:
        for a in inf.avisos[:15]:
            print("  -", a)


if __name__ == "__main__":
    main()
