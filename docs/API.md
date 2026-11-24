# API del servidor (HTTP/JSON, puerto 8080 por defecto)

Fechas en UTC (ISO 8601). Errores con cuerpo `{ "codigo": "..." }`. Autenticación: `Authorization: Bearer <token>`.

## Públicos
| Método y ruta | Descripción |
|---|---|
| `GET /api/estado` | Comprobación de vida |
| `GET /api/config` | `latidoSegundos` (30) e `inactividadMinutos` (120) para el panel |
| `GET /api/empleados` · `GET /api/obras` | Listas activas para los menús (`/api/obras` trae `subtareas` activas de cada obra; si hay alguna, hay que elegir una) |
| `POST /api/login` `{empleadoId, pin}` | → `token`, `nombre`, `debeCambiarPin`, `registroActivo`. 401 inválido, 423 bloqueado |

## Empleado (token de empleado)
| Ruta | Descripción |
|---|---|
| `POST /api/pin` `{pinActual, pinNuevo}` | Cambia el PIN (4 dígitos) |
| `GET /api/registro-activo` | Registro abierto del empleado o 204 |
| `POST /api/registros` `{id(GUID del cliente), obraId, equipo, subtareaId?}` | Play. 201 creado · 200 si el mismo id ya existe · 409 `registro_activo` (con `equipo`, `obraId`, `inicioUtc`) |
| `POST /api/registros/cambiar-obra` `{id, obraId, equipo, subtareaId?}` | Cierra el abierto y abre uno nuevo (atómico). 409 `sin_registro_activo` |
| `POST /api/registros/{id}/latido` | Cada 30 s. 409 `no_abierto` si el servidor ya lo cortó (incluye `finUtc`) |
| `POST /api/registros/{id}/cerrar` `{finUtc?}` | Pause (idempotente). `finUtc` = por ejemplo inicio de la inactividad |
| `POST /api/registros/sincronizar` `{registros:[{id,obraId,inicioUtc,finUtc?,equipo}]}` | Reenvío tras estar sin conexión. Resultado por ítem: `insertado`, `insertado_revisar`, `duplicado`, `actualizado`, `conflicto_abierto`, `invalido` |
| `GET /api/resumen` | Horas de hoy y de la semana (lunes a domingo) por obra, en segundos |

## Administración
`POST /api/admin/login` `{usuario, password}` → `token`, `debeCambiarClave`. Con clave temporal solo funciona `POST /api/admin/clave` `{claveActual, claveNueva}`.

Con token de admin: `GET/POST /api/admin/empleados`, `PUT /api/admin/empleados/{id}` `{nombre?, activo?}`, `POST .../{id}/reset-pin`, `GET/POST /api/admin/obras`, `PUT /api/admin/obras/{id}`, `GET/POST /api/admin/administradores`, `PUT .../{id}` `{activo}`, `POST .../{id}/reset-clave`, `GET /api/admin/en-vivo`, `GET /api/admin/registros?empleadoId&obraId&desde&hasta&revisar&limite` (fechas `yyyy-MM-dd` locales), `POST /api/admin/registros` (alta manual con `motivo`), `PUT /api/admin/registros/{id}` `{inicioUtc?, finUtc?, obraId?, motivo}`, `GET /api/admin/auditoria?registroId`, `GET /api/admin/reporte.xlsx?empleadoId&obraId&desde&hasta`.

Eliminar/recuperar (admin): `POST /api/admin/registros/{id}/eliminar` y `.../recuperar` con `{motivo}` (obligatorio). `GET /api/admin/registros?eliminados=true` lista solo los eliminados; sin ese parámetro no aparecen. 409 `registro_abierto` si está en curso; `PUT .../registros/{id}` devuelve 409 `registro_eliminado` si está eliminado.

Áreas y PIN (admin): `GET /api/empleados` (público) ahora trae `area`. `POST /api/admin/empleados {nombre, area?}` (por defecto Oficina), `PUT /api/admin/empleados/{id} {nombre?, activo?, area?}` (el cambio de área queda en la auditoría), `GET /api/admin/empleados?area=`, y el parámetro `area` en `en-vivo`, `registros`, `reporte.xlsx`. `GET /api/admin/pines?area=` (PIN legibles; deja constancia) y `GET /api/admin/pines.xlsx?area=` (Excel; deja constancia). 400 `area_invalida` si no es Oficina o Taller.

Backups (admin): `GET /api/admin/backups` (carpeta y lista) · `POST /api/admin/backups` (hace uno ahora).

## Página de descarga (sin autenticación)
`GET /` página con los programas de `datos/descargas` · `GET /descargar/{archivo}` baja un archivo de esa carpeta (404 si no está o es de otro tipo).

## Versión del panel (público)
`GET /api/panel/version` → `{ version, sha256, bytes, archivo, publicadoUtc }` del `Play.exe` de `datos\descargas` (404 si no hay). La versión se lee del propio .exe; la huella se recalcula solo si el archivo cambia. Los paneles la usan para actualizarse (`docs/PANEL.md`).

## Procesos en segundo plano
- Cada 30 s: registros abiertos sin latido hace más de 180 s pasan a `cortado` con fin = último latido.
- Cada 5 min: regenera `datos/excel/horas.xlsx`.
- Cada 10 min: revisa si toca el backup diario (a partir de las 02:00 locales, uno por día) y borra los de más de 30 días.

Subtareas (admin): `GET /api/admin/obras/{id}/subtareas` · `POST /api/admin/obras/{id}/subtareas {nombre}` · `PUT /api/admin/subtareas/{id} {nombre?, activo?}`. `POST /api/registros` y `cambiar-obra` devuelven `subtarea_requerida` si la obra tiene subtareas activas y no se manda una, y `subtarea_invalida` si no pertenece a la obra, está inactiva o la obra no tiene. El alta y la corrección de registros del admin aceptan `subtareaId` (y `quitarSubtarea` al corregir). `sincronizar` nunca rechaza por subtarea: guarda sin ella y marca «a revisar».

Subtareas terminadas y avisos: `PUT /api/admin/subtareas/{id}` acepta también `terminada` (true = tachada y deja de ofrecerse; false = reabrir; queda en la auditoría). `GET /api/admin/subtareas…` devuelve `terminada` y las terminadas van al final. **Empleado:** `POST /api/subtareas/{id}/avisar` → 201 (aviso nuevo) · 200 `yaAvisado` (ya tenía uno sin revisar) · 404 `no_encontrado` · 409 `subtarea_terminada`. **Admin:** `GET /api/admin/avisos?estado=` («nuevos» por defecto, «todos», «aceptado», «descartado»), `POST /api/admin/avisos/{id}/aceptar` (termina la subtarea y resuelve los demás avisos pendientes de ella) y `.../descartar`; 409 `aviso_resuelto` si ya estaba revisado. `GET /api/obras` solo trae las subtareas pendientes (activas y no terminadas).

Casilla «tarea terminada» (empleado): `GET /api/mis-avisos` → ids de subtareas que marcó y esperan revisión; `DELETE /api/subtareas/{id}/avisar` retira el aviso sin revisar (queda «retirado»; 204 idempotente).

Horas de Taller. **Empleado** (solo área Taller; otros reciben 403 `solo_taller`): `GET /api/horas` → `{hoy, cargas:[{fecha, minutos, origen}]}` (últimos 14 días) · `POST /api/horas {fecha:"yyyy-MM-dd", minutos}` carga o reemplaza (400 `fecha_no_permitida` si no es hoy ni ayer según el servidor, 400 `horas_invalidas` fuera de 1–1440 min, 409 `cargada_por_admin`). **Admin:** `GET /api/admin/horas?empleadoId&desde&hasta&eliminados`, `POST /api/admin/horas {empleadoId, fecha, minutos, motivo}` (409 `ya_cargado`, 400 `solo_taller`/`fecha_futura`), `PUT /api/admin/horas/{id} {minutos, motivo}` (deja el origen en «admin»), `POST /api/admin/horas/{id}/eliminar|recuperar {motivo}` y `GET /api/admin/horas.xlsx?empleadoId&desde&hasta`.

Asistencia (admin; solo lunes a viernes): `GET /api/admin/asistencia?anio&mes&area&empleadoId` → `{anio, mes, hoy, controlDesde, dias:[{fecha,tipo}], filas:[{empleadoId, empleado, area, activo, codigos[], presentes, ausentes, justificados}]}` con un código por día (P presente · A ausente · J justificado · S fin de semana · … el día no terminó · - sin control; 400 `periodo_invalido`). `GET /api/admin/asistencia.xlsx?anio&mes&area`. `GET /api/admin/faltas?desde&hasta&empleadoId&area&estado` (`sin_revisar`, `injustificada`, `justificada`; por defecto los últimos 60 días) · `GET /api/admin/faltas/alertas` → `{sinRevisar}` · `POST /api/admin/faltas/justificar {empleadoId, fecha, motivo}` (motivo obligatorio) · `POST /api/admin/faltas/injustificar {empleadoId, fecha, motivo?}` (también quita una justificación). 409 `no_corresponde` si ese día no es una ausencia (presente, fin de semana o todavía no terminó). Las horas de Taller también aparecen en `GET /api/admin/registros` con `origen:"carga"` (solo lectura) y en `reporte.xlsx`.

Horas de Taller por obra y subtarea: `POST /api/horas {fecha, minutos, obraId?, subtareaId?}` carga o reemplaza **la línea** de ese día, obra y subtarea (sin `obraId` = trabajo general); mismas reglas que Play (`obra_invalida`, `subtarea_requerida`, `subtarea_invalida`), 400 `horas_invalidas` si el día pasa de 24 h. `DELETE /api/horas?fecha=&obraId=&subtareaId=` quita una línea (hoy o ayer; 404 si no existe, 409 `cargada_por_admin`). `GET /api/horas` devuelve cada línea con `obraId, subtareaId, obra, subtarea`. Admin: `GET /api/admin/horas?...&obraId`, `POST /api/admin/horas` acepta `obraId` y `subtareaId` (puede usar una subtarea terminada); la lista y `/registros` traen obra y subtarea.

Excel de empleados (admin): `GET /api/admin/empleados-excel` → `{configurado, archivo, ultimaUtc, ok, mensaje, empleados, administradores, creados, actualizados, desactivados, errores:[{fila, mensaje}]}` y `POST /api/admin/empleados-excel/sincronizar` («Sincronizar ahora»). Con el Excel configurado, `POST/PUT /api/admin/empleados`, `reset-pin` y `POST /api/pin` (empleado) devuelven 409 `gestionado_por_excel`. Configuración: `Play:EmpleadosExcel` (ruta) y `Play:EmpleadosExcelSegundos` (cada cuánto mira el archivo; 10 por defecto). El usuario del administrador ya no distingue mayúsculas.
