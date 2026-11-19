==============================================================================
PROTOCOLOS FAT Y SAT - INSTRUCTIVO DE USO
==============================================================================

Nota para quien lo baja de GitHub: acá están el código (carpeta App) y los dos instructivos. El programa listo para usar, Protocolos FAT y SAT.exe (160 MB, más de lo que GitHub deja subir a un repositorio), está en la carpeta de red \\192.168.15.101\Archivos\PasantiasMM\Programas terminados\App FAT y SAT; también se genera con App\compilar_exe.bat.

Para quien nunca usó el programa. Si algo falla, mirá el archivo "PROBLEMAS Y SOLUCIONES.txt" (está en esta misma carpeta).

------------------------------------------------------------------------------
1. Qué hace este programa
------------------------------------------------------------------------------

Arma los protocolos de ensayo de Grupo Oeste en Word, listos para revisar y entregar:

- SAT: el protocolo + su Anexo 1 (energizado) + su Anexo 2 (señales y comandos). Son 3 archivos.
- FAT: el protocolo + su Anexo 1 (energizado) + su Anexo 2 (señales y comandos). Son 3 archivos.

Los datos técnicos (señales, comandos, térmicas, bornes) los saca de los planos en PDF. Vos cargás los datos de la obra
(cliente, número de obra, etc.) y el programa completa el resto. También revisa que todo sea coherente y te avisa si algo
no cierra con el plano.

Importante: el programa controla que el documento esté bien armado y que coincida con el plano. NO reemplaza la revisión
técnica de ingeniería (valores, normas, modelos de equipos).

------------------------------------------------------------------------------
2. Qué necesitás
------------------------------------------------------------------------------

- Una PC con Windows.
- Microsoft Word instalado (lo usa para armar el índice, numerar las páginas y sacar el PDF). Sin Word el programa
  funciona, pero los documentos quedan marcados como "NO LISTO PARA ENTREGAR".
- Los planos de la obra en PDF: el esquema funcional (EF) y, si es un archivo aparte, el constructivo (TP).
- Una carpeta donde guardar los documentos (mejor una carpeta corta, por ejemplo C:\Protocolos\Obra205).

------------------------------------------------------------------------------
3. Cómo abrirlo (primera vez)
------------------------------------------------------------------------------

1. En esta carpeta está el archivo "Protocolos FAT y SAT.exe".
2. NO lo abras desde la red: Windows suele dar "Acceso denegado" y, aunque abra, tarda mucho.
   Copialo a tu PC (por ejemplo al Escritorio) y abrilo desde ahí.
3. La primera vez tarda entre 20 y 40 segundos en aparecer la ventana. Esperá, no hagas doble clic de nuevo.
4. Si Windows muestra "Windows protegió su PC": tocá "Más información" y después "Ejecutar de todas formas".
   Pasa porque el programa es interno de la empresa y no tiene firma digital. No es un virus.

Para actualizar el programa, copiá otra vez el .exe nuevo sobre el viejo.

------------------------------------------------------------------------------
4. La ventana
------------------------------------------------------------------------------

La ventana está dividida en 4 pasos, de arriba hacia abajo:

- Paso 1 - Datos de la obra
- Paso 2 - Planos de ingeniería
- Paso 3 - Revisar y completar (cuatro pestañas)
- Paso 4 - Qué generar y dónde guardarlo

Arriba hay tres menús: Proyecto, Herramientas y Ayuda. En Ayuda > "Cómo se usa (4 pasos)" tenés un resumen.

------------------------------------------------------------------------------
5. Paso a paso
------------------------------------------------------------------------------

>> Paso 1 - Datos de la obra

Completá cada campo. Los marcados como obligatorios no pueden quedar vacíos.

- Cliente: por ejemplo EDESTE. Aparece en la firma del documento ("Por EDESTE").
- Nº de obra: solo el número, por ejemplo 205.
- Proyecto/Obra: el nombre completo de la obra, por ejemplo 205-EDESTE_Reemplazo RTUs.
- Ubicación: dónde está el tablero (ciudad o estación). Es obligatoria.
- Tipo de tablero: elegí de la lista (Tablero de Control, de Protección, etc.).
- Nombre / estación: el nombre de la estación transformadora, por ejemplo La Paz o Arroyito.
  Tiene que coincidir con el que dice el plano (se compara). No usar los símbolos  \ / : * ? " < > |
- Tensión: elegí de la lista o escribila, por ejemplo 33 KV o 66/13,2 KV. Se compara con lo que nombra el plano.
- Fecha: formato dd/mm/aaaa, por ejemplo 19/11/2026. Se completa sola con la de hoy.
- Revisión: una letra o número, hasta 3 caracteres (A, B, C2). Aparece en el nombre de los archivos.

El programa recuerda los últimos datos que usaste.

>> Paso 2 - Planos de ingeniería

1. Tocá el botón "Cargar planos (1 o 2 PDF)...".
2. Elegí el PDF del esquema funcional. Si el constructivo es otro archivo, elegí los dos a la vez
   (mantené Ctrl apretado y hacé clic en cada uno).
3. Aparece una ventana con una barra de avance. Esperá a que termine.
   - Si el plano tiene todo como texto, tarda unos segundos.
   - Si trae partes dibujadas como líneas (los números de interruptor de las celdas, los nombres de las térmicas, etc.),
     el programa las lee con OCR (lectura de imágenes). Eso tarda varios minutos la primera vez con cada plano.
     Después queda guardado y la segunda vez es inmediato. No cierres el programa mientras avanza.
4. Al terminar aparece un mensaje con lo que se leyó y, debajo del botón, un resumen en una línea, por ejemplo:
   "Térmicas: 11 - Señales: 32 - Comandos: 4 - Falta completar 5 dato(s)".
   - Texto en verde: nada pendiente.
   - Texto en naranja: hay datos para completar a mano (paso 3).

>> Paso 3 - Revisar y completar

Hay cuatro pestañas:

1. Referencias y hardware
   - Arriba: la lista de planos de referencia (nombre del archivo y su descripción). Se completa sola al cargar los planos.
   - Abajo: los componentes de hardware (RTAC, power coupler, módulos DI y DO). Tocá "Cargar set típico..." y
     poné las cantidades que dibuja el plano, o dejá que "Cargar planos" las calcule.
   - En la columna "Número de serie" podés escribir los números, o dejarlos en blanco para completar en el ensayo.
2. Anexo 1 · Energizado
   - La lista de térmicas (interruptores termomagnéticos) con su tensión (Grupo) y su descripción.
3. Anexo 2 · Señales
   - Arriba las señales (entradas digitales) con su borne o elemento. Abajo los comandos.
4. Control de calidad
   - Se llena sola cuando generás. Se explica en el paso 4.

Cómo editar una tabla:
- Doble clic en una celda, escribís el valor y apretás Enter (Esc cancela).
- Las filas en AMARILLO son las que falta completar. En el nombre de la pestaña aparece cuántas faltan
  (por ejemplo "Anexo 2 · Señales (36 · faltan 5)").
- Botones a la derecha de cada tabla: Agregar fila, Duplicar, Quitar, Subir, Bajar. Con la tecla Supr también se
  borran las filas seleccionadas.

Qué completar:
- Señales con la columna "Borne / Elemento" que dice "(ver hoja 29, módulo 3, terminal 1)": miralo en el plano y escribí el
  borne o elemento (por ejemplo -KI3.3 o -XFI1/5).
- Térmicas sin tensión o sin descripción: escribilas (por ejemplo 110 VCC y "Alimentación general").
  La tensión va como 220 VCA, 110 VCC o 48 VCC.
- Lo que el programa leyó por OCR (de imágenes) conviene mirarlo contra el plano; queda marcado como
  "pendiente de confirmación" en el informe.
- Los nombres de las señales deben quedar IGUALES a los del plano. Solo se toleran diferencias de tildes.

>> Paso 4 - Qué generar y dónde guardarlo

1. Marcá lo que querés generar:
   - SAT (protocolo + Anexo 1 + Anexo 2): genera los tres archivos del SAT.
   - FAT (protocolo), FAT Anexo 1, FAT Anexo 2: cada uno por separado.
   - Atajos: "Solo SAT", "FAT completo" y "Paquete completo" (SAT y FAT con todos sus anexos).
   - "Incluir lectura de protecciones": desmarcalo si ese párrafo no corresponde en este SAT/FAT.
   - "Exportar también PDF": genera además un PDF de cada Word (necesita Word).
2. Carpeta de salida: tocá "Elegir..." y elegí dónde se guardan. "Abrir carpeta" la abre.
3. Tocá "Generar documentos" (o Ctrl+G).
4. Mirá la barra de avance. Al terminar aparece un resumen y te pregunta si querés abrir la carpeta.

Si algo no cierra, el programa NO genera nada y te muestra un cartel "No se puede generar todavía" con la lista de lo que hay
que corregir. Corregilo y volvé a tocar "Generar documentos".

Si hay diferencias entre lo que cargaste y el plano que solo vos podés decidir (por ejemplo, el plano dice otra obra),
aparece "Confirmar datos de los PDF". Si estás seguro de que está bien, respondé "Sí": queda registrado a tu nombre.
Si no estás seguro, respondé "No", corregí el dato y generá de nuevo.

------------------------------------------------------------------------------
6. Qué se genera
------------------------------------------------------------------------------

En la carpeta de salida aparecen:

- Los documentos Word, con nombres como:
  EDESTE - Obra 205 - Tablero de Control La Paz - Protocolo SAT - rC.docx
  EDESTE - Obra 205 - Tablero de Control La Paz - Protocolo SAT - rC - Anexo 1.docx
  EDESTE - Obra 205 - Tablero de Control La Paz - Protocolo FAT - rC - Anexo 2.docx
- Un PDF por cada Word (si marcaste "Exportar también PDF").
- Un archivo ZIP con todo: "Paquete - ... .zip". Si empieza con "BORRADOR - " es porque el control de calidad
  encontró algo sin resolver: no es para entregar.
- "... - Informe de control de calidad.txt": el informe del control.
- "... - Trazabilidad - r?.csv": de qué hoja del plano salió cada señal, comando y térmica.
- La carpeta "versiones": copias de documentos anteriores (ver más abajo).
- "registro_operaciones.jsonl": un registro de cada vez que se generó algo (fecha, usuario, archivos).

------------------------------------------------------------------------------
7. Cómo leer el resultado (pestaña "Control de calidad")
------------------------------------------------------------------------------

Después de generar, el programa abre esa pestaña y escribe arriba un resumen, por ejemplo
"LISTO PARA ENTREGAR - 0 bloqueantes, 0 advertencias, 19 informativos".

- LISTO PARA ENTREGAR: no hay nada para corregir desde el punto de vista del documento.
- NO LISTO PARA ENTREGAR: hay que resolver lo que figura en la lista antes de entregar.

Cada fila de la lista tiene una gravedad, con su color:
- BLOQUEANTE (rojo): el documento no se debe entregar así.
- ADVERTENCIA (amarillo): conviene revisarlo.
- INFO (gris azulado): dato para tener en cuenta. Muchos dicen "PENDIENTE DE CONFIRMACIÓN": son datos que el plano no
  permite verificar (por ejemplo modelos de equipos, valores del ensayo dieléctrico, lo leído por OCR). Los tiene que
  confirmar ingeniería. No impiden entregar, pero hay que avisar.

Doble clic en una fila para ver el detalle y la solución sugerida. "Exportar informe..." lo guarda como texto.

------------------------------------------------------------------------------
8. Guardar y retomar un trabajo
------------------------------------------------------------------------------

Menú Proyecto:
- Guardar proyecto / Guardar proyecto como...: guarda todo lo cargado (datos, tablas, opciones) en un archivo.
- Abrir proyecto...: lo retoma donde lo dejaste (útil para hacer una revisión B de una obra ya hecha).
- Nuevo proyecto: vacía todo (te pregunta antes).

Los proyectos se guardan en tu usuario de Windows, en C:\Users\TU_USUARIO\AppData\Roaming\Protocolos FAT y SAT\proyectos
(si no elegís otra carpeta).

------------------------------------------------------------------------------
9. Menú Herramientas
------------------------------------------------------------------------------

- Controlar documentos existentes...: elegís uno o varios Word ya hechos (del mismo proyecto) y los revisa como si
  los hubieras generado ahora.
- Versiones anteriores de un documento...: si regeneraste un documento y querés volver a uno anterior.
- Ver registro de operaciones: quién generó qué y cuándo, en la carpeta de salida elegida.

------------------------------------------------------------------------------
10. Si generás de nuevo un documento que ya existe
------------------------------------------------------------------------------

El programa pregunta "Ya existen documentos". Si respondés que sí, el anterior NO se pierde: se guarda en la carpeta
"versiones" (con fecha y hora en el nombre) y el nuevo ocupa su lugar. Se recupera desde Herramientas > Versiones anteriores.
Antes de regenerar, cerrá los Word que estén abiertos.

------------------------------------------------------------------------------
11. Buenas costumbres
------------------------------------------------------------------------------

- Cargá siempre los planos de la MISMA revisión (EF y TP con la misma letra).
- Revisá que el nombre de la estación, el número de obra y la tensión sean los de la obra.
- Mirá lo resaltado en amarillo antes de generar.
- Antes de entregar, abrí los Word, revisá el índice y mirá la pestaña "Control de calidad".
- No edites a mano los Word y vuelvas a generar encima sin guardar una copia: la regeneración los reemplaza
  (aunque queda la versión anterior en "versiones").
- La fecha de la ventana es una sola: si el FAT y el SAT van con fechas distintas, generalos por separado.
- Guardá el proyecto (Proyecto > Guardar) antes de cerrar si pensás retomarlo.

------------------------------------------------------------------------------
12. Dónde está cada cosa
------------------------------------------------------------------------------

- El programa listo para usar: "Protocolos FAT y SAT.exe" (esta carpeta).
- El código fuente: carpeta "App" (solo para quien modifica el programa; el README de esa carpeta es técnico).
- Versiones viejas y pruebas anteriores: carpeta "Archivo anterior 2026-11-18" (se puede borrar).
- Tu configuración y proyectos: C:\Users\TU_USUARIO\AppData\Roaming\Protocolos FAT y SAT
- Lo ya leído por OCR de cada plano: C:\Users\TU_USUARIO\AppData\Local\GeneradorSAT\cache_ocr
  (si se borra, se vuelve a leer y tarda de nuevo).

Ante cualquier error que no figure en "PROBLEMAS Y SOLUCIONES.txt", sacá una captura del mensaje y avisá.
