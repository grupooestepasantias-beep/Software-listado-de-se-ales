"""python -m calidad listado.xlsx [-o salida.xlsx] [--ref referencia.xlsx | --sin-ref] [--perfil EPEN]"""
import argparse
import sys

from . import mejorar_archivo


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="python -m calidad", description="Mejora y valida un listado de senales (.xlsx)")
    ap.add_argument("entrada")
    ap.add_argument("-o", "--salida", help="por defecto <entrada>_final.xlsx (nunca pisa la entrada)")
    ap.add_argument("--ref", help="Excel terminado de referencia (por defecto el del perfil)")
    ap.add_argument("--sin-ref", action="store_true", help="no comparar con ninguna referencia")
    ap.add_argument("--perfil", default="EPEN")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    inf = mejorar_archivo(a.entrada, a.salida, a.perfil, ref=None if a.sin_ref else (a.ref or "auto"))
    print(inf.resumen_corto())
    print("Excel:  ", inf.salida)
    print("Informe:", inf.ruta_md)
    print("Cambios:", inf.ruta_csv)
    for c in inf.bloqueantes:
        print("BLOQUEANTE:", c.codigo, "-", c.detalle)
    return 0 if inf.aprobado else 1


if __name__ == "__main__":
    raise SystemExit(main())
