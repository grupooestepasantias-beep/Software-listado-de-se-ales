"""Lógica del formulario de proyecto, sin Tkinter (para poder probarla)."""
from __future__ import annotations

from modelo import Caratula, Proyecto, Referencia, Revision, TipoPunto

CAMPOS_TEXTO = ("cliente", "obra", "lugar", "departamento", "expediente", "titulo",
                "numero_documento", "proyecto", "dibujo", "aprobo", "archivo_magnetico",
                "escala", "revision", "fecha")
OBLIGATORIOS: tuple[str, ...] = ()  # la carátula se arma después: por ahora nada es obligatorio
COLS_REVISION = ("rev", "fecha", "descripcion", "proyecto", "revisor", "aprobador")


def datos_vacios() -> dict:
    d = {k: "" for k in CAMPOS_TEXTO}
    d["escala"] = "N/A"
    d.update(item_inicial="", offsets={t.value: "" for t in TipoPunto},
             referencias=[], revisiones=[])
    return d


def _entero(texto: str):
    try:
        v = int(str(texto).strip())
    except ValueError:
        return None
    return v if v >= 0 else None


def limpiar(datos: dict) -> dict:
    """Quita espacios y descarta filas de tablas totalmente vacías."""
    d = dict(datos)
    for k in CAMPOS_TEXTO:
        d[k] = str(d.get(k, "")).strip()
    d["referencias"] = [(str(c).strip(), str(t).strip()) for c, t in d.get("referencias", [])
                        if str(c).strip() or str(t).strip()]
    d["revisiones"] = [{k: str(r.get(k, "")).strip() for k in COLS_REVISION}
                       for r in d.get("revisiones", []) if any(str(v).strip() for v in r.values())]
    return d


def validar(datos: dict, max_referencias: int, max_revisiones: int,
            largo_documento: int | None = None) -> list[str]:
    """Devuelve la lista de problemas (vacía si el formulario está listo)."""
    d = limpiar(datos)
    p = [f"Falta completar: {k}" for k in OBLIGATORIOS if not d[k]]
    # El software siempre pregunta desde qué número arrancar (ITEM y un offset por tipo de punto)
    if _entero(d.get("item_inicial", "")) is None:
        p.append("ITEM inicial: ingresá un número entero (0 o mayor)")
    for tipo, v in d.get("offsets", {}).items():
        if _entero(v) is None:
            p.append(f"OFFSET inicial {tipo}: ingresá un número entero (0 o mayor)")
    doc = d["numero_documento"]
    if doc and largo_documento and len(doc.replace("-", "")) > largo_documento:
        p.append(f"Número de documento: admite hasta {largo_documento} caracteres sin contar guiones "
                 f"(tiene {len(doc.replace('-', ''))})")
    if len(d["referencias"]) > max_referencias:
        p.append(f"Hay {len(d['referencias'])} referencias y la carátula admite {max_referencias}")
    if len(d["revisiones"]) > max_revisiones:
        p.append(f"Hay {len(d['revisiones'])} revisiones y la carátula admite {max_revisiones}")
    for i, r in enumerate(d["revisiones"], 1):
        if not r["rev"]:
            p.append(f"Revisión {i}: falta la letra/número de revisión")
    for i, (c, t) in enumerate(d["referencias"], 1):
        if not c:
            p.append(f"Referencia {i}: falta el código del plano")
    return p


def a_proyecto(datos: dict, perfil_id: str, proyecto_base: Proyecto | None = None) -> Proyecto:
    """Convierte el formulario en Proyecto (conserva niveles/campos del proyecto base, si hay)."""
    d = limpiar(datos)
    car = Caratula(**{k: d[k] for k in CAMPOS_TEXTO},
                   referencias=[Referencia(c, t) for c, t in d["referencias"]],
                   revisiones=[Revision(**r) for r in d["revisiones"]])
    p = proyecto_base or Proyecto(perfil_id=perfil_id)
    p.perfil_id = perfil_id
    p.caratula = car
    p.item_inicial = _entero(d["item_inicial"]) or 0
    p.offsets_iniciales = {t: (_entero(v) or 0) for t, v in d["offsets"].items()}
    return p


def desde_proyecto(p: Proyecto) -> dict:
    c = p.caratula
    d = {k: getattr(c, k) for k in CAMPOS_TEXTO}
    d["item_inicial"] = str(p.item_inicial)
    d["offsets"] = {t.value: str(p.offsets_iniciales.get(t.value, "")) for t in TipoPunto}
    d["referencias"] = [(r.codigo, r.descripcion) for r in c.referencias]
    d["revisiones"] = [{k: getattr(r, k) for k in COLS_REVISION} for r in c.revisiones]
    return d
