# BITACORA

Una entrada por PC y por día. Sirve para armar el resumen del push (solo cuando el usuario lo indique).

## 2026-10-27 — primera PC en conectarse
- Aprobado el plan (multi-cliente: EPEN es el primer perfil).
- Creada `codigo/` con TAREAS.md, BITACORA.md y PREGUNTAS.md.
- Instalados en esta PC (autorizado): git 2.56, openpyxl 3.1.5, pymupdf 2.0.
- `codigo/` es ahora un repo git con origin = GitHub (rama main, 1 commit "Initial commit" con README.md). Lectura del repo verificada; NO se hizo push ni commit.
- Para la otra PC: instalar git y agregar `safe.directory` (ver TAREAS.md 1.1).
- Se leyó el PDF de lineamientos solo en parte (tipografía propia): se relee en la semana 1.

## 2026-10-27 — PC que tomó 1.3 (la otra PC ya quedó conectada, según el usuario)
- PDF de lineamientos releído completo con pymupdf (3 páginas: estados, formato de TAG, abreviaturas de DESC. SCADA).
- Hecho 1.3 y 1.4: `modelo.py` (Proyecto/Caratula/Nivel/Campo/Senal, guardar/cargar JSON), `perfiles.py` (cargar, validar, listar, duplicar), `perfiles/EPEN/` (perfil, estados, sufijos_medicion, unidades, abreviaturas) y 7 tests OK.
- Corrección al plan: CBC no es "regulador de tensión"; el PDF da RAT = regulador automático de tensión y deja CBC sin significado.
- Sin commit ni push (solo cuando el usuario lo indique).
- Hecho 1.7: `tags.py` y `tests/test_tags.py`. Patrón `{nivel}{campo}.{variable:02d}{bits}{C}` / `...{código_medición}` confirmado contra el ejemplo: 482 tags estándar se rearman idénticos; 46 reservas con "N/A" y 11 tags no estándar (TP1.01APOS, TP1.02AIMTA, SACC.01V48…06I110, UTR02T_132…06T_SSAA).
- El ejemplo usa SACA/SACC/UTR como campos especiales (el PDF dice SAA/SAC): agregados al perfil EPEN marcados como "del ejemplo".
- Creado `CONTEXTO_PARA_CLAUDE.md`: resumen completo del proyecto para que la otra cuenta tenga todo el contexto y pueda editar la carpeta. La otra cuenta debe leerlo primero.
- Siguiente en el tablero: Semana 1 de PC-A completa; 2.1 (generador) depende de las respuestas a PREGUNTAS.md. PC-B: 1.5 y 1.6.

## 2026-10-27 — PC-B (se conecta; el usuario confirmó que esta es la PC-B)
- Leído CONTEXTO_PARA_CLAUDE.md, TAREAS.md, BITACORA.md y PREGUNTAS.md. No se tocó código ni archivos de PC-A.
- TAREAS.md: 1.5 y 1.6 desglosadas en subtareas (1.5a-c, 1.6a-d); 2.2, 3.2 y 4.2 con subtareas resumidas.
- Archivos que PC-B va a crear: `excel_writer.py`, `herramientas/extraer_plantilla.py`, `plantillas/EPEN_plantilla.json`, `tests/test_excel_writer.py`.
- Sin commit ni push.

## 2026-10-27 — PC-B (cont.)
- Recibidas respuestas de PC-A/usuario: plantilla en `plantillas/<id_perfil>/`; "1 de {total}" sale de `perfil.datos["hojas"]["total"]`; nº de documento llega ya armado (`Caratula.numero_documento`) y se reparte por celda según la plantilla; columnas inactivas (Q, R, U, V) vacías y sin combinar.
- Instalado openpyxl 3.1.5 en PC-B (autorizado). 13 tests OK.
- Hecho 1.5a-c: `herramientas/extraer_plantilla.py` y `plantillas/EPEN/EPEN_plantilla.json`. Siguiente: 1.6a.

- PC-B: hechas 1.6a-d. `excel_writer.py` (`escribir_xlsx`, `cargar_plantilla`), `tests/test_excel_writer.py` (8 tests; filas 6-84 del ETAP idénticas en columnas activas, merges B/C/E, encabezado, carátula). Total 21 tests OK. `extraer_plantilla.py` ahora guarda también `caratula_campos` (posición de cada dato de la carátula); plantilla regenerada.
- Supuestos de PC-B (pendientes de confirmar): ITEM correlativo en todas las filas desde `item_inicial`; revisiones de más antigua a más nueva, escritas de abajo hacia arriba; `Senal.funcion` RESERVA se escribe como "RESERVA".
- Siguiente para PC-B: 2.2 (carátula + formulario + pantalla de inicio). Pedido a PC-A: clave `"plantilla": "plantillas/EPEN"` en perfil.json.

- PC-B: hecha 2.2. `app/` (`python -m app`): `principal.py` (Tkinter: Inicio + Formulario con pestañas Proyecto / Firmas y pie / Referencias / Revisiones / Numeración), `validacion.py` (lógica sin GUI), `tests/test_app.py`. Obligatorios: cliente, obra, título, nº de documento (20 caracteres sin guiones, largo tomado de la plantilla), ITEM y OFFSET inicial de cada tipo. Límites de referencias (14) y revisiones (4) vienen de la plantilla. 29 tests OK; la ventana se probó solo por código, no a ojo. Siguiente PC-B: 3.2 (necesita el generador 2.1 de PC-A para tener señales reales).

- PC-B: cambios pedidos por el usuario: (1) el nombre del cliente se escribe a mano en la pantalla de inicio (ya no sale del perfil; se quitó el cliente por defecto del escritor); (2) el nº de documento admite hasta 20 caracteres sin guiones y puede tener menos (error solo si excede); tests actualizados (excel_writer 9 OK, app 8 OK). Instalado pymupdf en PC-B (autorizado). Inspeccionado el plano ETAP-0325-...-6402_1.pdf: 93 páginas, texto extraíble; pág. 29/51/73 listan bornes con rótulos (ej. "Seccionador 229SL04 Remoto/Local/Abierto/Cerrado", "Reserva", "48 VCC"). Anotada la tarea 3.3.

## 2026-10-28 — PC-A (mientras PC-B trabaja en 3.3)
- Revisados los cambios de PC-B (sin tocarlos). Hecho lo que PC-B pidió: `"plantilla": "plantillas/EPEN"` en `perfiles/EPEN/perfil.json`.
- **Hecha 2.1**: `generador.py` + `tests/test_generador.py` (17 tests; total 53 OK). Probado de punta a punta con `escribir_xlsx`.
- **Cambios en `modelo.py` (compatibles hacia atrás: campos nuevos de `Senal` con valor por defecto)**: `par` (enlaza señalización y comando: mismo texto en ambas), `obs_segunda_fila` (texto de la 2ª fila del doble bit) y `segunda_fila` (la crea el generador). **PC-B**: para que el generador enlace comando↔señalización, el lector de planos puede poner en `par` el nombre del equipo (ej. "Seccionador 329SA03") y en `obs_segunda_fila` el texto del segundo estado (ej. "... Cerrado"). El escritor no necesita cambios: el generador entrega la 2ª fila con tag/descripciones vacíos, como el ejemplo. Llamada: `avisos = generador.generar(proyecto, perfil)` con `proyecto.offsets_iniciales` cargado (DI, AI, DO, AO que se usen); si falta uno lanza `ErrorGeneracion`.
- Reglas descubiertas en el ejemplo: doble bit = 2 filas y 2 offsets; comando comparte tag (con C) y offset con su señalización; reserva = tag y TAG HMI "N/A", DESC "RESERVA" y ocupa un offset DI; `AFP` usa rango 0..32767 y `VP` -32768..32767 (ajustado en `sufijos_medicion.json`).
- Perfil: `max_raw_a_escribir = 32767` (PENDIENTE), `variable_inicial = 0` y `variable_inicial_medicion = 1` (PENDIENTE).
- Se quitó una contraseña en texto plano de `PREGUNTAS.md` (no debe subirse a GitHub). Sin commit ni push.
- Agregadas 6 dudas del generador en `PREGUNTAS.md`. Siguiente PC-A: 3.1 (placa/entrada, validador).

## 2026-10-28 — PC-B
- Servidor otra vez accesible tras un corte. Hecha la primera versión de 3.3: `pdf_plano.py` (leer_plano, a_niveles), `plantillas/EPEN/lectura_plano.json`, pestaña "Señales (PDF)" en `app/principal.py` (lectura en hilo aparte, revisión de nivel/campo/descripción por página, "Aplicar al proyecto"), `tests/test_pdf_plano.py`. Con el plano 6402: 3 páginas de bornes (29, 51, 73), campos 04/05/06, 33KV, 53 señales cada una. 36 tests OK en total.
- Las señales quedan con: función, tipo (DI/DO), estados S0-S3 desde el perfil, observaciones = texto del plano, reserva marcada. Faltan TAG/OFFSET/DESC. SCADA/DESC. HMI (generador de PC-A) y PLACA/ENTRADA.
- Para PC-A: el generador 2.1 puede partir de `Proyecto.niveles` ya cargado (Senal con funcion, tipo_punto, estado_id, observaciones, es_reserva).

- PC-B (2026-10-28, cambios pedidos): (1) las reservas del PDF van todas juntas al final de cada nivel (campo "RESERVAS") y la observación aclara el campo y el tipo: "Reserva Campo 04 DI"; (2) el lector no depende de números de página: lee todo el PDF y detecta páginas de bornes por contenido (≥6 columnas rotuladas + alimentación o reservas; el cajetín se descarta por posición relativa `x_minimo_rel` en `lectura_plano.json`); (3) interfaz más compacta y específica: pestañas Carátula (grupos Obra / Documento / Firmas), Referencias y revisiones, Numeración (en una línea) y Señales (PDF); (4) tablas de referencias y revisiones: encabezado y filas en la misma grilla, empiezan vacías y solo crecen al agregar. 36 tests OK.
- PC-B: corrección: las reservas del PDF van en UN solo bloque al final de toda la hoja (Nivel "RESERVAS", sin campo propio); observación "Reserva Campo 04 DI" (con el nivel delante si el proyecto tiene varios niveles). 54 tests OK en total (incluye los nuevos de PC-A).

## 2026-10-28 — PC-A (3.1)
- Hecha 3.1. **Nuevos**: `asignacion_utr.py`, `validador.py`, `tests/test_utr_validador.py`, `tests/ejemplo_etap.py` (helper: `proyecto_desde_ejemplo()` arma un `Proyecto` desde la hoja EPEN del ETAP sin generar nada; PC-B puede usarlo para probar `excel_reader`). 84 tests OK (incluye los de PC-B).
- **`modelo.py`**: clase `Modulo(placa, tipo, entradas, desde)` y `Proyecto.modulos` (al final de los campos, no rompe llamadas posicionales; se guarda/carga en JSON).
- **Para PC-B (UI)**: (1) pedir los módulos del plano en Numeración o en una tabla (placa, DI/DO, nº de entradas, primera entrada) → `proyecto.modulos`; (2) tras `generador.generar` llamar `asignacion_utr.asignar_placas(proyecto, perfil)` (devuelve avisos); (3) botón "Validar" → `validador.validar_proyecto(proyecto, perfil)` (cada `Problema` tiene `gravedad`, `ubicacion`, `mensaje`; `str(problema)` ya es legible). El validador no modifica nada.
- El validador revisa: tag estándar y coherente con la función, DESC. SCADA ≤ 20, espacios/tabulaciones sobrantes, estados con grafía del perfil (sugiere "¿'error_0'?"), UNITS, tipo de punto vs función, orden de funciones, 2ª fila del doble bit, MIN<MAX en analógicas, PLACA/ENTRADA completas y comando doble bit con par ("1/2"), y duplicados de tag, OFFSET (por tipo), DESC. SCADA y entrada (placa+número).
- Corrida sobre el ejemplo ETAP: encuentra inconsistencias reales del propio ejemplo (OFFSET 284 repetido entre una alarma y una reserva, entrada A3.5.15 usada dos veces, DESC. SCADA repetida, espacios sobrantes, estados MARCHA/PARADA en vez de PAR/ARR, 3 filas sin OFFSET, 2 mediciones con tipo N/A). Ver PREGUNTAS.md.
- Sin commit ni push.

## 2026-10-28 — PC-B (foco en el listado, sin carátula)
- Pedido del usuario: enfocarse solo en el listado (la carátula se arma después). Regla de tensión para el dígito del tag: 132 kV y 66 kV → 3; 33 kV → 2; 13,2/13 kV y 6,6 kV → 1 (`plantillas/EPEN/lectura_plano.json` → `codigo_nivel`; `pdf_plano.codigo_nivel`; asigna `Nivel.codigo`). PC-A: si corresponde, moverlo al perfil.
- App: pestañas reordenadas (Señales (PDF) · Numeración · Carátula · Referencias y revisiones). Nuevo botón "Generar tags y offsets" que llama a `generador.generar` (PC-A) con avisos; campo "Lugar" (ej. LC) arma el prefijo del campo (`204LC`); la tabla de páginas pide también CONTROLADOR por campo; casilla "Incluir carátula" (por defecto apagada → el Excel lleva solo la hoja EPEN: `escribir_xlsx(..., incluir_caratula=False)`). Ya nada de la carátula es obligatorio.
- Prueba de punta a punta con el plano 6402 pág. 29: 204.001, 204.011… offsets desde 200, estados S0-S3, comandos 204.292C con offset de DO. 56 tests OK.
- Problema abierto: DESC. SCADA > 20 caracteres (39 avisos en un campo). Falta el motor de abreviaturas: ver PREGUNTAS.md.
- PC-B: respuesta del usuario: el Excel es un DICCIONARIO. Hecho `diccionario.py` + botón "Cargar Excel de nombres…" (se pueden sumar varios): aprende de cada fila (DESC. HMI sin prefijo + OBSERVACIONES → abreviatura de DESC. SCADA sin prefijo del campo), ignorando números (campo, equipo, tensión) pero NO el código de equipo (SA/SB/SL/ST cambian la abreviatura). Se aplica antes de `generador.generar`: exactas y parecidas (≥0,86, mismo código de equipo) se cargan y se marcan en `Senal.fijos`; si dos señales del campo darían la misma descripción, no se carga ninguna; si no entra en 20, queda para completar a mano. Con el ETAP (465 filas, 351 entradas) y el plano 6402 pág. 29: 7 de 32 señales resueltas, sin errores (otra obra: el diccionario crece al sumar más Excel). 62 tests OK (`tests/test_diccionario.py`).

## 2026-10-28 — PC-B (descripciones por reglas, sin diccionario)
- Pedido del usuario: en lugar de un diccionario, basarse en las reglas para armar los nombres y que la app pida los datos que falten. Hecho `descripciones.py` + `plantillas/EPEN/reglas_descripcion.json` (sembrado con los lineamientos pág. 3: INT, SBA, SBB, ST, F/U AUX, DIS; estados Abierto/Cerrado y comandos sin descripción). DESC. SCADA = prefijo del campo + equipo + descripción; si no entra en 20 se pegan las partes (como 301LAVALINTF/UAUX).
- Lo que las reglas no definen se pregunta en una ventana ("Abreviaturas que faltan"): equipo+código (ej. Seccionador SL), frase (solo el complemento si ya se conoce el comienzo: "falta tensión auxiliar" + "ssaa"), estado (Local/Remoto), texto sin equipo, y "largo"/repetida. Las respuestas quedan en `plantillas/<id>/abreviaturas_usuario.json` y no se vuelven a preguntar. Los comandos no se calculan: el generador les copia la descripción de su señalización.
- La app ya no usa `diccionario.py` (queda en el repo por si se quiere sumar un Excel como ayuda; el USRE dio 0 coincidencias). Nueva columna NOMBRE (LC, GTR01, TRAFO1…) por campo en la tabla de páginas para armar el prefijo (`204LC`); el "Lugar" global es el valor por defecto.
- Plano 6402 pág. 29: reglas resuelven 2 señales (SBB e INT) y piden 21 abreviaturas (equipo SL, complementos, textos sin equipo). 86 tests OK.
- Para PC-A: `Reglas`/`reglas_descripcion.json` podrían pasar al perfil si se quiere compartir; ver también PREGUNTAS.md (abreviaturas de equipo SL, "Campo… ACTUADA", etc.).

- PC-B: el usuario pidió sacar las abreviaturas del Excel de EPEN (ETAP). Hecho `herramientas/extraer_reglas.py`: lee el listado (465 filas) y carga en `plantillas/EPEN/reglas_descripcion.json` los equipos (INT; seccionador SA=SEC BA, SL=SEC L, ST=SEC T), 12 frases (F/Uaux, F/U FM, F/U CMDO, RES/DESC, M/INC, PUE/AB…), estados (Local/Remoto = L/R, EX/IN; Abierto/Cerrado y comandos sin descripción) y 202 textos completos de señales sin equipo. El Excel pisa a los lineamientos donde difieren (ej. F/Uaux en vez de F/U AUX, SEC BA en vez de SBA). Se omiten las que dependen de un número (MK01/MK02, BOB1/BOB2) y quedan 39 conflictos anotados en `_conflictos` (se usó la más frecuente). Inferida: SB = SEC BB (por analogía; no está en el Excel) en `_inferidas`. Plano 6402 pág. 29: las reglas resuelven 8 señales (antes 2) y piden 17 datos. 86 tests OK.
- PC-B: corrección en `descripciones.py`: una abreviatura respondida por el usuario que lleva números (ej. «F/UCC TC3-01») se guarda solo para ese texto exacto (`Pendiente.exacta`); si no lleva números vale para todos los textos parecidos. Antes se podía reutilizar mal para TC3-02. 87 tests OK. Conflictos de abreviaturas del Excel revisados con el usuario (lista en `_conflictos` de `reglas_descripcion.json`).

- PC-B: conflictos de abreviaturas: el usuario delegó la decisión. Se dejó la más usada del Excel; en los 2 empates (Falta Ucc comando / fuerza motriz) se igualó a la frase equivalente con equipo (F/U CMDO, F/U FM). Anotado en _decisiones de reglas_descripcion.json.

## 2026-10-28 — PC-B (nueva etapa: columnas fuera de SCADA)
- Decisiones del usuario: (1) por ahora se trabajan las columnas A-G y P, S, T, W (PROTOCOLO, POS DNP, BORNERA y N° DE BORNE siguen vacías); la sección SCADA (H-O) se pule después. (2) Los datos salen del PDF de plano y de carga a mano. (3) Lo ya hecho de SCADA (tags, offsets, descripciones por reglas) se OCULTA de la app: el código queda guardado. (4) Borrados `diccionario.py` y `tests/test_diccionario.py` (reemplazados por las reglas de abreviaturas).

## 2026-10-28 — PC-B (etapa: columnas fuera de SCADA)
- Respuestas del usuario: controlador = SEL-2241 + tensión del nivel para todo lo cableado (ej. SEL-2241-33kV; configurable en `plantillas/EPEN/lectura_plano.json`); PLACA la escribe el usuario por módulo (la app propone correlativas A4.2→A4.3…); ENTRADA de DI = número de borne impreso (1–32), deducido por la posición de la etiqueta; las SALIDAS (comandos/DO) quedan sin PLACA/ENTRADA por ahora; doble bit = 2 filas con ITEM propio, 1ª fila = 1er estado (Abierto/Local/Apertura) con su borne, 2ª fila = 2º estado con el suyo (como el ETAP: entradas 2 y 1); TAG HMI = armado desde el texto y editable; DESC. HMI = prefijo + texto sin tildes; OBSERVACIONES = texto del plano, editable; la tabla permite agregar, borrar y mover filas.
- `pdf_plano.py` reescrito: módulos (`Modulo`: página, franja, DI/DO, 32 bornes), borne por posición (la franja de salidas tiene 31 etiquetas: no se numera), filas en orden de borne, doble bit en 2 filas, controlador por defecto, TAG/DESC. HMI, reservas juntas al final con el campo en la observación. Ya NO genera tags, offsets ni descripciones SCADA.
- `excel_writer.escribir_xlsx(..., omitir_claves=[...])`: columnas que no se escriben; `plantillas/EPEN/etapas.json` define las de SCADA (H-O: tag_scada, offset, desc_scada, s0-s3, unidad). La app las oculta y no las exporta; `generador.py`, `descripciones.py`, `tags.py`, `validador.py` y `asignacion_utr.py` siguen en el repo sin usarse desde la app.
- App: `app/editor.py` (pestaña "Señales (PDF)": módulos y placas, tabla editable con doble clic, agregar campo/fila, borrar, subir/bajar con la 2ª fila del doble bit como bloque); Numeración solo pide ITEM; los OFFSET guardados en un proyecto se conservan. 82 tests OK.
- Nota para PC-A (cuando se retome SCADA): `generador._generar_campo` descarta y recrea las 2ª filas del doble bit (sin PLACA/ENTRADA/CONTROLADOR propios); habrá que conservarlos.
- PC-B (2026-10-28): el usuario no podía exportar el Excel: el ITEM inicial vacío bloqueaba la exportación con un aviso. Ahora ITEM arranca en 1 y vacío = 1 (solo es error si no es un número). Además, la ENTRADA ya no se completa (decisión del usuario: "lo de los bornes no tiene que ir"): `"asignar_entrada": false` en `plantillas/EPEN/lectura_plano.json`; el borne leído se conserva en `LecturaSenal.bornes` por si se retoma. La PLACA sigue siéndolo que escribe el usuario por módulo.

## 2026-10-28 — PC-B: REINICIO solo columnas A-G
- El usuario no quedó conforme ("tenía cosas de más") y pidió empezar de nuevo con SOLO las columnas A-G (ITEM, NIVEL, DESCRIP, CONTROLADOR, FUNCION, TAG HMI, DESC. HMI): pantalla = una tabla como el Excel que llena el PDF del plano y se corrige a mano.
- Respaldo antes de borrar: `Sofware listado/respaldo/codigo_2026-10-28_antes_de_limpiar.zip` (41 archivos; incluye todo lo de PC-A y lo mío sin commitear).
- BORRADO (confirmado por el usuario): `generador.py`, `tags.py`, `validador.py`, `asignacion_utr.py`, `tests/test_generador.py`, `tests/test_tags.py`, `tests/test_utr_validador.py`, `tests/ejemplo_etap.py` (los de PC-A siguen en el commit a836f74) y los JSON de SCADA del perfil EPEN (`estados`, `sufijos_medicion`, `unidades`, `abreviaturas`); `perfiles.py` ya no los carga/valida. Antes se había borrado `diccionario.py`.
- NO borrado (no confirmado): `descripciones.py` + `reglas_descripcion.json` + `abreviaturas_usuario.json` + `etapas.json` + `herramientas/extraer_reglas.py` (SCADA, sin uso; extraer_reglas ya no corre sin estados.json: está en el zip), carátula y plantilla del Excel (`excel_writer` carátula, `EPEN_plantilla.json`, `extraer_plantilla.py`) y `app/validacion.py` (carátula, sin uso).
- Nuevo: `hmi.py` (TAG/DESC. HMI), `pdf_plano.py` lean (sin módulos/placas/bornes/tipo/observaciones), `app/principal.py` (una ventana: cargar PDF, ITEM inicial, nombre de campo, tabla A-G editable con doble clic, agregar campo/fila, borrar, subir/bajar con el doble bit como bloque, guardar/abrir JSON, exportar). `escribir_xlsx(..., hasta_columna="G")` escribe solo A-G (encabezado, merges, filtro y área de impresión recortados). `app/editor.py` eliminado.
- 47 tests OK.

## 2026-10-28 — PC-B: ajustes sobre la tabla A-G (pedido del usuario)
1. CONTROLADOR/DISPOSITIVO DE CAMPO: el final es la tensión del nivel (SEL-2241-33kV; decimales con coma como el ETAP: 6,6kV). Al editar el NIVEL de un grupo, la tensión de sus controladores se actualiza (`pdf_plano.con_tension_del_nivel`); un relé u otro controlador sin tensión no cambia.
2. Controlador por señal: las de protección (texto que empieza con "Prot.") llevan el RELÉ DE PROTECCIÓN del campo, que se escribe en la ventana de páginas al cargar el PDF; multimedidor y alimentación (Vca/110Vcc) llevan SEL-2241-<kV>. Patrón en `plantillas/EPEN/lectura_plano.json` ("rele_patrones").
3. DESC. HMI lo más completa posible (expande Secc.→Seccionador, Prot.→Proteccion, Ten.→Tension, Conj.→Conjunto, Cmdo→Comando, F Motriz→Fuerza Motriz; sin tildes) y TAG HMI = esa descripción abreviada y unida con "_" (Falta→F, Auxiliar→Aux, Proteccion→Prot, Sobrecorriente→Sobrec, Principal→Ppal, Respaldo→Resp, Diferencial→Dif, Fuerza→Fza; las dos últimas de Resp/Dif/Fza salen del vocabulario del ETAP). Vocabulario en `lectura_plano.json` ("expansiones", "abreviaturas_tag"); lógica en `hmi.py`. Basado en el ETAP: 58 % de sus tags son la descripción con "_", el resto nombres de punto del relé o versiones acortadas; los controladores del ETAP son SEL-2241-132kV / -6,6kV / _SSAA, SEL-3555, SCHNEIDER Pxxx_Cnnn, ION 7400, PROT_CELDA_Cnnn.
- 54 tests OK (nuevo `tests/test_hmi.py`).
