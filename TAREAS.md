# TAREAS — Software listado de señales

Leer al empezar cada sesión y actualizar al terminar. Si ves cambios que no hiciste, los hizo la otra PC: no los reviertas.
Reglas: `git push` SOLO cuando el usuario lo indique. Cada PC toca solo sus módulos. Plan completo: ver plan aprobado (4 semanas, 4 h/día por PC).

Estados: [ ] pendiente · [~] en curso · [x] hecho · [!] bloqueado

## Semana 1 — Base y reglas
| # | Tarea | Dueño | Estado |
|---|---|---|---|
| 1.1 | Instalar/verificar git en cada PC y probar acceso al repo | PC-A y PC-B | [~] Primera PC lista (git 2.56, openpyxl, pymupdf; `codigo/` enlazada a origin/main). Falta: la otra PC instala git y ejecuta `git config --global --add safe.directory "//192.168.15.120/PasantiasMM/Sofware listado/codigo"` |
| 1.2 | Estructura de `codigo/` y archivos de coordinación | PC-A | [x] 2026-10-27 |
| 1.3 | `modelo.py` + estructura de perfiles de cliente | PC-A | [x] 2026-10-27 `modelo.py`, `perfiles.py`, `perfiles/EPEN/*.json`, `tests/test_perfiles_modelo.py` (7 tests OK: `python -m unittest discover -s tests`) |
| 1.4 | Extraer tablas del PDF de lineamientos al perfil EPEN (JSON) | PC-A | [x] cargado desde el PDF (pymupdf); quedan dudas en PREGUNTAS.md (AS repetido, AFP, CBC, 32767 vs 32768, campos especiales) |
| 1.5 | Leer plantilla del ejemplo ETAP (anchos, estilos, merges, filtros, impresión) | PC-B | [ ] |
| 1.6 | `excel_writer` EPEN con datos fijos que reproduzcan filas del ejemplo | PC-B | [ ] |
| 1.7 | Esqueleto de tags y lista de preguntas | PC-A | [x] 2026-10-27 `tags.py` (construir/parsear/validar TAG, DESC. SCADA, próxima variable) + `tests/test_tags.py`; verificado contra el ejemplo ETAP: 482 tags estándar rearmados idénticos, 11 no estándar. 13 tests OK |

## Semana 2 — Núcleo
| 2.1 | Generador: orden, ITEM, offsets, comando↔señalización, estados, UNITS | PC-A | [ ] |
| 2.2 | Caratula + formulario de proyecto + pantalla de inicio | PC-B | [ ] |

## Semana 3 — Completo
| 3.1 | Asignación placa/entrada, RESERVA, mediciones RAW/EU, validador | PC-A | [ ] |
| 3.2 | `excel_reader`, editor de señales, merges nivel/campo/función | PC-B | [ ] |

## Semana 4 — Cierre
| 4.1 | Pruebas contra ejemplo ETAP y ajuste de reglas | PC-A | [ ] |
| 4.2 | Exportar, errores, manual, empaquetado, aceptación | PC-B | [ ] |
