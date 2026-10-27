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
