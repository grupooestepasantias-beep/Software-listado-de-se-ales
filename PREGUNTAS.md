# PREGUNTAS PENDIENTES PARA EL USUARIO

Formato: `[ ] pregunta` → al responder, `[x] pregunta — respuesta`.

## Semana 1
- [ ] ¿Qué suele cambiar de un cliente a otro (columnas, tags, largos, estados, carátula)?
Suele cambiar 
- [ ] Número de documento: ¿cómo se compone cada parte? (ej. ETAP-0722-ET-CT-MC-LI-6209)

- [ ] Fórmula exacta del TAG SCADA (páginas 15 y 20 del PDF no se leyeron completas).

- [ ] Formato de TAG HMI y DESC. HMI.
- [ ] ¿Cómo se nombran campos y niveles nuevos?
- [ ] ¿Hay un ejemplo de datos de entrada para probar?
- [ ] ¿Autorizan instalar git (y openpyxl / lector de PDF) en las PCs?
preguntar
- [ ] ¿Cuál cuenta/PC es PC-A y cuál PC-B?
La PC-A es el usuario AD.GO\Pasante2 y la PC-B es el AD.GO\Pasante3. (La contraseña se quitó de este archivo para que no llegue a GitHub; la tiene el usuario.)
- [x] (PC-B) ¿Las filas de doble bit (señalización con 2 filas, p. ej. "Abierto" y "Cerrado") se modelan como 2 `Senal` (la 2ª sin tag/desc. scada) o como 1 con ambas? El ejemplo las escribe en 2 filas con el mismo tag/offset consecutivo.
- [x] (PC-B) Los comandos sin ITEM en el ejemplo: el escritor numera todas las filas; ver duda de PC-A sobre ITEM de comandos.

## Dudas del generador (PC-A, tarea 2.1) — verificadas contra el ejemplo ETAP
- [ ] TAG HMI: solo ~58 % se puede derivar de la descripción. El resto son nombres de punto del relé (ej. `ARRANQUE_PROT_PPAL_FASE_R`, `ENVIO_SENAL_TELEPROT`). ¿Vienen de una lista del fabricante/equipo (SEL-2241, P543, P142…) que podamos cargar como catálogo, o se escriben a mano en cada proyecto?
- [ ] DESC. SCADA (máx. 20): el generador solo la propone si la descripción entera entra; si no, la deja vacía y avisa. ¿Hay una lista de abreviaturas para acortar (Seccionador→SEC, Interruptor→INT, Falta Tensión Auxiliar→F/Uaux…) que podamos cargar?
- [ ] Doble bit: el ejemplo ocupa 2 filas (la 2ª sin tag ni descripciones, con "Cerrado"/"Remoto"). Una excepción: "Recierre" (SIN/CON) está en 1 sola fila. ¿Es un error del ejemplo o hay una regla?
- [ ] Offsets del ejemplo: tienen saltos (263-266, luego 271-282). ¿Son señales eliminadas que no se renumeraron? ¿El software debe numerar siempre sin huecos?
- [ ] Servicios auxiliares (SACA/SACC): en el ejemplo el rango RAW está invertido respecto del resto (tensión −32768…32767, corriente 0…32767). ¿Cambia por campo?
- [ ] Enlace señalización↔comando: el generador usa `Senal.par` (mismo texto en ambas). ¿Se puede deducir del plano (mismo equipo, ej. "Seccionador 329SA03")?
- [x] Reservas: el generador las trata como cualquier campo (tag/TAG HMI "N/A", DESC "RESERVA", ocupan un offset DI) y respeta el bloque único "RESERVAS" al final de la hoja que definió el usuario el 2026-10-28.

## Carga de PDF de plano (PC-B, tarea 3.3)
- [ ] En el plano 6402, las páginas 29/51/73 tienen columnas de bornes con rótulos verticales (ej. "Seccionador 229SL04 Remoto", "Falta Tensión Auxiliar SSAA", "Reserva") y tensiones (48 VCC, 110 Vcc). ¿Cada columna con rótulo = una señal de la lista? ¿Se ignoran "Negativo"/"Positivo" (alimentación)?
- [x] ¿Dónde figura en el plano el rótulo del módulo (DI9, etc.) para PLACA y ENTRADA? No aparece en el texto de la pág. 29.
- [ ] ¿Cómo se decide si una señal es ALARMA, SEÑALIZACION, COMANDO o MEDICION? (por palabras del rótulo: "Falta"/"Falla" = alarma, "Abierto/Cerrado" = señalización doble bit, "Apertura/Cierre" = comando...)
- [x] (PC-B) Cada columna rotulada del plano es una señal; Positivo/Negativo (alimentación) se ignoran — respuesta del usuario 2026-10-27.
- [x] (PC-B) Con el plano 6402 se obtiene "Interruptor 25204 en Remoto/Local" y "Campo 04 33KV Llave Tele/Distancia en D/en T": ¿los textos de OBSERVACIONES se corrigen a mano o hay una regla de redacción?
- [x] (PC-B) Las reservas del plano se ubican al final de cada campo. ¿Van ahí o dentro de su función (como en el ejemplo ETAP)?
- [x] (PC-B) Reservas: van todas juntas en un único bloque al final de TODA la hoja (Nivel "RESERVAS"); la descripción aclara el campo (y el nivel si hay varios) — respuesta del usuario 2026-10-28 (corrigió su primera respuesta).

## Cargar datos desde el Excel (PC-B, 2026-10-28)
- [~] El usuario dice que las descripciones y nombres ya están en un Excel (respondió: se usa como DICCIONARIO). ¿Cuál? ¿El listado viejo de la obra (como el ETAP), u otra planilla con los nombres de equipos y sus abreviaturas?
- [x] ¿Cómo se usa ese Excel: (a) como diccionario para reutilizar DESC. HMI / DESC. SCADA de filas parecidas (ej. "Falta Tensión Auxiliar" → "F/Uaux"), o (b) como proyecto base que se abre y se modifica con las señales nuevas del PDF?
- [ ] DESC. SCADA (máx. 20): el plano da textos largos ("Secc. 229SL04 Falta Tensión Auxiliar SSAA"). ¿La abreviatura sale de la tabla de lineamientos (INT, SBA, ST, F/U AUX…) más lo que aprenda del Excel, y lo que no entre queda para completar a mano?

## PLACA / ENTRADA y validador (PC-A, tarea 3.1)
- [ ] Módulos: el software pide por cada placa (ej. A3.4): tipo DI o DO, cantidad de entradas y primera entrada, y las asigna en orden. En el ejemplo ETAP el orden físico no siempre es correlativo (2,1 / 3,4 / 9,8 / 18,17). ¿Hay una regla (p. ej. por borne del plano) o se corrige a mano?
- [ ] ¿Cuántas entradas/salidas tiene cada tipo de módulo (en el ejemplo hay placas A1.4, A2.5, A3.4…)? ¿Es siempre 24 (DI) y 10 (DO) o depende del módulo?
- [ ] Un comando de 1 bit (CONECT/DESCONEC): ¿ocupa 1 salida ("5") o también un par ("5/6")?
- [ ] El ejemplo ETAP tiene inconsistencias que el validador marca: una alarma y una reserva con el mismo OFFSET 284 y la misma entrada A3.5.15; DESC. SCADA repetidas (303LC DISP GRL PPAL); estados MARCHA/PARADA en vez de PAR/ARR del PDF; 3 filas sin OFFSET; 2 mediciones con tipo N/A. ¿Son errores a corregir o excepciones válidas?
- [ ] Mediciones sin PLACA/ENTRADA (N/A) como en el ejemplo: ¿correcto, o las AI también ocupan una entrada de un módulo analógico?
- [ ] (PC-B) Los lineamientos dan SBA/SBB/ST para seccionadores, pero el plano usa SA/SB/SL/ST. ¿SL (seccionador de línea) cómo se abrevia? Mientras tanto la app lo pregunta.
- [ ] (PC-B) Señales sin equipo (ej. «Campo 04 33KV QF4 ACTUADA», «2TV04- Falta Vca Prot»): ¿hay una regla general (QF/QM/QC = interruptor/seccionador…) o se definen una por una?

## Etapa "columnas fuera de SCADA" (PC-B, 2026-10-28)
- [x] Columnas en alcance: A-G y P, S, T, W (PROTOCOLO, POS DNP, BORNERA, N° DE BORNE vacías). Origen de datos: PDF de plano y carga a mano. SCADA oculto de la app.
- [x] Doble bit: 2 filas con ITEM propio. Controlador: SEL-2241 + tensión del nivel. ENTRADA (DI) = borne impreso. PLACA: la escribe el usuario por módulo. TAG HMI armado y editable; DESC. HMI = prefijo + texto sin tildes.
- [x] (respuestas resumidas arriba; "doble bit", "comandos sin ITEM", "módulo", "OBSERVACIONES" y "reservas" quedaron resueltas con estas decisiones)
- [ ] Salidas (comandos/DO): por ahora sin PLACA/ENTRADA. Cuando se retomen: ¿el par es el N.º de relé de salida (borne/2, ej. 9/10) o los bornes impresos?
- [ ] Mediciones (AI): ¿se leen de otro plano/página? El plano 6402 no las trae en las páginas de bornes.
- [ ] Controladores de relés de protección (SCHNEIDER P543…) y comunicaciones (RTAC, TAPCON, EXEMYS del Excel de materiales): ¿se cargan a mano fila por fila o hay una lista por tablero?
