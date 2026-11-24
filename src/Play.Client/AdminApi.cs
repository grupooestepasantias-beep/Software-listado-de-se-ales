using System.Globalization;

namespace Play.Client;

/// <param name="PinConocido">false = el PIN lo eligió el empleado antes de que se guardara legible: hay que resetearlo para verlo.</param>
public record EmpleadoAdminDto(int Id, string Nombre, bool Activo, bool DebeCambiarPin, string Area = "Oficina", bool PinConocido = false);
public record PinAdminDto(int Id, string Nombre, string Area, bool Activo, string? Pin, bool DebeCambiarPin);
/// <param name="SubtareasActivas">Si es mayor que 0, quien registre horas en esta obra debe elegir una subtarea.</param>
public record ObraAdminDto(int Id, string Nombre, bool Activa, int SubtareasActivas = 0);
public record SubtareaAdminDto(int Id, int ObraId, string Nombre, bool Activa, bool Terminada = false);
/// <param name="Tipo">habil | finde</param>
public record DiaDto(DateOnly Fecha, string Tipo);
/// <param name="Codigos">Un código por día: P presente · A ausente · J justificado · S fin de semana · … el día no terminó · - sin control</param>
public record FilaAsistenciaDto(int EmpleadoId, string Empleado, string Area, bool Activo, List<string> Codigos, int Presentes, int Ausentes, int Justificados);
public record AsistenciaMesDto(int Anio, int Mes, DateOnly Hoy, DateOnly? ControlDesde, List<DiaDto> Dias, List<FilaAsistenciaDto> Filas);
/// <param name="Estado">sin_revisar | injustificada | justificada</param>
public record FaltaDto(int EmpleadoId, string Empleado, string Area, DateOnly Fecha, string Estado, string? Motivo, DateTime? ResueltaUtc, string? Administrador);
public record AlertasFaltas(int SinRevisar);

public record ErrorFilaExcel(int Fila, string Mensaje);
/// <summary>Estado de la última sincronización con el Excel de empleados (Configurado = false: los empleados se manejan desde la app).</summary>
public record EmpleadosExcelEstadoDto(bool Configurado, string? Archivo, DateTime? UltimaUtc, bool? Ok, string? Mensaje,
    int Empleados, int Administradores, int Creados, int Actualizados, int Desactivados, List<ErrorFilaExcel> Errores);

/// <summary>Una carga de horas de Taller vista por el administrador.</summary>
public record CargaAdminDto(int Id, int EmpleadoId, string Empleado, DateOnly Fecha, int Minutos, DateTime CreadaUtc, DateTime ActualizadaUtc, string Origen, bool Anulado,
    int? ObraId = null, string? Obra = null, int? SubtareaId = null, string? Subtarea = null);
/// <summary>Aviso de un empleado: «terminé esta subtarea».</summary>
public record AvisoAdminDto(int Id, int SubtareaId, string Subtarea, int ObraId, string Obra, int EmpleadoId, string Empleado, string Area,
    DateTime CreadoUtc, string Estado, DateTime? ResueltoUtc, bool SubtareaTerminada);
public record AdminDto(int Id, string Usuario, string NombreCompleto, bool Activo);
public record RegistroAdminDto(Guid Id, int EmpleadoId, string Empleado, int ObraId, string Obra, DateTime InicioUtc,
    DateTime? FinUtc, string Estado, string Origen, string Equipo, bool RevisarAdmin, long Segundos, bool Anulado = false, string Area = "Oficina",
    string? Subtarea = null, int? SubtareaId = null);
public record AuditoriaDto(int Id, DateTime FechaUtc, string Administrador, Guid? RegistroId, string Campo,
    string? ValorAnterior, string? ValorNuevo, string Motivo);
public record EnVivoDto(int EmpleadoId, string Empleado, string Obra, string Equipo, DateTime InicioUtc, DateTime UltimoLatidoUtc, long Segundos, string Area = "Oficina");
public record BackupInfo(string Archivo, long Bytes, DateTime FechaUtc);
public record BackupsDto(string Carpeta, List<BackupInfo> Backups);

public record AdminLoginResponse(string Token, bool DebeCambiarClave);
public record NuevoEmpleadoResponse(EmpleadoAdminDto Empleado, string PinInicial);
public record NuevoAdminResponse(AdminDto Administrador, string ClaveTemporal);
public record PinInicialResponse(string PinInicial);
public record ClaveTemporalResponse(string ClaveTemporal);

/// <param name="Eliminados">true = solo los registros eliminados (para recuperarlos).</param>
public record FiltroAdmin(int? EmpleadoId = null, int? ObraId = null, DateOnly? Desde = null, DateOnly? Hasta = null, bool? Revisar = null, int Limite = 1000, bool Eliminados = false, string? Area = null);

/// <summary>Cliente de la API de administración del servidor.</summary>
public sealed class AdminApi(ApiClient http)
{
    public string? Token { get => http.Token; set => http.Token = value; }

    private static string Qs(FiltroAdmin f, bool conLimite)
    {
        var p = new List<string>();
        if (f.EmpleadoId is { } e) p.Add($"empleadoId={e}");
        if (f.ObraId is { } o) p.Add($"obraId={o}");
        if (f.Desde is { } d) p.Add($"desde={d.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)}");
        if (f.Hasta is { } h) p.Add($"hasta={h.ToString("yyyy-MM-dd", CultureInfo.InvariantCulture)}");
        if (f.Revisar is true) p.Add("revisar=true");
        if (f.Eliminados && conLimite) p.Add("eliminados=true");
        if (!string.IsNullOrWhiteSpace(f.Area)) p.Add($"area={Uri.EscapeDataString(f.Area)}");
        if (conLimite) p.Add($"limite={f.Limite}");
        return p.Count == 0 ? "" : "?" + string.Join("&", p);
    }

    public Task<ApiResult<AdminLoginResponse>> LoginAsync(string usuario, string password) =>
        http.LlamarAsync<AdminLoginResponse>(HttpMethod.Post, "api/admin/login", new { usuario, password });
    public Task<ApiResult<Vacio>> CambiarClaveAsync(string claveActual, string claveNueva) =>
        http.LlamarAsync<Vacio>(HttpMethod.Post, "api/admin/clave", new { claveActual, claveNueva });

    // Empleados
    public Task<ApiResult<List<EmpleadoAdminDto>>> EmpleadosAsync(string? area = null) =>
        http.LlamarAsync<List<EmpleadoAdminDto>>(HttpMethod.Get, "api/admin/empleados" + (string.IsNullOrWhiteSpace(area) ? "" : $"?area={Uri.EscapeDataString(area)}"));
    public Task<ApiResult<NuevoEmpleadoResponse>> CrearEmpleadoAsync(string nombre, string? area = null) =>
        http.LlamarAsync<NuevoEmpleadoResponse>(HttpMethod.Post, "api/admin/empleados", new { nombre, area });
    public Task<ApiResult<EmpleadoAdminDto>> ActualizarEmpleadoAsync(int id, string? nombre = null, bool? activo = null, string? area = null) =>
        http.LlamarAsync<EmpleadoAdminDto>(HttpMethod.Put, $"api/admin/empleados/{id}", new { nombre, activo, area });

    /// <summary>PIN de los empleados, en texto legible. Cada consulta queda registrada en la auditoría.</summary>
    public Task<ApiResult<List<PinAdminDto>>> PinesAsync(string? area = null) =>
        http.LlamarAsync<List<PinAdminDto>>(HttpMethod.Get, "api/admin/pines" + (string.IsNullOrWhiteSpace(area) ? "" : $"?area={Uri.EscapeDataString(area)}"));
    /// <summary>Excel con los PIN (confidencial). Queda registrado en la auditoría.</summary>
    public Task<ApiResult<byte[]>> PinesExcelAsync(string? area = null) =>
        http.DescargarAsync("api/admin/pines.xlsx" + (string.IsNullOrWhiteSpace(area) ? "" : $"?area={Uri.EscapeDataString(area)}"));
    public Task<ApiResult<PinInicialResponse>> ResetearPinAsync(int id) => http.LlamarAsync<PinInicialResponse>(HttpMethod.Post, $"api/admin/empleados/{id}/reset-pin");

    // Obras
    public Task<ApiResult<List<ObraAdminDto>>> ObrasAsync() => http.LlamarAsync<List<ObraAdminDto>>(HttpMethod.Get, "api/admin/obras");
    public Task<ApiResult<ObraAdminDto>> CrearObraAsync(string nombre) => http.LlamarAsync<ObraAdminDto>(HttpMethod.Post, "api/admin/obras", new { nombre });
    public Task<ApiResult<ObraAdminDto>> ActualizarObraAsync(int id, string? nombre = null, bool? activo = null) =>
        http.LlamarAsync<ObraAdminDto>(HttpMethod.Put, $"api/admin/obras/{id}", new { nombre, activo });

    // Subtareas (propias de cada obra)
    /// <summary>Todas las subtareas de una obra, activas e inactivas.</summary>
    public Task<ApiResult<List<SubtareaAdminDto>>> SubtareasAsync(int obraId) =>
        http.LlamarAsync<List<SubtareaAdminDto>>(HttpMethod.Get, $"api/admin/obras/{obraId}/subtareas");
    public Task<ApiResult<SubtareaAdminDto>> CrearSubtareaAsync(int obraId, string nombre) =>
        http.LlamarAsync<SubtareaAdminDto>(HttpMethod.Post, $"api/admin/obras/{obraId}/subtareas", new { nombre });
    public Task<ApiResult<SubtareaAdminDto>> ActualizarSubtareaAsync(int id, string? nombre = null, bool? activa = null, bool? terminada = null) =>
        http.LlamarAsync<SubtareaAdminDto>(HttpMethod.Put, $"api/admin/subtareas/{id}", new { nombre, activo = activa, terminada });

    // Excel de empleados (la base de datos de empleados cuando está configurado)
    public Task<ApiResult<EmpleadosExcelEstadoDto>> EmpleadosExcelAsync() => http.LlamarAsync<EmpleadosExcelEstadoDto>(HttpMethod.Get, "api/admin/empleados-excel");
    public Task<ApiResult<EmpleadosExcelEstadoDto>> SincronizarEmpleadosExcelAsync() => http.LlamarAsync<EmpleadosExcelEstadoDto>(HttpMethod.Post, "api/admin/empleados-excel/sincronizar");

    // Asistencia y faltas
    public Task<ApiResult<AsistenciaMesDto>> AsistenciaAsync(int anio, int mes, string? area = null, int? empleadoId = null) =>
        http.LlamarAsync<AsistenciaMesDto>(HttpMethod.Get, $"api/admin/asistencia?anio={anio}&mes={mes}" + (area is null ? "" : $"&area={Uri.EscapeDataString(area)}") + (empleadoId is { } e ? $"&empleadoId={e}" : ""));
    public Task<ApiResult<byte[]>> AsistenciaExcelAsync(int anio, int mes, string? area = null) =>
        http.DescargarAsync($"api/admin/asistencia.xlsx?anio={anio}&mes={mes}" + (area is null ? "" : $"&area={Uri.EscapeDataString(area)}"));
    public Task<ApiResult<List<FaltaDto>>> FaltasAsync(DateOnly? desde = null, DateOnly? hasta = null, int? empleadoId = null, string? area = null, string? estado = null)
    {
        var p = new List<string>();
        if (desde is { } d) p.Add($"desde={d:yyyy-MM-dd}");
        if (hasta is { } h) p.Add($"hasta={h:yyyy-MM-dd}");
        if (empleadoId is { } e) p.Add($"empleadoId={e}");
        if (area is not null) p.Add($"area={Uri.EscapeDataString(area)}");
        if (estado is not null) p.Add($"estado={Uri.EscapeDataString(estado)}");
        return http.LlamarAsync<List<FaltaDto>>(HttpMethod.Get, "api/admin/faltas" + (p.Count == 0 ? "" : "?" + string.Join("&", p)));
    }
    public Task<ApiResult<AlertasFaltas>> AlertasFaltasAsync() => http.LlamarAsync<AlertasFaltas>(HttpMethod.Get, "api/admin/faltas/alertas");
    public Task<ApiResult<FaltaDto>> JustificarFaltaAsync(int empleadoId, DateOnly fecha, string motivo) =>
        http.LlamarAsync<FaltaDto>(HttpMethod.Post, "api/admin/faltas/justificar", new { empleadoId, fecha, motivo });
    public Task<ApiResult<FaltaDto>> InjustificarFaltaAsync(int empleadoId, DateOnly fecha, string? motivo = null) =>
        http.LlamarAsync<FaltaDto>(HttpMethod.Post, "api/admin/faltas/injustificar", new { empleadoId, fecha, motivo });
    // Horas cargadas por los empleados de Taller
    private static string ParamsHoras(int? empleadoId, DateOnly? desde, DateOnly? hasta, bool eliminados = false, int? obraId = null)
    {
        var p = new List<string>();
        if (empleadoId is { } e) p.Add($"empleadoId={e}");
        if (desde is { } d) p.Add($"desde={d:yyyy-MM-dd}");
        if (hasta is { } h) p.Add($"hasta={h:yyyy-MM-dd}");
        if (eliminados) p.Add("eliminados=true");
        if (obraId is { } o) p.Add($"obraId={o}");
        return p.Count == 0 ? "" : "?" + string.Join("&", p);
    }
    public Task<ApiResult<List<CargaAdminDto>>> HorasAsync(int? empleadoId = null, DateOnly? desde = null, DateOnly? hasta = null, bool eliminados = false, int? obraId = null) =>
        http.LlamarAsync<List<CargaAdminDto>>(HttpMethod.Get, "api/admin/horas" + ParamsHoras(empleadoId, desde, hasta, eliminados, obraId));
    public Task<ApiResult<CargaAdminDto>> CrearHorasAsync(int empleadoId, DateOnly fecha, int minutos, string motivo, int? obraId = null, int? subtareaId = null) =>
        http.LlamarAsync<CargaAdminDto>(HttpMethod.Post, "api/admin/horas", new { empleadoId, fecha, minutos, motivo, obraId, subtareaId });
    public Task<ApiResult<CargaAdminDto>> CorregirHorasAsync(int id, int minutos, string motivo) =>
        http.LlamarAsync<CargaAdminDto>(HttpMethod.Put, $"api/admin/horas/{id}", new { minutos, motivo });
    public Task<ApiResult<CargaAdminDto>> EliminarHorasAsync(int id, string motivo) =>
        http.LlamarAsync<CargaAdminDto>(HttpMethod.Post, $"api/admin/horas/{id}/eliminar", new { motivo });
    public Task<ApiResult<CargaAdminDto>> RecuperarHorasAsync(int id, string motivo) =>
        http.LlamarAsync<CargaAdminDto>(HttpMethod.Post, $"api/admin/horas/{id}/recuperar", new { motivo });
    public Task<ApiResult<byte[]>> HorasExcelAsync(int? empleadoId = null, DateOnly? desde = null, DateOnly? hasta = null) =>
        http.DescargarAsync("api/admin/horas.xlsx" + ParamsHoras(empleadoId, desde, hasta));

    // Avisos de «terminé esta subtarea» (estado: «nuevos» por defecto, «todos», «aceptado», «descartado»)
    public Task<ApiResult<List<AvisoAdminDto>>> AvisosAsync(string? estado = null) =>
        http.LlamarAsync<List<AvisoAdminDto>>(HttpMethod.Get, estado is null ? "api/admin/avisos" : $"api/admin/avisos?estado={Uri.EscapeDataString(estado)}");
    public Task<ApiResult<AvisoAdminDto>> AceptarAvisoAsync(int id) => http.LlamarAsync<AvisoAdminDto>(HttpMethod.Post, $"api/admin/avisos/{id}/aceptar");
    public Task<ApiResult<AvisoAdminDto>> DescartarAvisoAsync(int id) => http.LlamarAsync<AvisoAdminDto>(HttpMethod.Post, $"api/admin/avisos/{id}/descartar");

    // Administradores
    public Task<ApiResult<List<AdminDto>>> AdministradoresAsync() => http.LlamarAsync<List<AdminDto>>(HttpMethod.Get, "api/admin/administradores");
    public Task<ApiResult<NuevoAdminResponse>> CrearAdministradorAsync(string usuario, string? nombreCompleto) =>
        http.LlamarAsync<NuevoAdminResponse>(HttpMethod.Post, "api/admin/administradores", new { usuario, nombreCompleto });
    public Task<ApiResult<AdminDto>> ActivarAdministradorAsync(int id, bool activo) =>
        http.LlamarAsync<AdminDto>(HttpMethod.Put, $"api/admin/administradores/{id}", new { activo });
    public Task<ApiResult<ClaveTemporalResponse>> ResetearClaveAdminAsync(int id) =>
        http.LlamarAsync<ClaveTemporalResponse>(HttpMethod.Post, $"api/admin/administradores/{id}/reset-clave");

    // Registros
    public Task<ApiResult<List<EnVivoDto>>> EnVivoAsync(string? area = null) =>
        http.LlamarAsync<List<EnVivoDto>>(HttpMethod.Get, "api/admin/en-vivo" + (string.IsNullOrWhiteSpace(area) ? "" : $"?area={Uri.EscapeDataString(area)}"));
    public Task<ApiResult<List<RegistroAdminDto>>> RegistrosAsync(FiltroAdmin f) =>
        http.LlamarAsync<List<RegistroAdminDto>>(HttpMethod.Get, "api/admin/registros" + Qs(f, conLimite: true));
    /// <param name="subtareaId">Nueva subtarea (de la obra resultante). Si cambia la obra y no se indica, la subtarea se quita.</param>
    /// <param name="quitarSubtarea">true = dejar el registro sin subtarea.</param>
    public Task<ApiResult<RegistroAdminDto>> CorregirAsync(Guid id, DateTime? inicioUtc, DateTime? finUtc, int? obraId, string motivo, int? subtareaId = null, bool quitarSubtarea = false) =>
        http.LlamarAsync<RegistroAdminDto>(HttpMethod.Put, $"api/admin/registros/{id}", new { inicioUtc, finUtc, obraId, motivo, subtareaId, quitarSubtarea });
    public Task<ApiResult<RegistroAdminDto>> CrearRegistroAsync(int empleadoId, int obraId, DateTime inicioUtc, DateTime finUtc, string motivo, int? subtareaId = null) =>
        http.LlamarAsync<RegistroAdminDto>(HttpMethod.Post, "api/admin/registros", new { empleadoId, obraId, inicioUtc, finUtc, motivo, subtareaId });
    /// <summary>«Eliminar»: no se borra, queda marcado con motivo y se puede recuperar. No aplica a registros en curso.</summary>
    public Task<ApiResult<RegistroAdminDto>> EliminarRegistroAsync(Guid id, string motivo) =>
        http.LlamarAsync<RegistroAdminDto>(HttpMethod.Post, $"api/admin/registros/{id}/eliminar", new { motivo });
    public Task<ApiResult<RegistroAdminDto>> RecuperarRegistroAsync(Guid id, string motivo) =>
        http.LlamarAsync<RegistroAdminDto>(HttpMethod.Post, $"api/admin/registros/{id}/recuperar", new { motivo });
    public Task<ApiResult<List<AuditoriaDto>>> AuditoriaAsync(Guid? registroId = null) =>
        http.LlamarAsync<List<AuditoriaDto>>(HttpMethod.Get, "api/admin/auditoria" + (registroId is { } r ? $"?registroId={r}" : ""));

    /// <summary>Versión de Play.exe publicada para los empleados (404 si todavía no hay ninguna).</summary>
    public Task<ApiResult<VersionPanelDto>> VersionPanelAsync() => http.LlamarAsync<VersionPanelDto>(HttpMethod.Get, "api/panel/version");

    // Backups y reportes
    public Task<ApiResult<BackupsDto>> BackupsAsync() => http.LlamarAsync<BackupsDto>(HttpMethod.Get, "api/admin/backups");
    public Task<ApiResult<BackupInfo>> HacerBackupAsync() => http.LlamarAsync<BackupInfo>(HttpMethod.Post, "api/admin/backups");
    public Task<ApiResult<byte[]>> ReporteExcelAsync(FiltroAdmin f) => http.DescargarAsync("api/admin/reporte.xlsx" + Qs(f, conLimite: false));
}
