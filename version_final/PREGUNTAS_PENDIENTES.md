# Preguntas pendientes (2026-11-16)

Para contestar cuando puedas. Las que no bloquean nada están marcadas «no bloquea»; la app sigue funcionando con lo que se
decidió hasta ahora.

## Conexionado (etapa 4)
1. **Tablero** (lo dejé deducido, confirmalo). Regla que apliqué, sacada del Excel oficial de Senillosa y de los cajetines
   del ETAP: `TC` + dígito del nivel + `-` + campo de 2 cifras (campo 103 → `TC1-03`; campo 204 → `TC2-04`), y `TDCI` para
   SAA y SAC. Se puede cambiar por campo en «Datos…» (columna *Tablero*).
   - ¿Es correcta la regla?
   - **TP1** (campo del transformador): el oficial usa `TC2-01`. No lo deduje; queda vacío. ¿Se escribe a mano o hay regla?
   - Las mediciones «promedio» del oficial llevan tablero `TMED`. ¿Lo agrego para esas dos filas de cada campo?
2. **Bornera y borne de tablero**: ya se leen de las tablas de bornes dibujadas (OCR). Dudas:
   - Cuando una señal figura en varias borneras (X1.1, XA.1, XT.1…) elijo la fila con bobina A1. ¿Es el criterio correcto?
   - Las que entran directo a la UTR (el oficial pone `XDI.1` / 1-8) y los comandos (`XDO.1` / `1/2`): en el plano la tabla
     numera distinto (10, 11…). ¿El borne del oficial es el orden dentro del módulo (entrada 17-24 → 1-8)?
3. **Bornera y borne de equipo** (ej. `XP` / `17`, `2XP1` / `33`): no están como texto en ningún PDF que revisé. ¿De dónde salen?
4. **Placa** (ej. `UTR1.1.1`, `UTR2.1.D`): el PDF del tablero 33 kV (0811) la trae; el de 13,2 kV no. En el oficial, campos
   101, 103, 104 y 105 llevan `UTR1.1.1`, `UTR1.1.2`, `UTR1.1.3` y `UTR1.1.4`. ¿Es siempre «una placa por campo»?

## Descripciones SCADA
5. Amplié el vocabulario (de 85 descripciones en rosa quedaron 3). Algunas elecciones mías que conviene que revises:
   `Tensiones interrumpidas` → `U INTERR` (el oficial: `U/INTERRUMPI`); `Disparo protección de cuba cable` → `DISP P/CUBA CAB`;
   `Habilita recierre` → `HAB RECIERRE`; `Interruptor Ppal` → `INT` (como el oficial). Lista completa en `abreviaturas.json`.
6. Quedan 3 sin resolver: `F/U BAR 380 / 220 VCA`, `F/U BAR 220VCA SEG` e `INT 220VCA SEG AB` (con prefijo no entran en
   20 caracteres). ¿Cómo las querés abreviar?

## Para recordar (ya decidido, no hace falta responder)
- Controlador de medición, tablero y descripción del campo se cambian por campo en «Datos…».
- Las escalas, la separación de offsets y el prefijo «LM1» no se tocaron.
