# PREGUNTAS PENDIENTES PARA EL USUARIO

Formato: `[ ] pregunta` → al responder, `[x] pregunta — respuesta`. Las respondidas se borran en la próxima limpieza (quedan en git).

## Carátula (PC-A, 2026-10-29)
- [ ] Número de documento (ej. ETAP-0722-ET-CT-MC-LI-6209): hoy se escribe completo (hasta 20 caracteres, sin guiones). ¿Cómo se compone cada parte, para armarlo con campos separados?
- [ ] Fechas: ¿formato dd/mm/aaaa tanto en cada revisión como en el pie? ¿La fecha del pie es la de la última revisión?
- [ ] ¿La escala es siempre "N/A"? ¿"Nro. Expediente" suele ir vacío?
- [ ] La carátula admite 14 referencias y 4 revisiones (lo que tiene la plantilla del ETAP). Si hay más, ¿se agranda la plantilla o se hace otra hoja?
- [x] ¿La carátula va en la misma app que la tabla? — el usuario pidió integrarla: ahora es la pestaña «Carátula» de la app (2026-10-29).

## Tabla A-G (PC-B)
- [ ] Salidas (comandos/DO): por ahora sin PLACA/ENTRADA. Si se retoman: ¿el par es el N.º de relé de salida (borne/2, ej. 9/10) o los bornes impresos?
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
