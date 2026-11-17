# Barrido del lector de planos (sin cambios al código)

Fecha: 2026-11-16 (PC-A). Corrí `pdf_plano.leer_plano` con el perfil EPEN sobre los **112 PDF** de esquemas funcionales
(`-EF-`, `-Ef-`, `-Ad-`) que hay en `PasantiasMM` (se excluyeron carpetas «Superado» y el respaldo). No se tocó ningún archivo
del proyecto; solo se leyeron los PDF. Los números vienen de `barrido.json` (en el scratchpad de esta sesión).

Columnas: páginas del PDF / páginas con señales / señales leídas / de ellas reservas.

## 1. Funcionan bien (señales leídas y coherentes)
| Plano | Págs. | Leídas | Señales | Reservas | Nota |
|---|---|---|---|---|---|
| ETAP EF-6402_D | 93 | 3 | 159 | 64 | referencia del proyecto |
| ETAP EF-6302/6303/6304 (CAF y _C) | 62 | 3 | 115–117 | 14–18 | 4 señales sin entrada en 6303/6304; 1 en 6302 |
| ETAP EF-6301_1_CAF | 31 | 1 | 52 | 20 | |
| ETAP EL-EF-1461_B | 71 | 3 | 98 | 23 | falta campo y nivel en una hoja (se infirió) |
| ETAP EL-EF-0316/0346/0366/0386 (NC) | 30–57 | 1–3 | 53–117 | 16–21 | nivel y campo inferidos; 3–6 avisos de numeración |
| ETAP EL-EF-6501_0 | 26 | 1 | 36 | 18 | campo inferido |
| USRE Ef-1102_CAO | 29 | 1 | 46 | 16 | |
| USRE SET Ad-0808 (r2 y r4) | 22 | 1 | 71–72 | 30–33 | campo SAA/SAC; 1 aviso de numeración |
| USRE SET Ad-0811 (rev2 y rev4) | 58 | 2 | 116 | 51 | 57 señales sin placa; 4 avisos |
| USRE Ad-0821 (r2 y r3) | 62 | 8 | 100 | 21 | 4 campos; 4 avisos |

## 2. Leen señales pero SIN entrada (UTR)
Todas las señales vienen de una tira de relé, sin módulo de E/S, y no hay reservas; es lo esperable, pero hay que confirmarlo:
- ETAP EF-6309, 6310, 6311, 6312 (también «ACTU GABI»), EF-6110_B: 4, 18, 25, 25, 17 señales, todas sin entrada.
- USRE Ad-861 (rC y rE): 17 señales, todas sin entrada.
- Pregunta: ¿en estos tableros (puerta vidrio / TDCI de relés) las columnas P-T deben quedar vacías, o las entradas salen de otro plano (topográfico)?

## 3. Posibles fallas del lector: esquemas funcionales con **0 señales**
Son planos cuyo nombre dice EF pero el lector no encontró ninguna señal. Todos tienen las páginas rotadas 270°, muy poco
texto y `con_franja` = 1 con 0 títulos de hoja:

| Plano | Págs. | Caracteres | Hojas con rótulos |
|---|---|---|---|
| ETAP EF-6305 (0 y _1_CAF) | 19 | 4135 | 15 |
| ETAP EF-6308 (0 y _1_CAF) | 19 | 4499 | 15 |
| ETAP EF-6404_D | 20 | 3778 | 15 |
| ETAP EF-6406_D | 50 | 2224 | 5 |
| ETAP EF-6502_C | 9 | 766 | 4 |
| ETAP EF-1604, 1707, 6111, EL-0902 | 8–30 | — | — |
| USRE Ef-1103_CAO | 10 | — | — |

Hipótesis (no verificada): son esquemas de otro tipo (potencia, interconexión, auxiliares) y no de control, o su título de
cajetín no coincide con lo que espera `lectura_plano.json`. Falta abrir una hoja de cada uno para decidir; es la mejor
candidata para trabajar en `pdf_plano.py` (hoy lo toca la otra PC, por eso no lo hice).

## 4. Los planos USRE «Ad» (0807, 0810, 0830, 0840, 0841, 1041, 1042, 0871, 1700, 860, 870, 1054, 1056, 1600, 1601, 0960, 0820, 0821_rC): 0 señales
Son planos de arquitectura, topográficos o de detalle, no esquemas de señales: **no es un error**. Solo el 0808, 0811, 0821_r3
y 861 son esquemas de señales.

## 5. PDF sin texto (imágenes)
Todos los «… para CAO» de ETAP (6301, 6302, 6303, 6304, 6305, 6308, 6309, 6310, 6311, 6312) y `USRE-01-19-SET-Ct-PL-Ad-0808.pdf`:
la app avisa «PdfSinTexto». Hay versión `_CAF` con texto de casi todos, así que el aviso es correcto y alcanza con usar la versión original.

## 6. Avisos de numeración «por orden de aparición»
Aparecen en 12 planos (lista en la sección 1). La app ya los muestra para verificar en el plano; ningún caso falló por esto.

## 7. Resumen y pedidos
1. El lector anda bien en los esquemas de control con módulos de E/S (6402, 6302-6304, 6301, 1461, 0316-0386, 0808, 0811, 0821).
2. **Revisar a mano:** abrir una hoja de 6305, 6308, 6404, 6406 y 6502 para saber si tienen señales que el lector no ve.
3. **Decidir:** columnas P-T vacías cuando la fuente es una tira de relé (sección 2).
4. **Tiempo:** 1–10 s por PDF; no hay problemas de rendimiento.
