"""Qué cambia de un cliente a otro: contrasta el listado de EPEN (ETAP) con el de USRE, midiendo cada regla.

    python -m scada.comparar_clientes            # imprime la tabla y la guarda en diferencias_clientes.md
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

from . import ejemplos

RAIZ = Path(__file__).resolve().parent


def _pct(n: int, d: int) -> str:
    return f"{n}/{d} ({100 * n / d:.0f} %)" if d else "sin datos"


def medir(filas: list[dict]) -> dict:
    cmd = [f for f in filas if f["funcion"] == "COMANDO" and f["tag"] and f["tag"] != "N/A"]
    sen = {}
    for f in filas:
        if f["funcion"] == "SEÑALIZACION" and f["tag"]:
            sen.setdefault(re.sub(r"C$", "", f["tag"]), f["offset"])
    con_c = sum(f["tag"].endswith("C") for f in cmd)
    comp = sum(sen.get(re.sub(r"C$", "", f["tag"])) == f["offset"] for f in cmd if re.sub(r"C$", "", f["tag"]) in sen)
    con_sen = sum(re.sub(r"C$", "", f["tag"]) in sen for f in cmd)
    estados = [f["s0"] for f in filas if f["funcion"] in ("SEÑALIZACION", "COMANDO") and f["s0"].lower().startswith("err")]
    mayus = sum(e.startswith("ERR") for e in estados)
    meds = [f for f in filas if f["funcion"] == "MEDICION" and f["s0"]]
    raw_min = Counter(f["s0"] for f in meds if f["s0"].lstrip("-").isdigit() and int(f["s0"]) < 0)
    unidades = Counter(f["unidad"] for f in meds if f["unidad"] not in ("", "N/A"))
    orden_ab = Counter((f["s1"], f["s2"]) for f in filas
                       if f["funcion"] == "SEÑALIZACION" and f["s0"].lower().startswith("err") and {f["s1"], f["s2"]} == {"AB", "CE"})
    P = re.compile(r"^(\w+?)\.(\d{2})")
    primero: dict[str, int] = {}
    for f in filas:
        m = P.match(f["tag"] or "")
        if m and not re.search(r"[A-Z]{2}$", f["tag"]):
            primero.setdefault(m.group(1), int(m.group(2)))
    return dict(n=len(filas), cmd=len(cmd), con_c=con_c, comp=comp, con_sen=con_sen, err=len(estados), mayus=mayus,
                raw_min=raw_min.most_common(2), unidades=unidades.most_common(6), orden_ab=orden_ab.most_common(2),
                var0=Counter(primero.values()).most_common(3), campos=len(primero),
                con_hmi=sum(bool(f["desc_hmi"]) for f in filas))


def main() -> str:
    e, u = medir(ejemplos.etap()), medir(ejemplos.usre())
    filas = [
        ("Filas del listado", e["n"], u["n"]),
        ("Columnas", "A-W (DESC. HMI, UTR, placa, entrada)", "A-Q (sin DESC. HMI ni UTR; con columna AUTOTROL)"),
        ("Filas con DESC. HMI", _pct(e["con_hmi"], e["n"]), _pct(u["con_hmi"], u["n"])),
        ("Tag del comando termina en C", _pct(e["con_c"], e["cmd"]), _pct(u["con_c"], u["cmd"])),
        ("Comando usa el mismo offset que su señalización", _pct(e["comp"], e["con_sen"]), _pct(u["comp"], u["con_sen"])),
        ("Estados de transición/discrepancia en MAYÚSCULAS (ERR_0)", _pct(e["mayus"], e["err"]), _pct(u["mayus"], u["err"])),
        ("Orden S1/S2 en Abierto/Cerrado", str(e["orden_ab"]), str(u["orden_ab"])),
        ("MIN RAW con signo", str(e["raw_min"]), str(u["raw_min"])),
        ("Unidades de las mediciones", str(e["unidades"]), str(u["unidades"])),
        ("Variable inicial de los campos (valor, cantidad de campos)", f'{e["var0"]} de {e["campos"]}', f'{u["var0"]} de {u["campos"]}'),
    ]
    md = ["# Qué cambia de un cliente a otro (medido en los listados de la carpeta Ejemplos)", "",
          "| Regla | EPEN (ETAP) | USRE (Arroyito) |", "|---|---|---|"]
    md += [f"| {a} | {b} | {c} |" for a, b, c in filas]
    md += ["", "Conclusión: los dos clientes comparten el patrón del tag (`{nivel}{campo}.{variable}{bits}`) pero difieren en "
           "el offset del comando (propio en USRE), mayúsculas de los estados, rango RAW, unidades, variable inicial y "
           "columnas. Por eso todas esas reglas viven en un perfil por cliente (`perfiles/<cliente>/scada.json`)."]
    texto = "\n".join(md)
    (RAIZ / "diferencias_clientes.md").write_text(texto + "\n", encoding="utf-8")
    return texto


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    print(main())
