# PREGUNTAS PENDIENTES PARA EL USUARIO

Formato: `[ ] pregunta` → al responder, `[x] pregunta — respuesta`. Las respondidas se borran en la próxima limpieza (quedan en git).

## Carátula (PC-A, 2026-10-29)
- [ ] Número de documento (ej. ETAP-0722-ET-CT-MC-LI-6209): hoy se escribe completo (hasta 20 caracteres, sin guiones). ¿Cómo se compone cada parte, para armarlo con campos separados?
- [ ] Fechas: ¿formato dd/mm/aaaa tanto en cada revisión como en el pie? ¿La fecha del pie es la de la última revisión?
- [ ] ¿La escala es siempre "N/A"? ¿"Nro. Expediente" suele ir vacío?
- [ ] La carátula admite 14 referencias y 4 revisiones (lo que tiene la plantilla del ETAP). Si hay más, ¿se agranda la plantilla o se hace otra hoja?
- [x] ¿La carátula va en la misma app que la tabla? — el usuario pidió integrarla: ahora es la pestaña «Carátula» de la app (2026-10-29).

## Calidad de redacción (PC-A, 2026-11-03)
- [ ] **Tildes:** el ETAP no tiene ninguna tilde ni ñ en las descripciones, así que el paso de calidad las QUITA (`Tensión` → `Tension`). Tu pedido decía corregir `Tension`→`Tensión`: ¿los sistemas HMI/SCADA aceptan tildes? Si sí, se cambia una línea (`redaccion.json` → `tildes.modo: "agregar"`).
- [ ] Unidad de tensión: el ETAP usa `kV` sin espacio y coma decimal (`6,6kV`, `132kV`). ¿Dejamos ese estilo o preferís `33 kV` con espacio?
- [ ] Textos con otra tensión que la del campo (p. ej. `Campo 05 33KV` dentro de un campo de 132KV): vienen del plano. ¿Son error del plano o el campo realmente es de 33KV? Hoy solo se marcan.
- [ ] DESC. SCADA repetidas entre señales distintas (p. ej. `305tr SEC BB F/Uaux` ×3): ¿se aceptan o hay que diferenciarlas?
- [ ] ¿Largo máximo de DESC. HMI y TAG HMI? (el mayor del ETAP mide 70 en DESC. HMI.)

## Tabla A-G (PC-B)
- [x] Salidas (comandos/DO): PLACA/ENTRADA ya se leen del plano (2026-10-30): la salida n está en el borne 2n y un comando Apertura/Cierre va como par, ej. `9/10`.
- [ ] **UTR (PC-A, 2026-10-30):** (1) La ENTRADA se calcula contando solo los bornes de entrada (los "Negativo 48 VCC" no cuentan): borne 21 = DI17, como en tu imagen. ¿Es la regla en todos los módulos, o hay módulos con otra numeración (de 16 DI, analógicos)? (2) Las SALIDAS: asumo que la salida n está en el borne 2n (DO9 = borne 18), como pide el par `9/10` del ETAP; ¿es así? (3) La PLACA (A4.2) está dibujada, no se puede leer: ¿se escribe siempre a mano por módulo, o hay una regla (el nombre sale del tablero)? (4) Las señales de los tableros de protección (tiras de relé) quedan sin placa/entrada: ¿es correcto?
- [ ] ¿Qué otras abreviaturas del plano se expanden en la DESC. HMI? Hoy: Secc., Prot., Ten., Conj., Cmdo, F Motriz. Candidatas: SSAA, Vca/VCC, QF4/QM4/QC4 ACTUADA, TI/TV, "en D"/"en T", Med.
- [ ] En el TAG, "Fuerza" se abrevia Fza (vocabulario del ETAP). ¿O preferís F_Motriz?
- [ ] ¿Hay un largo máximo para TAG y DESC. HMI?
- [ ] Controladores de relés de protección (SCHNEIDER P543…) y comunicaciones (RTAC, TAPCON, EXEMYS): ¿se cargan a mano o hay una lista por tablero?
- [ ] Los lineamientos dan SBA/SBB/ST para seccionadores, pero el plano usa SA/SB/SL/ST. ¿SL cómo se abrevia? Señales sin equipo (QF4 ACTUADA, 2TV04 Falta Vca Prot): ¿hay una regla general?
- [ ] Mediciones: el rótulo "Multimedidor ION" está dibujado (no es texto); hoy se infiere que el campo mide por la alarma "Falla Multimedidor". ¿Está bien, o hay otro dato en el plano?

## SCADA H-O (PC-A, 2026-10-29) — lo que el motor ya hace y lo que hay que confirmar
Respondido por los datos de los ejemplos (verificado contra el ETAP; ver `prueba_scada\LEEME.md`): la variable arranca en 10 salvo el campo 303 (00); entre campos quedan 10 offsets DI y 8 AI libres; el comando comparte tag y offset con su señalización; las mediciones se numeran 01-14 saltando la 04 (132 kV) o la 12 (6,6 kV).
- [ ] **Variable inicial:** el ETAP arranca en 00 solo en el campo de la línea (303) y en 10 en todos los demás. ¿Es una regla (línea = 00, resto = 10) o un caso puntual?
- [ ] **Separación de offsets entre campos:** 10 en entradas digitales y 8 en analógicas (observado en el ETAP). ¿Es una regla del cliente o quedó así por las señales borradas?
- [ ] **Seccionadores:** el PDF dice SBA/SBB/ST pero el ETAP escribe "SEC BA / SEC L / SEC T". El motor usa el estilo del ETAP. ¿Cuál va?
- [ ] **Estados que el ETAP escribe distinto del PDF:** MARCHA/PARADA (PDF: PAR/ARR), CONSIGNA1-3 (PDF: NORMAL/OPERO), TELE/DISTANCIA en 6,6 kV (PDF: DIST/TELE). El motor sigue el PDF. ¿Está bien?
- [ ] **FALLA o ACTUO:** el ETAP usa FALLA en "UTR COMUNICACION…" y en "Prot. TR1 6,6kV - Falla Interna", pero ACTUO en "Prot. Ppal… Falla Interna" (303). El motor usa FALLA solo para las "UTR COMUNICACION" y avisa en los demás. ¿Cuál es el criterio?
- [ ] **MIN/MAX EU de las mediciones:** hoy se calculan como RAW×0,1 (RAW×0,01 en frecuencia y ángulo) porque así están en el ETAP, pero son los valores de ingeniería del aparato (relación de TI/TV). ¿Los cargamos por campo?
- [ ] **Abreviaturas (DESC. SCADA de 20 caracteres):** el glosario aprendido del ETAP resuelve solo el 42 % de un campo nuevo (acierta 82 % de lo que resuelve); el resto sale como PROPUESTA marcada para confirmar (siempre ≤ 20). El ETAP tiene varias abreviaturas para lo mismo (CMDO/CMNDO, F/FZA MOT/F/U FM, MK01/MK02, estilo pegado "303LcPrtTxTelepPpal"). ¿Cuál es la correcta, y hay una lista oficial de abreviaturas?
- [ ] **Qué cambia de un cliente a otro** (respondida por los datos, falta que la confirmes): USRE usa ERR_0 en mayúsculas, offset propio en los comandos, MIN RAW −32767, variable inicial 2/7/8 y no tiene DESC. HMI ni UTR. ¿Hay más diferencias que no se vean en los listados?
- [ ] MAX RAW: 32767 (ejemplo) o 32768 (PDF); rangos de SACA/SACC; significado de AFP, VP, IP, LF, IF, CBC; mediciones sin placa/entrada.
- [ ] Orden físico de las entradas (en el ETAP no siempre es correlativo) y cantidad de entradas por módulo.
- [ ] Inconsistencias del ETAP que el validador marcó: OFFSET 284 y entrada A3.5.15 repetidos, estados MARCHA/PARADA en vez de PAR/ARR, filas sin OFFSET. ¿Errores o excepciones válidas?
## Otros planos de ingeniería (carpeta ape) — PC-B, 2026-10-29
- [ ] Tableros de PROTECCIÓN (TP3-xx): sus hojas son cableado de relés (entradas binarias, disparos, "SEÑALIZACION A SISTEMA DE CONTROL - CAMPO 06"). Hoy no generan filas (correcto para las E/S del RTAC). ¿Querés que las señales del relé hacia el control entren al listado con el controlador del relé (SCHNEIDER P543_C306…)?
- [ ] Módulos analógicos (AI): cada rótulo con rango pasa a MEDICION y las "Reserva" no se cuentan. ¿Está bien, o cada entrada libre debe quedar como reserva analógica?
- [ ] Servicios auxiliares (TSACA / TSACPT): las hojas traen señales como "Falta tensión Int Ppal 110VCC" e "Interruptor QA Abrir/Cerrar". En el ETAP esos campos se llaman SACC/SACA, con nivel SSAA y controlador SEL-2241_SSAA. ¿Qué tablero corresponde a cuál (TSACPT = continua → SACC, TSACA = alterna → SACA)?
- [ ] Los PDF "para CAO" no tienen texto (son imágenes). ¿Siempre existe la versión "_CAF"/"_B" con texto para usar en su lugar?
- [ ] (PC-B) 19 de los 103 PDF vigentes de `ape` son imágenes (versiones "para CAO", "Correciones", hojas de SMEC/CAMMESA). ¿Es con esos con los que probaste? Para leerlos haría falta instalar un OCR (paquete pip de ~60 MB, puede fallar con la letra de los planos).

## Análisis de documentación (Senillosa) — PC-B, 2026-11-02
- [ ] Hojas "ENTRADAS DIGITALES – ALARMAS" de TDCI (72 canales, 39 con nombre) y de SSAA1/SSAA2 (48 y 75 señales): hoy se leen por OCR y se informan en la ventana de verificación (pestaña «Señales de tableros»), pero NO entran solas al listado. ¿Con qué NIVEL, CAMPO y FUNCIÓN las lista EPEN (¿ALARMAS, nivel de servicios auxiliares?) y cuál es el controlador (¿el módulo DI del TDCI?)? Con la respuesta se pueden sumar al listado.
- [ ] Campo 01 del TCONTROL: el EF no trae "Reconectador 152/01 con recierre / sin recierre" y la lista de señales (hoja 75) sí. ¿Se agregan al listado como ALARMAS (como en los campos 03/04/05)?
- [ ] Los campos 03/04/05 no tienen "Disparo / Falla protección de cuba cable" en sus listas (hojas 77/79/81) aunque sí en el EF: ¿es así en el proyecto o falta en la lista?
