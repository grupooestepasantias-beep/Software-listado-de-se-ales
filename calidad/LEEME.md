# Paso de calidad del listado (`calidad/`)

Toma un listado ya generado (`listado.xlsx`), **normaliza la redacción** de las descripciones, lo **contrasta con un
Excel terminado**, completa encabezado y pie, **valida** el resultado y deja un **informe** y un **registro de cambios**.
Nunca pisa el original: escribe `<nombre>_final.xlsx` al lado.

## Cómo se usa
Desde la app: **Exportar Excel…** ya lo hace solo. Deja junto al Excel exportado:
`x_final.xlsx` (versión final) · `x_final_informe_calidad.md` · `x_final_cambios.csv`.

Por línea de comandos (desde `codigo\`):
```
python -m calidad ruta\listado.xlsx                      # -> listado_final.xlsx + informe + cambios.csv
python -m calidad listado.xlsx -o salida.xlsx --ref ETAP.xlsx
python -m calidad listado.xlsx --sin-ref                  # sin comparar con una referencia
```
Desde código: `from calidad import mejorar_archivo; informe = mejorar_archivo("listado.xlsx")`
(`informe.aprobado`, `.bloqueantes`, `.pendientes`, `.resumen_corto()`). Código de salida 1 si hay errores bloqueantes.

## Qué hace (y qué no)
- **Solo** toca las columnas de texto: DESCRIP (C), DESC. HMI (G), DESC. SCADA (J). Nunca ITEM, NIVEL, CONTROLADOR, FUNCION,
  TAG HMI, TAG SCADA, OFFSET, estados, unidades ni UTR. Los códigos de equipo (229SB04, 2TV04, TC3-03…) se enmascaran.
- Reglas (todas configurables en `perfiles/<cliente>/redaccion.json`): espacios, `Campo04` → `Campo 04`, `2TV04- X` → `2TV04 - X`,
  unidad de tensión uniforme (`33KV`/`33Kv`/`33 KV`/`6.6KV` → `33kV`/`6,6kV`), siglas (`Ssaa` → `SSAA`, `ok` → `OK`), errores
  conocidos (diccionario), tildes según el sistema destino.
- **Tildes: por defecto se QUITAN (modo `quitar`)**, porque el ETAP terminado no tiene ninguna tilde ni ñ en las descripciones
  (0 de ~1200 celdas) y los sistemas HMI/SCADA reciben ASCII. Si el cliente quiere ortografía completa: `"tildes": {"modo": "agregar"}`
  (usa el diccionario `tildes.diccionario`: tension → tensión, proteccion → protección, senalizacion → señalización…).
- Un número de nivel sin unidad (`Campo 04 33 Falta…`) se completa **solo si** coincide con el NIVEL de la fila.
- Lo dudoso **no se corrige**: texto con otro nivel que la fila (`33kV` en un campo de 132KV), palabras repetidas, correcciones que
  pasarían de 20 caracteres en DESC. SCADA, diferencias con la referencia. Quedan en el informe (sección 4) y en el CSV (`estado=revisar`).

## Comparación con la referencia
Solo vincula señales con **el mismo TAG SCADA, la misma FUNCION, un único candidato y el mismo campo** (primer término de DESC. HMI).
Con eso: texto igual → coincide; igual salvo mayúsculas/tildes/espacios → se adopta el texto aprobado; distinto → **no se copia**,
se informa. Nunca compara por número de fila ni por parecido. Dos proyectos distintos casi no comparten TAG: es normal que den 0 vínculos.
El informe también lista defectos de la propia referencia (espacios dobles, `132KV` vs `132kV`…); no se replican.

## Validaciones (informe, sección 2)
Bloqueantes: el libro se reabre; hojas presentes; **ninguna celda cambia fuera del registro**; identificadores intactos; mismas filas y
mismos TAG/FUNCION en el mismo orden; descripciones no vaciadas; DESC. SCADA no pasa de 20 por la corrección; no se crean repetidas;
formato (celdas combinadas, anchos, alturas, filtro, paneles, impresión, formato condicional, imágenes) igual al de entrada.
Advertencias: DESC. SCADA repetidas, TAG repetidos, ortografía residual (solo con el diccionario configurado), segunda pasada estable,
impresión, encabezado/pie, carátula completa. Recomendaciones: formato del NIVEL, largo de DESC. HMI desconocido.

## Límites (el informe también los dice)
No hay corrector ortográfico general instalado: solo se detectan los errores del diccionario. No se valida el significado técnico.
Faltas de ortografía fuera del diccionario, o datos que faltan en la fuente, no se detectan ni se inventan.

## Reproducibilidad
Mismos datos + mismo `redaccion.json` + mismo código → mismo resultado; volver a pasar el `_final` no cambia nada (hay prueba).
Pruebas: `python -m unittest tests.test_calidad` (38).
