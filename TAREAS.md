# TAREAS — Software listado de señales

Leer al empezar cada sesión y actualizar al terminar. Si ves cambios que no hiciste, los hizo la otra PC: no los reviertas.
Reglas: `git push` SOLO cuando el usuario lo indique. Cada PC toca solo sus módulos.
Estados: [ ] pendiente · [~] en curso · [x] hecho · [!] bloqueado · [-] suspendido

## Etapa actual: tabla A-G desde el plano PDF (PC-B)
| # | Tarea | Dueño | Estado |
|---|---|---|---|
| A1 | Leer el plano PDF (`pdf_plano.py`) y llenar la tabla: NIVEL, DESCRIP, CONTROLADOR, FUNCION, TAG HMI, DESC. HMI (`hmi.py`) | PC-B | [x] |
| A2 | App de una ventana (`python -m app`): cargar PDF, editar tabla, guardar/abrir JSON, exportar Excel A-G | PC-B | [x] |
| A3 | Mediciones al final de cada campo (13 del ETAP, controlador editable) | PC-B | [x] 2026-10-29 |
| A4 | Probar con otros planos y ajustar abreviaturas / reglas | PC-B | [~] |

## Carátula (retomada el 29/10)
| # | Tarea | Dueño | Estado |
|---|---|---|---|
| C1 | Herramienta de prueba solo de carátula en `..\prueba_caratula\` (formulario + Excel + tests, idéntica al ETAP, logos elegibles y sin el sello) | PC-A | [x] 2026-10-29 |
| C2 | Probar el formulario con el usuario y ajustar campos (número de documento por partes, fechas, referencias) | PC-A | [ ] |
| C3 | Integrar la carátula a la app principal de `codigo\` (pestaña «Carátula», logos elegibles, una hoja A4 en el Excel) | PC-A (pedido del usuario) | [x] 2026-10-29 `app/caratula_ui.py`, `excel_writer.py`, `modelo.Caratula` |

## SCADA H-O (retomado el 29/10 por pedido del usuario, en `..\prueba_scada\`)
| # | Tarea | Dueño | Estado |
|---|---|---|---|
| S1 | Motor SCADA por perfil de cliente: tag, offset, estados/RAW/EU, unidades, comando↔señalización, reservas (`scada_gen.py`, `perfiles/EPEN/scada.json`) | PC-A | [x] 2026-10-29 |
| S2 | DESC. SCADA de 20 caracteres: glosario aprendido del ETAP + reglas + propuesta por palabras a confirmar (`descripcion.py`) | PC-A | [x] 2026-10-29 |
| S3 | Evaluación contra el ETAP (`evaluar.py`), comparación con USRE (`diferencias_clientes.md`), corrida con el plano real (`demo_plano.py`), 32 tests | PC-A | [x] 2026-10-29 |
| S4 | Revisar con el usuario las reglas "pendiente" del perfil (variable inicial, separación de offsets, SEC BA vs SBA, MARCHA/PARADA vs PAR/ARR) y las propuestas de DESC. SCADA | PC-A + usuario | [ ] |
| S5 | Integrar H-O a la app principal de `codigo\` (botón «Generar SCADA…», offsets iniciales, columnas H-O, «Propuestas SCADA…» para confirmar y recordar) | PC-A (pedido del usuario) | [x] 2026-10-29 paquete `scada/`, `app/scada_ui.py`, `app/principal.py` |
| I1 | **App completa con las 3 partes** (carátula + A-G + H-O) y exportación a UN Excel; 123 tests OK; corrida real con el plano 6402 (`..\prueba_scada\integrado.xlsx`) | PC-A | [x] 2026-10-29 |
| I2 | Probar la app integrada con otros planos, ajustar y pulir la interfaz | PC-B | [ ] |

## Cierre
| # | Tarea | Dueño | Estado |
|---|---|---|---|
| F1 | Manual de uso, empaquetado (.exe) y prueba de aceptación con el usuario | PC-B | [ ] |

## Suspendido hasta nueva orden
PLACA/ENTRADA automáticas, validador y lector de Excel existente. (SCADA H-O ya no está suspendido: ver arriba.) El código de PC-A (`generador.py`, `tags.py`, `validador.py`, `asignacion_utr.py`) está en el commit `a836f74` y en `..\respaldo\codigo_2026-10-28_antes_de_limpiar.zip`. Para recuperarlo: `git checkout a836f74 -- generador.py tags.py validador.py asignacion_utr.py`.