# Estudio de los topográficos de Senillosa: ¿de dónde salen los bornes?

Fecha: 2026-11-17. Solo lectura: no se tocó ningún archivo del proyecto. Se revisaron los 7 topográficos, los PDF funcionales
de los mismos tableros, las listas de materiales, `NUMEROS DE BORNES.xls` y el Excel oficial.

## 1. Los topográficos, uno por uno
| Tablero | PDF | Hojas | Qué dibuja | Bornes |
|---|---|---|---|---|
| TC2-01 (33 kV) | `TCAMPO 1 33 kV\2-Topografico\…0810 Rev 3.pdf` | 11 | vista frontal, montaje de componentes (hoja 7), bandejas laterales, cartelería | nombres de bornera y relés dibujados (`-X2`, `-X3`, `-X00`, `-KI3.1`, `-KTR2`…), **sin números de borne** |
| TCONTROL 13,2 kV | `TCONTROL 13,2kV\2-Topográfico\…0820_r2.pdf` | 12 | gabinete, bandejas frontal/posterior/lateral, calados, cartelería | ninguno legible |
| TDCI | `TDCI\2-Topográfico\…0807_r2.pdf` | 6 | vistas, cortes y detalles | nombres de bornera como texto (`-X1`, `-X110`, `-X220`, `-X48`, `-X4`, `-X01`) y térmicas (`-Q1`…`-Q14`); sin números de borne |
| TP01 | `TP01\2-Topografico\…860_r2.pdf` | 8 | vistas, bandejas, relés (hoja 6: bornes de relé RB.14 como 11, 12, 14, 21…) | solo los contactos del relé |
| TMED | `TMED\2-Topografico\…0871_r2.pdf` | 9 | vistas, calados, bandeja interior, cartelería | ninguno |
| TCOM01 | `TCOM01\2-Topográfico\…1041_r1.pdf` | 8 | vistas, cortes, detalles | nombres (`-X01`, `-X1`, `-X110`, `-X24`…) |
| TSSAA | `TSSAA\2-Topográfico\…0841_r3.pdf` | 7 | vistas, calados, elementos y mímico (hojas 5 y 6) | nombres (`-X0`…`-X7`, `-XF0`, `-XTIA1`) |

Conclusión: son planos **mecánicos** (dónde va cada cosa). Las regletas de bornes están dibujadas como bloques negros sin
numeración legible, ni siquiera ampliadas a 450 dpi. Dan **qué borneras y relés tiene cada tablero**, no a qué borne va cada señal.

## 2. Qué más hay y qué dice
- **Listas de materiales** (`1-Lista Materiales\*.xlsx`): texto limpio. Para el tablero 33 kV da cada bornera y su cantidad:
  `X1.1` 40 bornes, `XDI.1` 8, `XDI.G` 20, `XD0.1` 5, `XBCD` 10, `X00` 75, `X2` 44, `XT.1` 35, `XAI` 40, `XA.1` 40, `XAG` 10, `XCA` 16.
  Son los mismos nombres que usa el Excel oficial. Sirven para validar nombres, no para asignar señales.
- **`MATERIALES\NUMEROS DE BORNES.xls`**: solo la cantidad de tiras de identificadores (1-10, 11-20…) por tablero. No asigna señales.
- **PDF funcionales**: cada módulo de E/S trae su placa y el número de entrada de cada señal (la app ya lo lee). La placa es texto en el
  0811 (`UTR2.1.D`) y en el TDCI (`A1.4`), pero está **dibujada** en el 0821 (`UTR1.1.1` a `UTR1.1.4`): ahí la app no la lee.
  Bornera y borne por señal: **solo el TDCI** (`X4/18`, en los cables). El resto no los trae.
- **Los `.dwg`** (AutoCAD 2018) de los funcionales no se pueden abrir sin un programa de CAD; las cadenas de texto están comprimidas.

## 3. Cómo es el dato en el Excel oficial (observación, no regla)
- `XDI.1` (protecciones): borne = orden de entrada dentro del grupo (entradas 17 a 24 del módulo D → bornes 1 a 8).
- `X1.1` (contactos de campo): bornes correlativos (61 a 73 en el campo 101; 71 a 73 en el 201), en el **orden del listado**, no en el de las entradas.
- Térmicas y relés (`QC`/`QS`/`QF`/`QT`, `KR3.3`…) y llaves (`LLAVE 7.1`, `LTD1`) con su número de contacto (14, 20…).
- Bornera y borne de equipo (`XP`/17, `L0`/1, `1XP1`/24): bornes del equipo primario (interruptor, seccionador, relé).
Esa asignación sale del cableado; no está en ningún PDF.

## 4. Qué se puede automatizar hoy y qué no
| Dato | ¿Se puede? | Cómo |
|---|---|---|
| Tablero | sí | regla `TC<nivel>-<campo>` (ya hecho) |
| Placa | parcial | texto en 0811 y TDCI (ya se lee); dibujada en 0821 → necesita OCR |
| Entrada | sí | ya se lee |
| Bornera y borne de tablero | solo TDCI | leer `X4/18` bajo cada rótulo |
| Bornera y borne de tablero (otros tableros) | no con los PDF | hace falta el cableado (¿CAD, lista de cables?) |
| Bornera y borne de equipo | no con los PDF | ídem |
