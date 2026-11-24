# Especificación: Registro de horas por empleado y obra (LAN)

## Contexto
La empresa (30+ empleados, varias obras en simultáneo) quiere registrar las horas trabajadas por empleado y obra sin carga manual. Cada empleado usa un panel flotante mínimo (Usuario / Obra / Play-Pause) en su PC con Windows; todo se centraliza en un servidor dedicado de la LAN. Una aplicación de administración independiente permite consultar, corregir y exportar a Excel. Esta etapa es solo planificación; no se escribió código.

Carpeta de trabajo del proyecto: `Play` (en el Escritorio). Al comenzar la construcción hay que mover la sesión a esa carpeta (`change_directory`, ruta exacta a verificar: puede ser Escritorio local o el de OneDrive) y dejar el contexto documentado para que otra IA pueda continuar (ver «Documentación de contexto»).

## Decisiones tomadas (por el usuario)
| Tema | Decisión |
|---|---|
| Servidor | PC/servidor dedicado siempre encendido en la LAN; **SO aún por definir** |
| Escala | Más de 30 empleados simultáneos |
| Identificación | Elegir nombre + **PIN corto**; admin asigna PIN inicial, el empleado lo cambia; admin puede resetearlo |
| Roles | Empleado + Administrador (varios admins, cada uno con usuario y contraseña propios) |
| Cambio de obra con cronómetro activo | **Pedir confirmación** (cierra registro de A, abre B) |
| Olvidos | Detección de inactividad a las **2 horas** (cambiado el 2026-11-19; antes 15 min; configurable); al volver se **pregunta**: descontar o contar ese tiempo |
| Cierre/apagado/corte | Se cuenta hasta el **último latido** conocido; el registro se marca «cortado» |
| Doble registro | **Bloquear el nuevo** (mensaje «ya tenés un registro activo en PC-XX») |
| Sin conexión LAN | Seguir contando local y **sincronizar luego** sin duplicar; indicador «sin conexión» |
| Panel | Expandido: usuario, obra, Play/Pause, cronómetro. Contraído: punto de color + tiempo. Resumen hoy/semana de solo lectura |
| Arranque | Inicia con Windows, **en pausa**, pide PIN; nunca cuenta sin Play del empleado |
| Detalle | Solo obra (modelo preparado para agregar «tarea» a futuro) |
| Administración | **Programa de escritorio aparte** (.exe independiente) |
| Reportes | Excel (.xlsx), horas decimales + hh:mm, sin redondeo |
| Backups | Copia diaria automática en el servidor |
| Actualizaciones | Autoactualización del panel desde el servidor |
| Tecnología | Elegida por Claude (ver abajo) |

## Actualización 2026-11-18 (aclaraciones del usuario)
- **Excel:** el servidor mantiene la base (SQLite) y regenera automáticamente un archivo `.xlsx` con todos los registros (hojas: detalle, total por empleado, total por obra, cruce empleado×obra; horas decimales + hh:mm) en una carpeta del servidor. Nadie escribe directo en el .xlsx. El admin también puede exportar bajo pedido.
- **Entrega:** el panel es un único `.exe` autocontenido (Windows 10/11, sin instalar .NET). El servidor publica una página de descarga (`http://IP-servidor:8080`) desde la que cada empleado baja el .exe.
- **Red wifi:** las PCs están por wifi, así que el modo offline (cola local + sincronización idempotente) es obligatorio, no opcional.
- **PC servidor:** todavía sin decidir. Requisitos: siempre encendida durante la jornada, IP fija o reserva DHCP en el router, y conexión estable (idealmente por cable).
- Pendiente de la Fase 1: lista inicial de empleados y obras, primer administrador, y definir la PC servidor.

## Arquitectura recomendada
```
[PC empleado: Panel WPF] --HTTP/JSON (LAN)--> [Servidor: API ASP.NET Core como servicio de Windows] --> [Base de datos]
[PC admin: Admin WPF]  --HTTP/JSON (LAN)-->  (misma API)                                      \-> [Backups diarios]
```
- **Lenguaje/stack: C# / .NET 8.** Panel y Admin en WPF (liviano, nativo, siempre-encima, sin navegador). Servidor ASP.NET Core minimal API. .NET corre también en Linux, así que el SO del servidor sigue abierto.
- **Base de datos: SQLite (modo WAL) accedida SOLO por la API**, nunca compartiendo el archivo por red (SMB corrompe SQLite). Con 30–100 clientes y latidos cada 30–60 s la carga es mínima. Migrable a PostgreSQL (EF Core) si crece. Pendiente de confirmar al elegir el servidor.
- **Por qué cliente-servidor y no «carpeta compartida con una base común»:** evita corrupción por escrituras concurrentes, permite reglas de negocio centralizadas (un solo registro activo por empleado), hora única del servidor y sincronización idempotente.
- **Admin separado del panel:** mantiene el panel mínimo, evita que un empleado acceda a funciones de admin, y puede actualizarse sin tocar las 30+ PCs. Ambos comparten una librería común (modelos, cliente API).
- **Descubrimiento del servidor:** archivo de configuración con host/puerto; recomendar IP fija o nombre fijo para el servidor.

## Modelo de datos (borrador)
- `Empleado` (id, nombre, pin_hash, debe_cambiar_pin, activo)
- `Obra` (id, nombre, activa)
- `Administrador` (id, usuario, pass_hash, activo)
- `RegistroTiempo` (id **GUID generado por el cliente**, empleado_id, obra_id, inicio_utc, fin_utc nullable, ultimo_latido_utc, estado: abierto | cerrado | cortado | corregido, equipo, origen)
  - Índice único parcial: un solo registro `abierto` por empleado.
  - Pausar = cerrar registro; Play = abrir uno nuevo (modelo simple, sin tabla de pausas).
- `Auditoria` (id, admin_id, fecha, registro_id, campo, valor_anterior, valor_nuevo, **motivo obligatorio**)
- `Configuracion` (inactividad_min, retención de backups, etc.)
- Activación/desactivación en lugar de borrado: el historial nunca pierde referencias.

## Casos límite y soluciones
| Caso | Solución |
|---|---|
| Cierre accidental del programa | Latido cada ~30 s; el servidor cierra como «cortado» los registros sin latido >2–3 min usando el último latido. Al reabrir, el panel lo informa y arranca en pausa |
| Apagado/reinicio de la PC | Igual que arriba; Windows arranca el panel en pausa y pide PIN |
| Caída de la LAN | Cronómetro local + cola persistente en disco; reenvío con GUID (idempotente). Si al sincronizar hay solapamiento con otro registro del mismo empleado, se marca para revisión del admin |
| Doble registro | Restricción en base de datos + mensaje claro en el panel; el servidor es la fuente de verdad |
| Cambio de obra sin pausar | Confirmación; cierra A e inicia B en una sola operación |
| Olvidó pausar | Aviso a las 2 h sin mouse/teclado (Win32 `GetLastInputInfo`); al volver, elegir descontar o contar |
| Reloj de la PC desfasado | Tiempos de inicio/fin los fija el servidor; offline se usa el reloj monotónico local y se corrige al sincronizar |
| Registro que cruza la medianoche | Se guarda entero; los reportes lo reparten por día |
| Registro anormalmente largo | Alerta al admin (umbral por defecto 12 h, ajustable) |
| PIN erróneo repetido | Bloqueo temporal tras N intentos; PIN guardado con hash (PBKDF2/Argon2) |
| Pérdida de datos del servidor | Backup diario automático (retención por defecto 30 días) |

## Comportamiento de la ventana (panel)
- Sin bordes, siempre encima, arrastrable, esquina superior derecha por defecto.
- Modo contraído (≈100×25 px): punto verde = registrando, naranja/rojo = pausado, gris = sin conexión; muestra tiempo. Un clic lo expande.
- Recordar posición y estado (guardado en `%AppData%`), validando que siga dentro del monitor visible.
- No roba el foco (ventana no activable salvo al interactuar), bajo consumo (objetivo <50 MB RAM).
- El registro sigue corriendo con la ventana minimizada o contraída; cerrar la ventana la contrae/oculta en bandeja, no detiene el registro (salir requiere acción explícita con confirmación).

## App de administración
Alta/edición/desactivación de empleados y obras, reseteo de PIN, consulta por empleado/obra/fecha, historial, corrección de registros con motivo y auditoría, estado en vivo (quién está registrando y dónde), exportación a Excel (hojas: detalle de registros, total por empleado, total por obra, cruce empleado×obra; decimales + hh:mm), gestión de administradores y configuración (umbral de inactividad, retención de backups).

## Fases de desarrollo propuestas
0. Preparar carpeta `Play` + documentación de contexto.
1. Servidor + base de datos + API (registro, latido, cierre por abandono, idempotencia, auditoría).
2. Panel del empleado (UI mínima, PIN, Play/Pause, cambio de obra, resumen).
3. Robustez: modo offline, inactividad, arranque con Windows, recordar posición.
4. App de administración + exportación Excel.
5. Backups, instalador, autoactualización.
6. Pruebas multi-PC en la LAN y piloto con pocos empleados.

## Documentación de contexto (para otra IA o futuras actualizaciones)
En `Play/`: `README.md` (qué es y cómo se ejecuta), `CLAUDE.md` (convenciones y reglas del proyecto), `docs/ESPECIFICACION.md` (este documento, que ya incluye arquitectura y casos límite) y `docs/DECISIONES.md` (registro de decisiones y por qué). Crear `docs/ARQUITECTURA.md` cuando haya código.

## Pendientes / supuestos a confirmar al iniciar el desarrollo
- SO y nombre/IP fija del servidor (define SQLite vs PostgreSQL y servicio de Windows vs Linux).
- Lista inicial de empleados y obras; datos del primer administrador.
- Valores por defecto asumidos: latido 30 s, corte tras 2–3 min sin latido, alerta registro >12 h, retención backup 30 días, bloqueo de PIN tras 5 intentos.
- Si el empleado olvidó pausar y está inactivo más de X horas (p. ej. toda la noche), se cuenta hasta el último latido con actividad detectada; a validar en pruebas.
- Seguridad: la red es solo LAN (HTTP); se evalúa HTTPS con certificado interno más adelante.

## Verificación (cuando se desarrolle)
- Pruebas de API: un solo registro abierto por empleado, idempotencia de reenvíos, cierre por abandono.
- Simulación de 30+ clientes concurrentes con latidos.
- Pruebas manuales: matar el proceso, reiniciar la PC, desconectar el cable de red 5 min y reconectar, cambiar de obra, inactividad 2 h, doble registro desde 2 PCs.
- Verificar que el Excel exportado coincide con los registros y que cada corrección queda en auditoría.
- Piloto con 3–5 empleados durante una semana antes del despliegue general.
