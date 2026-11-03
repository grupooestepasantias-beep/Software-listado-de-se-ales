"""Gestión de archivos: versiones, registro de operaciones, proyectos y validación de entradas.

Reglas:
- Nunca se pisa un documento existente: se archiva en <carpeta>/versiones/ con fecha y hora.
- Los documentos de origen (planos, protocolos de referencia) solo se leen.
- Los archivos se escriben primero con nombre temporal y se renombran al terminar (sin archivos a medias).
- Cada operación importante queda en <carpeta>/registro_operaciones.jsonl.
"""
import datetime
import getpass
import hashlib
import json
import os
import re
import shutil
import sys

VERSION_PROYECTO = 1
CARPETA_VERSIONES = "versiones"
REGISTRO = "registro_operaciones.jsonl"
CARACTERES_PROHIBIDOS = r'\/:*?"<>|'


def carpeta_programa_usuario():
    """Carpeta junto al .exe (o al .py) donde se guardan config.json y los proyectos."""
    return os.path.dirname(sys.executable if getattr(sys, "frozen", False) else os.path.abspath(__file__))


def carpeta_proyectos():
    ruta = os.path.join(carpeta_programa_usuario(), "proyectos")
    os.makedirs(ruta, exist_ok=True)
    return ruta


def usuario():
    try:
        return getpass.getuser()
    except Exception:
        return "desconocido"


def sha256(ruta):
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(1 << 20), b""):
            h.update(bloque)
    return h.hexdigest()


def ahora():
    return datetime.datetime.now().strftime("%Y%m%d-%H%M%S")


# ------------------------------------------------------------------ versiones
def archivar_existente(ruta):
    """Si `ruta` existe la mueve a versiones/ con fecha y hora. Devuelve la nueva ruta o None."""
    if not os.path.exists(ruta):
        return None
    carpeta, nombre = os.path.split(ruta)
    base, ext = os.path.splitext(nombre)
    destino_dir = os.path.join(carpeta, CARPETA_VERSIONES)
    os.makedirs(destino_dir, exist_ok=True)
    destino = os.path.join(destino_dir, f"{base}__{ahora()}{ext}")
    n = 1
    while os.path.exists(destino):  # dos versiones en el mismo segundo
        n += 1
        destino = os.path.join(destino_dir, f"{base}__{ahora()}_{n}{ext}")
    shutil.move(ruta, destino)
    return destino


def guardar_docx_seguro(doc, ruta):
    """Guarda `doc` en `ruta`: archiva la versión anterior y escribe de forma atómica."""
    carpeta = os.path.dirname(ruta)
    os.makedirs(carpeta, exist_ok=True)
    temporal = os.path.join(carpeta, f"~tmp_{os.getpid()}_{os.path.basename(ruta)}")
    try:
        doc.save(temporal)
        archivada = archivar_existente(ruta)
        os.replace(temporal, ruta)
    finally:
        if os.path.exists(temporal):
            os.remove(temporal)
    return archivada


def listar_versiones(ruta):
    """Versiones archivadas de un documento, de la más nueva a la más vieja: [(ruta, fecha_legible)]."""
    carpeta, nombre = os.path.split(ruta)
    base, ext = os.path.splitext(nombre)
    directorio = os.path.join(carpeta, CARPETA_VERSIONES)
    if not os.path.isdir(directorio):
        return []
    patron = re.compile(re.escape(base) + r"__(\d{8}-\d{6})(?:_\d+)?" + re.escape(ext) + r"$")
    salida = []
    for f in os.listdir(directorio):
        m = patron.match(f)
        if m:
            fecha = datetime.datetime.strptime(m.group(1), "%Y%m%d-%H%M%S").strftime("%d/%m/%Y %H:%M:%S")
            salida.append((os.path.join(directorio, f), fecha))
    return sorted(salida, key=lambda x: x[0], reverse=True)


def restaurar_version(ruta_version, ruta_actual):
    """Vuelve a una versión anterior. La versión actual no se pierde: se archiva antes."""
    archivada = archivar_existente(ruta_actual)
    shutil.copy2(ruta_version, ruta_actual)
    return archivada


# ------------------------------------------------------------------ registro
def registrar(carpeta, accion, **datos):
    """Agrega una línea JSON al registro de operaciones de la carpeta. Nunca interrumpe el trabajo."""
    linea = {"fecha": datetime.datetime.now().isoformat(timespec="seconds"), "usuario": usuario(), "accion": accion}
    linea.update(datos)
    try:
        os.makedirs(carpeta, exist_ok=True)
        with open(os.path.join(carpeta, REGISTRO), "a", encoding="utf-8") as f:
            f.write(json.dumps(linea, ensure_ascii=False) + "\n")
    except OSError:
        pass


def leer_registro(carpeta):
    ruta = os.path.join(carpeta, REGISTRO)
    if not os.path.exists(ruta):
        return []
    salida = []
    with open(ruta, encoding="utf-8") as f:
        for linea in f:
            try:
                salida.append(json.loads(linea))
            except ValueError:
                continue
    return salida


# ------------------------------------------------------------------ proyectos
def nombre_archivo_seguro(texto, por_defecto="sin_nombre"):
    limpio = re.sub("[" + re.escape(CARACTERES_PROHIBIDOS) + r"\x00-\x1f]", "-", texto).strip(" .")
    return limpio[:80] or por_defecto


def escribir_json_atomico(ruta, contenido):
    os.makedirs(os.path.dirname(ruta), exist_ok=True)
    temporal = ruta + ".tmp"
    with open(temporal, "w", encoding="utf-8") as f:
        json.dump(contenido, f, ensure_ascii=False, indent=2)
    os.replace(temporal, ruta)


def guardar_proyecto(ruta, estado):
    """estado: dict con datos, documentos, componentes, termicas, senales, comandos, opciones."""
    contenido = {"version": VERSION_PROYECTO, "guardado": datetime.datetime.now().isoformat(timespec="seconds"),
                 "usuario": usuario()}
    contenido.update(estado)
    if os.path.exists(ruta):
        archivar_existente(ruta)  # el proyecto anterior también queda recuperable
    escribir_json_atomico(ruta, contenido)


def cargar_proyecto(ruta):
    with open(ruta, encoding="utf-8") as f:
        contenido = json.load(f)
    if not isinstance(contenido, dict) or "datos" not in contenido:
        raise ValueError("El archivo no es un proyecto del generador de protocolos.")
    if contenido.get("version", 1) > VERSION_PROYECTO:
        raise ValueError("El proyecto fue creado con una versión más nueva del programa.")
    return contenido


def listar_proyectos():
    ruta = carpeta_proyectos()
    return sorted(f for f in os.listdir(ruta) if f.lower().endswith(".json"))


# ------------------------------------------------------------------ validación de entradas
REQUERIDOS = [("CLIENTE", "Cliente"), ("NRO_OBRA", "Nº de obra"), ("OBRA", "Proyecto/Obra"),
              ("UBICACION", "Ubicación"), ("TIPO_TABLERO", "Tipo de tablero"), ("NOMBRE", "Nombre / estación"),
              ("REVISION", "Revisión")]
LARGO_MAXIMO = {"CLIENTE": 40, "NRO_OBRA": 12, "OBRA": 90, "UBICACION": 80, "TIPO_TABLERO": 60, "NOMBRE": 60,
                "REVISION": 3}


def fecha_de(datos, tipo):
    """Fecha del documento: FECHA_FAT / FECHA_SAT (cada ensayo tiene la suya); FECHA sirve de respaldo."""
    familia = "SAT" if str(tipo).startswith("SAT") else "FAT"
    return str(datos.get(f"FECHA_{familia}") or datos.get("FECHA") or "").strip()


def validar_entradas(datos, incluir=None):
    """Devuelve [(campo, mensaje)] con los problemas de los datos cargados. Lista vacía = correcto.

    `incluir` (claves de documentos) define qué fechas se exigen; sin él se exigen las dos.
    """
    errores = []
    familias = {"SAT" if str(k).startswith("SAT") else "FAT" for k in incluir} if incluir else {"FAT", "SAT"}
    for clave, etiqueta in REQUERIDOS:
        valor = str(datos.get(clave, "")).strip()
        if not valor:
            errores.append((clave, f"{etiqueta}: es obligatorio."))
            continue
        if re.search(r"[\x00-\x1f{}]", valor):
            errores.append((clave, f"{etiqueta}: contiene caracteres no permitidos (llaves o de control)."))
        if len(valor) > LARGO_MAXIMO.get(clave, 200):
            errores.append((clave, f"{etiqueta}: demasiado largo (máximo {LARGO_MAXIMO[clave]} caracteres)."))
    for familia in sorted(familias):
        clave = f"FECHA_{familia}" if f"FECHA_{familia}" in datos else "FECHA"
        etiqueta = f"Fecha {familia}"
        fecha = fecha_de(datos, familia)
        if not fecha:
            errores.append((clave, f"{etiqueta}: es obligatoria."))
            continue
        try:
            datetime.datetime.strptime(fecha, "%d/%m/%Y")
        except ValueError:
            errores.append((clave, f"{etiqueta}: usar el formato dd/mm/aaaa (por ejemplo 02/11/2026)."))
    revision = str(datos.get("REVISION", "")).strip()
    if revision and not re.fullmatch(r"[A-Za-z0-9]{1,3}", revision):
        errores.append(("REVISION", "Revisión: solo letras o números (por ejemplo A, B, C2)."))
    nombre = str(datos.get("NOMBRE", ""))
    if any(c in nombre for c in CARACTERES_PROHIBIDOS):
        errores.append(("NOMBRE", "Nombre / estación: no puede contener " + " ".join(CARACTERES_PROHIBIDOS)
                        + " (forma parte del nombre del archivo)."))
    return errores


def validar_pdf(ruta):
    """Un PDF subido para leer señales/térmicas: existe, es .pdf, tiene cabecera PDF y un tamaño razonable."""
    if not os.path.isfile(ruta):
        return "El archivo no existe."
    if not ruta.lower().endswith(".pdf"):
        return "El archivo no es un PDF."
    tamano = os.path.getsize(ruta)
    if tamano == 0:
        return "El archivo está vacío."
    if tamano > 300 * 1024 * 1024:
        return "El archivo es demasiado grande (más de 300 MB)."
    with open(ruta, "rb") as f:
        if not f.read(1024).lstrip().startswith(b"%PDF"):
            return "El archivo no tiene formato PDF válido."
    return ""
