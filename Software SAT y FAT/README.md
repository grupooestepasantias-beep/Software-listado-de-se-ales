# Software SAT y FAT - Generador de protocolos de ensayo (Grupo Oeste)

Aplicación de escritorio para Windows (Python + tkinter) que genera los protocolos de ensayo **SAT** y **FAT** en Word
a partir de los planos de ingeniería (PDF) y de los datos que carga el usuario. Los controla, exporta a PDF y deja registro.

> Este proyecto es independiente del listado de señales que está en la raíz del repositorio.

## Qué genera

| Documento | Archivo | Contenido |
|---|---|---|
| SAT | `<Cliente> - Obra <N> - <Tablero> - Protocolo SAT - r<Rev>.docx` | Protocolo principal |
| SAT Anexo 1 / Anexo 2 | `... - Protocolo SAT - r<Rev> - Anexo 1.docx` / `... Anexo 2.docx` | Formato de los SAT de referencia: portada simple, lista de verificación de energizado (Anexo 1) y señales/comandos (Anexo 2) |
| FAT | `... - Protocolo FAT - r<Rev>.docx` | Protocolo principal |
| FAT Anexo 1 | `... - Protocolo FAT - r<Rev> - Anexo 1.docx` | Procedimiento de energizado (térmicas -Q…) |
| FAT Anexo 2 | `... - Protocolo FAT - r<Rev> - Anexo 2.docx` | Señales DI y comandos DO (tablas) |

Cada generación entrega también: PDF de cada Word (si hay Word), un ZIP, la trazabilidad (CSV) y el informe de calidad.
El ZIP se llama `BORRADOR - …` si el control de calidad no da "LISTO PARA ENTREGAR".

## Reglas de diseño (importantes para quien lo mejore)
- **Los PDF son la única fuente de datos técnicos.** Nombres de señales y bornes salen exactos del plano; solo se ignoran
  diferencias de acentos u ortografía.
- **No se inventan datos.** Lo que no se puede verificar queda como *PENDIENTE DE CONFIRMACIÓN* (aviso INFO en el informe).
- SAT y FAT son independientes (fecha, texto y archivos propios; el SAT no menciona el FAT y viceversa).
- Antes de generar hay una compuerta (`revisar_previos`): valida datos, PDF (revisión, estación, nº de obra, EF/TP) y
  contrasta señales, comandos, térmicas y módulos de hardware contra el plano. Si algo no cierra, **no se genera nada**.

## Descarga directa (sin instalar Python)
En la sección **Releases** del repositorio (https://github.com/grupooestepasantias-beep/Software-listado-de-se-ales/releases) está `GeneradorSAT.exe`.
Descargarlo y ejecutarlo; solo hace falta Microsoft Word instalado.

## Requisitos
- Windows y Python 3.11+. `pip install -r requirements.txt` (`python-docx`, `pymupdf`).
- **Microsoft Word** instalado (se usa por COM para actualizar índice/campos y exportar PDF). Sin Word se generan los
  .docx igual, pero el control los marca "NO LISTO" (índice sin actualizar).

## Cómo usarlo
1. Ejecutar `python app.py` (o `GeneradorSAT.bat`, o el `.exe` si se compiló).
2. Cargar los **datos**: cliente, nº de obra, obra, ubicación, tipo de tablero, nombre, tensión, fechas (FAT/SAT) y revisión.
3. Marcar **qué generar**: SAT (incluye sus Anexo 1 y 2) / FAT / Anexo 1 / Anexo 2 del FAT.
4. **Planos**: botón *Leer planos (1 o 2 PDF)…* (pestaña Documentos y componentes): se carga un solo PDF funcional que tenga todo, o dos (funcional + constructivo), y se leen térmicas y señales de una vez. Cada anexo conserva además su propio *Subir PDF…*. Si el lector no reconoce el formato del plano no carga nada por suposición y hay que completar las tablas a mano.
   **Documentos de referencia**: agregar los PDF (la descripción se deduce del nombre: EF → ESQUEMA FUNCIONAL, TP → CONSTRUCTIVO).
5. **Componentes**: cargar el set típico (RTAC, Power Coupler, módulos DI/DO) o editarlos.
6. **Anexo 1**: *Subir PDF…* para leer las térmicas. **Anexo 2**: *Subir PDF…* del esquema funcional para leer las
   señales DI y los comandos DO. Revisar siempre las listas (botón *Sugerir descripciones…* completa las térmicas).
7. Elegir carpeta de salida y **Generar documentos**. Revisar la pestaña **Control de calidad**.

Las inconsistencias "confirmables" de los planos (por ejemplo, portada con otro nombre de estación) piden confirmación
explícita del usuario y quedan registradas en el informe.

## Control de calidad
Hallazgos con gravedad **BLOQUEANTE / ADVERTENCIA / INFO** y tipo **FORMATO / DOCUMENTAL / CONSISTENCIA**.
"LISTO PARA ENTREGAR" solo si no hay bloqueantes ni advertencias. No valida criterios de ingeniería (valores, normas).

## Versiones y seguridad de archivos
- Un documento existente no se pisa: pasa a `versiones\<nombre>__<fecha-hora>.docx`.
- Guardado atómico; `registro_operaciones.jsonl` con fecha, usuario, documentos y SHA-256.
- Proyectos guardables en JSON (menú *Proyecto*). Los planos solo se leen.

## Estructura del código
| Archivo | Función |
|---|---|
| `app.py` | Ventana (tkinter) |
| `generador_sat.py` | Arma los Word, compuerta previa, paquete completo (`generar_paquete`), trazabilidad |
| `extraer_pdf.py` | Lee señales DI, comandos DO y térmicas de los PDF (PyMuPDF); contraste con el plano |
| `validador.py` | Control de calidad de los Word y entre documentos |
| `gestion.py` | Versiones, registro, proyectos, validación de entradas |
| `word_tools.py` | Word por COM: actualizar índice/campos y exportar PDF |
| `docx_util.py` | Utilidades de edición .docx |
| `crear_plantilla.py` | Recrea las plantillas desde documentos de referencia (rutas de red de Grupo Oeste) |
| `plantilla_*.docx` | Plantillas con marcadores `{{FECHA}}`, `{{OBRA}}`, `{{NOMBRE}}`… (SAT, FAT y sus anexos 1 y 2: 6 plantillas) |
| `tests/`, `ejecutar_pruebas.py` | Pruebas automáticas (135) |
| `INFORME.md` | Informe de auditoría del desarrollo |

## Pruebas
```
python ejecutar_pruebas.py
```
Las pruebas que necesitan Word o los planos de la red (`\\192.168.15.120\PasantiasMM\la paz\Ing`) se omiten si no hay acceso.

## Compilar el .exe
```
pip install pyinstaller
python -m PyInstaller --noconfirm --onefile --windowed --name GeneradorSAT ^
  --add-data "plantilla_sat.docx;." --add-data "plantilla_fat.docx;." ^
  --add-data "plantilla_fat_anexo1.docx;." --add-data "plantilla_fat_anexo2.docx;." ^`r`n  --add-data "plantilla_sat_anexo1.docx;." --add-data "plantilla_sat_anexo2.docx;." ^
  --exclude-module pymupdf.layout --exclude-module pymupdf4llm --exclude-module onnxruntime --exclude-module PIL app.py
```
Los `--exclude-module` son necesarios: sin ellos "Subir PDF…" falla dentro del .exe. El .exe se publica en Releases, no dentro del código.

## Formatos de plano soportados
- **La Paz (EF + TP):** hojas DETALLE MODULO DI/DO y cableado con bornes -XFI/-XF: señales, comandos, bornes y térmicas se leen completos.
- **Hoja resumen de módulos (EDESTE/Arroyito, USRE-01-19-…-Ef-1102):** los nombres de señales y comandos se leen de la hoja de módulos (terminal por terminal, sin reservas ni comunes). El *elemento* de cada señal (-KI3.2…) y las térmicas (-QC, -QS) están dibujados como líneas en el PDF y no se pueden leer: se completan a mano y quedan registrados como dato manual. Para leerlos automáticamente habría que exportar el PDF con el texto como texto (no como geometría).

## Estado y pendientes
- Funciona: SAT y FAT, cada uno con Anexo 1 y Anexo 2 (6 Word), PDF, ZIP, trazabilidad, control de calidad, versiones.
- Pendientes de ingeniería (confirmar con el responsable, no son errores de código): modelos de equipos (SEL 2241/2243/2244),
  valores y normas del ensayo dieléctrico, descripciones/tensión de térmicas que no están en el plano, borne de
  "Falla Alimentación General" (el plano no lo da), SCADA SURVALENT.
- Ideas de mejora: interfaz sin dependencia de Word, plantillas editables desde la ventana, lectura de más formatos de plano.







