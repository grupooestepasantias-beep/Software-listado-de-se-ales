# Panel del empleado (Play.exe)

Ventana flotante (WPF, .NET 8) que cada empleado deja abierta todo el día. Código en `src/Play.Panel` (pantallas) y `src/Play.Client` (toda la lógica, sin interfaz, probada contra el servidor real en `tests/Play.Server.Tests/ClientTests.cs`).

## Qué hace
- **Expandido:** Usuario, Obra, botón Play/Pause (verde/naranja), cronómetro, punto de estado, resumen «Hoy · Semana». **Contraído:** punto + cronómetro + botón «+». El borde y el punto cambian de color: verde = registrando, naranja = en pausa, gris = sin usuario / sin conexión, rojo = registrando pero sin actividad.
- Siempre encima, sin barra de título, arrastrable; recuerda posición y si está contraído (`%AppData%\Play\ajustes.json`). Al contraer/expandir mantiene fija la esquina derecha. Por defecto aparece arriba a la derecha.
- Cerrar la ventana (Alt+F4) solo la contrae. Salir: clic derecho → «Salir» (si está registrando, pide pausar). Clic derecho también ofrece: resumen detallado, cambiar de usuario, iniciar con Windows, cambiar de servidor.
- Un solo panel por sesión de Windows. Los errores inesperados se anotan en `%AppData%\Play\errores.log` y el panel sigue funcionando.

## Casilla «Tarea terminada»
Debajo del menú **Tarea** hay una casilla **«Tarea terminada»** para la subtarea elegida. **Tildarla** le avisa al administrador (queda como aviso sin revisar: la tarea sigue pendiente hasta que él la acepte); **destildarla** retira el aviso si todavía no lo revisó. Refleja el estado real: si el administrador acepta la subtarea (sale de la lista) o descarta el aviso, la casilla se actualiza sola (cada 30 s). Sin conexión se destilda y avisa que no se pudo.

## Personal de Taller: cargar horas
Si el usuario es del área **Taller**, el panel **no muestra Play**: se elige la **Obra** (primero «(Sin obra: trabajo general)»), la **Tarea** (si la obra tiene subtareas pendientes es obligatoria), el **Día** (Hoy / Ayer) y las **Horas**, y se toca **Guardar** (también con Enter). Se escribe «8», «7,5», «7.5», «7:30» o «8 h» (de 1 minuto a 24 horas). Cada obra y tarea es una **línea** del día: abajo dice lo cargado en esa tarea y el total del día con el detalle por obra («Ese día: 8:00 h en total · Senillosa › Estructura: 5:00 · Ape: 3:00»); volver a guardar la misma tarea la corrige y **Quitar estas horas** la saca. La casilla **«Tarea terminada»** avisa al administrador igual que en Oficina. Debajo: «Esta semana: X h». Si el administrador cargó o corrigió una línea, queda bloqueada. «Mi resumen de horas…» lista los últimos 14 días con su obra. Sin conexión no se guarda (hay que repetir).
## Avisar que terminé una subtarea
Clic derecho → **«Avisar que terminé una subtarea…»** (con usuario ingresado): elige obra y subtarea (solo las obras con subtareas pendientes; si está registrando en una, la sugiere) y toca **Avisar**. Muestra «Listo: le avisaste al administrador.»; sin conexión avisa que no se pudo (no se guarda en cola: se repite cuando haya red). No tacha ni cierra nada: el administrador revisa el aviso.

## Áreas
Arriba de «Usuario» hay un menú **Área** (Oficina / Taller): la lista de nombres solo muestra a los de esa área. Al abrir elige el área del último usuario que ingresó en la PC (o la última elegida, o Oficina). Con el cronómetro andando el menú queda bloqueado; en pausa, cambiar de área equivale a cambiar de usuario. Si el servidor es anterior a las áreas, todos figuran en Oficina.

## PIN
Cuando los empleados se manejan desde el Excel (ver `docs/ADMIN.md`), el PIN es el del Excel: el empleado entra directo, **no elige ni cambia su PIN** (si lo intentara, el servidor responde `gestionado_por_excel`). Para cambiarlo se edita el Excel.

## Flujo
1. Primera vez: pide la **dirección del servidor** (ej. `192.168.1.50:8080`), comprueba que responda y la guarda. Se cambia con clic derecho → «Servidor…» (reinicia el panel).
2. Elegir usuario → escribir PIN de 4 números (entra solo al completar). Primer ingreso: obliga a elegir un PIN nuevo.
3. Elegir obra → Play. Si la obra tiene subtareas aparece el menú **Tarea** y hay que elegir una (sin eso Play avisa). Con el cronómetro andando, elegir otra obra o cambiar de subtarea **pide confirmación** y cierra/abre en una sola operación (al cambiar a una obra con subtareas, la subtarea se elige en el mismo cuadro).
4. Inicia con Windows (se activa en la primera ejecución) y **siempre queda en pausa**: nunca cuenta sin Play.

## Casos límite (todos con prueba automática)
| Caso | Qué pasa |
|---|---|
| Se cae el wifi/servidor | Sigue contando en la PC. Play/Pause/cambio de obra se guardan en `%AppData%\Play\pendientes.json` y se envían solos al volver (idempotente, sin duplicar). Aviso «Sin conexión» y punto gris |
| El servidor cortó el registro por falta de latidos pero el panel siguió contando | Al reconectar extiende el registro cortado (queda marcado «a revisar» para el admin) y continúa en uno nuevo: no se pierde ningún minuto |
| La PC se suspende/hiberna o el panel se congela (salto > 90 s entre ticks) | El registro termina en el último momento en que el panel estuvo vivo y avisa |
| Se cierra el programa o se reinicia la PC con el cronómetro andando | El servidor corta en el último latido. Al reabrir en la misma PC cierra ese registro ahí y queda en pausa con aviso |
| Apagar/cerrar sesión de Windows | Intenta pausar (hasta 3 s) para que termine a la hora exacta |
| Mismo usuario en dos PCs | El segundo Play se bloquea: «Ya tenés un registro activo en PC-XX» |
| Inactividad (2 h sin mouse/teclado, valor del servidor) | El punto se pone rojo; al volver pregunta «Descontarlo y pausar» (pausa en el momento en que empezó la inactividad) o «Contarlo como trabajo». No se puede cerrar el cuadro sin elegir |
| Reloj de la PC desfasado | Se estima el desfase con la hora del servidor y se usa para estampar registros hechos sin conexión |
| Registro rechazado como inválido al sincronizar (p. ej. más de 14 días) | Se archiva en `rechazados.json` y se avisa; no se descarta en silencio |

## Listas de usuarios y obras
El panel queda abierto todo el día y cerrar su ventana solo la contrae, así que **no alcanza con cargar las listas al arrancar**: cada 30 s las vuelve a pedir en silencio (sin avisos ni cambiar el indicador de conexión; los menús solo se tocan si algo cambió). Un empleado u obra creado por el administrador aparece en ≤30 s sin reabrir nada. Si al arrancar el servidor no responde (la PC se enciende antes que el servidor), reintenta cada 4 s hasta cargarlas. Si se vuelve a abrir `Play.exe` con el panel ya corriendo, la segunda copia se cierra sola y avisa a la primera, que se expande y actualiza las listas. (Se probó refrescar al desplegar el menú, pero cerraba el menú de forma intermitente: se descartó.)

## Actualización automática
Los paneles se actualizan solos: **publicar una versión nueva = copiar el `Play.exe` nuevo a `datos\descargas` del servidor** (con `scripts\publicar-panel.ps1 -Publicar <esa carpeta>`). Nadie tiene que volver a bajar nada.
1. **Versión:** cada publicación graba una versión en el .exe (por defecto `1.AAMM.DDHH.mm`, p. ej. `1.2611.1812.35`; debe SUBIR en cada publicación). El servidor la lee del propio archivo y calcula su huella SHA-256 (`GET /api/panel/version`, público).
2. **Consulta:** al abrirse y cada 10 min, el panel pregunta qué versión hay. Si es más nueva (y no es una que ya falló), la **descarga en segundo plano** (con un retraso al azar de hasta 15–90 s para que 30 PCs no bajen 140 MB a la vez) a `Play.exe.nuevo` y la **verifica**: tamaño, huella, que sea un ejecutable de Windows y que su versión sea la anunciada. Si algo no coincide, la descarta.
3. **Instalación segura:** **nunca con el cronómetro andando.** Se instala al abrir el programa (si ya estaba descargada), con el panel sin usuario ≥30 s sin uso, o en pausa con ≥2 min sin tocar mouse/teclado (almuerzo, reunión). Cada PC queda con la versión nueva la próxima vez que el empleado se aleje o abra el programa.
4. **Cómo reemplaza:** Windows no deja pisar un .exe en uso pero sí **renombrarlo**: `Play.exe` → `Play.exe.viejo`, `Play.exe.nuevo` → `Play.exe`; arranca la versión nueva (mismos argumentos + `--actualizado <evento>`) y **espera su confirmación** (hasta 40 s; si se cierra sola, falla antes).
5. **Vuelta atrás:** si la nueva no confirma, se cierra, se restaura el `.viejo`, se anota esa versión como rechazada (`VersionRechazada` en `ajustes.json`, no se insiste) y el panel original sigue funcionando sin que el empleado note nada. La nueva borra el `.viejo` cuando el anterior termina de cerrarse.
6. **Registro:** todo queda en `%AppData%\Play\actualizaciones.log`. En pantalla solo aparece «Programa actualizado a la versión X» tras un cambio y «No se pudo instalar…» si algo falla.
7. **Dónde NO actúa:** compilaciones de desarrollo y pruebas con `--datos` (salvo `--permitir-actualizacion`); solo el `Play.exe` publicado. Como la descarga la hace el propio programa, no aparece el aviso de «Windows protegió su PC» en las actualizaciones (solo en la primera instalación manual).
8. **Pruebas:** 22 pruebas automáticas (aviso del servidor, verificación, reemplazo, reversión, política) + `scripts\prueba-e2e-actualizacion.ps1` con **.exe reales publicados**: (1) A→B automática, (2) .exe roto → vuelta atrás, (3) con registro en curso no se reinicia y al reabrir se actualiza.
La versión publicada se ve en el programa de administración, pestaña Sistema. La **primera** vez (los paneles instalados antes de esta función) hay que bajar el `.exe` a mano una última vez.

## Limitaciones conocidas
- Para **iniciar sesión** hace falta conexión con el servidor (valida el PIN ahí). Si la red cae con el panel ya en uso, no hay problema; si el servidor está caído por la mañana, no se puede empezar.
- Memoria: ~80–90 MB privados (WPF autocontenido). El objetivo original de <50 MB no es alcanzable con WPF; la alternativa sería un .exe que requiera instalar el runtime de .NET en cada PC (~40 MB) o una tecnología más liviana.
- No está firmado digitalmente: Windows muestra «Windows protegió su PC» la primera vez (la página de descarga explica cómo continuar).
- La actualización automática descarga 140 MB por PC (sin compresión). En un wifi lento, con muchas PCs a la vez, tarda; por eso se escalona y se hace en segundo plano.
- Si el panel está en foco y Windows pide algo, no roba el foco al aparecer (`ShowActivated=false`), pero al hacer clic sobre él sí toma el foco como cualquier ventana.

## Lección aprendida
`InvariantGlobalization=true` ahorraba poca memoria pero hacía fallar **cada tecla** en los cuadros de texto (WPF crea una `CultureInfo` con el idioma del teclado). Los errores quedaban en `errores.log` y el panel seguía «vivo» sin dejar escribir. Antes de entregar un .exe, correr `scripts\prueba-e2e-panel.ps1` (escribe el PIN real con teclado) y revisar `errores.log`.

## Herramientas de desarrollo
- `scripts\prueba-e2e-panel.ps1`: abre el panel real, lo maneja con UI Automation (usuario, PIN, obra, Play, Pause) contra un servidor real temporal y verifica los registros. No tocar mouse/teclado mientras corre.
- `Play.exe --captura <carpeta>`: abre la interfaz con una API de ejemplo y guarda un PNG de cada estado (7 imágenes).
- `Play.exe --datos <carpeta>`: usa esa carpeta en vez de `%AppData%\Play` y **no toca el registro de Windows** (para pruebas).
- `scripts\publicar-panel.ps1 [-Publicar <carpeta datos\descargas del servidor>]`: genera `dist\panel\Play.exe` (un solo archivo, ~140 MB, no requiere .NET).
