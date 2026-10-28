"""Ayuda para tests: arma un Proyecto leyendo la hoja EPEN del ejemplo ETAP tal cual está (sin generar nada)."""
from pathlib import Path

from modelo import Campo, Funcion, Nivel, Proyecto, Senal, TipoPunto

EJEMPLO = Path(r"\\192.168.15.120\PasantiasMM\Sofware listado\Ejemplos\ETAP-0722-ET-CT-MC-LI-6209-1-Lista señales - CAO.xlsx")


def _txt(v) -> str:
    return "" if v is None else str(v)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return _txt(v)


def proyecto_desde_ejemplo() -> Proyecto:
    import openpyxl
    ws = openpyxl.load_workbook(EJEMPLO, read_only=True, data_only=True)["EPEN"]
    niveles, nivel, campo, fun = [], None, None, None
    for r in ws.iter_rows(min_row=6, values_only=True):
        if r[0] is None:
            continue
        if r[1]:
            nivel = Nivel(str(r[1]), "")
            niveles.append(nivel)
            campo = None
        if r[2] or campo is None:
            campo = Campo(_txt(r[2]) or "?")
            nivel.campos.append(campo)
        fun = r[4] or fun
        f = Funcion(fun)
        tp = TipoPunto(r[15]) if r[15] in ("DI", "DO", "AI", "AO") else TipoPunto.DI
        conv = _num if tp.es_analogico else _txt
        campo.senales.append(Senal(
            funcion=f, tipo_punto=tp, controlador=_txt(r[3]), tag_hmi=_txt(r[5]), desc_hmi=_txt(r[6]),
            tag_scada=_txt(r[7]), offset=int(r[8]) if r[8] not in (None, "") else None, desc_scada=_txt(r[9]),
            s0=conv(r[10]), s1=conv(r[11]), s2=conv(r[12]), s3=conv(r[13]), unidad=_txt(r[14]),
            placa=_txt(r[18]), entrada=_txt(r[19]), observaciones=_txt(r[22]),
            segunda_fila=(not _txt(r[7]) and f == Funcion.SENALIZACION)))
    return Proyecto("EPEN", niveles=niveles)
