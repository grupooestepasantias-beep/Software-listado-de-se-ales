# Cómo aplicar (los archivos de esta carpeta NO tocan los de `version_final`)

Copiar a `version_final` (los de `modificados` reemplazan a los actuales; ninguno cambió desde el 17/11/2026 10:51):

| Archivo | Qué es |
|---|---|
| `nuevos\cableado.py` | NUEVO: bornes de tablero desde las hojas de cableado |
| `nuevos\placas.py` | NUEVO: placa de módulo dibujada (UTR1.1.1…) con OCR |
| `nuevos\conexionado.py` | NUEVO: bornera y borne de EQUIPO aprendidos de un listado oficial |
| `nuevos\herramientas\aprender_conexionado.py` | NUEVO: aprende el conexionado de cualquier listado oficial (Excel) |
| `nuevos\perfiles\EPEN\conexionado_equipos.json` | NUEVO: 89 reglas aprendidas de `senillosa\USRE-0119-SET-C-T-LI-Ls-0744_rD_DV_2.xlsx` (editable) |
| `modificados\bornes.py` | `leer_bornes()` suma las hojas de cableado a las tablas |
| `modificados\pdf_plano.py` | `_placas_de_modulos` usa `placas.por_ocr` si no hay placas en el texto |
| `modificados\modelo.py` | `Senal` suma `bornera_equipo` y `borne_equipo` |
| `modificados\desde_pdf.py` | completa esas dos columnas con `conexionado` |
| `modificados\base\proyecto_db.py`, `base\senal.py` | pasan los dos campos nuevos a la base (fuente: regla) |
| `modificados\app\ventana.py` | solo el texto de avance de la lectura de bornes |
| `tests\test_cableado.py`, `test_placas.py`, `test_conexionado.py`, `tests\datos\cableado_F0811_h*.json` | pruebas nuevas |

Después: `python -m unittest discover -s tests` (247 pruebas, las mismas 85 omitidas de siempre).
Para aprender otro listado oficial: `python herramientas\aprender_conexionado.py "<listado>.xlsx" --agregar`.
Todo es opcional: sin reglas ni OCR, el programa se comporta como antes.
