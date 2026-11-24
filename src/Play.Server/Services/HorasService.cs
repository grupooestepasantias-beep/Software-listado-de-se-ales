using Microsoft.EntityFrameworkCore;
using Play.Server.Data;

namespace Play.Server.Services;

/// <summary>Una línea de horas vista por el propio empleado (un día, una obra y una subtarea).</summary>
/// <param name="Origen">panel = la cargó el empleado; admin = la cargó o corrigió un administrador (el empleado ya no puede cambiarla).</param>
/// <param name="ObraId">Null = trabajo general de Taller, sin obra.</param>
public record CargaDto(DateOnly Fecha, int Minutos, string Origen, int? ObraId = null, int? SubtareaId = null, string? Obra = null, string? Subtarea = null);
/// <param name="Hoy">Fecha de hoy según el servidor (el empleado solo puede cargar hoy y ayer).</param>
public record MisHorasDto(DateOnly Hoy, List<CargaDto> Cargas);
public record CargaAdminDto(int Id, int EmpleadoId, string Empleado, DateOnly Fecha, int Minutos, DateTime CreadaUtc, DateTime ActualizadaUtc, string Origen, bool Anulado,
    int? ObraId = null, string? Obra = null, int? SubtareaId = null, string? Subtarea = null);
public record CargarHorasRequest(DateOnly Fecha, int Minutos, int? ObraId = null, int? SubtareaId = null);
public record AltaHorasRequest(int EmpleadoId, DateOnly Fecha, int Minutos, string? Motivo, int? ObraId = null, int? SubtareaId = null);
public record CorregirHorasRequest(int Minutos, string? Motivo);
public record FiltroHoras(int? EmpleadoId, DateOnly? Desde, DateOnly? Hasta, bool Eliminados = false, int Limite = 2000, int? ObraId = null);

/// <summary>
/// Horas que cargan a mano los empleados de Taller (en lugar del cronómetro). Cada línea es un registro individual:
/// empleado + día + obra + subtarea + horas (la obra puede faltar: trabajo general de Taller). Un día puede tener varias líneas.
/// Las reglas de obra y subtarea son las mismas que para Play: si la obra tiene subtareas pendientes hay que elegir una.
/// Un empleado solo puede cargar hoy o ayer; después, solo un administrador (con motivo y constancia en la auditoría).
/// Las eliminadas no se borran: se marcan y se pueden recuperar.
/// </summary>
public class HorasService(PlayDb db, TimeProvider time, Microsoft.Extensions.Options.IOptions<PlayOptions> options)
{
    public const int MaxMinutos = 24 * 60;

    private DateTime Ahora => time.GetUtcNow().UtcDateTime;
    /// <summary>La fecha de hoy en la zona horaria configurada del servidor (la misma que usan los reportes).</summary>
    public DateOnly Hoy => DateOnly.FromDateTime(TimeZoneInfo.ConvertTimeFromUtc(Ahora, Zona.De(options.Value)));

    private static string Hm(int minutos) => $"{minutos / 60}:{minutos % 60:00}";

    private static CargaAdminDto Dto(CargaHoras c, string empleado) =>
        new(c.Id, c.EmpleadoId, empleado, c.Fecha, c.Minutos, c.CreadaUtc, c.ActualizadaUtc, c.Origen, c.Anulado, c.ObraId, c.Obra?.Nombre, c.SubtareaId, c.Subtarea?.Nombre);

    /// <summary>«Obra › Subtarea» (o «sin obra») para las constancias de la auditoría.</summary>
    private static string Etiqueta(CargaHoras c) =>
        c.Obra is null ? "sin obra" : c.Subtarea is null ? c.Obra.Nombre : $"{c.Obra.Nombre} › {c.Subtarea.Nombre}";

    private void Auditar(int adminId, string campo, string? anterior, string? nuevo, string motivo) =>
        db.Auditorias.Add(new Auditoria { FechaUtc = Ahora, AdministradorId = adminId, Campo = campo, ValorAnterior = anterior, ValorNuevo = nuevo, Motivo = motivo.Trim() });

    /// <summary>
    /// Valida la obra y la subtarea de una línea. Empleado (estricto): la obra tiene que estar activa y, si tiene subtareas pendientes,
    /// hay que elegir una de ellas. Administrador: puede usar también una subtarea ya terminada o inactiva de esa obra.
    /// </summary>
    private async Task<string?> ErrorDeObraAsync(int? obraId, int? subtareaId, bool estricto)
    {
        if (obraId is null) return subtareaId is null ? null : "subtarea_invalida";
        var obra = await db.Obras.AsNoTracking().FirstOrDefaultAsync(o => o.Id == obraId);
        if (obra is null || (estricto && !obra.Activa)) return "obra_invalida";
        var pendientes = await db.Subtareas.AsNoTracking().Where(s => s.ObraId == obraId && s.Activa && !s.Terminada).Select(s => s.Id).ToListAsync();
        if (subtareaId is null) return pendientes.Count > 0 ? "subtarea_requerida" : null;
        if (estricto) return pendientes.Contains(subtareaId.Value) ? null : "subtarea_invalida";
        return await db.Subtareas.AnyAsync(s => s.Id == subtareaId && s.ObraId == obraId) ? null : "subtarea_invalida";
    }

    // ---------------------------------------------------------------- empleado (solo Taller)

    private async Task<(Empleado? Emp, Res<T>? Error)> TallerAsync<T>(int empleadoId)
    {
        var e = await db.Empleados.AsNoTracking().FirstOrDefaultAsync(x => x.Id == empleadoId);
        if (e is null) return (null, Res<T>.Fallo("no_encontrado", 404));
        if (e.Area != Areas.Taller) return (null, Res<T>.Fallo("solo_taller", 403));
        return (e, null);
    }

    /// <summary>Las líneas de los últimos 14 días (y la fecha de hoy del servidor).</summary>
    public async Task<Res<MisHorasDto>> MisHorasAsync(int empleadoId)
    {
        var (_, error) = await TallerAsync<MisHorasDto>(empleadoId);
        if (error is not null) return error;
        var desde = Hoy.AddDays(-14);
        var cargas = await db.CargasHoras.AsNoTracking()
            .Where(c => c.EmpleadoId == empleadoId && !c.Anulado && c.Fecha >= desde)
            .OrderByDescending(c => c.Fecha).ThenBy(c => c.Obra!.Nombre).ThenBy(c => c.Subtarea!.Nombre)
            .Select(c => new CargaDto(c.Fecha, c.Minutos, c.Origen, c.ObraId, c.SubtareaId, c.Obra == null ? null : c.Obra.Nombre, c.Subtarea == null ? null : c.Subtarea.Nombre))
            .ToListAsync();
        return new(new MisHorasDto(Hoy, cargas));
    }

    private bool FechaPermitida(DateOnly fecha) => fecha == Hoy || fecha == Hoy.AddDays(-1);

    /// <summary>
    /// Carga (o corrige) las horas de una obra y subtarea de hoy o de ayer. Volver a cargar la misma línea (mismo día, obra y
    /// subtarea) la reemplaza; el total del día no puede pasar de 24 horas.
    /// </summary>
    public async Task<Res<CargaDto>> CargarAsync(int empleadoId, DateOnly fecha, int minutos, int? obraId = null, int? subtareaId = null)
    {
        var (_, error) = await TallerAsync<CargaDto>(empleadoId);
        if (error is not null) return error;
        if (!FechaPermitida(fecha)) return Res<CargaDto>.Fallo("fecha_no_permitida");
        if (minutos < 1 || minutos > MaxMinutos) return Res<CargaDto>.Fallo("horas_invalidas");
        if (await ErrorDeObraAsync(obraId, subtareaId, estricto: true) is { } errorObra) return Res<CargaDto>.Fallo(errorObra);

        var delDia = await db.CargasHoras.Where(x => x.EmpleadoId == empleadoId && x.Fecha == fecha && !x.Anulado).ToListAsync();
        var c = delDia.FirstOrDefault(x => x.ObraId == obraId && x.SubtareaId == subtareaId);
        if (c is not null && c.Origen == "admin") return Res<CargaDto>.Fallo("cargada_por_admin", 409); // ya la tocó un administrador
        if (delDia.Where(x => x != c).Sum(x => x.Minutos) + minutos > MaxMinutos) return Res<CargaDto>.Fallo("horas_invalidas");

        if (c is null)
        {
            c = new CargaHoras { EmpleadoId = empleadoId, Fecha = fecha, Minutos = minutos, ObraId = obraId, SubtareaId = subtareaId, CreadaUtc = Ahora, ActualizadaUtc = Ahora, Origen = "panel" };
            db.CargasHoras.Add(c);
        }
        else
        {
            c.Minutos = minutos;
            c.ActualizadaUtc = Ahora;
        }
        await db.SaveChangesAsync();
        return new(new CargaDto(c.Fecha, c.Minutos, c.Origen, c.ObraId, c.SubtareaId));
    }

    /// <summary>El empleado quita una de sus líneas de hoy o de ayer (queda marcada como eliminada, no se borra).</summary>
    public async Task<Res<bool>> RetirarAsync(int empleadoId, DateOnly fecha, int? obraId, int? subtareaId)
    {
        var (_, error) = await TallerAsync<bool>(empleadoId);
        if (error is not null) return error;
        if (!FechaPermitida(fecha)) return Res<bool>.Fallo("fecha_no_permitida");
        var c = await db.CargasHoras.FirstOrDefaultAsync(x => x.EmpleadoId == empleadoId && x.Fecha == fecha && !x.Anulado && x.ObraId == obraId && x.SubtareaId == subtareaId);
        if (c is null) return Res<bool>.Fallo("no_encontrado", 404);
        if (c.Origen == "admin") return Res<bool>.Fallo("cargada_por_admin", 409);
        c.Anulado = true;
        c.ActualizadaUtc = Ahora;
        await db.SaveChangesAsync();
        return new(true);
    }

    // ---------------------------------------------------------------- administración

    public async Task<List<CargaAdminDto>> ListarAsync(FiltroHoras f)
    {
        var q = db.CargasHoras.AsNoTracking().Where(c => c.Anulado == f.Eliminados);
        if (f.EmpleadoId is { } e) q = q.Where(c => c.EmpleadoId == e);
        if (f.ObraId is { } o) q = q.Where(c => c.ObraId == o);
        if (f.Desde is { } d) q = q.Where(c => c.Fecha >= d);
        if (f.Hasta is { } h) q = q.Where(c => c.Fecha <= h);
        return await q.OrderByDescending(c => c.Fecha).ThenBy(c => c.Empleado!.Nombre).ThenBy(c => c.Obra!.Nombre).ThenBy(c => c.Subtarea!.Nombre).Take(Math.Clamp(f.Limite, 1, 10000))
            .Select(c => new CargaAdminDto(c.Id, c.EmpleadoId, c.Empleado!.Nombre, c.Fecha, c.Minutos, c.CreadaUtc, c.ActualizadaUtc, c.Origen, c.Anulado,
                c.ObraId, c.Obra == null ? null : c.Obra.Nombre, c.SubtareaId, c.Subtarea == null ? null : c.Subtarea.Nombre)).ToListAsync();
    }

    public async Task<Res<CargaAdminDto>> CrearAsync(int adminId, AltaHorasRequest req)
    {
        if (string.IsNullOrWhiteSpace(req.Motivo)) return Res<CargaAdminDto>.Fallo("motivo_requerido");
        if (req.Minutos < 1 || req.Minutos > MaxMinutos) return Res<CargaAdminDto>.Fallo("horas_invalidas");
        if (req.Fecha > Hoy) return Res<CargaAdminDto>.Fallo("fecha_futura");
        var emp = await db.Empleados.FindAsync(req.EmpleadoId);
        if (emp is null) return Res<CargaAdminDto>.Fallo("datos_invalidos");
        if (emp.Area != Areas.Taller) return Res<CargaAdminDto>.Fallo("solo_taller");
        if (await ErrorDeObraAsync(req.ObraId, req.SubtareaId, estricto: false) is { } errorObra) return Res<CargaAdminDto>.Fallo(errorObra);
        if (await db.CargasHoras.AnyAsync(c => c.EmpleadoId == emp.Id && c.Fecha == req.Fecha && !c.Anulado && c.ObraId == req.ObraId && c.SubtareaId == req.SubtareaId)) return Res<CargaAdminDto>.Fallo("ya_cargado", 409);
        var delDia = await db.CargasHoras.Where(c => c.EmpleadoId == emp.Id && c.Fecha == req.Fecha && !c.Anulado).SumAsync(c => c.Minutos);
        if (delDia + req.Minutos > MaxMinutos) return Res<CargaAdminDto>.Fallo("horas_invalidas");

        var c = new CargaHoras { EmpleadoId = emp.Id, Fecha = req.Fecha, Minutos = req.Minutos, ObraId = req.ObraId, SubtareaId = req.SubtareaId, CreadaUtc = Ahora, ActualizadaUtc = Ahora, Origen = "admin" };
        db.CargasHoras.Add(c);
        await db.Entry(c).Reference(x => x.Obra).LoadAsync();
        await db.Entry(c).Reference(x => x.Subtarea).LoadAsync();
        Auditar(adminId, "horas_taller_creadas", null, $"{emp.Nombre} {req.Fecha:dd/MM/yyyy} ({Etiqueta(c)}): {Hm(req.Minutos)} h", req.Motivo);
        await db.SaveChangesAsync();
        return new(Dto(c, emp.Nombre));
    }

    public async Task<Res<CargaAdminDto>> CorregirAsync(int adminId, int id, int minutos, string? motivo)
    {
        if (string.IsNullOrWhiteSpace(motivo)) return Res<CargaAdminDto>.Fallo("motivo_requerido");
        if (minutos < 1 || minutos > MaxMinutos) return Res<CargaAdminDto>.Fallo("horas_invalidas");
        var c = await db.CargasHoras.Include(x => x.Empleado).Include(x => x.Obra).Include(x => x.Subtarea).FirstOrDefaultAsync(x => x.Id == id);
        if (c is null) return Res<CargaAdminDto>.Fallo("no_encontrado", 404);
        if (c.Anulado) return Res<CargaAdminDto>.Fallo("registro_eliminado", 409);
        if (c.Minutos == minutos) return Res<CargaAdminDto>.Fallo("sin_cambios");
        var otras = await db.CargasHoras.Where(x => x.EmpleadoId == c.EmpleadoId && x.Fecha == c.Fecha && !x.Anulado && x.Id != c.Id).SumAsync(x => x.Minutos);
        if (otras + minutos > MaxMinutos) return Res<CargaAdminDto>.Fallo("horas_invalidas");
        Auditar(adminId, "horas_taller", $"{c.Empleado!.Nombre} {c.Fecha:dd/MM/yyyy} ({Etiqueta(c)}): {Hm(c.Minutos)} h", $"{Hm(minutos)} h", motivo);
        c.Minutos = minutos;
        c.ActualizadaUtc = Ahora;
        c.Origen = "admin";
        await db.SaveChangesAsync();
        return new(Dto(c, c.Empleado.Nombre));
    }

    public async Task<Res<CargaAdminDto>> AnularAsync(int adminId, int id, string? motivo)
    {
        if (string.IsNullOrWhiteSpace(motivo)) return Res<CargaAdminDto>.Fallo("motivo_requerido");
        var c = await db.CargasHoras.Include(x => x.Empleado).Include(x => x.Obra).Include(x => x.Subtarea).FirstOrDefaultAsync(x => x.Id == id);
        if (c is null) return Res<CargaAdminDto>.Fallo("no_encontrado", 404);
        if (c.Anulado) return new(Dto(c, c.Empleado!.Nombre));
        c.Anulado = true;
        c.ActualizadaUtc = Ahora;
        Auditar(adminId, "horas_taller_eliminadas", $"{c.Empleado!.Nombre} {c.Fecha:dd/MM/yyyy} ({Etiqueta(c)}): {Hm(c.Minutos)} h", null, motivo);
        await db.SaveChangesAsync();
        return new(Dto(c, c.Empleado.Nombre));
    }

    public async Task<Res<CargaAdminDto>> RestaurarAsync(int adminId, int id, string? motivo)
    {
        if (string.IsNullOrWhiteSpace(motivo)) return Res<CargaAdminDto>.Fallo("motivo_requerido");
        var c = await db.CargasHoras.Include(x => x.Empleado).Include(x => x.Obra).Include(x => x.Subtarea).FirstOrDefaultAsync(x => x.Id == id);
        if (c is null) return Res<CargaAdminDto>.Fallo("no_encontrado", 404);
        if (!c.Anulado) return new(Dto(c, c.Empleado!.Nombre));
        // Si mientras tanto se cargó la misma línea (día, obra y subtarea), no puede haber dos; y el día no puede pasar de 24 horas.
        if (await db.CargasHoras.AnyAsync(x => x.EmpleadoId == c.EmpleadoId && x.Fecha == c.Fecha && !x.Anulado && x.ObraId == c.ObraId && x.SubtareaId == c.SubtareaId)) return Res<CargaAdminDto>.Fallo("ya_cargado", 409);
        var delDia = await db.CargasHoras.Where(x => x.EmpleadoId == c.EmpleadoId && x.Fecha == c.Fecha && !x.Anulado).SumAsync(x => x.Minutos);
        if (delDia + c.Minutos > MaxMinutos) return Res<CargaAdminDto>.Fallo("horas_invalidas");
        c.Anulado = false;
        c.ActualizadaUtc = Ahora;
        Auditar(adminId, "horas_taller_recuperadas", null, $"{c.Empleado!.Nombre} {c.Fecha:dd/MM/yyyy} ({Etiqueta(c)}): {Hm(c.Minutos)} h", motivo);
        await db.SaveChangesAsync();
        return new(Dto(c, c.Empleado.Nombre));
    }
}
