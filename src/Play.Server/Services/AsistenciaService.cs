using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Play.Server.Data;

namespace Play.Server.Services;

/// <param name="Tipo">habil | finde</param>
public record DiaDto(DateOnly Fecha, string Tipo);
/// <param name="Codigos">Un código por día del período: P presente · A ausente · J justificado · S sábado/domingo · … día que todavía no terminó · - sin control</param>
public record FilaAsistenciaDto(int EmpleadoId, string Empleado, string Area, bool Activo, List<string> Codigos, int Presentes, int Ausentes, int Justificados);
public record AsistenciaMesDto(int Anio, int Mes, DateOnly Hoy, DateOnly? ControlDesde, List<DiaDto> Dias, List<FilaAsistenciaDto> Filas);
/// <param name="Estado">sin_revisar | injustificada | justificada</param>
public record FaltaDto(int EmpleadoId, string Empleado, string Area, DateOnly Fecha, string Estado, string? Motivo, DateTime? ResueltaUtc, string? Administrador);
public record FaltaRequest(int EmpleadoId, DateOnly Fecha, string? Motivo);
public record FiltroFaltas(DateOnly? Desde, DateOnly? Hasta, int? EmpleadoId, string? Area, string? Estado);

/// <summary>
/// Control de asistencia (solo lunes a viernes). Presente = el empleado cumplió su carga del día: en Oficina,
/// al menos un registro del cronómetro (Play); en Taller, haber cargado horas. Los días se cierran a las 23:59 (hora del
/// servidor): ahí se genera UNA falta por empleado y día (índice único), que el administrador justifica o deja como
/// injustificada. El control empieza el día en que se activó la función (no hay faltas hacia atrás) y, para un empleado
/// nuevo, el día de su alta.
/// </summary>
public class AsistenciaService(PlayDb db, TimeProvider time, IOptions<PlayOptions> options)
{
    private const string ClaveDesde = "asistencia_desde";
    private const string ClaveCerrada = "asistencia_cerrada";
    private static readonly TimeSpan HoraCierre = new(23, 59, 0);

    private DateTime Ahora => time.GetUtcNow().UtcDateTime;
    private TimeZoneInfo Zona_ => Zona.De(options.Value);
    private DateTime AhoraLocal => TimeZoneInfo.ConvertTimeFromUtc(Ahora, Zona_);
    public DateOnly Hoy => DateOnly.FromDateTime(AhoraLocal);

    /// <summary>Último día ya cerrado: hoy si ya pasaron las 23:59, si no, ayer.</summary>
    private DateOnly CerradoHasta => AhoraLocal.TimeOfDay >= HoraCierre ? Hoy : Hoy.AddDays(-1);

    private static bool EsFinDeSemana(DateOnly f) => f.DayOfWeek is DayOfWeek.Saturday or DayOfWeek.Sunday;

    // ---------------------------------------------------------------- ajustes

    private async Task<DateOnly?> LeerFechaAsync(string clave)
    {
        var v = await db.Ajustes.AsNoTracking().Where(a => a.Clave == clave).Select(a => a.Valor).FirstOrDefaultAsync();
        return DateOnly.TryParse(v, out var f) ? f : null;
    }

    private async Task GuardarFechaAsync(string clave, DateOnly f)
    {
        var a = await db.Ajustes.FindAsync(clave);
        if (a is null) db.Ajustes.Add(new Ajuste { Clave = clave, Valor = f.ToString("yyyy-MM-dd") });
        else a.Valor = f.ToString("yyyy-MM-dd");
    }

    // ---------------------------------------------------------------- cálculo

    private sealed record EmpleadoInfo(int Id, string Nombre, string Area, bool Activo, DateOnly? Alta);

    private sealed class Calculo
    {
        public List<EmpleadoInfo> Empleados { get; init; } = [];
        public Dictionary<(int, DateOnly), string> Codigos { get; init; } = [];
        public Dictionary<(int, DateOnly), Falta> Faltas { get; init; } = [];
        public DateOnly? Desde { get; init; }
    }

    /// <summary>Calcula el código de cada empleado y día entre dos fechas (inclusive). Solo lectura.</summary>
    private async Task<Calculo> CalcularAsync(DateOnly desde, DateOnly hasta, int? empleadoId, string? area, bool soloActivos = false)
    {
        var zona = Zona_;
        var control = await LeerFechaAsync(ClaveDesde);
        var cerrado = CerradoHasta;

        var qe = db.Empleados.AsNoTracking().AsQueryable();
        if (empleadoId is { } e) qe = qe.Where(x => x.Id == e);
        if (Areas.Normalizar(area) is { } a) qe = qe.Where(x => x.Area == a);
        if (soloActivos) qe = qe.Where(x => x.Activo);
        var todos = await qe.OrderBy(x => x.Nombre).Select(x => new EmpleadoInfo(x.Id, x.Nombre, x.Area, x.Activo, x.CreadoFecha)).ToListAsync();

        var ids = todos.Select(x => x.Id).ToList();
        var faltas = (await db.Faltas.AsNoTracking().Where(f => f.Fecha >= desde && f.Fecha <= hasta && ids.Contains(f.EmpleadoId)).ToListAsync())
            .ToDictionary(f => (f.EmpleadoId, f.Fecha));

        // Actividad por empleado y día: registros del cronómetro (Oficina) y horas cargadas (Taller).
        var (desdeUtc, hastaUtc) = Zona.RangoUtc(zona, desde, hasta);
        var porRegistro = new HashSet<(int, DateOnly)>();
        var regs = await db.Registros.AsNoTracking()
            .Where(r => !r.Anulado && ids.Contains(r.EmpleadoId) && r.InicioUtc < hastaUtc && (r.FinUtc == null || r.FinUtc > desdeUtc))
            .Select(r => new { r.EmpleadoId, r.InicioUtc, r.FinUtc }).ToListAsync();
        foreach (var r in regs)
        {
            var ini = DateOnly.FromDateTime(TimeZoneInfo.ConvertTimeFromUtc(r.InicioUtc, zona));
            var fin = DateOnly.FromDateTime(TimeZoneInfo.ConvertTimeFromUtc(r.FinUtc ?? Ahora, zona));
            for (var d = ini < desde ? desde : ini; d <= fin && d <= hasta; d = d.AddDays(1)) porRegistro.Add((r.EmpleadoId, d));
        }
        var porCarga = (await db.CargasHoras.AsNoTracking().Where(c => !c.Anulado && c.Fecha >= desde && c.Fecha <= hasta && ids.Contains(c.EmpleadoId))
            .Select(c => new { c.EmpleadoId, c.Fecha }).ToListAsync()).Select(c => (c.EmpleadoId, c.Fecha)).ToHashSet();

        var codigos = new Dictionary<(int, DateOnly), string>();
        foreach (var emp in todos)
        {
            var inicioControl = control is null ? (DateOnly?)null : (emp.Alta is { } al && al > control ? al : control);
            for (var d = desde; d <= hasta; d = d.AddDays(1))
            {
                var presente = emp.Area == Areas.Taller ? porCarga.Contains((emp.Id, d)) : porRegistro.Contains((emp.Id, d));
                string codigo;
                if (EsFinDeSemana(d)) codigo = "S";
                else if (presente) codigo = "P";
                else if (inicioControl is null || d < inicioControl) codigo = "-";
                else if (d > cerrado) codigo = "…";
                else codigo = faltas.TryGetValue((emp.Id, d), out var fa) && fa.Estado == EstadoFalta.Justificada ? "J" : "A";
                codigos[(emp.Id, d)] = codigo;
            }
        }

        // Los empleados dados de baja solo figuran si tuvieron actividad o faltas en el período.
        var visibles = todos.Where(e => e.Activo || codigos.Where(k => k.Key.Item1 == e.Id).Any(k => k.Value is "P" or "A" or "J")).ToList();
        return new Calculo { Empleados = visibles, Codigos = codigos, Faltas = faltas, Desde = control };
    }

    // ---------------------------------------------------------------- cierre de días

    /// <summary>
    /// Cierra los días que ya terminaron: guarda una falta «ausente» por cada empleado activo que no cumplió su carga.
    /// Se puede llamar las veces que se quiera (no duplica). Devuelve cuántas faltas nuevas generó.
    /// </summary>
    public async Task<int> CerrarDiasAsync()
    {
        var hoy = Hoy;
        var desde = await LeerFechaAsync(ClaveDesde);
        if (desde is null)
        {
            // Primera vez: el control empieza hoy (no se generan faltas hacia atrás).
            await GuardarFechaAsync(ClaveDesde, hoy);
            await GuardarFechaAsync(ClaveCerrada, hoy.AddDays(-1));
            await db.SaveChangesAsync();
            desde = hoy;
        }
        var cerrada = await LeerFechaAsync(ClaveCerrada) ?? desde.Value.AddDays(-1);
        var hasta = CerradoHasta;
        if (hasta <= cerrada) return 0;

        var inicio = cerrada.AddDays(1);
        var calc = await CalcularAsync(inicio, hasta, null, null, soloActivos: true);
        var n = 0;
        foreach (var ((empId, fecha), codigo) in calc.Codigos)
        {
            if (codigo != "A" || calc.Faltas.ContainsKey((empId, fecha))) continue;
            db.Faltas.Add(new Falta { EmpleadoId = empId, Fecha = fecha, Estado = EstadoFalta.Ausente, CreadaUtc = Ahora });
            n++;
        }
        await GuardarFechaAsync(ClaveCerrada, hasta);
        await db.SaveChangesAsync();
        return n;
    }

    // ---------------------------------------------------------------- consultas

    public async Task<AsistenciaMesDto> MesAsync(int anio, int mes, string? area, int? empleadoId)
    {
        var primero = new DateOnly(anio, mes, 1);
        var ultimo = primero.AddMonths(1).AddDays(-1);
        var calc = await CalcularAsync(primero, ultimo, empleadoId, area);
        var dias = new List<DiaDto>();
        for (var d = primero; d <= ultimo; d = d.AddDays(1))
            dias.Add(new DiaDto(d, EsFinDeSemana(d) ? "finde" : "habil"));

        var filas = calc.Empleados.Select(e =>
        {
            var cods = dias.Select(d => calc.Codigos[(e.Id, d.Fecha)]).ToList();
            return new FilaAsistenciaDto(e.Id, e.Nombre, e.Area, e.Activo, cods, cods.Count(c => c == "P"), cods.Count(c => c == "A"), cods.Count(c => c == "J"));
        }).ToList();
        return new(anio, mes, Hoy, calc.Desde, dias, filas);
    }

    /// <summary>Historial de faltas (ausencias): sin revisar, injustificadas o justificadas.</summary>
    public async Task<List<FaltaDto>> FaltasAsync(FiltroFaltas f)
    {
        var hasta = f.Hasta ?? CerradoHasta;
        var desde = f.Desde ?? hasta.AddDays(-60);
        if (hasta < desde) return [];
        var calc = await CalcularAsync(desde, hasta, f.EmpleadoId, f.Area);
        var admins = await db.Administradores.AsNoTracking().ToDictionaryAsync(a => a.Id, a => a.Usuario);
        var lista = new List<FaltaDto>();
        foreach (var e in calc.Empleados)
            for (var d = desde; d <= hasta; d = d.AddDays(1))
            {
                var c = calc.Codigos[(e.Id, d)];
                if (c is not ("A" or "J")) continue;
                calc.Faltas.TryGetValue((e.Id, d), out var fa);
                var estado = c == "J" ? "justificada" : fa?.Estado == EstadoFalta.Injustificada ? "injustificada" : "sin_revisar";
                lista.Add(new FaltaDto(e.Id, e.Nombre, e.Area, d, estado, fa?.Motivo, fa?.ResueltaUtc, fa?.AdministradorId is { } aid ? admins.GetValueOrDefault(aid) : null));
            }
        var est = (f.Estado ?? "").Trim().ToLowerInvariant();
        if (est is "sin_revisar" or "injustificada" or "justificada") lista = lista.Where(x => x.Estado == est).ToList();
        return lista.OrderByDescending(x => x.Fecha).ThenBy(x => x.Empleado).ToList();
    }

    /// <summary>Cantidad de faltas todavía sin revisar (empleados activos; últimos 90 días). Es la alerta para el administrador.</summary>
    public async Task<int> ContarSinRevisarAsync()
    {
        var control = await LeerFechaAsync(ClaveDesde);
        if (control is null) return 0;
        var hasta = CerradoHasta;
        var desde = hasta.AddDays(-90) > control ? hasta.AddDays(-90) : control.Value;
        if (hasta < desde) return 0;
        var calc = await CalcularAsync(desde, hasta, null, null, soloActivos: true);
        return calc.Codigos.Count(k => k.Value == "A" && !(calc.Faltas.TryGetValue(k.Key, out var fa) && fa.Estado == EstadoFalta.Injustificada));
    }

    // ---------------------------------------------------------------- el administrador resuelve las faltas

    private async Task<(Res<FaltaDto>? Error, EmpleadoInfo? Emp)> ValidarAsync(int empleadoId, DateOnly fecha)
    {
        var calc = await CalcularAsync(fecha, fecha, empleadoId, null);
        var emp = calc.Empleados.FirstOrDefault(e => e.Id == empleadoId);
        if (emp is null) return (Res<FaltaDto>.Fallo("no_encontrado", 404), null);
        // Solo se resuelve una ausencia (o una ya justificada): no un día presente, de fin de semana o que todavía no terminó.
        if (calc.Codigos[(empleadoId, fecha)] is not ("A" or "J")) return (Res<FaltaDto>.Fallo("no_corresponde", 409), null);
        return (null, emp);
    }

    private FaltaDto Dto(EmpleadoInfo e, Falta f, int adminId) =>
        new(e.Id, e.Nombre, e.Area, f.Fecha, f.Estado == EstadoFalta.Justificada ? "justificada" : f.Estado == EstadoFalta.Injustificada ? "injustificada" : "sin_revisar", f.Motivo, f.ResueltaUtc, null);

    private async Task<Falta> ObtenerFaltaAsync(int empleadoId, DateOnly fecha)
    {
        var f = await db.Faltas.FirstOrDefaultAsync(x => x.EmpleadoId == empleadoId && x.Fecha == fecha);
        if (f is null) { f = new Falta { EmpleadoId = empleadoId, Fecha = fecha, Estado = EstadoFalta.Ausente, CreadaUtc = Ahora }; db.Faltas.Add(f); }
        return f;
    }

    private static string Nombre(EstadoFalta e) => e switch { EstadoFalta.Justificada => "justificada", EstadoFalta.Injustificada => "injustificada", _ => "sin revisar" };

    /// <summary>Justifica la falta (el motivo es obligatorio). El administrador simplemente la registra: no hace falta otra aprobación.</summary>
    public async Task<Res<FaltaDto>> JustificarAsync(int adminId, int empleadoId, DateOnly fecha, string? motivo)
    {
        if (string.IsNullOrWhiteSpace(motivo)) return Res<FaltaDto>.Fallo("motivo_requerido");
        if (motivo.Trim().Length > 500) return Res<FaltaDto>.Fallo("motivo_largo");
        var (error, emp) = await ValidarAsync(empleadoId, fecha);
        if (error is not null) return error;
        var f = await ObtenerFaltaAsync(empleadoId, fecha);
        var antes = f.Estado == EstadoFalta.Justificada && !string.IsNullOrWhiteSpace(f.Motivo) ? $"justificada: {f.Motivo}" : Nombre(f.Estado);
        f.Estado = EstadoFalta.Justificada;
        f.Motivo = motivo.Trim();
        f.ResueltaUtc = Ahora;
        f.AdministradorId = adminId;
        db.Auditorias.Add(new Auditoria { FechaUtc = Ahora, AdministradorId = adminId, Campo = "falta_justificada", ValorAnterior = $"{emp!.Nombre} {fecha:dd/MM/yyyy}: {antes}", ValorNuevo = $"{emp.Nombre} {fecha:dd/MM/yyyy}: justificada", Motivo = f.Motivo });
        await db.SaveChangesAsync();
        return new(Dto(emp, f, adminId));
    }

    /// <summary>La falta queda como injustificada (el motivo es opcional). También sirve para quitar una justificación.</summary>
    public async Task<Res<FaltaDto>> InjustificarAsync(int adminId, int empleadoId, DateOnly fecha, string? motivo)
    {
        var (error, emp) = await ValidarAsync(empleadoId, fecha);
        if (error is not null) return error;
        var f = await ObtenerFaltaAsync(empleadoId, fecha);
        var antes = f.Estado == EstadoFalta.Justificada && !string.IsNullOrWhiteSpace(f.Motivo) ? $"justificada: {f.Motivo}" : Nombre(f.Estado);
        f.Estado = EstadoFalta.Injustificada;
        f.Motivo = string.IsNullOrWhiteSpace(motivo) ? null : motivo.Trim();
        f.ResueltaUtc = Ahora;
        f.AdministradorId = adminId;
        db.Auditorias.Add(new Auditoria { FechaUtc = Ahora, AdministradorId = adminId, Campo = "falta_injustificada", ValorAnterior = $"{emp!.Nombre} {fecha:dd/MM/yyyy}: {antes}", ValorNuevo = $"{emp.Nombre} {fecha:dd/MM/yyyy}: injustificada", Motivo = f.Motivo ?? "Falta injustificada" });
        await db.SaveChangesAsync();
        return new(Dto(emp, f, adminId));
    }
}

/// <summary>Cada minuto cierra los días terminados y genera las faltas (una sola por empleado y día).</summary>
public class AsistenciaWorker(IServiceScopeFactory scopes, ILogger<AsistenciaWorker> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMinutes(1));
        do
        {
            try
            {
                using var scope = scopes.CreateScope();
                var n = await scope.ServiceProvider.GetRequiredService<AsistenciaService>().CerrarDiasAsync();
                if (n > 0) log.LogInformation("{N} falta(s) generada(s) al cerrar el día.", n);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                log.LogError(ex, "Error al cerrar los días de asistencia.");
            }
        } while (await timer.WaitForNextTickAsync(ct));
    }
}
