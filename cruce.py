"""Cruce de la información de varios documentos y verificación del listado antes de armarlo.

1. Las hojas de LISTA DE SEÑALES (se encuentran por el índice del documento o por el título del cajetín) se leen por
   columnas: cada columna es una señal con su nombre completo, su relé/borne y su módulo de la UTR.
2. Cada señal leída de los esquemas funcionales (EF) se busca en esas listas: mismo código de equipo (152/01, 189T/03)
   y rótulo parecido (el OCR confunde O/0, por eso se compara con `documentos.clave_ocr`).
3. Resultado por señal: verificada · texto distinto (se muestran los dos) · sin respaldo (solo figura en el EF).
   Aparte: señales que figuran en las listas y no en el EF (recuperadas), duplicados y páginas que no se pudieron leer.
Nada se inventa: lo que no se encuentra queda como pendiente, con el archivo y la hoja de donde sale cada dato."""
from __future__ import annotations

import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from typing import Optional

from documentos import Documento, PaginaDoc, clave_ocr, filas

CODIGO = re.compile(r"\b\d{2,3}[A-Z]{0,2}/\d{2}\b")
TITULO_LISTA = re.compile(r"LISTA(DO)?\s+DE\s+SE.ALES|SE.ALES\s+Y\s+ALARMAS", re.I)
UMBRAL_IGUAL, UMBRAL_PARECIDO = 0.88, 0.62


@dataclass
class CeldaLista:
    archivo: str
    pagina: int
    hoja: str
    seccion: str
    texto: str                       # nombre completo de la señal (varias líneas unidas)
    rele: str = ""                   # -KS6.1
    borne: str = ""                  # 14-B-1
    modulo: str = ""                 # UTR1.1.1 / SEL 2244 / Entradas Digitales
    codigos: tuple = ()
    campo: str = ""                  # campo al que pertenece la hoja de lista (por los códigos de equipo; "" si no hay pista)

    @property
    def origen(self) -> str:
        return f"{self.archivo} · hoja {self.hoja or '?'} (pág. {self.pagina})"


@dataclass
class Verificacion:
    archivo_ef: str
    pagina_ef: int
    campo: str
    rotulo: str
    estado: str                      # verificada | distinto | sin_respaldo | ambigua
    celda: Optional[CeldaLista] = None
    ratio: float = 0.0
    nota: str = ""


@dataclass
class Informe:
    verificaciones: list[Verificacion] = field(default_factory=list)
    recuperadas: list[CeldaLista] = field(default_factory=list)      # en una lista y no en el EF
    tableros: list[CeldaLista] = field(default_factory=list)         # señales de hojas de tablero que el lector de EF no toma
    duplicados: list[str] = field(default_factory=list)
    sin_leer: list[str] = field(default_factory=list)                # "archivo pág. N"
    listas: list[str] = field(default_factory=list)                  # "archivo hoja N (pág. M)"
    indices: list[str] = field(default_factory=list)                 # "archivo: n entradas"
    sin_lista: bool = False

    def contar(self) -> Counter:
        return Counter(v.estado for v in self.verificaciones)

    def resumen(self) -> str:
        c = self.contar()
        partes = [f"{len(self.verificaciones)} señales del EF: {c['verificada']} verificadas en las listas, "
                  f"{c['distinto']} con texto distinto, {c['ambigua']} ambiguas, {c['sin_respaldo']} sin respaldo."]
        if self.sin_lista:
            partes.append("No se encontró ninguna hoja de LISTA DE SEÑALES entre los documentos: nada pudo verificarse.")
        else:
            partes.append(f"{len(self.recuperadas)} señales figuran en las listas y no en el EF.")
        if self.tableros:
            reservas = sum(1 for c in self.tableros if c.texto.lower().startswith("reserva"))
            partes.append(f"{len(self.tableros)} señales leídas de hojas de tablero que el lector de EF no toma "
                          f"({reservas} de reserva): nivel/campo/función por confirmar.")
        if self.duplicados:
            partes.append(f"{len(self.duplicados)} posibles duplicados.")
        if self.sin_leer:
            partes.append(f"{len(self.sin_leer)} páginas no se pudieron leer (necesitan OCR): " + ", ".join(self.sin_leer[:6])
                          + ("…" if len(self.sin_leer) > 6 else ""))
        return " ".join(partes)


# ---------------------------------------------------------------- lectura de las listas
def es_hoja_de_lista(pg: PaginaDoc) -> bool:
    return bool(TITULO_LISTA.search(pg.seccion) or TITULO_LISTA.search(pg.titulo))


def celdas_de_lista(pg: PaginaDoc) -> list[CeldaLista]:
    """Una celda por columna de la hoja. Las columnas se ubican con el renglón que más cajas repite (en estas hojas,
    el de 'UTR1.1.1' o 'Entradas Digitales', uno por señal); lo que cae sobre esa columna arriba de los códigos de relé
    es el nombre de la señal."""
    renglones = filas(pg.cajas, tol=3.0)
    ancla = max(renglones, key=len, default=[])
    if len(ancla) < 6:
        return []
    centros = [c.cx for c in ancla]
    paso = sorted(b - a for a, b in zip(centros, centros[1:]))[len(centros) // 2]
    cols: dict[int, list] = defaultdict(list)
    for c in pg.cajas:
        i = min(range(len(centros)), key=lambda k: abs(centros[k] - c.cx))
        if abs(centros[i] - c.cx) <= paso * 0.6:
            cols[i].append(c)
    titulo = next((r[0].cy for r in renglones if any(TITULO_LISTA.search(c.texto) for c in r)), 0)
    celdas = []
    for i in range(len(centros)):
        cajas = sorted(cols[i], key=lambda c: c.cy)
        tope = next((c.cy for c in cajas if re.match(r"-?[KX][A-Z]*\d|\d{1,2}-[A-D]-\d", c.texto)), ancla[0].cy)
        nombre = [c for c in cajas if c.cy > titulo + 3 and c.cy < min(tope, ancla[0].cy) - 3]
        texto = " ".join(c.texto for c in nombre).strip()
        texto = re.sub(r"(\d{2,3}/\d{2}|CAMPO \d{2})(?=[A-Za-z])", r"\1 ", texto)   # el OCR pega el código con la palabra siguiente
        texto = re.sub(r"(\d)\s+/\s+(\d)", r"\1/\2", texto)                          # '152 / 03' -> '152/03'
        if not texto:
            continue
        rele = next((c.texto for c in cajas if re.match(r"-?K[A-Z]*\d", c.texto)), "")
        borne = next((c.texto for c in cajas if re.match(r"\d{1,2}-[A-D]-\d", c.texto)), "")
        modulo = " / ".join(c.texto for c in cajas if c.cy >= ancla[0].cy - 3 and c.cy < ancla[0].cy + 40
                            and not re.match(r"(?i)hoja|titulo|obra|proyecto", c.texto))
        celdas.append(CeldaLista(pg.archivo, pg.n, pg.hoja, pg.seccion, texto, rele, borne, modulo,
                                 tuple(sorted(set(CODIGO.findall(texto.upper()))))))
    return celdas


TITULO_SENALES = re.compile(r"ENTRADAS|SALIDAS|ALARMAS|SE.ALES\s+DIGITALES", re.I)


def senales_de_tablero(pg: PaginaDoc) -> list[CeldaLista]:
    """Hojas de tableros de servicios auxiliares / DCI: el nombre de cada señal está arriba de su columna, en dos o tres
    renglones seguidos ('Falta de tensión' / 'barra 380/220Vca'), sobre los cables y los bornes.
    Solo se toma el primer bloque de renglones pegados que caen sobre las columnas: lo demás es dibujo."""
    if (es_hoja_de_lista(pg) or pg.es_indice or not TITULO_SENALES.search(pg.titulo + " " + pg.seccion)
            or re.search(r"(?i)esquema|tablas", pg.titulo + " " + pg.seccion)):
        return []
    renglones = [r for r in filas(pg.cajas, tol=3.0) if r[0].cy > 40 and r[0].cy < 400]
    renglones = [r for r in renglones if not any(re.match(r"(?i)(ENTRADAS|SALIDAS|ALARMAS)\b", c.texto) and len(r) <= 3
                                                 and c.cy < 75 for c in r) or len(r) > 3]
    primero = next((r for r in renglones if len(r) >= 4), None)
    if primero is None:
        return []
    centros = [c.cx for c in primero]
    paso = sorted(b - a for a, b in zip(centros, centros[1:]))[len(centros) // 2]
    bloque, ultimo = [], primero[0].cy
    for r in renglones:
        if r[0].cy < primero[0].cy - 3:
            continue
        if r[0].cy - ultimo > 18:
            break
        sobre = [c for c in r if min(abs(c.cx - x) for x in centros) <= paso * 0.5]
        if not sobre:
            break
        bloque.append(sobre)
        ultimo = r[0].cy
    por_col: dict[int, list] = defaultdict(list)
    for r in bloque:
        for c in r:
            por_col[min(range(len(centros)), key=lambda k: abs(centros[k] - c.cx))].append(c)
    canales = [c for c in pg.cajas if re.fullmatch(r"D[I1l]?\d{1,2}", c.texto)]
    bornes = [c for c in pg.cajas if re.fullmatch(r"-?X[A-Z0-9]*\s*/?\s*\d{1,2}", c.texto)]
    if len(canales) < 4 and len(bornes) < 4:
        return []      # sin fila de canales ni de bornes sobre las columnas no es una hoja de este formato: no se arriesga un nombre mal armado
    out = []
    for i, x in enumerate(centros):
        texto = " ".join(c.texto for c in sorted(por_col[i], key=lambda c: c.cy)).strip()
        if not texto or re.fullmatch(r"[\d\s.,/-]+", texto) or re.search(r"(?i)mm2|/Ce\b", texto) or len(texto) > 90:
            continue          # cables y números de borne, no nombres de señal
        canal = next((c.texto for c in canales if abs(c.cx - x) <= paso * 0.5), "")
        borne = next((c.texto for c in bornes if abs(c.cx - x) <= paso * 0.5), "")
        out.append(CeldaLista(pg.archivo, pg.n, pg.hoja, pg.seccion or pg.titulo, texto, "", borne, canal,
                              tuple(sorted(set(CODIGO.findall(texto.upper()))))))
    return out


ABREVIATURAS = (("PROT.", "PROTECCION "), ("DESHABI.", "DESHABILITA "), ("DESHABI ", "DESHABILITA "),
                ("HABILIT A.", "HABILITA "), ("HABILITA.", "HABILITA "), ("HABILIT.", "HABILITA "))
REFERENCIAS = re.compile(r"-?[A-Z]{2,4}\.\d+\s*:?\s*\d*\s*Q?\b|\b\d{2}\.\d{2}\b")   # -XDI.1: 1Q · -LTD.3 · 16.01


def _comparable(texto: str) -> str:
    """Quita las referencias a otras hojas y expande abreviaturas, para comparar el nombre de la señal y nada más."""
    t = re.sub(r"(\d)\s+/\s+(\d)", r"\1/\2", texto.upper())
    for corto, largo in ABREVIATURAS:
        t = t.replace(corto, largo)
    return REFERENCIAS.sub(" ", t)


def _parecido(a: str, b: str) -> float:
    a, b = _comparable(a), _comparable(b)
    r = SequenceMatcher(None, clave_ocr(a), clave_ocr(b)).ratio()
    ta, tb = a.split(), b.split()
    if ta and tb and len(ta[-1]) == 1 and len(tb[-1]) == 1 and ta[-1] != tb[-1]:
        r *= 0.5          # 'grupo A' y 'grupo B' son señales distintas aunque casi todo el texto coincida
    return r


def _campo_de_celdas(celdas: list[CeldaLista]) -> str:
    votos = Counter()
    for c in celdas:
        for cod in c.codigos:
            votos[cod[-2:]] += 1
        for m in re.finditer(r"(?i)CAMP[O0]\s?0?(\d{1,2})", c.texto):
            votos[m.group(1).zfill(2)] += 2
    return votos.most_common(1)[0][0] if votos else ""


# ---------------------------------------------------------------- cruce
def verificar(paginas, documentos: list[Documento]) -> Informe:
    """`paginas`: PaginaLeida del EF (pdf_plano). Marca cada LecturaSenal con `verificacion` y devuelve el informe."""
    inf = Informe()
    celdas: list[CeldaLista] = []
    for d in documentos:
        if d.indice:
            inf.indices.append(f"{d.nombre}: {len(d.indice)} entradas de índice")
        inf.sin_leer += [f"{d.nombre} pág. {n}" for n in d.sin_leer]
        de_doc: list[list[CeldaLista]] = []
        for pg in d.paginas:
            if es_hoja_de_lista(pg):
                cs = celdas_de_lista(pg)
                if cs:
                    inf.listas.append(f"{d.nombre} hoja {pg.hoja or '?'} (pág. {pg.n}): {len(cs)} señales")
                    de_doc.append(cs)
        # una hoja de lista sin códigos de equipo ('Tensiones interrumpidas') es del mismo campo que la que le sigue
        campo = ""
        for cs in reversed(de_doc):
            campo = _campo_de_celdas(cs) or campo
            for c in cs:
                c.campo = campo
        celdas += [c for cs in de_doc for c in cs]
    leidas_ef = {(p.archivo, p.pagina) for p in paginas}
    for d in documentos:
        for pg in d.paginas:
            if (pg.archivo, pg.n) not in leidas_ef:
                inf.tableros += senales_de_tablero(pg)
    inf.sin_lista = not celdas and not inf.tableros
    usadas: set[int] = set()
    vistos: dict[tuple, str] = {}
    for pg in paginas:
        for ls in pg.senales:
            if ls.es_reserva or not ls.columnas:
                continue
            for rotulo in ls.columnas:
                v = _cruzar_rotulo(pg, rotulo, celdas, usadas)
                inf.verificaciones.append(v)
                ls.verificacion = _frase(v)
                clave = (pg.nivel, pg.campo, clave_ocr(rotulo))
                if clave in vistos and not re.match(r"(?i)com[uú]n|tensiones interrumpidas", rotulo):
                    inf.duplicados.append(f"{rotulo} (campo {pg.campo}): {vistos[clave]} y {pg.archivo} pág. {pg.pagina}")
                vistos.setdefault(clave, f"{pg.archivo} pág. {pg.pagina}")
    inf.recuperadas = [c for i, c in enumerate(celdas) if i not in usadas]
    return inf


def _cruzar_rotulo(pg, rotulo: str, celdas: list[CeldaLista], usadas: set[int]) -> Verificacion:
    base = dict(archivo_ef=pg.archivo, pagina_ef=pg.pagina, campo=pg.campo, rotulo=rotulo)
    if not celdas:
        return Verificacion(**base, estado="sin_respaldo", nota="no hay hoja de lista de señales")
    codigos = tuple(sorted(set(CODIGO.findall(rotulo.upper()))))
    es_comando = bool(re.match(r"(?i)\s*(cierre|apertura|habilita|deshabilita|comando)\b", rotulo))
    candidatas = [(i, c) for i, c in enumerate(celdas)
                  if (not codigos or set(codigos) & set(c.codigos)) and (not pg.campo or not c.campo or c.campo == pg.campo)
                  and (not c.modulo or es_comando == ("SALIDAS" in c.modulo.upper()))]   # un comando se busca entre las salidas
    puntaje = sorted(((_parecido(rotulo, c.texto), i, c) for i, c in candidatas), key=lambda t: -t[0])
    if not puntaje or puntaje[0][0] < UMBRAL_PARECIDO:
        return Verificacion(**base, estado="sin_respaldo",
                            nota="el código de equipo no figura en ninguna lista" if codigos and not candidatas
                            else "ninguna señal de las listas se parece")
    r, i, c = puntaje[0]
    usadas.add(i)
    empate = len([1 for p in puntaje if p[0] >= r - 0.02]) > 1 and not codigos
    if r >= UMBRAL_IGUAL:
        return Verificacion(**base, estado="ambigua" if empate else "verificada", celda=c, ratio=r,
                            nota="el mismo texto aparece en varias columnas y no hay código de equipo" if empate else "")
    return Verificacion(**base, estado="distinto", celda=c, ratio=r,
                        nota=f"EF: «{rotulo}»  ·  lista: «{c.texto}»")


def _frase(v: Verificacion) -> str:
    if v.estado == "verificada":
        return f"verificada en {v.celda.origen}"
    if v.estado == "distinto":
        return f"texto distinto en {v.celda.origen}: «{v.celda.texto}»"
    if v.estado == "ambigua":
        return f"coincide con varias columnas de {v.celda.origen}"
    return "sin respaldo en las listas"
