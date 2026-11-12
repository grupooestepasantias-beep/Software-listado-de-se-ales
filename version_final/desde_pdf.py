"""PDF de ingeniería -> campos numerados (numeracion.py) -> hoja del listado con el formato de EPEN (columnas A a W).

Uso por consola (valores por defecto):  python desde_pdf.py ruta.pdf [salida.xlsx]
La ventana (app/ventana.py, `python -m app`) es la forma normal de usarlo: ahí se cargan los datos que la app pregunta.
"""
from __future__ import annotations

import re
import sys
from collections import Counter
from pathlib import Path

import openpyxl
from openpyxl.styles import PatternFill

import descripcion
import estados as est
import estilo
import excel_writer
import hmi
import numeracion as num
import pdf_plano
import perfiles
from modelo import Campo, Funcion, Nivel, Proyecto, Senal, TipoPunto

# Apartado UTR (columnas P a W: tipo, placa, entrada, observaciones). Por pedido del usuario no se muestra ni se exporta;
# poner True para volver a activarlo (el cálculo sigue haciéndose por dentro).
MOSTRAR_UTR = False
COLUMNAS_UTR = ("tipo", "placa", "entrada", "obs")

# Columnas que el usuario puede corregir a mano en la tabla (clave de la tabla -> atributo de la señal).
EDITABLES = {"ctl": "controlador", "taghmi": "tag_hmi", "deschmi": "desc_hmi", "tag": "tag_scada", "offset": "offset",
             "desc": "desc_scada", "k": "s0", "l": "s1", "m": "s2", "n": "s3", "o": "unidad", "tipo": "tipo_punto",
             "placa": "placa", "entrada": "entrada", "obs": "observaciones"}


def clave_fila(nivel: str, campo: str, funcion: str, n: int) -> str:
    """Identifica una fila del listado para guardar lo que el usuario corrigió: nivel, campo, función y su orden dentro
    de esa función (estable mientras el PDF y los datos no cambien)."""
    return f"{nivel}|{campo}|{funcion}|{n}"


def claves_de(proyecto: Proyecto) -> list[str]:
    """Clave de cada fila de `proyecto`, en el orden en que se escriben."""
    cuenta: dict[tuple, int] = {}
    claves = []
    for nv in proyecto.niveles:
        for c in nv.campos:
            for s in c.senales:
                base = (nv.nombre, c.numero, s.funcion.value)
                claves.append(clave_fila(*base, cuenta.get(base, 0)))
                cuenta[base] = cuenta.get(base, 0) + 1
    return claves


def aplicar_ediciones(proyecto: Proyecto, ediciones: dict) -> int:
    """Pone en el proyecto lo que el usuario corrigió a mano. Devuelve cuántas celdas cambió."""
    if not ediciones:
        return 0
    cambiadas = 0
    senales = [s for nv in proyecto.niveles for c in nv.campos for s in c.senales]
    for clave, s in zip(claves_de(proyecto), senales):
        for col, valor in ediciones.get(clave, {}).items():
            attr = EDITABLES.get(col)
            if attr is None:
                continue
            if attr == "tipo_punto":
                valor = TipoPunto(valor) if valor in ("DI", "DO", "AI", "AO") else None
            elif attr == "offset":
                try:
                    valor = int(valor)
                except (TypeError, ValueError):
                    continue
            setattr(s, attr, valor)
            cambiadas += 1
    return cambiadas

# Números de medición que ciertos niveles no usan (ETAP: 04 en 132 kV, 12 en 6,6 kV). 33 kV: sin saltos (a confirmar).
SALTOS_MEDICION = {"3": (4,), "1": ()}
AMARILLO = PatternFill("solid", fgColor="FFFF00")


def prefijo_de(digito: str, campo: str) -> str:
    """Primer tramo del TAG SCADA: dígito de la tensión + número de campo ('2' + '04' = '204'). Un campo especial
    (TP1, RN1, SAA, SAC…) va solo, sin dígito de nivel (LINEAMIENTOS, pág. 2). Sin campo: '?' hasta que lo indiquen."""
    if not campo:
        return f"{digito}?"
    return campo if not campo.isdigit() else digito + campo


_EQUIPO = re.compile(r"\b\d{2,3}[A-Z]{0,2}/\d{2}\b|\b\d{3}S[A-Z]\d{2}\b|\b\d{5}\b")


def _raiz(texto: str) -> str:
    """Equipo al que se refiere un rótulo, para emparejar señal y comando: su código ('152/01', '25204', '229SB04') o,
    si no tiene, el texto sin la última palabra ('Interruptor 25204 Abierto' -> 'interruptor 25204')."""
    m = _EQUIPO.search(texto)
    return m.group(0).lower() if m else texto.rsplit(" ", 1)[0].strip().lower()


def _frase(texto: str, prefijos: list[str]) -> str:
    """Rótulo sin tildes, en minúscula y sin su palabra inicial ('Comando protección grupo A' -> 'proteccion grupo a')."""
    t = hmi.sin_acentos(texto).lower().strip()
    for pref in prefijos:
        q = hmi.sin_acentos(pref).lower()
        if t.startswith(q + " "):
            return t[len(q):].strip()
    return ""


def _senal_del_comando(campo: num.Campo, cmd, cfg: dict):
    """Entrada que señaliza a un comando sin equipo: 'Comando protección grupo A' <-> 'Señalización protección grupo A'."""
    reglas = cfg.get("comando_con_senalizacion")
    if not reglas:
        return None
    frase = _frase(cmd.texto, reglas["prefijos_comando"])
    if not frase:
        return None
    return next((x for x in campo.senales if not x.reserva and not x.comando and not x.doble
                 and _frase(x.texto, reglas["prefijos_senal"]) == frase), None)


def campos_desde_pdf(ruta, perfil, inicios: dict[str, int] | None = None, inicio_por_defecto: int = 10, avance=None, info=None):
    """Devuelve (campos, avisos). Nivel, campo y descripción salen del cajetín de cada hoja del PDF; las hojas de un
    mismo campo se suman. `inicios`: {prefijo: variable inicial}."""
    cfg = pdf_plano.cargar_config(perfil)
    paginas = pdf_plano.leer_plano(ruta, perfil, avance=avance, info=info)
    campos: dict[str, num.Campo] = {}
    avisos: list[str] = []
    comandos: dict[str, list] = {}               # comandos de cada campo, de todas sus hojas (salidas aparte de las entradas)
    for p in paginas:
        digito = pdf_plano.codigo_nivel(p.nivel, cfg)
        pref = prefijo_de(digito, p.campo)
        senales: list[num.Senal] = []
        for s in p.senales:
            if s.funcion == Funcion.COMANDO:
                if s.columnas:
                    comandos.setdefault(pref, []).append(s)     # el comando se empareja con su señal más abajo
                continue
            if s.es_reserva:
                senales.append(num.Senal(num.ALARMAS, s.texto, reserva=True, origen=s))
                continue
            f = num.ALARMAS if s.funcion == Funcion.ALARMAS else num.SENALIZACION
            senales.append(num.Senal(f, s.texto, doble=len(s.columnas) == 2, pares=tuple(s.columnas), origen=s))
        if pref in campos:                     # otra hoja del mismo campo
            campos[pref].senales += senales
            campos[pref].paginas.append(p.pagina)
            campos[pref].inferidos += [x for x in p.inferidos if x not in campos[pref].inferidos]
            campos[pref].mediciones = campos[pref].mediciones or (num.MEDICIONES_ETAP if p.mediciones else ())
            continue
        base = (p.descripcion or "").strip()
        desc = base if "campo" in base.lower() else f"{base} Campo {pref}".strip()
        campos[pref] = num.Campo(
            pref, (inicios or {}).get(pref, inicio_por_defecto), senales,
            mediciones=num.MEDICIONES_ETAP if p.mediciones else (), saltar_medicion=SALTOS_MEDICION.get(digito, ()),
            nivel=p.nivel, nivel_pdf=p.nivel, clave=pref, paginas=[p.pagina], inferidos=list(p.inferidos),
            numero_pdf=p.campo,
            archivos=[Path(ruta).name], descripcion_base=base, numero=p.campo, descripcion=desc, controlador=pdf_plano.controlador_por_defecto(p.nivel, cfg))
        if p.inferidos:
            avisos.append(f"Campo {pref}: {', '.join(p.inferidos)} no figuran en el cajetín; los deduje de la hoja.")
    # Cada comando va con la señal Abierto/Cerrado de su mismo equipo (aunque esté en otra hoja del campo: las
    # entradas y las salidas suelen estar en hojas distintas) y comparte con ella tag y offset. El que no tiene señal
    # (ej. habilitar/deshabilitar) lleva un tag propio terminado en C: es una señal del campo con su comando.
    for pref, cmds in comandos.items():
        campo = campos[pref]
        for cmd in cmds:
            señal = next((x for x in campo.senales if x.funcion == num.SENALIZACION and x.doble and not x.comando
                          and x.pares[0].lower().endswith("abierto") and _raiz(x.pares[0]) == _raiz(cmd.columnas[0])), None)
            if not señal:
                señal = _senal_del_comando(campo, cmd, cfg)
                if señal:                                  # la entrada deja de ser una alarma suelta: señaliza al comando
                    señal.funcion = num.SENALIZACION
            if señal:
                señal.comando, señal.origen_comando = True, cmd
            else:
                campo.senales.append(num.Senal(num.SENALIZACION, cmd.texto, doble=len(cmd.columnas) == 2, comando=True,
                                               pares=tuple(cmd.columnas), origen=cmd, origen_comando=cmd))
                avisos.append(f"Campo {pref}: el comando «{cmd.texto}» no tiene señal Abierto/Cerrado; se le dio tag propio.")
    return list(campos.values()), avisos


def a_proyecto(filas, campos, datos, perfil=None):
    """Filas numeradas -> (Proyecto para el escritor de Excel, «sin resolver» por fila, «es fila libre» por fila).

    Por campo: ALARMAS, SEÑALIZACION, COMANDO y MEDICION; las reservas, todas juntas en un bloque al final.
    `datos` (libro.Datos): prefijo de descripción, controlador y relé por campo, estados y rangos elegidos."""
    perfil = perfil or perfiles.cargar_perfil("EPEN")
    cfg = pdf_plano.cargar_config(perfil)
    meta = {c.prefijo: c for c in campos}
    clave = {c.prefijo: c.clave for c in campos}              # los datos del usuario van por clave fija
    funcion = {num.ALARMAS: Funcion.ALARMAS, num.SENALIZACION: Funcion.SENALIZACION,
               num.COMANDO: Funcion.COMANDO, num.MEDICION: Funcion.MEDICION}
    niveles: dict[str, Nivel] = {}
    por_campo: dict[str, Campo] = {}
    sin_resolver: dict[str, list[tuple[bool, bool]]] = {}
    indice: dict[str, int] = {}
    con_varios_niveles = len({c.nivel for c in campos}) > 1

    def pref_desc(f):
        return datos.prefijo_desc.get(clave[f.campo]) or f.campo

    def pref_desc_de(c):
        return datos.prefijo_desc.get(c.clave) or c.prefijo

    def controlador(f, s):
        ctl = datos.controlador.get(clave[f.campo]) or meta[f.campo].controlador
        ori = s.origen if s else None
        return pdf_plano._controlador(ori, ctl, datos.rele.get(clave[f.campo], ""), cfg) if ori is not None else ctl

    def placa_de(ls, clave_campo):
        """Placa del módulo: la que eligió el usuario (si el plano no la trae) o la del plano."""
        if ls is None or not getattr(ls, "tipo", ""):
            return ""
        return datos.placas.get(f"{clave_campo}|{ls.pagina}|{ls.modulo}|{ls.tipo}") or ls.placa

    def entrada_de(ls, estado=0, par=False):
        """Entrada (DI/AI) o salida (DO) del módulo. `estado` = 0/1 en una señal doble (cada fila, su propio borne);
        `par` = comando de dos salidas ('1/2')."""
        e = getattr(ls, "entradas", None)
        if not e:
            return ""
        if par:
            return "/".join(str(x) for x in e)
        return str(e[min(estado, len(e) - 1)])      # una sola entrada para dos estados ('en local'/'en remoto'): la misma

    modo = getattr(datos, "estilo", "") or estilo.ETAP
    usre = modo == estilo.USRE
    cfg_tag = {**cfg, "abreviaturas_tag": {}} if usre else cfg           # USRE: el TAG HMI no se abrevia

    def tag_de(texto):
        t = estilo.sin_barra(texto)
        return hmi.tag_hmi_desde(estilo.titulo(t) if usre else t, cfg_tag)

    def desc_de(pref, texto):
        t = estilo.sin_barra(texto)
        return estilo.titulo(hmi.completar(t, cfg)) if usre else hmi.desc_hmi_desde(pref, t, cfg)

    def campo_modelo(f):
        if f.campo not in por_campo:
            c = meta[f.campo]
            nv = niveles.setdefault(c.nivel, Nivel(nombre=c.nivel, codigo=pdf_plano.codigo_nivel(c.nivel, cfg)))
            por_campo[f.campo] = Campo(numero=c.numero, descripcion=c.descripcion, prefijo=pref_desc(f))
            nv.campos.append(por_campo[f.campo])
        return por_campo[f.campo]

    for orden in (num.ALARMAS, num.SENALIZACION, num.COMANDO, num.MEDICION):
        for f in filas:
            if f.funcion != orden or (f.senal and f.senal.reserva):
                continue
            pref = pref_desc(f)
            valores = [None] * 5
            tag_hmi = desc_hmi = ctl = ""
            tipo_u = placa_u = entrada_u = obs_u = ""
            if f.hueco:
                desc, ok = "", True
            elif f.extra:
                desc, ok = "", True                              # 2.ª fila de una señal doble: sin descripción SCADA
                valores[4] = est.NA
                ctl = controlador(f, f.senal)
                if orden == num.SENALIZACION and len(f.senal.pares) == 2 and not usre:   # …pero su propio TAG y DESC. HMI (2.º estado)
                    tag_hmi = tag_de(f.senal.pares[1])
                    desc_hmi = desc_de(pref, f.senal.pares[1])
                if f.senal.origen is not None and f.senal.origen.tipo and f.senal.origen is not f.senal.origen_comando:
                    tipo_u = f.senal.origen.tipo
                    placa_u = placa_de(f.senal.origen, clave[f.campo])
                    entrada_u = entrada_de(f.senal.origen, 1)
                    obs_u = f.senal.pares[1] if len(f.senal.pares) == 2 else ""
            elif orden == num.MEDICION:
                i = indice.setdefault(f.campo, 0)
                indice[f.campo] += 1
                desc, ok = descripcion.descripcion_medicion(pref, i)
                valores = est.rango(i, datos.rangos)
                c = meta[f.campo]
                m = pdf_plano.filas_mediciones(c.nivel, c.numero, pref, cfg)
                if i < len(m):
                    tag_hmi, desc_hmi, ctl = m[i].tag_hmi, m[i].desc_hmi, m[i].controlador
                    if usre:
                        ctl = f"SATEC - PM335_{pdf_plano.tension_texto(c.nivel)}"
                    obs_u = cfg["mediciones"]["juego"][i].format(campo=c.numero, tension=pdf_plano.tension_texto(c.nivel)).strip()
                tipo_u, placa_u, entrada_u = "AI", "N/A", "N/A"     # multimedidor: no entra por un módulo de la UTR
            else:
                desc, ok = descripcion.descripcion_scada(pref, f.senal.texto)
                cmd_pares = (tuple(f.senal.origen_comando.columnas)
                             if orden == num.COMANDO and f.senal.origen_comando is not None else None)
                valores = est.estados(f.senal, datos.estados, modo, cmd_pares)
                ctl = controlador(f, f.senal)
                texto = (f.senal.origen_comando.texto if orden == num.COMANDO and f.senal.origen_comando
                         else (estilo.texto_doble(*f.senal.pares) if usre else f.senal.pares[0])
                         if orden == num.SENALIZACION and len(f.senal.pares) == 2                     # 1.er estado (ETAP)
                         else f.senal.texto)
                if orden == num.SENALIZACION and f.senal.origen_comando is f.senal.origen:   # comando sin señal propia
                    texto = f"Estado {texto}"
                # columnas de la UTR: salen del módulo de entradas/salidas del plano
                if orden == num.COMANDO:
                    cmd = f.senal.origen_comando
                    if cmd is not None and cmd.tipo:
                        tipo_u, placa_u = cmd.tipo, placa_de(cmd, clave[f.campo])
                        entrada_u = entrada_de(cmd, par=len(cmd.entradas) == 2)
                    obs_u = cmd.texto if cmd is not None else f.senal.texto
                elif f.senal.origen is not None and f.senal.origen is not f.senal.origen_comando:
                    ori = f.senal.origen
                    if ori.tipo:
                        tipo_u, placa_u, entrada_u = ori.tipo, placa_de(ori, clave[f.campo]), entrada_de(ori, 0)
                    obs_u = f.senal.pares[0] if f.senal.pares else f.senal.texto
                tag_hmi = tag_de(texto)
                desc_hmi = desc_de(pref, texto)
            s = Senal(funcion=funcion[orden], controlador=ctl, tag_hmi=tag_hmi, desc_hmi=desc_hmi, tag_scada=f.tag,
                      offset=f.offset, desc_scada=desc, segunda_fila=f.extra,
                      s0=valores[0], s1=valores[1], s2=valores[2], s3=valores[3], unidad=valores[4],
                      tipo_punto=TipoPunto(tipo_u) if tipo_u in ("DI", "DO", "AI", "AO") else None,
                      placa=placa_u, entrada=entrada_u, observaciones=obs_u)
            campo_modelo(f).senales.append(s)
            sin_resolver.setdefault(f.campo, []).append((not ok, f.hueco))

    # Reservas: todas juntas al final de la hoja, separadas por nivel y campo (el nivel y la descripción del campo
    # figuran en su primera fila).
    reservas_por: dict[str, list] = {}
    for f in filas:
        if f.senal and f.senal.reserva:
            c = meta[f.campo]
            lugar = f"{c.nivel} " if con_varios_niveles and c.nivel else ""
            ori = f.senal.origen
            tiene = ori is not None and ori.tipo
            reservas_por.setdefault(f.campo, []).append(Senal(
                funcion=Funcion.RESERVA, controlador=controlador(f, f.senal), tag_hmi="N/A",
                desc_hmi=f"RESERVA {lugar}Campo {c.numero}", tag_scada="N/A", offset=f.offset,
                desc_scada="RESERVA", es_reserva=True,
                s0=est.NA, s1=est.NA, s2=est.NA, s3=est.NA, unidad=est.NA,
                tipo_punto=TipoPunto(ori.tipo) if tiene and ori.tipo in ("DI", "DO", "AI", "AO") else None,
                placa=placa_de(ori, clave[f.campo]) if tiene else "", entrada=entrada_de(ori, 0) if tiene else "",
                observaciones="RESERVA"))
    niveles_res: dict[str, Nivel] = {}
    for c in campos:
        if c.prefijo in reservas_por:
            nv = niveles_res.setdefault(c.nivel, Nivel(nombre=c.nivel, codigo=pdf_plano.codigo_nivel(c.nivel, cfg)))
            nv.campos.append(Campo(numero=c.numero, descripcion=c.descripcion, prefijo=pref_desc_de(c),
                                   senales=reservas_por[c.prefijo]))
    marcas_res = [(False, False) for nv in niveles_res.values() for c in nv.campos for _ in c.senales]

    _tags_hmi_unicos(niveles)

    # mismo orden que escribe el Excel: nivel > campo > filas
    marcas = [m for nv in niveles.values() for c in nv.campos for m in sin_resolver[next(
        k for k, v in por_campo.items() if v is c)]]
    lista = list(niveles.values()) + list(niveles_res.values())
    marcas += marcas_res
    proyecto = Proyecto("EPEN", niveles=lista, item_inicial=datos.item_inicial)
    aplicar_ediciones(proyecto, getattr(datos, "ediciones", {}))
    return proyecto, [m[0] for m in marcas], [m[1] for m in marcas]


def _tags_hmi_unicos(niveles: dict) -> None:
    """Un TAG HMI no puede repetirse en el listado. Si un rótulo no nombra el equipo ('Comando protección grupo A' está en
    cada campo), se le antepone el campo ('Campo_01_Comando_Prot_grupo_A'); si aún así se repite, se numera."""
    usados = Counter(s.tag_hmi for nv in niveles.values() for c in nv.campos for s in c.senales
                     if s.tag_hmi and s.tag_hmi != "N/A")
    for nv in niveles.values():
        for c in nv.campos:
            for s in c.senales:
                if usados[s.tag_hmi] > 1 and s.tag_hmi and s.tag_hmi != "N/A":
                    s.tag_hmi = f"Campo_{c.numero}_{s.tag_hmi}"
    vistos: Counter = Counter()
    for nv in niveles.values():
        for c in nv.campos:
            for s in c.senales:
                if s.tag_hmi and s.tag_hmi != "N/A":
                    vistos[s.tag_hmi] += 1
                    if vistos[s.tag_hmi] > 1:
                        s.tag_hmi = f"{s.tag_hmi}_{vistos[s.tag_hmi]}"


def marcas_vigentes(proyecto: Proyecto, marcas: list[bool], ediciones: dict) -> list[bool]:
    """Una descripción SCADA que el usuario corrigió a mano deja de ser «a revisar»."""
    if not ediciones:
        return marcas
    corregidas = {k for k, e in ediciones.items() if "desc" in e}
    return [m and k not in corregidas for m, k in zip(marcas, claves_de(proyecto))]


def escribir(filas, campos, datos, ruta, perfil, caratula=None) -> int:
    """Hoja del listado con el formato de EPEN, columnas A a W (con la carátula delante si se pasa una). Devuelve
    cuántas descripciones quedaron en amarillo (no entraron en 20 caracteres con las abreviaturas)."""
    proyecto, marcas, huecos = a_proyecto(filas, campos, datos, perfil)
    marcas = marcas_vigentes(proyecto, marcas, getattr(datos, "ediciones", {}))
    if caratula is not None:
        proyecto.caratula = caratula
    excel_writer.escribir_xlsx(proyecto, perfil, ruta, incluir_caratula=caratula is not None,
                               hasta_columna="W" if MOSTRAR_UTR else "O")
    primera = perfil.datos["hojas"]["primera_fila_datos"]
    wb = openpyxl.load_workbook(ruta)
    ws = wb[perfil.datos["hojas"]["listado"]]
    item = datos.item_inicial
    for i, (m, hueco) in enumerate(zip(marcas, huecos)):
        fila = primera + i
        if hueco:
            ws.cell(fila, 1).value = None          # las filas libres (futuras ampliaciones) no llevan ITEM
        else:
            ws.cell(fila, 1).value = item
            item += 1
        if m:
            ws.cell(fila, 10).fill = AMARILLO
    wb.save(ruta)
    return sum(marcas)


def main(argv):
    if not argv:
        sys.exit(__doc__)
    import libro
    ruta = Path(argv[0])
    salida = Path(argv[1]) if len(argv) > 1 else Path(__file__).parent / (ruta.stem + "_scada.xlsx")
    L = libro.Libro()
    L.agregar_pdf(ruta)
    L.calcular()
    n = L.exportar(salida)
    print(*L.avisos, sep="\n")
    print(f"Listo: {salida}\nDescripciones en amarillo (a revisar): {n}")


if __name__ == "__main__":
    main(sys.argv[1:])
