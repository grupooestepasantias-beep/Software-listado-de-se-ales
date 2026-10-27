# PREGUNTAS PENDIENTES PARA EL USUARIO

Formato: `[ ] pregunta` → al responder, `[x] pregunta — respuesta`.

## Semana 1
- [ ] ¿Qué suele cambiar de un cliente a otro (columnas, tags, largos, estados, carátula)?
- [ ] Número de documento: ¿cómo se compone cada parte? (ej. ETAP-0722-ET-CT-MC-LI-6209)
- [ ] Fórmula exacta del TAG SCADA (páginas 15 y 20 del PDF no se leyeron completas).
- [ ] Formato de TAG HMI y DESC. HMI.
- [ ] ¿Cómo se nombran campos y niveles nuevos?
- [ ] ¿Hay un ejemplo de datos de entrada para probar?
- [ ] ¿Autorizan instalar git (y openpyxl / lector de PDF) en las PCs?
- [ ] ¿Cuál cuenta/PC es PC-A y cuál PC-B?

## Dudas surgidas al cargar el perfil EPEN (PDF de lineamientos)
- [ ] El código AS figura dos veces en el PDF: "Corriente fase S" y "Potencia aparente". ¿Se distinguen solo por la unidad (A vs MVA)?
- [ ] AFP = "Angulo de fase total" en el PDF, pero en el ejemplo parece factor de potencia: ¿qué unidad y rango lleva?
- [ ] VP, IP, LF, IF aparecen en el ejemplo pero no en el PDF: ¿qué miden?
- [ ] CBC figura sin significado en el PDF (RAT = regulador automático de tensión). ¿Qué es CBC?
- [ ] MAX RAW: el PDF dice 32768 y el ejemplo escribe 32767. ¿Cuál va en el Excel?
- [ ] Campos especiales (TP1, TP2, RN1, RN2, SAA, SAC): en el ejemplo el tag no lleva dígito de nivel (TP1.431). ¿Reemplazan a nivel+campo?
- [ ] ¿Existe la unidad "MV" que mencionaste, o es MW? ¿KV o kV, ºC o °C?
- [ ] El offset, ¿se cuenta por tipo de punto (DI/AI/DO/AO) con contadores separados? (en el ejemplo DI y AI empiezan ambos en 200)
- [ ] ¿Los comandos sin ITEM (los que comparten tag con su señalización) se numeran o no?

## Dudas de tags (verificadas contra el ejemplo ETAP)
- [ ] Servicios auxiliares: el PDF dice SAA/SAC pero el ejemplo usa SACA/SACC (y UTR). ¿Cuál es la grafía correcta?
- [ ] Mediciones de SSAA y UTR: SACC.01V48, SACC.04I220S, UTR02T_132, UTR06T_SSAA, TP1.01APOS, TP1.02AIMTA no siguen el patrón. ¿Tienen una regla propia o son excepciones manuales?
- [ ] La variable (00-99) ¿arranca siempre en 00? En el ejemplo algunos campos arrancan en 10 (TP1, 101, 102…). ¿Por qué, y de a cuánto salta?
- [ ] En el campo 303 aparecen variables fuera de orden (…12, 78, 79, 13…): ¿son agregados posteriores en una obra intervenida?
- [ ] Una señalización con comando lleva C en el tag (303.632C) igual que el comando: ¿es la regla general? ¿Y la señalización sin comando va sin C?
- [ ] DESC. SCADA: el PDF la muestra pegada (301LAVALINTF/UAUX) y el ejemplo con espacios (303LC SEC BA). ¿Se usan espacios? ¿Qué significa "LC" en 303LC (Loma Campana)? ¿Se pide al inicio de cada proyecto?
- [ ] Reservas: el tag va como "N/A" (46 casos en el ejemplo). ¿Siempre? ¿Con qué estados y tipo (DI/DO) se completan?
