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
  llenan (etapa 4). El índice DNP es el mismo número que el OFFSET (regla del usuario, 2026-11-13; si cambia, avisa).
- Estados con el texto del Excel oficial: ABIERTO/CERRADO, LOCAL/REMOTO, TELE/DISTANCIA, AUTO/MAN, CON/SIN, con
  `error_0`/`error_1` de las Reglas.

## Formatos de salida (`formatos/`, etapa 2)
«Exportar Excel…» pregunta el formato (sugiere *completo* para obras USRE y *reducido* para ETAP). Siempre sale un .xlsx
normal, editable. Elegir un formato no borra nada de la base: solo decide qué columnas salen.
| Formato | Columnas | Aspecto |
|---|---|---|
| `reducido` | A-O: ITEM … UNITS (HMI, SCADA, mediciones y estados) | el de siempre |
| `completo` | A-AB como el Excel oficial de Senillosa: + tipo, tablero, placa, entrada, bornera y borne de tablero y de equipo, índice DNP, observaciones | títulos de 4 filas, combinaciones, anchos, alturas, filtro e impresión del oficial |
- Cada formato es `formatos/<id>.json` (qué campo de la base va en cada columna) + una plantilla de `plantillas/`. Para
  sumar una columna o un formato nuevo se edita el JSON; no hace falta tocar el programa.
- `formatos/escritor.py` escribe desde la base (`ProyectoDB`). La plantilla del completo sale del Excel oficial con
  `herramientas/extraer_plantilla.py` (`plantillas/USRE/USRE_listado.json`).
- Decisiones del usuario: la columna G «EXTERNAL NAME» queda vacía; se ignora la hoja oculta «ScaInit» del oficial; no se
  fija el panel (el oficial lo tiene en A64). El índice DNP es igual al OFFSET. Tablero, bornera y borne salen vacíos
  hasta la etapa 4. La carátula sigue la de la plantilla EPEN.

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
