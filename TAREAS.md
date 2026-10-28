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
| 1.5 | Leer plantilla del ejemplo ETAP (anchos, estilos, merges, filtros, impresión) | PC-B | [x] 2026-10-27 (1.5a-c hechas) |
| 1.5a | Verificar Python/openpyxl en PC-B y `safe.directory` (cierra 1.1 de PC-B) | PC-B | [x] 2026-10-27 Python 3.14.7 + openpyxl 3.1.5 (instalado con autorización); 13 tests OK. git no se usó en PC-B |
| 1.5b | `herramientas/extraer_plantilla.py` (solo lectura del ejemplo): anchos, alturas, estilos filas 1-5 y de datos, merges de Caratula y EPEN, autofiltro A5:W584, área de impresión, títulos 1:5, formato condicional col. J | PC-B | [x] 2026-10-27 |
| 1.5c | Guardar resultado en `plantillas/<id_perfil>/` (carpeta propia de PC-B) | PC-B | [x] 2026-10-27 `plantillas/EPEN/EPEN_plantilla.json` (~580 KB: caratula 72 merges/721 celdas; listado con anchos, encabezado, estilos filas 6-8, filtro A5:W584, impresión, 4 reglas de duplicados en J). PC-A: agregar en perfil.json `"plantilla": "plantillas/EPEN"` |
| 1.6 | `excel_writer` EPEN con datos fijos que reproduzcan filas del ejemplo | PC-B | [x] 2026-10-27 (1.6a-d hechas) |
| 1.6a | `excel_writer.py`: `escribir_xlsx(proyecto, perfil, ruta)`; hojas/columnas/orden salen del perfil (no fijos); PROTOCOLO, POS DNP, BORNERA, N° BORNE vacías | PC-B | [x] 2026-10-27 |
| 1.6b | Encabezado filas 1-5 + datos desde fila 6; merges verticales B (NIVEL), C (DESCRIP), E (FUNCION) | PC-B | [x] 2026-10-27 (también autofiltro, impresión, títulos 1:5 y duplicados en DESC. SCADA) |
| 1.6c | Caratula con datos fijos (referencias, revisiones, cliente/obra, nº documento un carácter por celda, "Hoja 1 de 2") | PC-B | [x] 2026-10-27 (posiciones en `caratula_campos` de la plantilla; "1 de {total}" desde `perfil.datos["hojas"]["total"]`; el nº de documento llega armado y debe tener 20 caracteres sin guiones) |
| 1.6d | `Proyecto` de prueba armado a mano con filas del ejemplo + `tests/test_excel_writer.py` (celda por celda y merges contra el ETAP) | PC-B | [x] 2026-10-27 filas 6-84 del campo 303 + carátula; 21 tests OK en total |
| 1.7 | Esqueleto de tags y lista de preguntas | PC-A | [x] 2026-10-27 `tags.py` (construir/parsear/validar TAG, DESC. SCADA, próxima variable) + `tests/test_tags.py`; verificado contra el ejemplo ETAP: 482 tags estándar rearmados idénticos, 11 no estándar. 13 tests OK |

## Semana 2 — Núcleo
| 2.1 | Generador: orden, ITEM, offsets, comando↔señalización, estados, UNITS | PC-A | [x] 2026-10-28 `generador.py` (`generar(proyecto, perfil)` → lista de avisos) + `tests/test_generador.py`. Completa orden por función, TAG SCADA, OFFSET (contador por tipo desde `offsets_iniciales`), S0-S3/RAW, UNITS, TAG/DESC. HMI, DESC. SCADA (solo si entra en 20), RESERVA, 2ª fila de doble bit y comando con el tag/offset de su señalización. Respeta `Senal.fijos`. ITEM lo numera el escritor. Probado con `escribir_xlsx` de PC-B. 53 tests OK |
| 2.2 | Caratula + formulario de proyecto + pantalla de inicio | PC-B | [x] 2026-10-27 `app/` (`python -m app`): pantalla de inicio (perfil, nuevo / abrir .json), formulario con carátula, firmas, referencias, revisiones y numeración (ITEM y OFFSET inicial por DI/AI/DO/AO), guardar JSON y exportar Excel. Lógica en `app/validacion.py`, tests en `tests/test_app.py` (29 tests OK en total). "Cargar Excel existente" queda para 3.2 |

## Semana 3 — Completo
| 3.1 | Asignación placa/entrada, RESERVA, mediciones RAW/EU, validador | PC-A | [x] 2026-10-28 `asignacion_utr.py` (`asignar_placas(proyecto, perfil)`: consume `Proyecto.modulos` en orden; DI 1 entrada por fila incl. 2ª fila y reservas; DO doble bit "1/2"; analógicas N/A; respeta `fijos`), `validador.py` (`validar_proyecto(proyecto, perfil)` → lista de `Problema` error/aviso) y `tests/test_utr_validador.py` + `tests/ejemplo_etap.py` (carga el ETAP como Proyecto). RESERVA y RAW/EU ya estaban en el generador. 84 tests OK. UI de módulos y botón "Validar" quedan para PC-B |
| 3.2 | `excel_reader`, editor de señales, merges nivel/campo/función | PC-B | [ ] (subtareas: leer Excel existente a `Proyecto`; editor de señales con campos "fijos"; recalcular merges) |
| 3.3 | Cargar PDF de plano de ingeniería y armar la lista de señales (hoja 2): leer rótulos de bornes/módulos con pymupdf y proponer filas | PC-B (lectura) / PC-A (reglas de tags, estados, placa/entrada) | [~] 2026-10-28 Primera versión de PC-B: `pdf_plano.py` + `plantillas/EPEN/lectura_plano.json` (vocabulario) + pestaña "Señales (PDF)" en la app. Cada columna rotulada = una señal; Positivo/Negativo ignorados (confirmado por el usuario); pares Abierto/Cerrado, Remoto/Local, en D/en T → 1 señal de doble bit; Cierre/Apertura → COMANDO DO; Reserva → RESERVA. Plano 6402: págs. 29/51/73 = campos 04/05/06 de 33KV, 53 señales c/u. Deja vacíos TAG, OFFSET, DESC. SCADA, DESC. HMI (generador 2.1 de PC-A) y PLACA/ENTRADA (el rótulo del módulo es un dibujo). Pendiente: reglas de alarma vs. falla, medición (AI), nombres de campo. 36 tests OK |

## Etapa actual (2026-10-28): REINICIO — solo columnas A-G
La app muestra y exporta únicamente A ITEM · B NIVEL · C DESCRIP · D CONTROLADOR · E FUNCION · F TAG (HMI) · G DESC. HMI; el PDF del plano llena la tabla y se corrige a mano. Todo lo demás (PLACA, ENTRADA, TIPO, OBSERVACIONES, SCADA, carátula) queda fuera. Se borró la lógica SCADA de PC-A del árbol de trabajo (sigue en el commit a836f74 y en `respaldo/`). Las filas de las semanas 2-3 que hablan de generador/validador/UTR quedan SUSPENDIDAS hasta nueva orden.

## Semana 4 — Cierre
| 4.1 | Pruebas contra ejemplo ETAP y ajuste de reglas | PC-A | [ ] |
| 4.2 | Exportar, errores, manual, empaquetado, aceptación | PC-B | [ ] (subtareas: exportar desde la app; mensajes de error del validador; manual; PyInstaller; prueba end-to-end con el usuario) |
