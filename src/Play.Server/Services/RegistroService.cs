using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Play.Server.Data;

namespace Play.Server.Services;

public record RegistroDto(Guid Id, int EmpleadoId, int ObraId, DateTime InicioUtc, DateTime? FinUtc,
    DateTime UltimoLatidoUtc, string Estado, string Equipo, string Origen, bool RevisarAdmin, int? SubtareaId = null)
{
    public static RegistroDto De(RegistroTiempo r) => new(r.Id, r.EmpleadoId, r.ObraId, r.InicioUtc, r.FinUtc,
        r.UltimoLatidoUtc, r.Estado.ToString().ToLowerInvariant(), r.Equipo, r.Origen, r.RevisarAdmin, r.SubtareaId);
}

public record SincronizarItem(Guid Id, int ObraId, DateTime InicioUtc, DateTime? FinUtc, string? Equipo, int? SubtareaId = null);
public record SincronizarResultado(Guid Id, string Resultado);
public record ObraSegundos(int ObraId, string Obra, long Segundos);
public record PeriodoResumen(long TotalSegundos, List<ObraSegundos> PorObra);
public record ResumenDto(PeriodoResumen Hoy, PeriodoResumen Semana);

/// <summary>Reglas de negocio del registro de tiempo. El servidor es la fuente de verdad.</summary>
public class RegistroService(PlayDb db, TimeProvider time, IOptions<PlayOptions> options)
{
    private readonly PlayOptions _o = options.Value;
    private DateTime Ahora => time.GetUtcNow().UtcDateTime;

    private static string Equipo(string? e)
    {
        e = (e ?? "").Trim();
        return e.Length > 60 ? e[..60] : e;
    }

    public async Task<RegistroDto?> ActivoAsync(int empleadoId)
    {
        var r = await db.Registros.AsNoTracking().FirstOrDefaultAsync(x => x.EmpleadoId == empleadoId && x.Estado == EstadoRegistro.Abierto);
        return r is null ? null : RegistroDto.De(r);
    }

    /// <summary>
    /// Regla de subtareas: si la obra tiene alguna subtarea ACTIVA hay que elegir una de ellas; si no tiene, no se puede mandar ninguna.
    /// Devuelve el código de error o null si está bien.
    /// </summary>
    private async Task<string?> ErrorDeSubtareaAsync(int obraId, int? subtareaId)
    {
        var activas = await db.Subtareas.AsNoTracking().Where(s => s.ObraId == obraId && s.Activa && !s.Terminada).Select(s => s.Id).ToListAsync();
        if (activas.Count == 0) return subtareaId is null ? null : "subtarea_invalida";
        if (subtareaId is null) return "subtarea_requerida";
        return activas.Contains(subtareaId.Value) ? null : "subtarea_invalida";
    }

    /// <summary>
    /// Un empleado avisa que terminó una subtarea. No la cierra: queda un aviso para que el administrador lo revise.
    /// Idempotente: si el mismo empleado ya tiene un aviso sin revisar de esa subtarea, no se duplica.
    /// </summary>
    public async Task<IResult> AvisarSubtareaAsync(int empleadoId, int subtareaId)
    {
        var s = await db.Subtareas.AsNoTracking().FirstOrDefaultAsync(x => x.Id == subtareaId);
        if (s is null || !s.Activa) return Results.NotFound(new { codigo = "no_encontrado" });
        if (s.Terminada) return Results.Conflict(new { codigo = "subtarea_terminada" });
        var existente = await db.AvisosSubtarea.AsNoTracking().FirstOrDefaultAsync(a => a.SubtareaId == subtareaId && a.EmpleadoId == empleadoId && a.Estado == EstadoAviso.Nuevo);
        if (existente is not null) return Results.Ok(new { id = existente.Id, yaAvisado = true });
        var nuevo = new AvisoSubtarea { SubtareaId = subtareaId, EmpleadoId = empleadoId, CreadoUtc = Ahora, Estado = EstadoAviso.Nuevo };
        db.AvisosSubtarea.Add(nuevo);
        await db.SaveChangesAsync();
        return Results.Created($"/api/subtareas/{subtareaId}/avisar", new { id = nuevo.Id, yaAvisado = false });
    }
    /// <summary>Subtareas que este empleado marcó como terminadas y que el administrador todavía no revisó (para su casilla en el panel).</summary>
    public async Task<List<int>> MisAvisosAsync(int empleadoId) =>
        await db.AvisosSubtarea.AsNoTracking().Where(a => a.EmpleadoId == empleadoId && a.Estado == EstadoAviso.Nuevo).Select(a => a.SubtareaId).Distinct().ToListAsync();

    /// <summary>El empleado destilda la casilla: su aviso sin revisar queda «retirado». Idempotente.</summary>
    public async Task<IResult> RetirarAvisoAsync(int empleadoId, int subtareaId)
    {
        var avisos = await db.AvisosSubtarea.Where(a => a.SubtareaId == subtareaId && a.EmpleadoId == empleadoId && a.Estado == EstadoAviso.Nuevo).ToListAsync();
        foreach (var a in avisos) { a.Estado = EstadoAviso.Retirado; a.ResueltoUtc = Ahora; }
        if (avisos.Count > 0) await db.SaveChangesAsync();
        return Results.NoContent();
    }

    /// <summary>Play. Idempotente por Id; bloquea si el empleado ya tiene un registro abierto.</summary>
    public async Task<IResult> IniciarAsync(int empleadoId, Guid id, int obraId, string? equipo, int? subtareaId = null)
    {
        var existente = await db.Registros.AsNoTracking().FirstOrDefaultAsync(r => r.Id == id);
        if (existente is not null)
            return existente.EmpleadoId == empleadoId ? Results.Ok(RegistroDto.De(existente)) : Results.Conflict(new { codigo = "id_en_uso" });

        var obra = await db.Obras.FindAsync(obraId);
        if (obra is null || !obra.Activa) return Results.BadRequest(new { codigo = "obra_invalida" });
        if (await ErrorDeSubtareaAsync(obraId, subtareaId) is { } errorSubtarea) return Results.BadRequest(new { codigo = errorSubtarea });

        var abierto = await db.Registros.AsNoTracking().FirstOrDefaultAsync(r => r.EmpleadoId == empleadoId && r.Estado == EstadoRegistro.Abierto);
        if (abierto is not null) return ConflictoActivo(abierto);

        var now = Ahora;
        var nuevo = new RegistroTiempo
        {
            Id = id, EmpleadoId = empleadoId, ObraId = obraId, SubtareaId = subtareaId, InicioUtc = now, UltimoLatidoUtc = now,
            Estado = EstadoRegistro.Abierto, Equipo = Equipo(equipo), Origen = "panel",
        };
        db.Registros.Add(nuevo);
        try
        {
            await db.SaveChangesAsync();
        }
        catch (DbUpdateException)
        {
            // Carrera: otro Play del mismo empleado ganó, o el mismo Id llegó dos veces a la vez.
            db.ChangeTracker.Clear();
            var ya = await db.Registros.AsNoTracking().FirstOrDefaultAsync(r => r.Id == id && r.EmpleadoId == empleadoId);
            if (ya is not null) return Results.Ok(RegistroDto.De(ya));
            var otro = await db.Registros.AsNoTracking().FirstOrDefaultAsync(r => r.EmpleadoId == empleadoId && r.Estado == EstadoRegistro.Abierto);
            return otro is not null ? ConflictoActivo(otro) : Results.Problem("No se pudo iniciar el registro.");
        }
        return Results.Created($"/api/registros/{id}", RegistroDto.De(nuevo));
    }

    private static IResult ConflictoActivo(RegistroTiempo abierto) =>
        Results.Conflict(new { codigo = "registro_activo", registroId = abierto.Id, equipo = abierto.Equipo, obraId = abierto.ObraId, inicioUtc = abierto.InicioUtc });

    /// <summary>Latido: el panel avisa que sigue vivo. 409 si el servidor ya cerró ese registro.</summary>
    public async Task<IResult> LatidoAsync(int empleadoId, Guid id)
    {
        var r = await db.Registros.FirstOrDefaultAsync(x => x.Id == id && x.EmpleadoId == empleadoId);
        if (r is null) return Results.NotFound();
        if (r.Estado != EstadoRegistro.Abierto)
            return Results.Conflict(new { codigo = "no_abierto", estado = r.Estado.ToString().ToLowerInvariant(), finUtc = r.FinUtc });

        var now = Ahora;
        r.UltimoLatidoUtc = now;
        if (now - r.InicioUtc > TimeSpan.FromHours(_o.MaxRecordHours)) r.RevisarAdmin = true;
        await db.SaveChangesAsync();
        return Results.Ok(RegistroDto.De(r));
    }

    /// <summary>Pause. Idempotente. finUtc opcional (p. ej. inicio de la inactividad), entre el inicio y ahora.</summary>
    public async Task<IResult> CerrarAsync(int empleadoId, Guid id, DateTime? finUtc)
    {
        var r = await db.Registros.FirstOrDefaultAsync(x => x.Id == id && x.EmpleadoId == empleadoId);
        if (r is null) return Results.NotFound();
        if (r.Estado == EstadoRegistro.Abierto)
        {
            CerrarRegistro(r, finUtc);
            await db.SaveChangesAsync();
        }
        return Results.Ok(RegistroDto.De(r));
    }

    private void CerrarRegistro(RegistroTiempo r, DateTime? finUtc)
    {
        var now = Ahora;
        var fin = finUtc?.ToUniversalTime() ?? now;
        if (fin > now) fin = now;
        if (fin < r.InicioUtc) fin = r.InicioUtc;
        r.FinUtc = fin;
        r.Estado = EstadoRegistro.Cerrado;
        if (fin - r.InicioUtc > TimeSpan.FromHours(_o.MaxRecordHours)) r.RevisarAdmin = true;
    }

    /// <summary>Cambio de obra o de subtarea: cierra el registro abierto y abre uno nuevo, de forma atómica.</summary>
    public async Task<IResult> CambiarObraAsync(int empleadoId, Guid nuevoId, int obraId, string? equipo, int? subtareaId = null)
    {
        var ya = await db.Registros.AsNoTracking().FirstOrDefaultAsync(r => r.Id == nuevoId);
        if (ya is not null)
            return ya.EmpleadoId == empleadoId ? Results.Ok(RegistroDto.De(ya)) : Results.Conflict(new { codigo = "id_en_uso" });

        var obra = await db.Obras.FindAsync(obraId);
        if (obra is null || !obra.Activa) return Results.BadRequest(new { codigo = "obra_invalida" });
        if (await ErrorDeSubtareaAsync(obraId, subtareaId) is { } errorSubtarea) return Results.BadRequest(new { codigo = errorSubtarea });

        await using var tx = await db.Database.BeginTransactionAsync();
        var actual = await db.Registros.FirstOrDefaultAsync(r => r.EmpleadoId == empleadoId && r.Estado == EstadoRegistro.Abierto);
        if (actual is null) return Results.Conflict(new { codigo = "sin_registro_activo" });

        CerrarRegistro(actual, null);
        await db.SaveChangesAsync(); // primero cierra, para no violar el índice de «un solo abierto»

        var now = Ahora;
        var nuevo = new RegistroTiempo
        {
            Id = nuevoId, EmpleadoId = empleadoId, ObraId = obraId, SubtareaId = subtareaId, InicioUtc = actual.FinUtc ?? now, UltimoLatidoUtc = now,
            Estado = EstadoRegistro.Abierto, Equipo = Equipo(equipo), Origen = "panel",
        };
        db.Registros.Add(nuevo);
        await db.SaveChangesAsync();
        await tx.CommitAsync();
        return Results.Ok(RegistroDto.De(nuevo));
    }

    /// <summary>
    /// Reenvía registros hechos sin conexión. Idempotente por Id. Nunca descarta horas:
    /// ante solapamientos inserta igual y marca el registro para revisión del administrador.
    /// </summary>
    public async Task<List<SincronizarResultado>> SincronizarAsync(int empleadoId, IEnumerable<SincronizarItem> items)
    {
        var res = new List<SincronizarResultado>();
        foreach (var it in items)
            res.Add(new SincronizarResultado(it.Id, await SincronizarUnoAsync(empleadoId, it)));
        return res;
    }

    private async Task<string> SincronizarUnoAsync(int empleadoId, SincronizarItem it)
    {
        var now = Ahora;
        var inicio = it.InicioUtc.ToUniversalTime();
        var fin = it.FinUtc?.ToUniversalTime();
        var tolerancia = now.AddMinutes(1);

        if (inicio > tolerancia || inicio < now.AddDays(-_o.MaxOfflineDays) || (fin is not null && (fin < inicio || fin > tolerancia)))
            return "invalido";
        if (fin > now) fin = now;
        if (inicio > now) inicio = now;

        var existente = await db.Registros.FirstOrDefaultAsync(r => r.Id == it.Id);
        if (existente is not null)
        {
            if (existente.EmpleadoId != empleadoId) return "invalido";
            if (existente.Estado == EstadoRegistro.Corregido || existente.Anulado) return "duplicado"; // el admin ya lo ajustó o eliminó: no se pisa ni se resucita
            if (existente.Estado == EstadoRegistro.Abierto && fin is not null)
            {
                CerrarRegistro(existente, fin);
                await db.SaveChangesAsync();
                return "actualizado";
            }
            if (existente.Estado == EstadoRegistro.Cortado && fin is not null && fin > existente.FinUtc)
            {
                // El servidor lo cortó por falta de latidos, pero el panel trabajó localmente hasta más tarde.
                existente.FinUtc = fin;
                existente.Estado = EstadoRegistro.Cerrado;
                existente.RevisarAdmin = true;
                await db.SaveChangesAsync();
                return "actualizado";
            }
            return "duplicado";
        }

        var obra = await db.Obras.FindAsync(it.ObraId);
        if (obra is null) return "invalido";

        var hasta = fin ?? now;
        var solapa = await db.Registros.AnyAsync(r => r.EmpleadoId == empleadoId && !r.Anulado && r.InicioUtc < hasta && (r.FinUtc ?? now) > inicio);

        if (fin is null && await db.Registros.AnyAsync(r => r.EmpleadoId == empleadoId && r.Estado == EstadoRegistro.Abierto))
            return "conflicto_abierto";

        // Subtarea: lo hecho sin conexión nunca se rechaza. Si la subtarea no corresponde a la obra (o falta aunque la obra
        // ya exige una porque el administrador la agregó mientras tanto), se guarda sin subtarea y queda para revisar.
        int? subtarea = it.SubtareaId is { } sid && await db.Subtareas.AnyAsync(s => s.Id == sid && s.ObraId == it.ObraId) ? it.SubtareaId : null;
        var faltaSubtarea = subtarea is null && await db.Subtareas.AnyAsync(s => s.ObraId == it.ObraId && s.Activa && !s.Terminada);

        db.Registros.Add(new RegistroTiempo
        {
            Id = it.Id, EmpleadoId = empleadoId, ObraId = it.ObraId, SubtareaId = subtarea, InicioUtc = inicio, FinUtc = fin,
            UltimoLatidoUtc = fin ?? now, Estado = fin is null ? EstadoRegistro.Abierto : EstadoRegistro.Cerrado,
            Equipo = Equipo(it.Equipo), Origen = "offline", RevisarAdmin = solapa || faltaSubtarea,
        });
        try
        {
            await db.SaveChangesAsync();
        }
        catch (DbUpdateException)
        {
            db.ChangeTracker.Clear();
            return await db.Registros.AnyAsync(r => r.Id == it.Id) ? "duplicado" : "conflicto_abierto";
        }
        return solapa || faltaSubtarea ? "insertado_revisar" : "insertado";
    }

    /// <summary>Cierra como «cortado» los registros abiertos sin latidos recientes, hasta el último latido.</summary>
    public async Task<int> CerrarAbandonadosAsync()
    {
        var limite = Ahora.AddSeconds(-_o.CutoffSeconds);
        var abandonados = await db.Registros.Where(r => r.Estado == EstadoRegistro.Abierto && r.UltimoLatidoUtc < limite).ToListAsync();
        foreach (var r in abandonados)
        {
            r.Estado = EstadoRegistro.Cortado;
            r.FinUtc = r.UltimoLatidoUtc;
            if (r.FinUtc - r.InicioUtc > TimeSpan.FromHours(_o.MaxRecordHours)) r.RevisarAdmin = true;
        }
        if (abandonados.Count > 0) await db.SaveChangesAsync();
        return abandonados.Count;
    }

    /// <summary>Horas de hoy y de la semana (lunes a domingo, hora local de la zona configurada).</summary>
    public async Task<ResumenDto> ResumenAsync(int empleadoId)
    {
        var now = Ahora;
        var zona = Services.Zona.De(_o);
        var local = TimeZoneInfo.ConvertTimeFromUtc(now, zona);
        var inicioHoyLocal = local.Date;
        var diasDesdeLunes = ((int)local.DayOfWeek + 6) % 7;
        var inicioSemanaLocal = inicioHoyLocal.AddDays(-diasDesdeLunes);

        DateTime ALocalUtc(DateTime d) => TimeZoneInfo.ConvertTimeToUtc(DateTime.SpecifyKind(d, DateTimeKind.Unspecified), zona);
        var hoyDesde = ALocalUtc(inicioHoyLocal);
        var hoyHasta = ALocalUtc(inicioHoyLocal.AddDays(1));
        var semDesde = ALocalUtc(inicioSemanaLocal);
        var semHasta = ALocalUtc(inicioSemanaLocal.AddDays(7));

        var regs = await db.Registros.AsNoTracking().Include(r => r.Obra).Include(r => r.Subtarea)
            .Where(r => r.EmpleadoId == empleadoId && !r.Anulado && r.InicioUtc < semHasta && (r.FinUtc == null || r.FinUtc > semDesde))
            .ToListAsync();

        PeriodoResumen Calc(DateTime desde, DateTime hasta)
        {
            var porObra = regs
                .Select(r =>
                {
                    var a = r.InicioUtc > desde ? r.InicioUtc : desde;
                    var fin = r.FinUtc ?? now;
                    var b = fin < hasta ? fin : hasta;
                    // Con subtarea se muestra «Obra › Subtarea» (cada subtarea suma por separado).
                    var nombre = (r.Obra?.Nombre ?? "") + (r.Subtarea is { } st ? " › " + st.Nombre : "");
                    return (r.ObraId, Obra: nombre, Seg: b > a ? (long)(b - a).TotalSeconds : 0L);
                })
                .Where(x => x.Seg > 0)
                .GroupBy(x => (x.ObraId, x.Obra))
                .Select(g => new ObraSegundos(g.Key.ObraId, g.Key.Obra, g.Sum(x => x.Seg)))
                .OrderBy(x => x.Obra).ToList();
            return new PeriodoResumen(porObra.Sum(x => x.Segundos), porObra);
        }

        return new ResumenDto(Calc(hoyDesde, hoyHasta), Calc(semDesde, semHasta));
    }
}
