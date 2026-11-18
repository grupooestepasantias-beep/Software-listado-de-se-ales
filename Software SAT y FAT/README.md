# Protocolos FAT y SAT - código fuente

Programa de Grupo Oeste que genera los protocolos de ensayo **SAT** y **FAT** en Word (con sus Anexo 1 y Anexo 2) a partir de
los planos de ingeniería en PDF y de los datos de la obra. El ejecutable listo para usar es `Protocolos FAT y SAT.exe`, que está
en la carpeta de arriba; esta carpeta es el código para modificarlo.

## Qué genera
| Documento | Contenido |
|---|---|
| SAT | Protocolo + **Anexo 1** (lista de verificación de energizado) + **Anexo 2** (señales y comandos), en tres archivos |
| FAT | Protocolo + **Anexo 1** (procedimiento de energizado) + **Anexo 2** (señales y comandos), en tres archivos |

Además: PDF de cada Word (con Microsoft Word instalado), un ZIP, la trazabilidad (CSV) y el informe de control de calidad.

## Cómo se usa (cuatro pasos)
1. **Datos de la obra**: cliente, nº de obra, ubicación, tipo de tablero, nombre/estación, tensión, fecha y revisión.
2. **Planos de ingeniería**: *Cargar planos (1 o 2 PDF)*. Alcanza con un funcional que traiga todo, o el funcional y el constructivo.
   Se leen las térmicas, las señales y los comandos. Lo que no se puede leer queda **resaltado en amarillo**.
3. **Revisar**: pestañas Anexo 1 y Anexo 2; doble clic en una celda para completarla o corregirla.
4. **Generar**: elegir qué documentos y la carpeta de salida, y *Generar documentos* (Ctrl+G).

Reglas del programa: los PDF son la única fuente de datos técnicos; nada se inventa (lo que no figura en el plano queda
"pendiente de confirmación"); antes de generar se contrasta todo contra el plano y, si algo no cierra, no se genera nada.

## Qué lee de los planos
- **Formato La Paz** (hojas *DETALLE MODULO DI/DO* y *ENTRADAS/SALIDAS DIGITALES*): señales, comandos, bornes y térmicas con el
  texto del PDF. Los interruptores de las celdas de 13,2 kV (por ejemplo `Interruptor 15201 Abierto`) vienen dibujados como
  líneas: se leen por OCR del encabezado de cada hoja de cableado, y el "(C1)" de la hoja de módulos se reemplaza por ese número.
- **Formato con hoja resumen de módulos** (EDESTE / Arroyito): nombres de la hoja de módulos; térmicas, elementos (`-KI3.2`,
  `-QC`, `-XFI/1-2`…) y bobinas de comando (`-KC1.3`) por OCR.
- El OCR (`ocr_plano.py`) tarda unos minutos la primera vez por plano y queda guardado en `%LOCALAPPDATA%\GeneradorSAT\cache_ocr`.
  Todo lo leído por OCR figura en el informe como *pendiente de confirmación*.

## Estructura
| Archivo / carpeta | Función |
|---|---|
| `app.py` | Ventana (tkinter) |
| `generador_sat.py` | Arma los Word, control previo, paquete completo, trazabilidad |
| `extraer_pdf.py` | Lectura de señales, comandos y térmicas de los PDF; contraste con el plano |
| `ocr_plano.py` | OCR de lo que el plano trae dibujado como líneas (térmicas, elementos, encabezados) |
| `validador.py` | Control de calidad de los Word |
| `gestion.py` | Versiones, registro de operaciones, proyectos, validación de entradas |
| `word_tools.py`, `docx_util.py` | Word por COM (índice, páginas, PDF) y utilidades de edición |
| `crear_plantilla.py` | Vuelve a crear las plantillas desde los documentos de referencia |
| `plantillas/` | Las 6 plantillas Word con marcadores `{{FECHA}}`, `{{OBRA}}`… |
| `recursos/` | Ícono y datos de versión del `.exe` |
| `tests/`, `ejecutar_pruebas.py` | Pruebas automáticas |
| `compilar_exe.bat` | Genera el `.exe` |

## Requisitos
- Windows con **Microsoft Word** (índice, números de página y PDF) y Python 3.11+.
- `pip install -r requirements.txt` (python-docx, pymupdf, rapidocr-onnxruntime).

## Ejecutar, probar y compilar
```
python app.py                 # abrir la ventana desde el código
python ejecutar_pruebas.py    # pruebas (las que usan los planos de la red se omiten si no hay acceso)
compilar_exe.bat              # crea dist\Protocolos FAT y SAT.exe
```
Como `.exe`, la configuración y los proyectos se guardan por usuario en `%APPDATA%\Protocolos FAT y SAT`.
