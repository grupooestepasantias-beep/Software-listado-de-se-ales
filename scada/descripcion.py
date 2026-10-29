"""DESC. SCADA (máx. 20 caracteres): {prefijo} + equipo + frase/estado.

Orden de búsqueda para cada señal (la primera que resuelve gana; lo demás queda marcado, nunca se inventa en silencio):
  1. respuestas del usuario (glosario.usuario)
  2. frase completa aprendida del listado del cliente                -> origen "glosario"
  3. composición por reglas: equipo (SEC BA, INT) + estado (L/R, T/D) o frase aprendida  -> "reglas"
  4. protecciones: "Prot. Ppal/Res <función>" -> función aprendida + PPAL / Presp           -> "reglas"
  5. PROPUESTA por palabras (vocabulario del cliente + recorte): siempre entra en el largo máximo,
     pero va marcada "propuesta" para que el usuario la confirme o corrija                    -> "propuesta"
Las claves llevan los números exactos (TC3-01 ≠ TC3-02); la versión general ("#") solo se guarda si todas las
respuestas aprendidas coinciden (si no, es ambigua y se prefiere preguntar).
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from . import texto as tx
from .perfil import PerfilScada

SECCIONES = ("texto", "frase", "rele", "palabra")
RE_REL = re.compile(r"^prot(?:eccion)?\.?\s*(ppal|principal|res|resp|respaldo)?\b[\s.\-–]*(.*)$")
RE_REL_ALIAS = {"principal": "ppal", "respaldo": "res", "resp": "res"}
# palabras de relleno que una abreviatura omite
RELLENO = {"de", "del", "la", "el", "los", "las", "por", "y", "a", "en", "con", "para", "se", "al", "un", "una"}


@dataclass
class Resultado:
    desc: Optional[str]
    origen: str            # usuario | glosario | reglas | propuesta | pendiente
    motivo: str = ""       # si falta algo: qué es


@dataclass
class Glosario:
    texto: dict[str, str] = field(default_factory=dict)    # frase completa (sin prefijo) -> abreviatura (sin prefijo)
    frase: dict[str, str] = field(default_factory=dict)    # frase sin equipo -> abreviatura
    rele: dict[str, str] = field(default_factory=dict)     # función de protección -> abreviatura (sin PPAL/Presp)
    palabra: dict[str, str] = field(default_factory=dict)  # palabra -> abreviatura (para las propuestas)
    pegado: list[str] = field(default_factory=list)        # frases que el cliente escribió pegadas al prefijo
    usuario: dict[str, dict[str, str]] = field(default_factory=lambda: {s: {} for s in SECCIONES})

    @classmethod
    def cargar(cls, ruta: Path) -> "Glosario":
        g = cls()
        if Path(ruta).is_file():
            d = json.loads(Path(ruta).read_text(encoding="utf-8"))
            for s in SECCIONES:
                setattr(g, s, dict(d.get(s, {})))
            g.pegado = list(d.get("pegado", []))
            g.usuario = {s: dict(d.get("usuario", {}).get(s, {})) for s in SECCIONES}
        return g

    def guardar(self, ruta: Path) -> None:
        d = {s: dict(sorted(getattr(self, s).items())) for s in SECCIONES}
        d["pegado"] = sorted(self.pegado)
        d["usuario"] = {s: dict(sorted(v.items())) for s, v in self.usuario.items()}
        Path(ruta).write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")

    def buscar(self, seccion: str, exacta: str, general: str) -> Optional[tuple[str, str]]:
        """Primero lo que dijo el usuario, después lo aprendido; en cada caso la clave exacta y luego la general."""
        for origen, tabla in (("usuario", self.usuario[seccion]), ("glosario", getattr(self, seccion))):
            for k in (exacta, general):
                if k in tabla:
                    return tabla[k], origen
        return None

    def recordar(self, seccion: str, clave: str, abreviatura: str) -> None:
        """Guarda una respuesta del usuario (vale para ese texto exacto y no se vuelve a preguntar)."""
        self.usuario[seccion][clave] = abreviatura.strip()


# ---------------------------------------------------------------- análisis del texto
def analizar_equipo(texto: str, perfil: PerfilScada) -> Optional[tuple[str, str]]:
    """'Seccionador 329SA03 Falta Tension Auxiliar' -> ('SEC BA', 'falta tension auxiliar')."""
    cfg = perfil.desc
    palabras = tx.norm(texto).split()
    if len(palabras) < 2:
        return None
    equipo = cfg["sinonimos_equipo"].get(palabras[0].rstrip("."))
    if not equipo:
        return None
    abrev = cfg["equipos"].get(equipo)
    resto = palabras[1:]
    if isinstance(abrev, dict):  # el código del equipo (229SL04) dice cuál es: SA, SB, SL, ST
        if not re.fullmatch(r"(?=.*\d)[a-z0-9]+", resto[0]):
            return None
        letras = "".join(re.findall(r"[a-z]+", resto[0])).upper()
        if letras not in abrev:
            return None
        abrev, resto = abrev[letras], resto[1:]
    elif resto and re.fullmatch(r"(?=.*\d)[a-z0-9]+", resto[0]):
        resto = resto[1:]
    return abrev, " ".join(resto)


def analizar_rele(texto: str) -> Optional[tuple[str, str]]:
    """'PROT PPAL EXCITACION FASE R' -> ('ppal', 'excitacion fase r')."""
    m = RE_REL.match(tx.norm(texto))
    if not m or not m.group(1):
        return None
    return RE_REL_ALIAS.get(m.group(1), m.group(1)), m.group(2)


def unir(prefijo: str, *partes: str, maximo: int = 20, pegado: bool = False) -> Optional[str]:
    """Une prefijo y partes con espacios; si no entra, prueba pegado. None si no entra de ninguna forma."""
    p = [x for x in partes if x]
    intentos = ([prefijo + "".join(p)] if pegado else []) + [" ".join([prefijo, *p]), prefijo + "".join(p)]
    for d in intentos:
        if len(d) <= maximo:
            return d
    return None


def _claves(texto: str) -> tuple[str, str]:
    return tx.clave_exacta(texto), tx.clave(texto)


# ---------------------------------------------------------------- composición
def proponer(prefijo: str, texto: str, estado_id: Optional[str], perfil: PerfilScada,
             glosario: Glosario, con_propuesta: bool = True) -> Resultado:
    """DESC. SCADA de una señal. `texto` es la DESC. HMI sin el prefijo del campo."""
    mx = perfil.maximo
    exacta, general = _claves(texto)

    r = glosario.buscar("texto", exacta, general)
    if r:
        d = unir(prefijo, r[0], maximo=mx, pegado=exacta in glosario.pegado or general in glosario.pegado)
        if d:
            return Resultado(d, r[1])

    eq = analizar_equipo(texto, perfil)
    if eq:
        abrev_eq, resto = eq
        familia = re.sub(r"^(sen|com)_", "", estado_id or "")   # acepta "ab_ce" y "sen_ab_ce"
        if familia in perfil.desc["estado_abreviado"]:
            parte = perfil.desc["estado_abreviado"][familia]
            d = unir(prefijo, abrev_eq, parte, maximo=mx)
            if d:
                return Resultado(d, "reglas")
        elif resto:
            rf = glosario.buscar("frase", *_claves(resto))
            if rf:
                d = unir(prefijo, abrev_eq, rf[0], maximo=mx)
                if d:
                    return Resultado(d, rf[1] if rf[1] == "usuario" else "reglas")

    rel = analizar_rele(texto)
    if rel:
        lado, funcion = rel
        rf = glosario.buscar("rele", *_claves(funcion))
        suf = perfil.desc["sufijo_rele"].get(lado)
        if rf and suf:
            d = unir(prefijo, rf[0], suf, maximo=mx)
            if d:
                return Resultado(d, rf[1] if rf[1] == "usuario" else "reglas")

    # señales sin equipo cuya abreviatura depende del tipo de estado (Llave T/D, Recierre HAB, RBC MAN/AUTO)
    familia = re.sub(r"^(sen|com)_", "", estado_id or "")
    for rg in perfil.desc.get("reglas_texto", []):
        if rg["familia"] == familia and re.search(rg["patron"], tx.norm(texto)):
            d = unir(prefijo, rg["abrev"], maximo=mx)
            if d:
                return Resultado(d, "reglas")

    motivo = f"falta la abreviatura de «{texto}»"
    if con_propuesta:
        p = abreviar_por_palabras(prefijo, texto, perfil, glosario)
        if p:
            return Resultado(p, "propuesta", motivo)
    return Resultado(None, "pendiente", motivo)


def vocabulario(perfil: PerfilScada, glosario: Glosario) -> dict[str, str]:
    """Palabra -> abreviatura. Prioridad: lo que contestó el usuario, lo aprendido del cliente, el vocabulario base."""
    return {**perfil.desc.get("vocabulario_base", {}), **glosario.palabra, **glosario.usuario.get("palabra", {})}


def _palabras(texto: str, vocab: dict[str, str], baja: set[str]) -> list[dict]:
    """Texto -> piezas {abrev, info, fija}. 'falta tension auxiliar' se junta en F/Uaux, 'falta tension' en F/U."""
    ws = [w for w in re.split(r"[\s/\-–.,()]+", tx.norm(texto)) if w and w not in RELLENO]
    piezas, i = [], 0
    while i < len(ws):
        w = ws[i]
        if w == "falta" and i + 1 < len(ws) and ws[i + 1] == "tension":
            if i + 2 < len(ws) and ws[i + 2] in ("auxiliar", "aux"):
                piezas.append({"abrev": "F/Uaux", "info": 4, "w": "falta tension auxiliar"})
                i += 3
            else:
                piezas.append({"abrev": "F/U", "info": 4, "w": "falta tension"})
                i += 2
            continue
        if w in vocab:
            piezas.append({"abrev": vocab[w], "info": 3, "w": w})
        elif re.search(r"\d", w):
            piezas.append({"abrev": w.upper(), "info": 3, "w": w})          # código de equipo / valor: se conserva
        else:
            piezas.append({"abrev": w if len(w) <= 3 else w[:4].capitalize(), "info": 1 if w in baja else 2, "w": w})
        i += 1
    return piezas


def abreviar_por_palabras(prefijo: str, texto: str, perfil: PerfilScada, glosario: Glosario,
                          conservar: frozenset = frozenset()) -> Optional[str]:
    """PROPUESTA (a confirmar): conserva el equipo si lo hay, abrevia palabra por palabra con el vocabulario del
    cliente y, si no entra en el largo, descarta primero lo de menor información. `conservar` = palabras que no se
    pueden perder (las que distinguen esta señal de las otras del campo). Siempre entra en el largo máximo."""
    mx = perfil.maximo
    vocab = vocabulario(perfil, glosario)
    baja = set(perfil.desc.get("baja_informacion", []))
    eq = analizar_equipo(texto, perfil)
    cabeza = [{"abrev": eq[0], "info": 9, "w": "<equipo>"}] if eq else []
    piezas = cabeza + _palabras(eq[1] if eq else texto, vocab, baja)
    if not piezas:
        return None
    unir_ = lambda: " ".join([prefijo, *[p["abrev"] for p in piezas]])  # noqa: E731
    protegidas = lambda p: p["w"] == "<equipo>" or any(c in p["w"] for c in conservar)  # noqa: E731
    while len(unir_()) > mx:
        # 1) primero se acortan las palabras largas que no son abreviaturas del vocabulario
        largas = [p for p in piezas if len(p["abrev"]) > 4 and p["w"] not in vocab and p["info"] < 4 and not protegidas(p)]
        if largas:
            p = max(largas, key=lambda x: len(x["abrev"]))
            p["abrev"] = p["abrev"][:4] if len(p["abrev"]) > 4 else p["abrev"][:-1]
            continue
        # 2) después se descarta lo de menor información (las protegidas no)
        libres = [p for p in piezas if not protegidas(p)]
        if libres:
            piezas.remove(min(libres, key=lambda p: (p["info"], -piezas.index(p))))
            continue
        # 3) solo quedan protegidas: se recorta la más larga
        p = max(piezas, key=lambda x: len(x["abrev"]))
        if len(p["abrev"]) <= 2:
            return None
        p["abrev"] = p["abrev"][:-1]
    return unir_()


# ---------------------------------------------------------------- aprendizaje desde un listado terminado
def _partir_scada(desc_scada: str, prefijo: str) -> Optional[tuple[str, bool]]:
    """('303LC SEC BA', '303LC') -> ('SEC BA', False);  ('303LcPrtTx', '303LC') -> ('PrtTx', True)."""
    if not desc_scada.lower().startswith(prefijo.lower()):
        return None
    resto = desc_scada[len(prefijo):]
    pegado = bool(resto) and not resto.startswith(" ")
    return resto.strip(), pegado


def _elegir(votos: dict[str, Counter], general: bool) -> dict[str, str]:
    """Clave exacta: gana la respuesta más repetida. Clave general (con #): solo si todas coinciden."""
    out = {}
    for k, c in votos.items():
        if general and (len(c) > 1 or sum(c.values()) < 2):   # general: unánime y visto al menos 2 veces
            continue
        out[k] = c.most_common(1)[0][0]
    return out


def aprender(filas: list[dict], perfil: PerfilScada) -> Glosario:
    """Construye el glosario a partir de filas normalizadas (ver ejemplos.py: desc_hmi, desc_scada, funcion, tag)."""
    ex: dict[str, dict[str, Counter]] = {s: defaultdict(Counter) for s in SECCIONES}
    ge: dict[str, dict[str, Counter]] = {s: defaultdict(Counter) for s in SECCIONES}
    pegados: dict[str, Counter] = defaultdict(Counter)

    def voto(seccion: str, texto: str, abrev: str) -> None:
        e, g = _claves(texto)
        ex[seccion][e][abrev] += 1
        ge[seccion][g][abrev] += 1

    for f in filas:
        if f["funcion"] not in ("ALARMAS", "SEÑALIZACION") or not f["desc_hmi"] or not f["desc_scada"]:
            continue
        if f["desc_scada"].upper() == "RESERVA" or not f["tag"] or f["tag"] == "N/A":
            continue
        prefijo, texto = tx.separar_prefijo(f["desc_hmi"])
        partido = _partir_scada(f["desc_scada"], prefijo)
        if not partido or not partido[0]:
            continue
        abrev, pegado = partido
        voto("texto", texto, abrev)
        e, g = _claves(texto)
        pegados[e][pegado] += 1
        pegados[g][pegado] += 1
        eq = analizar_equipo(texto, perfil)
        if eq and abrev.startswith(eq[0] + " ") and f["funcion"] == "ALARMAS":
            voto("frase", eq[1], abrev[len(eq[0]) + 1:])
        rel = analizar_rele(texto)
        if rel:
            suf = perfil.desc["sufijo_rele"].get(rel[0], "")
            if suf and abrev.lower().endswith(" " + suf.lower()):
                voto("rele", rel[1], abrev[: -len(suf) - 1].strip())
        # palabra por palabra, solo si la cantidad coincide (alineación segura)
        pal = [w for w in re.split(r"[\s/\-–.,()]+", tx.norm(texto)) if w and w not in RELLENO and not re.search(r"\d", w)]
        abr = abrev.split()
        if eq:
            pal = [w for w in pal if w not in tx.norm(texto).split()[:2]]
        if pal and len(pal) == len(abr):
            for w, a in zip(pal, abr):
                ex["palabra"][w][a] += 1
    g = Glosario()
    for s in SECCIONES:
        tabla = _elegir(ex[s], general=False)
        # las claves generales (con #) se suman solo si no chocan con una exacta y todas sus respuestas coinciden
        for k, v in _elegir(ge[s], general=True).items():
            if "#" in k and k not in tabla:
                tabla[k] = v
        setattr(g, s, tabla)
    g.pegado = [k for k, c in pegados.items() if c[True] > c[False]]
    return g
