# CONTEXTO PARA CLAUDE (leer entero antes de tocar nada)

Hay **2 cuentas de Claude (PC-A = usuario AD.GO\Pasante2, PC-B = AD.GO\Pasante3)** trabajando sobre **la misma carpeta del servidor**. Si ves cambios que no hiciste, los hizo la otra: no los reviertas ni los pises. Actualizado: 2026-10-29.

## Qué se construye
Software que arma el **Listado de Señales** de estaciones transformadoras en un Excel. Hoy se hace a mano. Es **multi-cliente** (las reglas viven en `perfiles/<cliente>/` y `plantillas/<cliente>/`; EPEN es el primero). Ejemplos y reglas en `..\Ejemplos` y `..\Reglas` (solo lectura): el modelo a reproducir es `ETAP-0722-ET-CT-MC-LI-6209-1-Lista señales - CAO.xlsx`.

## Alcance actual: la app tiene las TRES partes del Excel (integradas el 29/10)
- **Listado A-G**: ITEM, NIVEL, DESCRIP, CONTROLADOR, FUNCION, TAG HMI, DESC. HMI. La llena el PDF del plano y se corrige a mano.
- **SCADA H-O** (botón «Generar SCADA…»): tag, offset, descripción SCADA (≤ 20), estados S0-S3/RAW/EU y unidades, con el motor del paquete `scada/` (reglas por cliente en `perfiles/<cliente>/scada.json`, abreviaturas en `glosario.json`). Las descripciones que no se pueden resolver salen como PROPUESTA (amarillo) y se confirman en «Propuestas SCADA…» (lo confirmado queda fijo y se recuerda).
- **Carátula** (pestaña «Carátula»): datos de la obra, referencias, revisiones y 2 logos elegibles.
- «Exportar Excel…» junta lo que haya: carátula (si se completó) + listado A-G (+ H-O si se generó el SCADA).
- **Suspendido**: PLACA/ENTRADA automáticas y validador. El código viejo de PC-A está en el commit `a836f74` y en `..\respaldo\`.
- Reglas del dominio vigentes: orden fijo ALARMAS → SEÑALIZACION → COMANDO → MEDICION; doble bit = 2 filas con ITEM propio; reservas juntas al final de la hoja; controlador = SEL-2241 + tensión del nivel; TAG HMI = descripción abreviada con "_"; DESC. HMI = prefijo + texto sin tildes.

## Reglas de trabajo (obligatorias)
1. Se trabaja en `\\192.168.15.120\PasantiasMM\Sofware listado\codigo\` (repo git; origin = https://github.com/grupooestepasantias-beep/Software-listado-de-se-ales, rama `main`).
2. **`git push` SOLO cuando el usuario lo indique.** No hagas commit ni push por iniciativa propia.
3. Nunca escribas contraseñas en archivos, comandos ni campos. El acceso al servidor lo autentica el usuario en Windows.
4. Antes de borrar algo, mirá que esté en git o en `..\respaldo\`, y que el usuario lo haya confirmado.
5. Al empezar leé `TAREAS.md`, `BITACORA.md` y `PREGUNTAS.md`; al terminar actualizalos. Las dudas para el usuario van en `PREGUNTAS.md`. Español en todo.
6. Tras cada cambio: `python -m unittest discover -s tests` (desde `codigo\`). Para instalar algo, pedí autorización.

## Mapa de `codigo\`
```
modelo.py          Proyecto > Nivel > Campo > Senal, Caratula (con logos), Revision, Referencia (JSON guardar/cargar)
perfiles.py        cargar/validar/duplicar perfiles;  perfiles/EPEN/{perfil,scada,glosario}.json
pdf_plano.py       lee el plano PDF (pymupdf) -> niveles/campos/señales;  hmi.py = TAG/DESC. HMI
excel_writer.py    escribir_xlsx(proyecto, perfil, ruta, incluir_caratula=, hasta_columna="G"|"O"); carátula con logos y 1 hoja A4
scada/             motor SCADA H-O: gen.py (generar_scada), descripcion.py (DESC. SCADA), perfil.py, evaluar.py (mide contra el ETAP:
                   python -m scada.evaluar), aprender.py (regenera el glosario), comparar_clientes.py
plantillas/EPEN/   EPEN_plantilla.json, lectura_plano.json, imagenes/ (logos del ETAP)
herramientas/      extraer_plantilla.py (regenera la plantilla desde el ETAP)
app/               principal.py (ventana: python -m app), caratula_ui.py (pestaña Carátula), scada_ui.py (offsets, propuestas),
                   validacion.py, catalogo_ui.py
tests/             pruebas unitarias (test_scada, test_caratula, test_integracion, ...)
```
Carpetas hermanas `..\prueba_caratula\` y `..\prueba_scada\`: PROTOTIPOS ya integrados en `codigo\` (quedan de referencia; no se mantienen).

## Entorno
Python 3.11 (PC-A) / 3.14 (PC-B), openpyxl, pymupdf. Git en `C:\Program Files\Git\cmd` (puede no estar en el PATH). Para git sobre la carpeta de red cada PC necesita una vez: `git config --global --add safe.directory "//192.168.15.120/PasantiasMM/Sofware listado/codigo"`.