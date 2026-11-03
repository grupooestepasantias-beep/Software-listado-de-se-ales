"""Carga los listados terminados de la carpeta Ejemplos como filas normalizadas (para aprender reglas y medir).

Cada fila es un dict con:
  hoja_fila, item, nivel, campo, controlador, funcion, tag_hmi, desc_hmi, tag, offset, desc_scada,
  s0, s1, s2, s3, unidad, tipo, placa, entrada, obs, ref  (nivel/campo/funcion ya rellenados hacia abajo)
`ref` = identificador de la fila de origen (para mostrar diferencias).
Los dos formatos tienen columnas distintas: ETAP (A-W) y USRE (A-Q, sin DESC. HMI ni UTR).
"""
from __future__ import annotations

from pathlib import Path

BASE = Path(__file__).resolve().parents[2]   # carpeta 'Sofware listado' (hermana de codigo)
ETAP = BASE / "Ejemplos" / "ETAP-0722-ET-CT-MC-LI-6209-1-Lista señales - CAO.xlsx"
USRE = BASE / "Ejemplos" / "USRE-0119-ET-CT-PN-SE-1700_C.xlsx"


def _t(v) -> str:
    return "" if v is None else str(v).strip()


def _n(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return _t(v)


def _int(v):
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _filas(ruta: Path, mapa: dict) -> list[dict]:
    import openpyxl
    ws = openpyxl.load_workbook(ruta, read_only=True, data_only=True)["EPEN"]
    out, nivel, campo, funcion = [], "", "", ""
    for i, r in enumerate(ws.iter_rows(min_row=6, values_only=True), start=6):
        if r[0] is None and not any(r[k] is not None for k in (mapa["tag"], mapa["offset"])):
            continue
        g = lambda k: r[mapa[k]] if mapa.get(k) is not None and mapa[k] < len(r) else None  # noqa: E731
        nivel = _t(g("nivel")) or nivel
        campo = _t(g("campo")) or campo
        funcion = _t(g("funcion")) or funcion
        out.append(dict(
            ref=f"{ruta.stem[:4]}:{i}", item=_int(r[0]), nivel=nivel, campo=campo, funcion=funcion,
            controlador=_t(g("controlador")), tag_hmi=_t(g("tag_hmi")), desc_hmi=_t(g("desc_hmi")),
            tag=_t(g("tag")), offset=_int(g("offset")), desc_scada=_t(g("desc_scada")),
            s0=_t(g("s0")), s1=_t(g("s1")), s2=_t(g("s2")), s3=_t(g("s3")),
            unidad=_t(g("unidad")), tipo=_t(g("tipo")), placa=_t(g("placa")), entrada=_t(g("entrada")),
            obs=_t(g("obs")), raw=r))
    return out


def etap() -> list[dict]:
    m = dict(nivel=1, campo=2, controlador=3, funcion=4, tag_hmi=5, desc_hmi=6, tag=7, offset=8, desc_scada=9,
             s0=10, s1=11, s2=12, s3=13, unidad=14, tipo=15, placa=18, entrada=19, obs=22)
    return _filas(ETAP, m)


def usre() -> list[dict]:
    # USRE: F=TAG HMI, G=OFFSET HMI, H=TAG AUTOTROL, I=TAG SCADA, J=OFFSET, K=DESC. SCADA, L-O=S0-S3, P=UNITS, Q=obs
    m = dict(nivel=1, campo=2, controlador=3, funcion=4, tag_hmi=5, tag=8, offset=9, desc_scada=10,
             s0=11, s1=12, s2=13, s3=14, unidad=15, obs=16)
    filas = _filas(USRE, m)
    for f in filas:  # la columna UNITS de USRE trae "Doble Bit" en las señalizaciones
        f["doble_bit"] = f["unidad"].lower() == "doble bit"
        if f["doble_bit"]:
            f["unidad"] = "N/A"
    return filas
