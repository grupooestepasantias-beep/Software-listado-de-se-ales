# CONTEXTO PARA CLAUDE (leer entero antes de tocar nada)

Este archivo resume el proyecto para la cuenta de Claude que trabaja desde la otra PC. Hay **2 cuentas de Claude (PC-A y PC-B)** trabajando sobre **la misma carpeta del servidor**. Si ves cambios que vos no hiciste, los hizo la otra cuenta: **no los reviertas ni los pises**.
Última actualización: 2026-10-27 (PC-A).

## 1. Qué estamos construyendo
Un software que arma el **Listado de Señales** (SCADA/HMI/UTR de estaciones transformadoras) en un **Excel**, hoy hecho a mano. Debe:
- empezar desde cero (pidiendo los datos) **o** cargar un Excel existente y modificarlo,
- aplicar las reglas del cliente de forma automática y validada,
- exportar un .xlsx igual al de los ejemplos y permitir seguir editándolo.

**Alcance de esta etapa:** solo las hojas **Caratula** y **EPEN** del primer ejemplo (`ETAP-0722-…-Lista señales - CAO.xlsx`). Fuera de alcance: hojas auxiliares Hoja1/Hoja2, el formato USRE/Arroyito (otro juego de columnas) y las columnas PROTOCOLO, POS DNP/DATASET MMS, BORNERA y N° DE BORNE (quedan vacías).
De la zona UTR solo se completan: **UNITS, TIPO DE SEÑALIZACION, PLACA ENTRADA, ENTRADA**.

**Multi-cliente:** los ejemplos y el PDF de reglas son de EPEN, pero las reglas pueden variar por cliente. Por eso **no hay reglas de cliente escritas en el código**: cada cliente es un *perfil* (`perfiles/<id>/*.json`). EPEN es el primer perfil. Todo (generador, validador, escritor de Excel) debe leer el perfil activo.

**Plazo:** 1 mes = 4 semanas × 5 días × 4 h por PC (20 jornadas por PC).

## 2. Reglas de trabajo (obligatorias)
1. Todo se trabaja en `\\192.168.15.120\PasantiasMM\Sofware listado\codigo\` (árbol de trabajo compartido; es un repo git con `origin` = https://github.com/grupooestepasantias-beep/Software-listado-de-se-ales, rama `main`).
2. **`git push` SOLO cuando el usuario lo indique explícitamente.** No hagas commit ni push por iniciativa propia. Si el usuario pide push y falla por login, que lo haga él en su terminal (GitHub pide iniciar sesión).
3. Nunca escribas contraseñas ni credenciales en archivos, comandos ni campos. El acceso al servidor lo autentica el usuario en Windows.
4. Cada PC es dueña de módulos distintos para no pisarse. Antes de editar un archivo que no es tuyo, mirá `TAREAS.md`.
5. Al empezar: leé `TAREAS.md`, `BITACORA.md` y `PREGUNTAS.md`. Al terminar: actualizá `TAREAS.md` (estado) y `BITACORA.md` (qué hiciste). Las dudas para el usuario van en `PREGUNTAS.md`.
6. Idioma: español en archivos de coordinación, comentarios y respuestas al usuario.
7. Hay un `commit` local hecho (`36e8d43`, archivos de coordinación). Todo lo posterior está sin commitear y sin pushear.

## 3. Reparto de tareas
- **PC-A** (reglas y lógica): `modelo.py`, `perfiles.py`, `perfiles/`, `tags.py`, y luego `generador.py`, `asignacion_utr.py`, `validador.py`.
- **PC-B** (Excel e interfaz): `excel_writer.py`, `excel_reader.py`, `app/` (Tkinter), formato de Caratula/EPEN.
- Tablero completo y estado actual: `TAREAS.md`.

Estado al 2026-10-27: PC-A completó 1.2, 1.3, 1.4 y 1.7 (13 tests OK). **Pendiente para PC-B: 1.5 y 1.6** (leer la plantilla del ejemplo y escribir `excel_writer` con datos fijos), y confirmar la tarea 1.1 (git en la otra PC: ya fue conectada según el usuario).
La 2.1 (generador) de PC-A depende de las respuestas a `PREGUNTAS.md`.

## 4. Qué hay en `codigo\`
```
modelo.py                 dataclasses: Proyecto > Nivel > Campo > Senal, Caratula, Revision, Referencia;
                          enums TipoPunto (DI/AI/DO/AO) y Funcion; Proyecto.guardar()/cargar() en JSON
perfiles.py               cargar_perfil(id), validar(perfil), listar_perfiles(), duplicar_perfil(origen, nuevo)
perfiles/EPEN/            perfil.json (columnas A-W, orden, largos, patrón de tag), estados.json,
                          sufijos_medicion.json, unidades.json, abreviaturas.json
tags.py                   construir_tag / parsear_tag / validar_tag / proxima_variable / construir_desc_scada
generador.py              generar(proyecto, perfil) -> avisos: ordena por función, asigna TAG/OFFSET/estados/UNITS/HMI,
                          crea la 2ª fila del doble bit, enlaza comando<->señalización por Senal.par, respeta Senal.fijos
excel_writer.py, app/, pdf_plano.py, herramientas/, plantillas/   (PC-B: Excel, interfaz Tkinter y lectura del plano)
tests/                    test_perfiles_modelo.py, test_tags.py
TAREAS.md BITACORA.md PREGUNTAS.md CONTEXTO_PARA_CLAUDE.md
```
Ejecutar tests (desde `codigo\`): `python -m unittest discover -s tests`

Entorno de esta PC: Python 3.11, `openpyxl 3.1.5`, `pymupdf 2.0` (instalados con autorización del usuario), git 2.56 en `C:\Program Files\Git\cmd` (puede no estar en el PATH de la sesión). Si tu PC no tiene alguno, **pedí autorización al usuario antes de instalar**. Para leer PDFs usá `import pymupdf` (no uses `python -I`, que ignora los paquetes del usuario). El módulo `modelo`/`perfiles`/`tags` usa solo la biblioteca estándar; openpyxl es para el Excel.
Para git sobre la carpeta de red cada PC necesita (una vez): `git config --global --add safe.directory "//192.168.15.120/PasantiasMM/Sofware listado/codigo"`.

## 5. Archivos de referencia (solo lectura) en `..\`
- `Ejemplos\ETAP-0722-ET-CT-MC-LI-6209-1-Lista señales - CAO.xlsx` — **el modelo a reproducir** (579 señales, hojas Caratula y EPEN).
- `Ejemplos\USRE-0119-ET-CT-PN-SE-1700_C.xlsx` — otro cliente/formato (A–Q, con AUTOTROL, sin UTR). Solo para verificar que el modelo admite un segundo perfil.
- `Ejemplos\ETAP-0325-ET-CT-PL-EF-6402_1.pdf` — plano de ingeniería; de ahí salen PLACA y ENTRADA (ver §7).
- `Reglas\LISTADO DE SEÑALES-LINEAMIENTOS-Epen.pdf` — reglas de EPEN (3 páginas). Ya volcadas en `perfiles/EPEN/`.

## 6. Estructura del Excel de ejemplo (para el `excel_writer`, tareas 1.5 y 1.6)
**Hoja EPEN** (dimensión A1:X606; área de impresión A1:X584; títulos a repetir filas 1:5; autofiltro en A5:W584):
- Filas 1-5 = encabezado (fila 1 letras A, B, C…; 2 = títulos y grupos "HMI SEL", "SCADA CENTRO DE CONTROL", "UTR"; 3 = subtítulos TAG / DESC. HMI SEL / TAG / OFFSET / DESC. SCADA / MEDICIONES-ESTADOS / UNITS / TIPO DE SEÑALIZACION…; 4 = S0 S1 S2 S3; 5 = MIN RAW, MAX RAW, MIN EU, MAX EU). Los datos empiezan en la **fila 6**.
- Columnas: A ITEM · B NIVEL · C DESCRIP · D CONTROLADOR · E FUNCION · F TAG (HMI SEL) · G DESC. HMI SEL · H TAG (SCADA) · I OFFSET · J DESC. SCADA · K-N S0-S3 / MIN RAW-MAX RAW-MIN EU-MAX EU · O UNITS · P TIPO DE SEÑALIZACION · Q PROTOCOLO · R POS DNP · S PLACA ENTRADA · T ENTRADA · U BORNERA · V N° BORNE · W DESCRIPCION/OBSERVACIONES.
- Celdas **combinadas verticalmente** en B (NIVEL), C (DESCRIP) y E (FUNCION) cubriendo todas las filas de cada grupo (ej. `B6:B178`, `C103:C178`, `E6:E68`); también aparecen combinadas algunas U.
- Formato condicional "valores duplicados" sobre la columna J (DESC. SCADA) en algunos rangos.
- Hay otras 2 hojas auxiliares (Hoja1: LEN de descripciones; Hoja2: CONCATENATE prefijo+descripción) que **no** se reproducen.
- Orden fijo de filas: por NIVEL > campo > FUNCION en este orden **ALARMAS → SEÑALIZACION → COMANDO → MEDICION** (RESERVA donde corresponda). Las mediciones van al final de su nivel/campo.

**Hoja Caratula** (A1:AD50; área de impresión A1:AD50):
- B2 "REFERENCIAS"; lista de planos en B3:B16 (código) y G3:G16 (título, celdas combinadas G:AD por fila).
- Tabla de revisiones: filas 25-29, columnas A:B REV · C:H FECHA · I:U DESCRIPCIÓN · V:X PROY. · Y:AA REV. · AB:AD APR. (fila 29 son los títulos; la revisión más reciente arriba; ejemplo: 1 / CONFORME A OBRA, 0 / APC).
- C31 cliente (combinada C31:AD32) · C33 "Obra:" y C34 la obra (C34:AD37) · A38 "Lugar:" · H38 "Depto.:" · S38 "Nro. Expediente:" · A40 "Título:" y A41 el título.
- Fila 44 "Documento N°:": el número del documento va **un carácter por celda** (D44…AD44), con "-" en N44; ej. `ETAP-0722-ET-CT-MC-LI-6209`.
- Pie: C45 "Proyectó:" (C46) · C47 "Dibujó:" (C48) · C49 "Aprobó:" (C50) · J45 "Archivo Magnético:" (J47) · R45 "Escala:" (R46, "N/A") · X45 "Revisión:" (X46) · J49 "Fecha:" (J50) · R49 "Hoja:" (T49).
- "Hoja X de Y" = cantidad de hojas del libro = **siempre "1 de 2"** (Caratula + listado).
- Conviene **extraer anchos, estilos, bordes y merges del propio ejemplo** (leer con openpyxl) en vez de redibujarlos a mano.

## 7. Reglas del dominio ya confirmadas por el usuario
**Jerarquía y orden:** NIVEL de tensión (comunes: 132kV, 33kV, 13,2kV, 6,6kV, SSAA…, pero pueden aparecer otros) → DESCRIP/Campo (nombre y número salen del plano de ingeniería; se tipean a mano) → CONTROLADOR (se tipea a mano, no hay catálogo) → FUNCIÓN en orden fijo e inalterable (de él salen tags y offsets).

**Tipos de punto:** DI (entrada digital), AI (analógica), DO (salida digital), AO (salida analógica). Digitales usan 0/1; analógicas manejan rangos (temperatura, amperaje…).

**ITEM y OFFSET:** correlativos desde el inicio de la hoja. **El software siempre debe preguntar desde qué número arrancar** (una obra intervenida continúa desde el último número de la obra vieja). Se ordenan por campo y, dentro del campo, por función (alarma, señalización, comando, medición); las mediciones al final: campo 1, campo 2, etc. Un **COMANDO comparte tag y offset con su SEÑALIZACIÓN** (los tags con `C`): hay que verificar que no se repitan ni se dupliquen.

**Tag SCADA** (patrón confirmado contra el ejemplo): `{nivel}{campo}.{variable 00-99}{bits 1|2}{C si comando}` y para mediciones `{nivel}{campo}.{variable}{código}` (AR/AS/AT corriente, AU/AV/AW tensión, AP/AQ potencias, AF frecuencia, AFP…). Ej.: `303.001`, `303.632C`, `303.01AU`. Nivel: 3=132kV, 2=33kV, 1=13,2kV. Campos especiales sin dígito de nivel: TP1, TP2, RN1, RN2, SAA/SAC (el ejemplo usa SACA, SACC, UTR). Implementado en `tags.py`.

**Descripciones:** DESC. SCADA **máx. 20 caracteres** (prefijo del campo + descripción, ej. `303LC SEC BA F/Uaux`). TAG HMI y DESC. HMI = prefijo del campo + descripción con las reglas del PDF (nombre que pide la empresa). Tablas de abreviaturas en `perfiles/EPEN/abreviaturas.json`.

**Estados S0-S3 / rangos** (`perfiles/EPEN/estados.json` y `sufijos_medicion.json`):
- Digitales: se usa **N/A** en los estados que no aplican (alarma de 1 bit = NORMAL / ACTUO / N/A / N/A). En señalización de doble bit se usan los 4: `error_0 / AB / CE / error_1`, y variantes LOC-REM, DIST-TELE, MAN-AUT, SIN-CON, EX-IN, PAR-ARR, SUB-BAJ; también 1 bit NORMAL-OPERO y CONECT-DESCONEC.
- Analógicas: K/L = MIN RAW/MAX RAW (cuenta cruda del aparato, -32768…32767/32768) y M/N = MIN EU/MAX EU (valores de ingeniería escalados a la unidad, que fija el aparato).
- UNITS: N/A para digitales; para analógicas KV, A, Hz, MW, MVA, Mvar, V, ºC… (grafía exacta aún a confirmar).
- **RESERVA** = señal que físicamente corresponde a un módulo y tiene el cable puesto pero no se usa (queda para futuros cambios); en el ejemplo lleva tag "N/A".

**UTR (zona P-T):** TIPO DE SEÑALIZACION = DI/AI/DO/AO. PLACA ENTRADA y ENTRADA se asignan en el orden de la placa (módulo) según el **plano de ingeniería**: hay que fijarse en el rótulo del módulo (ej. `DI9`), **no** en el número grande de arriba (ese no importa por ahora). Los comandos ocupan pares de salidas (1/2, 9/10). Primera versión: carga manual en la app; leer el plano automáticamente queda como mejora.

**Carátula:** el cliente, obra, lugar, depto., expediente, título, firmas, escala y revisiones se piden al inicio (pantalla de inicio/consulta). Las letras de revisión las da el usuario al principio. Las REFERENCIAS (planos) se cargan a mano. El número de documento se arma por partes (cómo se compone: pregunta pendiente).

## 8. Tecnología y arquitectura
Python 3.11 + openpyxl + interfaz de escritorio Tkinter/ttk (empaquetado opcional a .exe con PyInstaller). Se descartaron VBA (difícil de versionar entre 2 PCs) y web/Flask (más infraestructura).
Módulos previstos: `modelo`, `perfiles`, `tags`, `generador` (ordena, crea tags/offsets/descripciones/estados), `asignacion_utr` (placa/entrada, pares de comando, RESERVA), `validador` (20 car., duplicados, grafías ERR_0 vs error_0, KV vs kV, tags/offsets repetidos), `excel_writer`, `excel_reader`, `app/`.
Contrato entre PCs: PC-B consume `modelo.py` (no lo cambia; pide cambios por `TAREAS.md`/`BITACORA.md`). El escritor de Excel debe leer columnas, hojas y orden **del perfil** (`perfil.columnas`, `perfil.datos["hojas"]`), no escribirlos fijos.

## 9. Cronograma
- **Sem. 1** base y reglas: PC-A 1.1-1.4 y 1.7 ✅ · PC-B 1.5 y 1.6 pendientes.
- **Sem. 2** núcleo: PC-A generador (2.1) · PC-B Caratula + formulario + pantalla de inicio (2.2).
- **Sem. 3** completo: PC-A placa/entrada, RESERVA, RAW/EU, validador (3.1) · PC-B `excel_reader`, editor de señales, merges (3.2).
- **Sem. 4** cierre: PC-A pruebas contra el ejemplo y ajuste de reglas · PC-B exportar, errores, manual, empaquetado, aceptación.
Verificación final: regenerar el ejemplo ETAP y compararlo celda por celda (valores y celdas combinadas) con el original; abrir el .xlsx en Excel (filtros, formato condicional, impresión); prueba end-to-end con el usuario.

## 10. Dudas abiertas (detalle en `PREGUNTAS.md`)
Compone del número de documento; fórmula de TAG/DESC. HMI; AS repetido (corriente S / potencia aparente); AFP, VP, IP, LF, IF; CBC; MAX RAW 32767 vs 32768; campos especiales y SSAA/UTR (SACC vs SAC); dónde arranca la variable; offset por tipo de punto; ITEM de comandos; MV vs MW y grafía KV/kV, ºC/°C; reglas de RESERVA.
Mientras no haya respuesta: usá el supuesto más cercano al ejemplo, **marcalo como pendiente** en el código/perfil y no inventes.

## 11. Cómo trabajar bien acá
- Sin respuesta del usuario sobre una regla, no la hardcodees: ponela en el perfil (`perfiles/EPEN/`) con una nota `pendiente`.
- Después de cada cambio corré `python -m unittest discover -s tests` y agregá tests para lo nuevo (los tests contra el ejemplo ETAP se saltan solos si el archivo o openpyxl no están).
- Los archivos `.xlsx`/`.pdf` de `Ejemplos\` y `Reglas\` no se modifican.
- Al terminar la sesión dejá `TAREAS.md` y `BITACORA.md` actualizados; así la otra cuenta sabe dónde seguir.
