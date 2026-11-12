"""Estado del listado SCADA: PDFs cargados, datos que se preguntan y filas numeradas. Sin interfaz (la usa app_scada.py)."""
from __future__ import annotations

import json
import re
import tempfile
from dataclasses import asdict, dataclass, field
from pathlib import Path

import desde_pdf
import estilo
import numeracion as num
import pdf_plano
import perfiles


def _clave(texto: str) -> str:
    return " ".join(texto.lower().split())


def clave_modulo(clave_campo: str, ls) -> str:
    """Identifica un módulo de E/S: campo, hoja del PDF, posición en la hoja y tipo (DI/DO/AI)."""
    return f"{clave_campo}|{ls.pagina}|{ls.modulo}|{ls.tipo}"


@dataclass
class Datos:
    """Lo que la app le pregunta al usuario. Los diccionarios van por campo, con la clave fija del campo (`Campo.clave`)."""
    variable_inicial: dict[str, int] = field(default_factory=dict)
    numero: dict[str, str] = field(default_factory=dict)             # campo si se corrige (ej. "04", "TP1")
    nivel: dict[str, str] = field(default_factory=dict)              # tensión del campo si se cambia (ej. "33KV")
    prefijo_desc: dict[str, str] = field(default_factory=dict)       # prefijo de descripciones (ej. "204LC")
    controlador: dict[str, str] = field(default_factory=dict)        # vacío = el del nivel (SEL-2241-33kV)
    rele: dict[str, str] = field(default_factory=dict)               # relé de las señales de protección
    placas: dict[str, str] = field(default_factory=dict)             # placa por módulo si el plano no la trae
    item_inicial: int = 1
    offset_digital: int = 200
    offset_medicion: int = 200
    estados: dict[str, list[str]] = field(default_factory=dict)      # por tipo de señal; vacío = default
    rangos: dict[int, dict] = field(default_factory=dict)            # por medición; vacío = default
    ediciones: dict[str, dict] = field(default_factory=dict)         # celdas corregidas a mano: {clave de fila: {columna: valor}}
    estilo: str = ""                                                 # ETAP o USRE (vacío = se detecta por el nombre del PDF)
    mediciones: dict[str, bool] = field(default_factory=dict)        # por campo: ¿lleva las 13 mediciones?
    descripcion: dict[str, str] = field(default_factory=dict)        # por campo: texto de DESCRIP si se corrige (ej. "Entrada TR01")


class Libro:
    def __init__(self, perfil=None):
        self.perfil = perfil or perfiles.cargar_perfil("EPEN")
        self.cfg = pdf_plano.cargar_config(self.perfil)
        self.rutas: list[str] = []           # PDFs cargados (para guardar el proyecto y volver a abrirlo)
        self.campos: list[num.Campo] = []
        self.hechos: list[str] = []          # claves de los campos ya numerados
        self.filas: list[num.Fila] = []
        self.datos = Datos()
        self.avisos: list[str] = []
        self.ultimo_info: dict = {}      # estadísticas de la última lectura (para explicar un PDF sin señales)

    # ------------------------------------------------------------ carga
    @staticmethod
    def copia_local(ruta, avance_copia=None) -> Path:
        """Copia el PDF a una carpeta local (leerlo directo del servidor es lento y a veces se corta). Si ya se copió y
        no cambió (mismo nombre, tamaño y fecha), reutiliza la copia: volver a cargarlo es instantáneo."""
        origen = Path(ruta)
        st = origen.stat()
        carpeta = Path(tempfile.gettempdir()) / "listado_scada_cache"
        carpeta.mkdir(exist_ok=True)
        destino = carpeta / f"{int(st.st_mtime)}_{st.st_size}_{origen.name}"
        if destino.exists() and destino.stat().st_size == st.st_size:
            return destino
        parcial = destino.with_suffix(".parcial")
        hecho = 0
        with open(origen, "rb") as fin, open(parcial, "wb") as fout:
            while bloque := fin.read(1 << 20):
                fout.write(bloque)
                hecho += len(bloque)
                if avance_copia:
                    avance_copia(hecho, st.st_size)
        parcial.replace(destino)
        return destino

    def agregar_pdf(self, ruta, avance=None, avance_copia=None) -> tuple[list[str], list[str]]:
        """Suma los campos del PDF. Devuelve (campos nuevos, campos que ya estaban); de un campo repetido se suman
        solo las señales que no estaban. `avance_copia(bytes, total)` informa la copia desde el servidor y
        `avance(n, total)` por qué hoja va la lectura."""
        local = self.copia_local(ruta, avance_copia)
        self.ultimo_info = {}
        leidos, avisos = desde_pdf.campos_desde_pdf(local, self.perfil, avance=avance, info=self.ultimo_info)
        self.avisos += avisos
        if str(Path(ruta)) not in self.rutas:
            self.rutas.append(str(Path(ruta)))
        for c in leidos:                                  # el nombre del archivo es el original, no el de la copia
            c.archivos = [Path(ruta).name]
        por_clave = {c.clave: c for c in self.campos}
        nuevos, repetidos = [], []
        for c in leidos:
            previo = por_clave.get(c.clave)
            if previo is None:
                nuevos.append(c)
                por_clave[c.clave] = c
                continue
            repetidos.append(c)
            vistas = {(x.funcion, _clave(x.texto)) for x in previo.senales if not x.reserva}
            previo.senales += [x for x in c.senales if not x.reserva and (x.funcion, _clave(x.texto)) not in vistas]
            previo.mediciones = previo.mediciones or c.mediciones
            previo.paginas += c.paginas
            previo.archivos += [x for x in c.archivos if x not in previo.archivos]
        self.campos += nuevos
        for c in nuevos:
            self.datos.prefijo_desc.setdefault(c.clave, c.prefijo)
            self.datos.controlador.setdefault(c.clave, c.controlador)
            # variable inicial 10 (regla del usuario: el campo 1 empieza en 10), o menos si no entra en 00-99
            self.datos.variable_inicial.setdefault(c.clave, max(0, min(10, 100 - self.cantidad(c))))
            # un campo numerado (de control) lleva las mediciones del multimedidor aunque el plano no lo nombre
            self.datos.mediciones.setdefault(c.clave, bool(c.mediciones) or c.numero_pdf.isdigit())
        if not self.datos.estilo:
            self.datos.estilo = estilo.detectar(Path(r).name for r in self.rutas)
        return [c.clave for c in nuevos], [c.clave for c in repetidos]

    @staticmethod
    def cantidad(campo: num.Campo) -> int:
        """Señales que usan un número de variable (las reservas no)."""
        return sum(1 for x in campo.senales if not x.reserva)

    @staticmethod
    def equipos(campo: num.Campo) -> int:
        """Equipos distintos que se nombran en las señales del campo (interruptor, seccionadores, TV, TI, térmicas…)."""
        txt = " ".join(x.texto for x in campo.senales)
        return len(set(re.findall(r"\b\d{3}S[A-Z]\d{2}\b|\b\d{5}\b|\b\d?T[VI]\d{1,2}\b|\bQ[A-Z]\d\b", txt)))

    def modulos(self) -> list[dict]:
        """Módulos de entradas/salidas leídos (uno por campo, hoja y módulo), con la placa que trae el plano. Sirven para
        preguntar la placa de los que no la traen. Las señales que no vienen de un módulo (tiras de relé) no figuran."""
        vistos: dict[str, dict] = {}
        for c in self.campos:
            for s in c.senales:
                for ls in (s.origen, s.origen_comando):
                    if ls is None or not getattr(ls, "tipo", ""):
                        continue
                    clave = clave_modulo(c.clave, ls)
                    m = vistos.setdefault(clave, {"clave": clave, "campo": c.numero or c.clave, "hoja": ls.pagina,
                                                  "tipo": ls.tipo, "senales": 0, "placa_pdf": ls.placa})
                    m["senales"] += 1
        return sorted(vistos.values(), key=lambda m: (m["hoja"], m["tipo"], m["clave"]))

    def digito(self, nivel: str) -> str:
        return pdf_plano.codigo_nivel(nivel, self.cfg)

    def pendientes(self) -> list[str]:
        return [c.clave for c in self.campos if c.clave not in self.hechos]

    # ------------------------------------------------------------ cálculo
    def _aplicar_datos(self, campos) -> None:
        """Pasa a cada campo lo que el usuario eligió: tensión (que define el primer dígito del tag) y variable inicial."""
        for c in campos:
            c.nivel = self.datos.nivel.get(c.clave) or c.nivel_pdf
            d = self.digito(c.nivel)
            c.numero = self.datos.numero.get(c.clave) or c.numero_pdf
            c.prefijo = desde_pdf.prefijo_de(d, c.numero)
            c.saltar_medicion = desde_pdf.SALTOS_MEDICION.get(d, ())
            c.controlador = pdf_plano.controlador_por_defecto(c.nivel, self.cfg)
            base = self.datos.descripcion.get(c.clave) or c.descripcion_base
            c.descripcion = f"{base} Campo {c.prefijo}".strip() if "campo" not in base.lower() else base
            c.variable_inicial = self.datos.variable_inicial.get(c.clave, 1)
            c.mediciones = num.MEDICIONES_ETAP if self.datos.mediciones.get(c.clave, bool(c.mediciones)) else ()
            for s in c.senales:        # «en local» con una sola entrada: en el estilo USRE es una fila, en el ETAP son dos
                una = (s.origen is not None and len(getattr(s.origen, "entradas", ()) or ()) == 1 and len(s.pares) == 2)
                if una:
                    s.doble = self.datos.estilo != estilo.USRE
                    s.dos_estados = not s.doble

    def calcular(self, agregar: bool = False) -> None:
        """agregar=False: numera todo de nuevo. agregar=True: deja lo hecho y numera solo los campos nuevos a continuación."""
        if agregar and self.filas:
            nuevos = [c for c in self.campos if c.clave not in self.hechos]
            self._aplicar_datos(nuevos)
            digital = [f.offset for f in self.filas if f.funcion != num.MEDICION]
            analog = [f.offset for f in self.filas if f.funcion == num.MEDICION]
            inicio_di = max(digital) + 1 if digital else self.datos.offset_digital
            inicio_ai = max(analog) + 1 + num.HUECO if analog else self.datos.offset_medicion
            self.filas += num.numerar(nuevos, inicio_di, inicio_ai)
        else:
            self._aplicar_datos(self.campos)
            self.filas = num.numerar(self.campos, self.datos.offset_digital, self.datos.offset_medicion)
        self.hechos = [c.clave for c in self.campos]

    # ------------------------------------------------------------ salida
    def proyecto(self):
        """(Proyecto, marcas amarillas, filas libres) para escribir el Excel o mostrar la tabla."""
        return desde_pdf.a_proyecto(self.filas, self.campos, self.datos, self.perfil)

    def marcas(self, proyecto, marcas) -> list[bool]:
        """Marcas amarillas vigentes (lo corregido a mano ya no está «a revisar»)."""
        return desde_pdf.marcas_vigentes(proyecto, marcas, self.datos.ediciones)

    def exportar(self, ruta, caratula=None) -> int:
        """Escribe el Excel. Con `caratula` (modelo.Caratula) la hoja de carátula va delante del listado."""
        return desde_pdf.escribir(self.filas, self.campos, self.datos, ruta, self.perfil, caratula)

    # ------------------------------------------------------------ ediciones a mano
    def editar(self, clave: str, columna: str, valor: str) -> None:
        """Guarda una celda corregida a mano; sobrevive a recalcular (va por la clave de la fila)."""
        self.datos.ediciones.setdefault(clave, {})[columna] = valor

    def deshacer_edicion(self, clave: str, columna: str) -> None:
        e = self.datos.ediciones.get(clave, {})
        e.pop(columna, None)
        if not e:
            self.datos.ediciones.pop(clave, None)

    # ------------------------------------------------------------ proyecto (.json)
    def guardar(self, ruta, caratula=None) -> None:
        """Guarda lo necesario para seguir otro día: los PDFs, los datos que se preguntaron, las celdas corregidas y la
        carátula. Los campos y las filas no se guardan: se vuelven a leer de los PDFs al abrir."""
        datos = asdict(self.datos)
        datos["rangos"] = {str(k): v for k, v in datos["rangos"].items()}
        Path(ruta).write_text(json.dumps({
            "version": 1, "pdfs": self.rutas, "datos": datos, "calculado": bool(self.filas),
            "caratula": asdict(caratula) if caratula is not None else None,
        }, ensure_ascii=False, indent=2), encoding="utf-8")

    def abrir(self, ruta, avance=None, avance_copia=None) -> tuple[dict | None, list[str]]:
        """Carga un proyecto guardado: vuelve a leer sus PDFs y restituye los datos. Devuelve (carátula como dict o None,
        PDFs que ya no están en su lugar)."""
        d = json.loads(Path(ruta).read_text(encoding="utf-8"))
        self.vaciar()
        faltan = []
        for p in d.get("pdfs", []):
            if Path(p).is_file():
                self.agregar_pdf(p, avance=avance, avance_copia=avance_copia)
            else:
                faltan.append(p)
        guardados = d.get("datos", {})
        guardados["rangos"] = {int(k): v for k, v in guardados.get("rangos", {}).items()}
        validos = {k: v for k, v in guardados.items() if k in Datos.__dataclass_fields__}
        self.datos = Datos(**validos)
        if d.get("calculado") and self.campos:
            self.calcular()
        return d.get("caratula"), faltan

    def vaciar(self) -> None:
        self.__init__(self.perfil)
