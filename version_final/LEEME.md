# Listado de Señales — versión final (combinada)

Arma el Excel «Listado de Señales» con el formato de EPEN a partir de los PDF de ingeniería (esquemas funcionales).
Junta lo bueno de la app anterior (`..\codigo\`) con el módulo SCADA nuevo (`..\pruebas\scada\`). Esas dos carpetas
**no se tocaron**: quedan como están.

## Abrir
Desde esta carpeta (necesita Python con openpyxl, pymupdf y Pillow):

    python -m app

## Uso
1. **Agregar PDF…** (se pueden sumar varios; cada uno se copia a un caché local la primera vez). La pestaña
   **Campos leídos** muestra campo, tensión, señales y hojas de donde salió cada señal.
2. **Datos…**: variable inicial por campo, prefijo, controlador, relé, offsets, ITEM inicial, estados, rangos y **placas**
   (si el plano no las trae).
3. **Calcular** (pregunta si recalcular todo o agregar a lo ya hecho). La pestaña **Listado** muestra A–W; amarillo = DESC.
   SCADA sin resolver en 20 caracteres.
4. **Corregir a mano**: doble clic en una celda (controlador, tags, descripciones, estados, unidad, tipo, placa, entrada,
   observaciones). Queda en verde, se guarda con el proyecto y **sobrevive a recalcular**. Dejarla vacía vuelve al valor
   calculado.
5. **Carátula**: datos de la obra, referencias, revisiones y logos. Si se completó algo, el Excel sale con la hoja Caratula.
6. **Exportar Excel…**, **Guardar proyecto…** / **Abrir proyecto…** (el .json guarda las rutas de los PDF, los datos, las
   correcciones y la carátula; al abrir se vuelven a leer los PDF).

## Estilos del listado (`estilo.py`)
La app detecta el estilo por el nombre del PDF (`USRE-…` o `ETAP-…`) y se cambia en «Datos…».
| | ETAP (Aguada Pichana) | USRE (Senillosa) |
|---|---|---|
| DESC. HMI | prefijo del campo + texto sin tildes | sin prefijo, en Título |
| Señal doble (abierto/cerrado) | un TAG/DESC. HMI por estado | UN solo TAG/DESC. HMI (`Reconectador_15201_Abierto_Cerrado`), 2.ª fila vacía |
| «en local» con una sola entrada | 2 filas | 1 fila, 1 offset (tag de 2 bits) |
| Estados | error_0 / AB / CE / error_1 | err_0 / ABIERTO / CERRADO / err_1; REMOTO/LOCAL; ABRIR/CERRAR |
| Alarmas | NORMAL / ACTUO | NORMAL / ACTUO, FALTA o FALLA según el texto |
| Controlador de mediciones | el del perfil | `SATEC - PM335_<tensión>` |
Valen para los dos: variable inicial 10 por campo (baja sola si no entra en 00-99), código de equipo sin barra
(152/01 → 15201), las 13 mediciones en todo campo numerado (se destilda por campo en «Datos…») y descripción del campo
editable en «Datos…» (el plano no la trae: «Entrada TR01», «LM1»…).
Sale de comparar `134.xlsx` (app) con `USRE-0119-SET-C-T-LI-Ls-0744_rD_DV_2.xlsx` (hecho a mano).

## Base central (`base/`, etapa 1 del generador nuevo)
- `base/senal.py` — `SenalBase`: UNA señal con todos los datos de una fila (identificación, nivel, campo, controlador,
  función, HMI, SCADA, estados o escalas MIN/MAX RAW y EU, unidad, tipo, tablero, placa, entrada, bornera y borne de
  tablero y de equipo, índice DNP, observaciones). Lo que no se conoce queda vacío. `origen` anota de dónde salió cada
  dato: `pdf`, `regla` o `manual` (lo manual no se degrada al recalcular).
- `base/proyecto_db.py` — `ProyectoDB`: la lista de `SenalBase` + PDFs, datos y carátula. Se llena con `Libro.base()`,
  se guarda/carga en JSON versionado y vuelve a un `Proyecto` con `a_proyecto()`: el Excel que sale de la base
  (`Libro.exportar_base`) es idéntico al de la exportación directa (lo prueban `tests/test_base.py`).
- Los proyectos guardados son versión 2 (llevan la base); los de la versión 1 siguen abriendo.
- Cada señal recuerda hoja y PDF de origen (para los avisos de la etapa 3). Tablero, borne e índice DNP todavía no se
  llenan (etapa 4). El índice DNP es solo una columna: queda vacía (el usuario pidió no calcularlo; 2026-11-16).
- Estados con el texto del Excel oficial: ABIERTO/CERRADO, LOCAL/REMOTO, TELE/DISTANCIA, AUTO/MAN, CON/SIN, con
  `error_0`/`error_1` de las Reglas.

## Formatos de salida (`formatos/`, etapa 2)
«Exportar Excel…» saca siempre el formato **completo** (el reducido se quitó de la pantalla a pedido del usuario el
2026-11-16; sigue existiendo en `formatos/reducido.json` por si se necesita desde código). Siempre sale un .xlsx normal,
editable. Un formato no borra nada de la base: solo decide qué columnas salen.
| Formato | Columnas | Aspecto |
|---|---|---|
| `reducido` | A-O: ITEM … UNITS (HMI, SCADA, mediciones y estados) | el de siempre |
| `completo` | A-AB como el Excel oficial de Senillosa: + tipo, tablero, placa, entrada, bornera y borne de tablero y de equipo, índice DNP, observaciones | títulos de 4 filas, combinaciones, anchos, alturas, filtro e impresión del oficial |
- Cada formato es `formatos/<id>.json` (qué campo de la base va en cada columna) + una plantilla de `plantillas/`. Para
  sumar una columna o un formato nuevo se edita el JSON; no hace falta tocar el programa.
- `formatos/escritor.py` escribe desde la base (`ProyectoDB`). La plantilla del completo sale del Excel oficial con
  `herramientas/extraer_plantilla.py` (`plantillas/USRE/USRE_listado.json`).
- Decisiones del usuario: la columna G «EXTERNAL NAME» queda vacía; se ignora la hoja oculta «ScaInit» del oficial; no se
  fija el panel (el oficial lo tiene en A64). El índice DNP sale vacío. Tablero, bornera y borne salen vacíos
  hasta la etapa 4. La carátula sigue la de la plantilla EPEN.

## Filas libres y controlador de medición
- Las filas libres (los 10 lugares que se dejan entre secciones para ampliaciones) salen **vacías, sin OFFSET ni ITEM**.
  El contador de offsets sí las salta, así que los números de las filas con datos tienen un salto. La base conserva el
  offset reservado de cada una.
- «Datos…» tiene una columna **Controlador (medición)** por campo, al lado de Controlador (ej. `15203_MED`). Si no la
  cambiás, se usa la del estilo (`SATEC - PM335_<tensión>` en USRE). Escalas y separación de offsets no se tocaron.

## Servicios auxiliares (SAA alterna / SAC continua)
Las alarmas del campo SAA del plano se reparten en SAA y SAC (Reglas). Prioridad: lo que elegís en el proyecto, lo que
ya contestaste (`perfiles/EPEN/servicios_auxiliares.json`) y lo que dice el propio rótulo (Vca / Vcc). La app pregunta
**solo** las alarmas que no sabe, en «Datos… → Servicios auxiliares» (rosa = sin asignar; quedan en SAA hasta que las
asignes), y recuerda las respuestas para los próximos proyectos. Las reservas quedan en SAA. Detalle y las 39
respuestas del TDCI de Senillosa: `propuestas/servicios_auxiliares.md`.

## Avisos (`avisos/`, etapa 3)
Pestaña **Avisos** y filas coloreadas en el Listado. Los avisos **solo informan: nunca cambian un dato**. Doble clic en un
aviso lleva a su fila (con campo, ITEM y hoja del PDF).
- **Celeste** = contradice una regla: TAG SCADA o TAG HMI repetido (salvo señal + comando, que comparten tag), OFFSET
  repetido entre dos digitales o dos mediciones (es válido entre señal y comando y entre digital y medición; las filas
  libres no cuentan), ITEM repetido, TAG fuera del formato de las Reglas, DESC. SCADA de más de 20 caracteres,
  controlador de otra tensión que el nivel (si nombra una), escala invertida, y **el Excel exportado no coincide con la base**
  (al exportar se vuelve a leer el archivo y se compara celda por celda).
- **Rosa** = falta información o revisar: DESC. SCADA sin abreviar a 20 caracteres, datos obligatorios que faltan
  (incluye escalas incompletas), TAG HMI y DESC. HMI que nombran otro equipo, conexionado incompleto (solo con el formato
  completo, resumido en un aviso) y lo que no se pudo interpretar al leer el PDF.
- Cada regla es una función de `avisos/reglas.py` en la lista `REGLAS`; sumar una no toca las demás. Los parámetros
  (campos especiales, códigos de medición, largo de DESC. SCADA) están en `perfiles/EPEN/avisos.json`.
- La pestaña se arma con `app/avisos_ui.py`.
- También avisa (rosa) cuando dos señales distintas quedan con la misma DESC. SCADA.

## Descripciones SCADA y tablero
- **Vocabulario** (`abreviaturas.json`): ampliado con las Reglas y con cómo abrevia el Excel oficial de Senillosa (INT, PP DISP
  GRL, F/U BAR 110VCC…). En los PDF de Senillosa las descripciones sin resolver bajaron de 85 a 3. En un campo especial
  (SAA, SAC, TP1…) el rótulo conserva su tensión (`F/U CMDO 33` / `F/U CMDO 13`) para que no se repitan.
- **Tablero** por campo: `TC` + dígito del nivel + `-` + campo (campo 103 → `TC1-03`), `TDCI` para SAA y SAC; se cambia en
  «Datos… → Tablero». Sale en la columna TABLERO del formato completo. Bornera y borne todavía no se leen (ver
  `PREGUNTAS_PENDIENTES.md`).

## Qué viene de dónde
| Pieza | Origen |
|---|---|
| Lector de PDF (`pdf_plano.py`), modelo, perfil EPEN, escritor de Excel, carátula | `..\codigo\` (lector con las mejoras de esta etapa) |
| Numeración de TAG/OFFSET, estados, DESC. SCADA, columnas UTR (P, S, T, W), campos leídos, multi-PDF | `..\pruebas\scada\` |
| Corrección a mano, guardar/abrir proyecto, carátula dentro de la ventana | nuevo en esta carpeta |

## Lo que NO entró (a pedido del usuario)
Motor SCADA viejo (`scada/`, glosario, «Propuestas SCADA»), paso de calidad (`calidad/`), cruce con listas de señales,
OCR y catálogo de controladores. Siguen en `..\codigo\` por si se necesitan.

## Pendiente / límites
- PDF que son imagen (sin texto): necesitan OCR (no instalado).
- BORNERA EQUIPO / N° DE BORNE EQUIPO (U, V), PROTOCOLO y POS DNP quedan vacíos.
- Las placas salen del funcional; el topográfico todavía no se lee (decisión: dejarlo para después).

## Pruebas

    python -m unittest discover -s tests
