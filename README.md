# Play — Registro de horas por empleado y obra (LAN)

Software para Windows que registra las horas de trabajo de cada empleado en cada obra, dentro de la red local de la empresa.

- **Panel del empleado:** ventana flotante mínima (Usuario / Obra / Play-Pause / cronómetro), siempre visible y contraíble.
- **Servidor central:** API en la LAN con la base de datos única (30+ empleados simultáneos).
- **Administración:** programa de escritorio aparte (usuarios, obras, consultas, correcciones auditadas, exportación a Excel).

## Estado actual
Servidor terminado (API de empleados y administración, Excel automático, backups diarios, página de descarga) y panel del empleado terminado (`docs/PANEL.md`). Programa de administración terminado (`docs/ADMIN.md`: `scripts\publicar-admin.ps1` → `dist\admin\PlayAdmin.exe`). Falta la autoactualización del panel (ver `CLAUDE.md`).

## Desarrollo
```
dotnet test                                  # 36 pruebas (servidor + lógica del panel contra el servidor real)
powershell -ExecutionPolicy Bypass -File scripts\publicar-panel.ps1   # genera dist\panel\Play.exe
dotnet run --project src/Play.Server         # servidor en http://localhost:8080 (datos en bin/.../datos)
```

## Instalar el servidor en la PC servidor (Windows x64)
1. En esta PC: `powershell -ExecutionPolicy Bypass -File scripts\publicar-servidor.ps1` (genera `dist\servidor`).
2. Copiar `dist\servidor` y `scripts\instalar-servicio.ps1` a la PC servidor y ejecutar el script como administrador. Instala el servicio `PlayServidor`, abre el puerto 8080 y muestra la dirección (`http://IP:8080`).
3. Entregar los PIN y la clave temporal que figuran en `C:\PlayServidor\datos\accesos_iniciales.txt` y borrar el archivo.
4. Generar el panel con `scripts\publicar-panel.ps1 -Publicar C:\PlayServidor\datos\descargas` (o copiar `dist\panel\Play.exe` a esa carpeta): los empleados lo bajan desde `http://IP:8080`. La primera vez cada panel pide la dirección del servidor.
5. Reservar la IP de esa PC en el router. Los backups quedan en `datos\backups` y el Excel en `datos\excel\horas.xlsx`.

## Documentación
- [docs/ESPECIFICACION.md](docs/ESPECIFICACION.md): decisiones, arquitectura, modelo de datos, casos límite, fases.
- [docs/DECISIONES.md](docs/DECISIONES.md): registro de decisiones y su motivo.
- [CLAUDE.md](CLAUDE.md): contexto y reglas para cualquier IA que continúe el proyecto.
