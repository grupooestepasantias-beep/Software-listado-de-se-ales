using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Play.Server;
using Play.Server.Data;
using Play.Server.Services;

// La raíz de contenido es la carpeta del programa, sin importar desde dónde se lance (consola, acceso directo o servicio de Windows).
var builder = WebApplication.CreateBuilder(new WebApplicationOptions { Args = args, ContentRootPath = AppContext.BaseDirectory });

builder.Services.Configure<PlayOptions>(builder.Configuration.GetSection("Play"));

// Las opciones se leen de forma diferida (IOptions) para que respeten los ajustes aplicados al construir el host (p. ej. en las pruebas).
builder.Services.AddDbContext<PlayDb>((sp, o) =>
{
    var dir = DataDirDe(sp);
    o.UseSqlite($"Data Source={Path.Combine(dir, "play.db")};Default Timeout=30");
});
builder.Services.AddSingleton(TimeProvider.System);
builder.Services.AddScoped<AuthService>();
builder.Services.AddScoped<RegistroService>();
builder.Services.AddScoped<AdminService>();
builder.Services.AddScoped<HorasService>();
builder.Services.AddScoped<AsistenciaService>();
builder.Services.AddSingleton<EmpleadosExcelEstado>();
builder.Services.AddScoped<EmpleadosExcelService>();
builder.Services.AddHostedService<EmpleadosExcelWorker>();
builder.Services.AddHostedService<AsistenciaWorker>();
builder.Services.AddScoped<ReporteService>();
builder.Services.AddSingleton<PanelVersionService>();
builder.Services.AddScoped<BackupService>();
builder.Services.AddHostedService<BackupWorker>();
builder.Services.AddHostedService<AbandonedRecordsWorker>();
builder.Services.AddHostedService<ExcelWorker>();
builder.Host.UseWindowsService(); // permite instalarlo como servicio de Windows

var app = builder.Build();

using (var scope = app.Services.CreateScope())
    await Seeder.InicializarAsync(scope.ServiceProvider.GetRequiredService<PlayDb>(),
        scope.ServiceProvider.GetRequiredService<IOptions<PlayOptions>>().Value, DataDirDe(scope.ServiceProvider));

// ---------- Página de descarga del programa ----------
var carpetaDescargas = DescargaService.Carpeta(app.Services.GetRequiredService<IOptions<PlayOptions>>().Value, app.Environment.ContentRootPath);
Directory.CreateDirectory(carpetaDescargas);

app.MapGet("/", (HttpContext c) =>
    Results.Content(DescargaService.Pagina(DescargaService.Listar(carpetaDescargas), $"{c.Request.Scheme}://{c.Request.Host}"), "text/html; charset=utf-8"));

app.MapGet("/descargar/{archivo}", (string archivo) =>
    DescargaService.Buscar(carpetaDescargas, archivo) is { } f
        ? Results.File(f.FullName, "application/octet-stream", f.Name, enableRangeProcessing: true)
        : Results.NotFound());

// Versión del panel publicada (para que cada panel se actualice solo). 404 si no hay Play.exe publicado.
app.MapGet("/api/panel/version", async (PanelVersionService v, CancellationToken ct) =>
    await v.LeerAsync(DescargaService.Buscar(carpetaDescargas, "Play.exe"), ct) is { } info ? Results.Ok(info) : Results.NotFound());

// ---------- Endpoints públicos (listas para los menús y login) ----------
app.MapGet("/api/estado", () => Results.Ok(new { ok = true }));

app.MapGet("/api/config", (IOptions<PlayOptions> o) => Results.Ok(new
{
    latidoSegundos = o.Value.HeartbeatSeconds,
    inactividadMinutos = o.Value.InactivityMinutes,
}));

app.MapGet("/api/empleados", async (PlayDb db) =>
    Results.Ok(await db.Empleados.AsNoTracking().Where(e => e.Activo).OrderBy(e => e.Nombre).Select(e => new { e.Id, e.Nombre, e.Area }).ToListAsync()));

app.MapGet("/api/obras", async (PlayDb db) =>
    Results.Ok(await db.Obras.AsNoTracking().Where(o => o.Activa).OrderBy(o => o.Nombre).Select(o => new
    {
        o.Id, o.Nombre,
        // Solo las subtareas activas; si hay alguna, el panel obliga a elegir una.
        Subtareas = o.Subtareas.Where(s => s.Activa && !s.Terminada).OrderBy(s => s.Nombre).Select(s => new { s.Id, s.Nombre }).ToList(),
    }).ToListAsync()));

app.MapPost("/api/login", async (LoginRequest req, AuthService auth, RegistroService reg) =>
{
    if (!AuthService.PinValido(req.Pin)) return Results.Json(new { codigo = "invalido" }, statusCode: 401);
    var (ok, error, hasta) = await auth.LoginEmpleadoAsync(req.EmpleadoId, req.Pin);
    if (ok is null)
        return error == "bloqueado"
            ? Results.Json(new { codigo = "bloqueado", hastaUtc = hasta }, statusCode: 423)
            : Results.Json(new { codigo = "invalido" }, statusCode: 401);
    return Results.Ok(new { ok.Token, ok.EmpleadoId, ok.Nombre, ok.DebeCambiarPin, registroActivo = await reg.ActivoAsync(ok.EmpleadoId) });
});

// ---------- Endpoints del empleado (requieren Authorization: Bearer <token>) ----------
var emp = app.MapGroup("/api").AddEndpointFilter(async (ctx, next) =>
{
    var auth = ctx.HttpContext.RequestServices.GetRequiredService<AuthService>();
    var id = await auth.EmpleadoDeSolicitudAsync(ctx.HttpContext.Request);
    if (id is null) return Results.Json(new { codigo = "no_autenticado" }, statusCode: 401);
    ctx.HttpContext.Items["empleadoId"] = id.Value;
    return await next(ctx);
});

static int Emp(HttpContext c) => (int)c.Items["empleadoId"]!;

emp.MapPost("/pin", async (HttpContext c, CambiarPinRequest r, AuthService auth, IOptions<PlayOptions> opciones) =>
    !string.IsNullOrWhiteSpace(opciones.Value.EmpleadosExcel) ? Results.Json(new { codigo = "gestionado_por_excel" }, statusCode: 409) // el PIN se cambia en el Excel
    : await auth.CambiarPinAsync(Emp(c), r.PinActual, r.PinNuevo) ? Results.NoContent() : Results.BadRequest(new { codigo = "pin_invalido" }));

emp.MapGet("/registro-activo", async (HttpContext c, RegistroService s) =>
    await s.ActivoAsync(Emp(c)) is { } r ? Results.Ok(r) : Results.NoContent());

emp.MapPost("/registros", (HttpContext c, IniciarRequest r, RegistroService s) => s.IniciarAsync(Emp(c), r.Id, r.ObraId, r.Equipo, r.SubtareaId));
emp.MapPost("/registros/cambiar-obra", (HttpContext c, IniciarRequest r, RegistroService s) => s.CambiarObraAsync(Emp(c), r.Id, r.ObraId, r.Equipo, r.SubtareaId));
emp.MapPost("/registros/sincronizar", async (HttpContext c, SincronizarRequest r, RegistroService s) => Results.Ok(await s.SincronizarAsync(Emp(c), r.Registros)));
emp.MapPost("/registros/{id:guid}/latido", (HttpContext c, Guid id, RegistroService s) => s.LatidoAsync(Emp(c), id));
emp.MapPost("/registros/{id:guid}/cerrar", (HttpContext c, Guid id, CerrarRequest? r, RegistroService s) => s.CerrarAsync(Emp(c), id, r?.FinUtc));
emp.MapPost("/subtareas/{id:int}/avisar", (HttpContext c, int id, RegistroService s) => s.AvisarSubtareaAsync(Emp(c), id));
emp.MapDelete("/subtareas/{id:int}/avisar", (HttpContext c, int id, RegistroService s) => s.RetirarAvisoAsync(Emp(c), id));
emp.MapGet("/mis-avisos", async (HttpContext c, RegistroService s) => Results.Ok(await s.MisAvisosAsync(Emp(c))));
// Horas de Taller: solo para empleados del área Taller (el servidor lo exige; los demás reciben 403 `solo_taller`).
emp.MapGet("/horas", async (HttpContext c, HorasService s) => De(await s.MisHorasAsync(Emp(c))));
emp.MapPost("/horas", async (HttpContext c, CargarHorasRequest r, HorasService s) => De(await s.CargarAsync(Emp(c), r.Fecha, r.Minutos, r.ObraId, r.SubtareaId)));
emp.MapDelete("/horas", async (HttpContext c, HorasService s, DateOnly fecha, int? obraId, int? subtareaId) => De(await s.RetirarAsync(Emp(c), fecha, obraId, subtareaId)));
emp.MapGet("/resumen", async (HttpContext c, RegistroService s) => Results.Ok(await s.ResumenAsync(Emp(c))));

// ---------- Administración ----------
app.MapPost("/api/admin/login", async (AdminLoginRequest req, AuthService auth) =>
{
    var (token, error, debeCambiar, hasta) = await auth.LoginAdminAsync(req.Usuario ?? "", req.Password ?? "");
    if (token is null)
        return error == "bloqueado"
            ? Results.Json(new { codigo = "bloqueado", hastaUtc = hasta }, statusCode: 423)
            : Results.Json(new { codigo = "invalido" }, statusCode: 401);
    return Results.Ok(new { token, debeCambiarClave = debeCambiar });
});

var adm = app.MapGroup("/api/admin").AddEndpointFilter(async (ctx, next) =>
{
    var http = ctx.HttpContext;
    var a = await http.RequestServices.GetRequiredService<AuthService>().AdminDeSolicitudAsync(http.Request);
    if (a is null) return Results.Json(new { codigo = "no_autenticado" }, statusCode: 401);
    // Con clave temporal solo se permite cambiarla.
    if (a.Value.DebeCambiar && !http.Request.Path.Equals("/api/admin/clave", StringComparison.OrdinalIgnoreCase))
        return Results.Json(new { codigo = "debe_cambiar_clave" }, statusCode: 403);
    http.Items["adminId"] = a.Value.Id;
    return await next(ctx);
});

static int Adm(HttpContext c) => (int)c.Items["adminId"]!;
static IResult De<T>(Res<T> r, Func<T, object>? map = null) =>
    r.Ok ? Results.Ok(map is null ? r.Valor : map(r.Valor!)) : Results.Json(new { codigo = r.Error }, statusCode: r.Http);

adm.MapPost("/clave", async (HttpContext c, CambiarClaveRequest r, AuthService auth) =>
    await auth.CambiarPassAdminAsync(Adm(c), r.ClaveActual ?? "", r.ClaveNueva ?? "") ? Results.NoContent() : Results.BadRequest(new { codigo = "clave_invalida" }));

adm.MapGet("/empleados", async (AdminService s, string? area) => Results.Ok(await s.EmpleadosAsync(area)));
adm.MapPost("/empleados", async (NuevoEmpleadoRequest r, AdminService s) => De(await s.CrearEmpleadoAsync(r.Nombre ?? "", r.Area), v => new { empleado = v.Empleado, pinInicial = v.Pin }));
adm.MapPut("/empleados/{id:int}", async (HttpContext c, int id, ActualizarRequest r, AdminService s) => De(await s.ActualizarEmpleadoAsync(Adm(c), id, r.Nombre, r.Activo, r.Area)));

// PIN visibles para el administrador (cada consulta y cada exportación queda en la auditoría).
adm.MapGet("/pines", async (HttpContext c, AdminService s, string? area) => Results.Ok(await s.PinesAsync(Adm(c), area)));
adm.MapGet("/pines.xlsx", async (HttpContext c, AdminService s, string? area) =>
{
    var pines = await s.ListarPinesAsync(area);
    await s.RegistrarExportacionDePinesAsync(Adm(c), area, pines.Count);
    return Results.File(ReporteService.GenerarExcelPines(pines, area), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "pines.xlsx");
});
adm.MapPost("/empleados/{id:int}/reset-pin", async (HttpContext c, int id, AdminService s) => De(await s.ResetearPinAsync(Adm(c), id), pin => new { pinInicial = pin }));

adm.MapGet("/obras", async (AdminService s) => Results.Ok(await s.ObrasAsync()));
adm.MapPost("/obras", async (NombreRequest r, AdminService s) => De(await s.CrearObraAsync(r.Nombre ?? "")));
adm.MapPut("/obras/{id:int}", async (int id, ActualizarRequest r, AdminService s) => De(await s.ActualizarObraAsync(id, r.Nombre, r.Activo)));

// Subtareas de cada obra (activas e inactivas; las inactivas dejan de ofrecerse a los empleados).
adm.MapGet("/obras/{id:int}/subtareas", async (int id, AdminService s) => De(await s.SubtareasAsync(id)));
adm.MapPost("/obras/{id:int}/subtareas", async (int id, NombreRequest r, AdminService s) => De(await s.CrearSubtareaAsync(id, r.Nombre ?? "")));
adm.MapPut("/subtareas/{id:int}", async (HttpContext c, int id, ActualizarRequest r, AdminService s) => De(await s.ActualizarSubtareaAsync(Adm(c), id, r.Nombre, r.Activo, r.Terminada)));

// Avisos de «terminé esta subtarea» (los crean los empleados; el administrador los acepta -> subtarea tachada- o los descarta).
adm.MapGet("/avisos", async (AdminService s, string? estado) => Results.Ok(await s.AvisosAsync(estado)));
adm.MapPost("/avisos/{id:int}/aceptar", async (HttpContext c, int id, AdminService s) => De(await s.AceptarAvisoAsync(Adm(c), id)));
adm.MapPost("/avisos/{id:int}/descartar", async (HttpContext c, int id, AdminService s) => De(await s.DescartarAvisoAsync(Adm(c), id)));

adm.MapGet("/administradores", async (AdminService s) => Results.Ok(await s.AdministradoresAsync()));
adm.MapPost("/administradores", async (NuevoAdminRequest r, AdminService s) => De(await s.CrearAdministradorAsync(r.Usuario ?? "", r.NombreCompleto), v => new { administrador = v.Admin, claveTemporal = v.Clave }));
adm.MapPut("/administradores/{id:int}", async (HttpContext c, int id, ActualizarRequest r, AdminService s) => De(await s.ActualizarAdministradorAsync(Adm(c), id, r.Activo ?? true)));
adm.MapPost("/administradores/{id:int}/reset-clave", async (HttpContext c, int id, AdminService s) => De(await s.ResetearClaveAdminAsync(Adm(c), id), clave => new { claveTemporal = clave }));

adm.MapGet("/en-vivo", async (AdminService s, string? area) => Results.Ok(await s.EnVivoAsync(area)));
adm.MapGet("/registros", async (AdminService s, int? empleadoId, int? obraId, DateOnly? desde, DateOnly? hasta, bool? revisar, int? limite, bool? eliminados, string? area) =>
    Results.Ok(await s.RegistrosAsync(new FiltroRegistros(empleadoId, obraId, desde, hasta, revisar, limite ?? 500, eliminados ?? false, area))));
adm.MapPost("/registros/{id:guid}/eliminar", async (HttpContext c, Guid id, MotivoRequest r, AdminService s) => De(await s.AnularAsync(Adm(c), id, r.Motivo ?? "")));
adm.MapPost("/registros/{id:guid}/recuperar", async (HttpContext c, Guid id, MotivoRequest r, AdminService s) => De(await s.RestaurarAsync(Adm(c), id, r.Motivo ?? "")));
adm.MapPost("/registros", async (HttpContext c, AltaRegistroRequest r, AdminService s) => De(await s.CrearRegistroAsync(Adm(c), r)));
adm.MapPut("/registros/{id:guid}", async (HttpContext c, Guid id, CorreccionRequest r, AdminService s) => De(await s.CorregirAsync(Adm(c), id, r)));
adm.MapGet("/auditoria", async (AdminService s, Guid? registroId, int? limite) => Results.Ok(await s.AuditoriaAsync(registroId, limite ?? 500)));

// Horas cargadas por los empleados de Taller.
adm.MapGet("/horas", async (HorasService s, int? empleadoId, DateOnly? desde, DateOnly? hasta, bool? eliminados, int? obraId) =>
    Results.Ok(await s.ListarAsync(new FiltroHoras(empleadoId, desde, hasta, eliminados ?? false, ObraId: obraId))));
adm.MapPost("/horas", async (HttpContext c, AltaHorasRequest r, HorasService s) => De(await s.CrearAsync(Adm(c), r)));
adm.MapPut("/horas/{id:int}", async (HttpContext c, int id, CorregirHorasRequest r, HorasService s) => De(await s.CorregirAsync(Adm(c), id, r.Minutos, r.Motivo)));
adm.MapPost("/horas/{id:int}/eliminar", async (HttpContext c, int id, MotivoRequest r, HorasService s) => De(await s.AnularAsync(Adm(c), id, r.Motivo)));
adm.MapPost("/horas/{id:int}/recuperar", async (HttpContext c, int id, MotivoRequest r, HorasService s) => De(await s.RestaurarAsync(Adm(c), id, r.Motivo)));
adm.MapGet("/horas.xlsx", async (HorasService s, int? empleadoId, DateOnly? desde, DateOnly? hasta) =>
    Results.File(ReporteService.GenerarExcelHoras(await s.ListarAsync(new FiltroHoras(empleadoId, desde, hasta))),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "horas-taller.xlsx"));

// Asistencia (solo lunes a viernes): libro mensual y faltas (justificadas o injustificadas).
adm.MapGet("/asistencia", async (AsistenciaService s, int? anio, int? mes, string? area, int? empleadoId) =>
{
    var hoy = s.Hoy;
    var a = anio ?? hoy.Year; var m = mes ?? hoy.Month;
    if (a is < 2000 or > 2100 || m is < 1 or > 12) return Results.BadRequest(new { codigo = "periodo_invalido" });
    return Results.Ok(await s.MesAsync(a, m, area, empleadoId));
});
adm.MapGet("/asistencia.xlsx", async (AsistenciaService s, int? anio, int? mes, string? area) =>
{
    var hoy = s.Hoy;
    var a = anio ?? hoy.Year; var m = mes ?? hoy.Month;
    if (a is < 2000 or > 2100 || m is < 1 or > 12) return Results.BadRequest(new { codigo = "periodo_invalido" });
    var libro = await s.MesAsync(a, m, area, null);
    var primero = new DateOnly(a, m, 1);
    var faltas = await s.FaltasAsync(new FiltroFaltas(primero, primero.AddMonths(1).AddDays(-1), null, area, null));
    return Results.File(ReporteService.GenerarExcelAsistencia(libro, faltas), "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", $"asistencia_{a}-{m:00}.xlsx");
});
adm.MapGet("/faltas", async (AsistenciaService s, DateOnly? desde, DateOnly? hasta, int? empleadoId, string? area, string? estado) =>
    Results.Ok(await s.FaltasAsync(new FiltroFaltas(desde, hasta, empleadoId, area, estado))));
adm.MapGet("/faltas/alertas", async (AsistenciaService s) => Results.Ok(new { sinRevisar = await s.ContarSinRevisarAsync() }));
adm.MapPost("/faltas/justificar", async (HttpContext c, FaltaRequest r, AsistenciaService s) => De(await s.JustificarAsync(Adm(c), r.EmpleadoId, r.Fecha, r.Motivo)));
adm.MapPost("/faltas/injustificar", async (HttpContext c, FaltaRequest r, AsistenciaService s) => De(await s.InjustificarAsync(Adm(c), r.EmpleadoId, r.Fecha, r.Motivo)));
// Excel de empleados: estado de la última sincronización y «Sincronizar ahora».
adm.MapGet("/empleados-excel", (EmpleadosExcelService s) => Results.Ok(s.Dto()));
adm.MapPost("/empleados-excel/sincronizar", async (EmpleadosExcelService s) => Results.Ok(await s.SincronizarAsync(forzar: true)));

adm.MapGet("/backups", (BackupService b) => Results.Ok(new { carpeta = b.Carpeta, backups = b.Listar() }));
adm.MapPost("/backups", async (BackupService b) => Results.Ok(await b.HacerBackupAsync()));

adm.MapGet("/reporte.xlsx", async (ReporteService s, int? empleadoId, int? obraId, DateOnly? desde, DateOnly? hasta, string? area) =>
    Results.File(await s.GenerarExcelAsync(new FiltroReporte(empleadoId, obraId, desde, hasta, area)),
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "horas.xlsx"));

app.Run();

static string DataDirDe(IServiceProvider sp)
{
    var dir = Path.GetFullPath(sp.GetRequiredService<IOptions<PlayOptions>>().Value.DataDir, sp.GetRequiredService<IHostEnvironment>().ContentRootPath);
    Directory.CreateDirectory(dir);
    return dir;
}

record AdminLoginRequest(string? Usuario, string? Password);
record CambiarClaveRequest(string? ClaveActual, string? ClaveNueva);
record NombreRequest(string? Nombre);
record MotivoRequest(string? Motivo);
record NuevoEmpleadoRequest(string? Nombre, string? Area);
record ActualizarRequest(string? Nombre, bool? Activo, string? Area = null, bool? Terminada = null);
record NuevoAdminRequest(string? Usuario, string? NombreCompleto);
record LoginRequest(int EmpleadoId, string Pin);
record CambiarPinRequest(string PinActual, string PinNuevo);
record IniciarRequest(Guid Id, int ObraId, string? Equipo, int? SubtareaId = null);
record CerrarRequest(DateTime? FinUtc);
record SincronizarRequest(List<SincronizarItem> Registros);

public partial class Program;
