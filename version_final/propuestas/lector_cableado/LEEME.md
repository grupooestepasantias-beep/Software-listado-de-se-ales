# Lector de bornes desde las hojas de cableado (aporte de la app «Protocolos FAT y SAT»)

Fecha: 2026-11-17. Módulo nuevo `cableado.py` + `tests/test_cableado.py`. No cambia lo que ya funciona: **suma** una segunda
fuente de bornes. Salida: `FilaBorne` (la misma de `bornes.py`, con `descripcion` = nombre de la señal), así que
`bornes.buscar()`, `desde_pdf.borne_de()` y el guardado del proyecto la usan sin cambios.

## El hallazgo
`estudio_topograficos.md` concluyó que el borne de cada señal «no está en ningún PDF» salvo en el TDCI. En los **funcionales**
sí está: cada hoja de cableado (hojas 4 a 38 del 0811) trae, arriba, una franja de celdas con el **nombre de la señal** y,
abajo, una fila de bornes dibujados como círculos con su número y la bornera a la izquierda:

    [ Subir Tap ][      Bajar Tap      ][ Parada de emergencia ]
       (31)          (32)      (33)         (34)       (35)         <- «-XT.1:»

La señal de cada borne es la celda de arriba. Es lo mismo que resuelve el lector de la app de FAT/SAT para los planos de
Arroyito (nombre de la columna + elemento/borne debajo), adaptado a este formato.

## Cómo lee (`cableado.py`)
1. **OCR fino**: la hoja a 250 dpi **sin reducir** la imagen (`RapidOCR(max_side_len=5000)`; el valor por defecto reduce
   cualquier imagen a 2000 px de lado y el texto chico —números de borne, la T de «289T»— se pierde o se confunde).
2. **Celdas**: salen de las **líneas verticales del encabezado** (vectores del PDF, `page.get_drawings()`), no del texto. Si
   a las celdas de los extremos les falta la línea, se agregan con el ancho típico mientras haya texto fuera.
3. **Nombres**: texto de la fila de nombres de cada celda (se descartan los títulos de grupo, que abarcan varias celdas, y las
   referencias de cable que quedan debajo). Se limpian los ceros por oes (`INTERRUPT0R` → `INTERRUPTOR`) y las palabras pegadas
   a números (`252/01CERRADO`).
4. **Bornes**: los números de la fila que tiene una bornera a la izquierda (`-X1.1:`, `-XT.1:`, `-XDI.G:`…). El círculo se lee
   como `O`/`0` pegado al número (`21O`, `270`): se corrige por fila. Se ignoran las filas rotuladas **sin** dos puntos
   (`-X1.1`): son el cable al común de la bobina (bornes 24-28), no la señal.
5. Cada borne queda con el nombre de la celda en la que está. Dos bornes bajo una celda → dos filas con el mismo nombre
   (`buscar` toma la primera y marca la otra como alternativa: la señal queda «dudosa», como siempre).
6. Reservas no se emiten. Todo queda en la caché de `%TEMP%\listado_ocr_cache` (≈ 10 s por hoja la primera vez).

## Integración (hecha en la copia de trabajo; `bornes.py` y `ventana.py`)
- `bornes.leer_bornes()` = tablas del final **+** `cableado.leer_cableado()`. Las tablas mandan: del cableado solo entran los
  `(bornera, borne)` que las tablas no traen. Si el cableado falla, se ignora (el listado sale igual).
- `ventana.py`: el avance muestra «Leyendo los bornes de las hojas de cableado… hoja n de N».

## Verificación
- **Contra el Excel oficial** (campo 201, hojas 11 y 12 del 0811 rev4): X1.1 61 a 71 y 73 salen con el nombre correcto
  (`INTERRUPTOR 252/01 CERRADO` = 61, `ABIERTO` = 62, `EN LOCAL` = 63, `EN REMOTO` = 64, `SECCIONADOR 289/01 CERRADO` = 65,
  `EN LOCAL` = 67, `EN REMOTO` = 68, `RESORTE DESCARGADO` = 71). Hoja 20: `Subir Tap` 31, `Bajar Tap` 32-33,
  `Parada de emergencia` 34-35, como en el plano.
- **Contra las tablas del final** (hojas 52, 53 y 56): de 36 bornes que se pueden comparar, 33 coinciden y 3 difieren por el
  OCR de la tabla, no por el cableado (la tabla lee `Seccionador 289/ 01 Abierto` donde el cableado y el plano dicen `289T/01`;
  `Linite inferior`; `Imcompleto`). En el borne 70 el cableado es el correcto.
- `tests/test_cableado.py` (10 pruebas) usa lecturas OCR reales guardadas en `tests/datos/cableado_F0811_h11/12/20.json`;
  no necesita el OCR instalado. La suite completa pasa (222 pruebas).

## Prueba de punta a punta (0811 rev4, campo 201 + 2?: 71 señales con rótulo)
Con `Libro.agregar_pdf` y la lectura de bornes completa: solo con las tablas del final **59 de 71** señales tienen bornera y
borne; tablas + cableado, **61 de 71**; solo cableado, 15 de 71 (hecho con la primera versión del módulo, antes de la
relectura ampliada de las filas). En el 0811 las tablas ya cubren casi todo; el cableado **completa y confirma**, y es la
única fuente en los planos sin tablas del final. Cuesta tiempo: ≈ 10 s por hoja de cableado la primera vez (todo el 0811
tardó 526 s con las tablas), después queda en la caché.

## Placas dibujadas (`placas.py`)
En el TCONTROL 13,2 kV (`…Ad-0821_r3`) la placa de cada módulo (`UTR1.1.1` … `UTR1.1.4`) está **dibujada**, no es texto, y
la columna PLACA salía vacía. `placas.por_ocr(page, cantidad)` lee con OCR la franja de arriba de la hoja y devuelve las
placas de izquierda a derecha; `pdf_plano._placas_de_modulos` lo usa cuando no hay placas en el texto y solo si hay una
por módulo (si no, queda vacía). Resultado en el 0821 r3: **167 de 167** filas con placa (antes 0). 6 pruebas en
`tests/test_placas.py` (con lecturas simuladas).

## Qué sigue sin fuente en el plano
- **TABLERO (2.ª columna, la del equipo), BORNERA EQUIPO y N° DE BORNE EQUIPO**: no están en ninguno de los PDF revisados
  (ni en el texto ni en las hojas de cableado); salen del conexionado del equipo primario. Hace falta la regla o una lista.

## Qué no resuelve todavía (con los números)
De las 39 hojas del 0811 se leen **103 bornes distintos** (sin repetidos), pero no todas las hojas tienen la misma forma:
- **Hojas con varias filas de bornes** (8, 9, 10: comandos y relés): salen filas, pero los nombres son del tipo
  `INTERRUPTOR 252/01 CERRAR` para varios bornes distintos (a revisar en el plano antes de usarlos).
- **Hojas sin salida** (14, 15, 19: bornera `XDI.1`/`XA.1`/`XDO.1` de la UTR): la fila de números está en otra forma
  (numeración 1-8 del módulo); hace falta ver una hoja de cada una.
- **Comandos**: `desde_pdf` todavía no pide borne para los comandos (`orden == COMANDO`); se puede agregar con
  `borne_de(f.campo, texto_del_comando)` una vez revisadas las hojas 9 y 10.
- Las hojas con muchas columnas se apoyan en que cada celda tenga su nombre arriba; si una celda tiene el nombre en el
  encabezado de otra hoja, queda sin nombre y no se emite.

## Sobre `ocr.py`
`ocr._ocr()` crea `RapidOCR()` con la configuración por defecto, que **reduce** las imágenes grandes (lado máximo 2000 px).
Una hoja A3 a 200 dpi mide 3307 × 2339: se achica antes de leerla. En los planos de Arroyito eso hacía perder textos chicos
(`-QS`, `-QM2`); con `max_side_len=5000` se leen. Es probable que explique parte de las confusiones 229T / 289T de las
tablas, pero **no lo probé con `leer_tabla`**: conviene probar `RapidOCR(max_side_len=5000, min_side_len=30)` en `ocr._ocr()`
con las hojas 52, 53 y 56 y ver si mejora la lectura (cambia el tiempo por hoja).

## Conexionado de equipo (BORNERA EQUIPO / N° DE BORNE EQUIPO) — `conexionado.py`
**Qué dice el listado oficial** (`senillosa\USRE-0119-SET-C-T-LI-Ls-0744_rD_DV_2.xlsx`, 450 filas):
- Las columnas **TABLERO** de las posiciones U y X quedan **siempre vacías** en el oficial (0 de 450). La única TABLERO con dato es la R
  (`TC2-01`…), que el programa ya completa.
- **BORNERA EQUIPO / N° DE BORNE EQUIPO** (Y, Z): 107 de 450 filas. Son los bornes del **equipo de campo** (interruptor `XP`/17,
  seccionador `L0`/41, protección `1XP1`/22, reconectador `IOM-XP1`/12…). No están en ningún PDF; **son los mismos para el mismo
  equipo** de un campo a otro, y cambian con el nivel y el tipo de campo (seccionador cerrado: `L0`/41 en la entrada, `L0`/2 en las líneas).

**Cómo se hizo general (para cualquier obra y listado):** nada está escrito en el código.
1. `herramientas/aprender_conexionado.py <listado oficial.xlsx> [--agregar]` lee cualquier listado con ese formato (busca las columnas por
   su **título**, no por la letra) y guarda reglas en `perfiles/EPEN/conexionado_equipos.json`: rótulo normalizado (sin tildes, sin el
   código de equipo: `Interruptor 252 / 01 Abierto` = `Interruptor 25201 Abierto` = `interruptor # abierto`; reconectador = interruptor;
   puesta a tierra `#t`) + nivel + tipo de campo -> (bornera, borne). Si la bornera cambia solo con el número de campo (campo 103 -> `1XP3`,
   104 -> `1XP4`) guarda una plantilla `1XP{c}`.
2. `desde_pdf` completa las dos columnas **solo si todas las reglas que coinciden dan el mismo valor**; busca por rótulo exacto y, si no, por
   parecido (`Seccionado 289 / 01 Falta Tensión` -> `Seccionador # falta tensión`). Si hay dudas, queda vacío. Lo completado figura como
   dato de la **regla** (no del plano): hay que confirmarlo contra el conexionado de cada obra.
3. Para otra obra o cliente: aprender su listado oficial (`--agregar` suma, no pisa) o editar el JSON a mano. Sin reglas, las columnas quedan
   vacías como hoy.

**Condición:** el tipo de campo sale de la **descripción del campo** (primera palabra: `Entrada`, `LM`, `TR`…): hay que cargarla en
«Datos… → Descripción del campo» (`Entrada TR01`, `LM1`…). Con la descripción por defecto (`Campo 103`) los casos que dependen del tipo
de campo quedan vacíos en vez de elegir uno.

**Prueba con el listado oficial** (reglas aprendidas de ese mismo Excel; el programa genera el listado desde el PDF y se compara contra el oficial):
- 0821 r3 (TCONTROL 13,2 kV) con descripciones `Entrada TR01`/`LM1`/`LM2`/`LM3`: 30 filas con equipo; de las 22 que se pueden comparar con
  el oficial, **22 iguales, 0 distintas, 0 que falten**. Sin cargar las descripciones: 6 filas (las no ambiguas).
- 0811 rev4 (campo 201): 9 de 9 comparables iguales, 0 distintas.
- Limitación honesta: se aprendió de UNA obra; cubre interruptor, seccionador, puesta a tierra, reconectador, protecciones y varias alarmas
  de Senillosa. Lo que no está en el listado oficial (otros equipos) queda vacío hasta aprender otro listado.
