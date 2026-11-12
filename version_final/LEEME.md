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
