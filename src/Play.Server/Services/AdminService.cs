using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Play.Server.Data;

namespace Play.Server.Services;

/// <param name="PinConocido">false = el PIN lo eligió el empleado antes de que se guardara legible: hay que resetearlo para verlo.</param>
public record EmpleadoAdminDto(int Id, string Nombre, bool Activo, bool DebeCambiarPin, string Area = Areas.Oficina, bool PinConocido = false);
public record PinAdminDto(int Id, string Nombre, string Area, bool Activo, string? Pin, bool DebeCambiarPin);
/// <param name="SubtareasActivas">Si es mayor que 0, quien registre horas en esta obra debe elegir una subtarea.</param>
public record ObraAdminDto(int Id, string Nombre, bool Activa, int SubtareasActivas = 0);
/// <param name="Terminada">Terminada = ya no es una tarea pendiente (se ve tachada y deja de ofrecerse a los empleados).</param>
public record SubtareaAdminDto(int Id, int ObraId, string Nombre, bool Activa, bool Terminada = false);
/// <summary>Aviso de un empleado: «terminé esta subtarea».</summary>
public record AvisoAdminDto(int Id, int SubtareaId, string Subtarea, int ObraId, string Obra, int EmpleadoId, string Empleado, string Area,
    DateTime CreadoUtc, string Estado, DateTime? ResueltoUtc, bool SubtareaTerminada);
public record AdminDto(int Id, string Usuario, string NombreCompleto, bool Activo);
public record RegistroAdminDto(Guid Id, int EmpleadoId, string Empleado, int ObraId, string Obra, DateTime InicioUtc,
    DateTime? FinUtc, string Estado, string Origen, string Equipo, bool RevisarAdmin, long Segundos, bool Anulado = false, string Area = Areas.Oficina,
    string? Subtarea = null, int? SubtareaId = null);
public record AuditoriaDto(int Id, DateTime FechaUtc, string Administrador, Guid? RegistroId, string Campo,
    string? ValorAnterior, string? ValorNuevo, string Motivo);
public record EnVivoDto(int EmpleadoId, string Empleado, string Obra, string Equipo, DateTime InicioUtc, DateTime UltimoLatidoUtc, long Segundos, string Area = Areas.Oficina);

/// <param name="Eliminados">false = los registros normales; true = solo los eliminados (para recuperarlos).</param>
public record FiltroRegistros(int? EmpleadoId, int? ObraId, DateOnly? Desde, DateOnly? Hasta, bool? Revisar, int Limite = 500, bool Eliminados = false, string? Area = null);
/// <param name="SubtareaId">Nueva subtarea (debe ser de la obra resultante). Si se cambia la obra y no se indica, la subtarea se quita.</param>
/// <param name="QuitarSubtarea">true = dejar el registro sin subtarea.</param>
public record CorreccionRequest(DateTime? InicioUtc, DateTime? FinUtc, int? ObraId, string Motivo, int? SubtareaId = null, bool QuitarSubtarea = false);
public record AltaRegistroRequest(int EmpleadoId, int ObraId, DateTime InicioUtc, DateTime FinUtc, string Motivo, int? SubtareaId = null);

/// <summary>Resultado de una operación de administración: valor o error (codigo + http).</summary>
public record Res<T>(T? Valor, string? Error = null, int Http = 200)
{
    public bool Ok => Error is null;
    public static Res<T> Fallo(string error, int http = 400) => new(default, error, http);
}

public class AdminService(PlayDb db, TimeProvider time, IOptions<PlayOptions> options)
{
    private readonly PlayOptions _o = options.Value;
    private DateTime Ahora => time.GetUtcNow().UtcDateTime;

    // ---------- Empleados ----------
    private static EmpleadoAdminDto Dto(Empleado e) => new(e.Id, e.Nombre, e.Activo, e.DebeCambiarPin, e.Area, e.PinVisible is not null);

    public async Task<List<EmpleadoAdminDto>> EmpleadosAsync(string? area = null)
    {
        var q = db.Empleados.AsNoTracking().AsQueryable();
        if (Areas.Normalizar(area) is { } a) q = q.Where(e => e.Area == a);
        return await q.OrderBy(e => e.Nombre).Select(e => new EmpleadoAdminDto(e.Id, e.Nombre, e.Activo, e.DebeCambiarPin, e.Area, e.PinVisible != null)).ToListAsync();
    }

    /// <summary>Crea el empleado (Oficina por defecto) con un PIN inicial aleatorio, que el administrador puede ver cuando quiera.</summary>
    /// <summary>true = el Excel de empleados es la base de datos: nombre, PIN, área y estado de los empleados se cambian ahí, no en la app.</summary>
    private bool ExcelManda => !string.IsNullOrWhiteSpace(_o.EmpleadosExcel);

    public async Task<Res<(EmpleadoAdminDto Empleado, string Pin)>> CrearEmpleadoAsync(string nombre, string? area = null)
    {
        if (ExcelManda) return Res<(EmpleadoAdminDto, string)>.Fallo("gestionado_por_excel", 409);
        nombre = (nombre ?? "").Trim();
        if (nombre.Length == 0) return Res<(EmpleadoAdminDto, string)>.Fallo("nombre_requerido");
        var areaOk = string.IsNullOrWhiteSpace(area) ? Areas.Oficina : Areas.Normalizar(area);
        if (areaOk is null) return Res<(EmpleadoAdminDto, string)>.Fallo("area_invalida");
        if (await db.Empleados.AnyAsync(e => e.Nombre == nombre)) return Res<(EmpleadoAdminDto, string)>.Fallo("nombre_duplicado", 409);
        var pin = PinHasher.NuevoPin();
        var e = new Empleado { Nombre = nombre, Area = areaOk, PinHash = PinHasher.Hash(pin), PinVisible = pin, DebeCambiarPin = true,
            CreadoFecha = DateOnly.FromDateTime(TimeZoneInfo.ConvertTimeFromUtc(Ahora, Zona.De(_o))) };
        db.Empleados.Add(e);
        await db.SaveChangesAsync();
        return new((Dto(e), pin));
    }

    public async Task<Res<EmpleadoAdminDto>> ActualizarEmpleadoAsync(int adminId, int id, string? nombre, bool? activo, string? area = null)
    {
        if (ExcelManda) return Res<EmpleadoAdminDto>.Fallo("gestionado_por_excel", 409);
        var e = await db.Empleados.FindAsync(id);
        if (e is null) return Res<EmpleadoAdminDto>.Fallo("no_encontrado", 404);
        if (nombre is not null)
        {
            nombre = nombre.Trim();
            if (nombre.Length == 0) return Res<EmpleadoAdminDto>.Fallo("nombre_requerido");
            if (await db.Empleados.AnyAsync(x => x.Nombre == nombre && x.Id != id)) return Res<EmpleadoAdminDto>.Fallo("nombre_duplicado", 409);
            e.Nombre = nombre;
        }
        if (area is not null)
        {
            var areaOk = Areas.Normalizar(area);
            if (areaOk is null) return Res<EmpleadoAdminDto>.Fallo("area_invalida");
            if (areaOk != e.Area)
            {
                Auditar(adminId, null, "area", $"{e.Nombre}: {e.Area}", $"{e.Nombre}: {areaOk}", "Cambio de área");
                e.Area = areaOk;
            }
        }
        if (activo is not null) e.Activo = activo.Value;
        await db.SaveChangesAsync();
        return new(Dto(e));
    }

    /// <summary>PIN de todos los empleados (los que se conocen), para que el administrador los vea. Cada consulta deja constancia.</summary>
    public async Task<List<PinAdminDto>> PinesAsync(int adminId, string? area = null)
    {
        var lista = await ListarPinesAsync(area);
        Auditar(adminId, null, "pines_consultados", null, $"{lista.Count} empleado(s){(Areas.Normalizar(area) is { } a ? $", área {a}" : "")}", "Consulta de PIN");
        await db.SaveChangesAsync();
        return lista;
    }

    /// <summary>Lista sin dejar constancia (la usa la exportación a Excel, que registra su propia constancia).</summary>
    public async Task<List<PinAdminDto>> ListarPinesAsync(string? area = null)
    {
        var q = db.Empleados.AsNoTracking().AsQueryable();
        if (Areas.Normalizar(area) is { } a) q = q.Where(e => e.Area == a);
        return await q.OrderBy(e => e.Area).ThenBy(e => e.Nombre)
            .Select(e => new PinAdminDto(e.Id, e.Nombre, e.Area, e.Activo, e.PinVisible, e.DebeCambiarPin)).ToListAsync();
    }

    public async Task RegistrarExportacionDePinesAsync(int adminId, string? area, int cantidad)
    {
        Auditar(adminId, null, "pines_exportados", null, $"{cantidad} empleado(s){(Areas.Normalizar(area) is { } a ? $", área {a}" : "")}", "Exportación de PIN a Excel");
        await db.SaveChangesAsync();
    }

    public async Task<Res<string>> ResetearPinAsync(int adminId, int empleadoId)
    {
        if (ExcelManda) return Res<string>.Fallo("gestionado_por_excel", 409);
        var e = await db.Empleados.FindAsync(empleadoId);
        if (e is null) return Res<string>.Fallo("no_encontrado", 404);
        var pin = PinHasher.NuevoPin();
        e.PinHash = PinHasher.Hash(pin);
        e.PinVisible = pin;
        e.DebeCambiarPin = true;
        e.IntentosFallidos = 0;
        e.BloqueadoHastaUtc = null;
        Auditar(adminId, null, "pin_reseteado", null, e.Nombre, "Reseteo de PIN");
        await db.SaveChangesAsync();
        return new(pin);
    }

    // ---------- Obras ----------
    public async Task<List<ObraAdminDto>> ObrasAsync() =>
        await db.Obras.AsNoTracking().OrderBy(o => o.Nombre)
            .Select(o => new ObraAdminDto(o.Id, o.Nombre, o.Activa, o.Subtareas.Count(s => s.Activa && !s.Terminada))).ToListAsync();

    private async Task<ObraAdminDto> DtoObraAsync(Obra o) =>
        new(o.Id, o.Nombre, o.Activa, await db.Subtareas.CountAsync(s => s.ObraId == o.Id && s.Activa && !s.Terminada));

    public async Task<Res<ObraAdminDto>> CrearObraAsync(string nombre)
    {
        nombre = (nombre ?? "").Trim();
        if (nombre.Length == 0) return Res<ObraAdminDto>.Fallo("nombre_requerido");
        if (await db.Obras.AnyAsync(o => o.Nombre == nombre)) return Res<ObraAdminDto>.Fallo("nombre_duplicado", 409);
        var o = new Obra { Nombre = nombre };
        db.Obras.Add(o);
        await db.SaveChangesAsync();
        return new(await DtoObraAsync(o));
    }

    // ---------- Subtareas (propias de cada obra) ----------
    private static SubtareaAdminDto Dto(Subtarea s) => new(s.Id, s.ObraId, s.Nombre, s.Activa, s.Terminada);

    /// <summary>Todas las subtareas de una obra (activas, inactivas y terminadas); las terminadas van al final.</summary>
    public async Task<Res<List<SubtareaAdminDto>>> SubtareasAsync(int obraId)
    {
        if (!await db.Obras.AnyAsync(o => o.Id == obraId)) return Res<List<SubtareaAdminDto>>.Fallo("no_encontrado", 404);
        return new(await db.Subtareas.AsNoTracking().Where(s => s.ObraId == obraId).OrderBy(s => s.Terminada).ThenBy(s => s.Nombre).Select(s => Dto(s)).ToListAsync());
    }

    public async Task<Res<SubtareaAdminDto>> CrearSubtareaAsync(int obraId, string nombre)
    {
        nombre = (nombre ?? "").Trim();
        if (nombre.Length == 0) return Res<SubtareaAdminDto>.Fallo("nombre_requerido");
        if (nombre.Length > 80) return Res<SubtareaAdminDto>.Fallo("nombre_largo");
        if (!await db.Obras.AnyAsync(o => o.Id == obraId)) return Res<SubtareaAdminDto>.Fallo("no_encontrado", 404);
        if (await db.Subtareas.AnyAsync(s => s.ObraId == obraId && s.Nombre == nombre)) return Res<SubtareaAdminDto>.Fallo("nombre_duplicado", 409);
        var s = new Subtarea { ObraId = obraId, Nombre = nombre };
        db.Subtareas.Add(s);
        await db.SaveChangesAsync();
        return new(Dto(s));
    }

    public async Task<Res<SubtareaAdminDto>> ActualizarSubtareaAsync(int adminId, int id, string? nombre, bool? activa, bool? terminada = null)
    {
        var s = await db.Subtareas.FindAsync(id);
        if (s is null) return Res<SubtareaAdminDto>.Fallo("no_encontrado", 404);
        if (nombre is not null)
        {
            nombre = nombre.Trim();
            if (nombre.Length == 0) return Res<SubtareaAdminDto>.Fallo("nombre_requerido");
            if (nombre.Length > 80) return Res<SubtareaAdminDto>.Fallo("nombre_largo");
            if (await db.Subtareas.AnyAsync(x => x.ObraId == s.ObraId && x.Nombre == nombre && x.Id != id)) return Res<SubtareaAdminDto>.Fallo("nombre_duplicado", 409);
            s.Nombre = nombre;
        }
        if (activa is not null) s.Activa = activa.Value;
        if (terminada is not null) await CambiarTerminadaAsync(adminId, s, terminada.Value, false);
        await db.SaveChangesAsync();
        return new(Dto(s));
    }

    /// <summary>
    /// Marca o reabre una subtarea (deja constancia en la auditoría). Al terminarla, los avisos pendientes de esa subtarea
    /// pasan a «aceptados». Hay que guardar los cambios después.
    /// </summary>
    private async Task CambiarTerminadaAsync(int adminId, Subtarea s, bool terminada, bool dePorUnAviso)
    {
        if (s.Terminada == terminada) return;
        var obra = await db.Obras.AsNoTracking().Where(o => o.Id == s.ObraId).Select(o => o.Nombre).FirstOrDefaultAsync();
        var nombre = $"{obra} › {s.Nombre}";
        s.Terminada = terminada;
        s.TerminadaUtc = terminada ? Ahora : null;
        if (terminada)
        {
            var pendientes = await db.AvisosSubtarea.Where(a => a.SubtareaId == s.Id && a.Estado == EstadoAviso.Nuevo).ToListAsync();
            foreach (var a in pendientes) { a.Estado = EstadoAviso.Aceptado; a.ResueltoUtc = Ahora; a.AdministradorId = adminId; }
        }
        Auditar(adminId, null, terminada ? "subtarea_terminada" : "subtarea_reabierta", terminada ? null : nombre, terminada ? nombre : null,
            terminada ? (dePorUnAviso ? "Marcada como terminada a partir del aviso de un empleado" : "Marcada como terminada") : "Reabierta");
    }

    // ---------- Avisos de «terminé esta subtarea» ----------
    /// <param name="estado">«nuevos» (por defecto, sin revisar), «todos» o el nombre de un estado.</param>
    public async Task<List<AvisoAdminDto>> AvisosAsync(string? estado = null, int limite = 300)
    {
        var q = db.AvisosSubtarea.AsNoTracking().AsQueryable();
        if (string.IsNullOrWhiteSpace(estado) || estado.Equals("nuevos", StringComparison.OrdinalIgnoreCase)) q = q.Where(a => a.Estado == EstadoAviso.Nuevo);
        else if (!estado.Equals("todos", StringComparison.OrdinalIgnoreCase) && Enum.TryParse<EstadoAviso>(estado, true, out var e)) q = q.Where(a => a.Estado == e);
        return await q.OrderByDescending(a => a.CreadoUtc).ThenByDescending(a => a.Id).Take(Math.Clamp(limite, 1, 2000))
            .Select(a => new AvisoAdminDto(a.Id, a.SubtareaId, a.Subtarea!.Nombre, a.Subtarea.ObraId, a.Subtarea.Obra!.Nombre, a.EmpleadoId, a.Empleado!.Nombre,
                a.Empleado.Area, a.CreadoUtc, a.Estado.ToString().ToLowerInvariant(), a.ResueltoUtc, a.Subtarea.Terminada)).ToListAsync();
    }

    private async Task<AvisoAdminDto> AvisoDtoAsync(int id) => (await AvisosAsync("todos", 2000)).First(x => x.Id == id);

    /// <summary>El administrador acepta el aviso: la subtarea queda terminada (tachada).</summary>
    public async Task<Res<AvisoAdminDto>> AceptarAvisoAsync(int adminId, int id)
    {
        var a = await db.AvisosSubtarea.Include(x => x.Subtarea).FirstOrDefaultAsync(x => x.Id == id);
        if (a is null) return Res<AvisoAdminDto>.Fallo("no_encontrado", 404);
        if (a.Estado != EstadoAviso.Nuevo) return Res<AvisoAdminDto>.Fallo("aviso_resuelto", 409);
        await CambiarTerminadaAsync(adminId, a.Subtarea!, true, true);
        a.Estado = EstadoAviso.Aceptado; a.ResueltoUtc ??= Ahora; a.AdministradorId ??= adminId;
        await db.SaveChangesAsync();
        return new(await AvisoDtoAsync(id));
    }

    /// <summary>El administrador descarta el aviso (la subtarea sigue pendiente).</summary>
    public async Task<Res<AvisoAdminDto>> DescartarAvisoAsync(int adminId, int id)
    {
        var a = await db.AvisosSubtarea.Include(x => x.Subtarea).ThenInclude(s => s!.Obra).Include(x => x.Empleado).FirstOrDefaultAsync(x => x.Id == id);
        if (a is null) return Res<AvisoAdminDto>.Fallo("no_encontrado", 404);
        if (a.Estado != EstadoAviso.Nuevo) return Res<AvisoAdminDto>.Fallo("aviso_resuelto", 409);
        a.Estado = EstadoAviso.Descartado; a.ResueltoUtc = Ahora; a.AdministradorId = adminId;
        Auditar(adminId, null, "aviso_descartado", $"{a.Empleado?.Nombre}: {a.Subtarea?.Obra?.Nombre} › {a.Subtarea?.Nombre}", null, "Aviso de subtarea terminada descartado");
        await db.SaveChangesAsync();
        return new(await AvisoDtoAsync(id));
    }
    public async Task<Res<ObraAdminDto>> ActualizarObraAsync(int id, string? nombre, bool? activa)
    {
        var o = await db.Obras.FindAsync(id);
        if (o is null) return Res<ObraAdminDto>.Fallo("no_encontrado", 404);
        if (nombre is not null)
        {
            nombre = nombre.Trim();
            if (nombre.Length == 0) return Res<ObraAdminDto>.Fallo("nombre_requerido");
            if (await db.Obras.AnyAsync(x => x.Nombre == nombre && x.Id != id)) return Res<ObraAdminDto>.Fallo("nombre_duplicado", 409);
            o.Nombre = nombre;
        }
        if (activa is not null) o.Activa = activa.Value;
        await db.SaveChangesAsync();
        return new(await DtoObraAsync(o));
    }

    // ---------- Administradores ----------
    public async Task<List<AdminDto>> AdministradoresAsync() =>
        await db.Administradores.AsNoTracking().OrderBy(a => a.Usuario).Select(a => new AdminDto(a.Id, a.Usuario, a.NombreCompleto, a.Activo)).ToListAsync();

    public async Task<Res<(AdminDto Admin, string Clave)>> CrearAdministradorAsync(string usuario, string? nombreCompleto)
    {
        usuario = (usuario ?? "").Trim();
        if (usuario.Length == 0) return Res<(AdminDto, string)>.Fallo("usuario_requerido");
        if (await db.Administradores.AnyAsync(a => a.Usuario == usuario)) return Res<(AdminDto, string)>.Fallo("usuario_duplicado", 409);
        var clave = PinHasher.NuevaClaveTemporal();
        var a = new Administrador { Usuario = usuario, NombreCompleto = (nombreCompleto ?? usuario).Trim(), PassHash = PinHasher.Hash(clave), DebeCambiarPass = true };
        db.Administradores.Add(a);
        await db.SaveChangesAsync();
        return new((new AdminDto(a.Id, a.Usuario, a.NombreCompleto, a.Activo), clave));
    }

    public async Task<Res<AdminDto>> ActualizarAdministradorAsync(int actorId, int id, bool activo)
    {
        if (id == actorId && !activo) return Res<AdminDto>.Fallo("no_podes_desactivarte", 400);
        var a = await db.Administradores.FindAsync(id);
        if (a is null) return Res<AdminDto>.Fallo("no_encontrado", 404);
        a.Activo = activo;
        await db.SaveChangesAsync();
        return new(new AdminDto(a.Id, a.Usuario, a.NombreCompleto, a.Activo));
    }

    public async Task<Res<string>> ResetearClaveAdminAsync(int actorId, int id)
    {
        var a = await db.Administradores.FindAsync(id);
        if (a is null) return Res<string>.Fallo("no_encontrado", 404);
        var clave = PinHasher.NuevaClaveTemporal();
        a.PassHash = PinHasher.Hash(clave);
        a.DebeCambiarPass = true;
        a.IntentosFallidos = 0;
        a.BloqueadoHastaUtc = null;
        Auditar(actorId, null, "clave_admin_reseteada", null, a.Usuario, "Reseteo de clave de administrador");
        await db.SaveChangesAsync();
        return new(clave);
    }

    // ---------- Registros ----------
    public async Task<List<RegistroAdminDto>> RegistrosAsync(FiltroRegistros f)
    {
        var now = Ahora;
        var (desdeUtc, hastaUtc) = Zona.RangoUtc(Zona.De(_o), f.Desde, f.Hasta);
        var eliminados = f.Eliminados;
        var q = db.Registros.AsNoTracking().Where(r => r.Anulado == eliminados);
        if (f.EmpleadoId is { } e) q = q.Where(r => r.EmpleadoId == e);
        if (f.ObraId is { } o) q = q.Where(r => r.ObraId == o);
        if (f.Revisar is true) q = q.Where(r => r.RevisarAdmin);
        if (Areas.Normalizar(f.Area) is { } area) q = q.Where(r => r.Empleado!.Area == area);
        if (desdeUtc is { } d) q = q.Where(r => r.FinUtc == null || r.FinUtc > d);
        if (hastaUtc is { } h) q = q.Where(r => r.InicioUtc < h);

        var lista = await q.OrderByDescending(r => r.InicioUtc).Take(Math.Clamp(f.Limite, 1, 5000))
            .Select(r => new { r.Id, r.EmpleadoId, Empleado = r.Empleado!.Nombre, Area = r.Empleado!.Area, r.ObraId, Obra = r.Obra!.Nombre, r.SubtareaId, Subtarea = r.Subtarea == null ? null : r.Subtarea.Nombre, r.InicioUtc, r.FinUtc, r.Estado, r.Origen, r.Equipo, r.RevisarAdmin, r.Anulado })
            .ToListAsync();
        var resultado = lista.Select(r => new RegistroAdminDto(r.Id, r.EmpleadoId, r.Empleado, r.ObraId, r.Obra, r.InicioUtc, r.FinUtc,
            r.Estado.ToString().ToLowerInvariant(), r.Origen, r.Equipo, r.RevisarAdmin, (long)((r.FinUtc ?? now) - r.InicioUtc).TotalSeconds, r.Anulado, r.Area, r.Subtarea, r.SubtareaId)).ToList();

        // Las horas que cargan a mano los empleados de Taller también figuran entre los registros (Origen «carga»; solo lectura:
        // se corrigen o eliminan en «Horas de Taller»), con su obra y subtarea. No tienen «a revisar»: con ese filtro no aparecen.
        if (f.Revisar is not true)
        {
            var zona = Zona.De(_o);
            var qc = db.CargasHoras.AsNoTracking().Where(c => c.Anulado == eliminados);
            if (f.EmpleadoId is { } ec) qc = qc.Where(c => c.EmpleadoId == ec);
            if (f.ObraId is { } oc) qc = qc.Where(c => c.ObraId == oc);
            if (Areas.Normalizar(f.Area) is { } areaC) qc = qc.Where(c => c.Empleado!.Area == areaC);
            if (f.Desde is { } dc) qc = qc.Where(c => c.Fecha >= dc);
            if (f.Hasta is { } hc) qc = qc.Where(c => c.Fecha <= hc);
            var cargas = await qc.OrderByDescending(c => c.Fecha).Take(Math.Clamp(f.Limite, 1, 5000))
                .Select(c => new { c.Id, c.EmpleadoId, Empleado = c.Empleado!.Nombre, Area = c.Empleado.Area, c.Fecha, c.Minutos, c.Anulado, c.ObraId, Obra = c.Obra == null ? null : c.Obra.Nombre, c.SubtareaId, Subtarea = c.Subtarea == null ? null : c.Subtarea.Nombre }).ToListAsync();
            resultado.AddRange(cargas.Select(c =>
            {
                var ini = Zona.MedianocheLocalAUtc(zona, c.Fecha);
                return new RegistroAdminDto(IdDeCarga(c.Id), c.EmpleadoId, c.Empleado, c.ObraId ?? 0, c.Obra ?? "(Carga de horas)", ini, ini.AddMinutes(c.Minutos), "cargada", "carga", "", false,
                    c.Minutos * 60L, c.Anulado, c.Area, c.Subtarea, c.SubtareaId);
            }));
            resultado = resultado.OrderByDescending(r => r.InicioUtc).ThenBy(r => r.Empleado).Take(Math.Clamp(f.Limite, 1, 5000)).ToList();
        }
        return resultado;
    }

    /// <summary>Id ficticio de una carga de horas en la lista de registros (no corresponde a ningún registro de Play).</summary>
    private static Guid IdDeCarga(int id) => new(id, 0, 0, [0x43, 0x41, 0x52, 0x47, 0x41, 0, 0, 0]);

    /// <summary>
    /// «Eliminar» un registro: no se borra de la base, queda marcado (con motivo y constancia) y deja de contar en totales,
    /// reportes y resúmenes. Se puede recuperar con <see cref="RestaurarAsync"/>. No se eliminan registros en curso.
    /// </summary>
    public async Task<Res<RegistroAdminDto>> AnularAsync(int adminId, Guid id, string motivo)
    {
        if (string.IsNullOrWhiteSpace(motivo)) return Res<RegistroAdminDto>.Fallo("motivo_requerido");
        var r = await db.Registros.Include(x => x.Empleado).Include(x => x.Obra).Include(x => x.Subtarea).FirstOrDefaultAsync(x => x.Id == id);
        if (r is null) return Res<RegistroAdminDto>.Fallo("no_encontrado", 404);
        if (r.Estado == EstadoRegistro.Abierto) return Res<RegistroAdminDto>.Fallo("registro_abierto", 409);
        if (r.Anulado) return new(Dto(r)); // ya estaba eliminado: no se duplica la constancia

        r.Anulado = true;
        Auditar(adminId, r.Id, "anulado", Resumen(r), "(eliminado)", motivo);
        await db.SaveChangesAsync();
        return new(Dto(r));
    }

    public async Task<Res<RegistroAdminDto>> RestaurarAsync(int adminId, Guid id, string motivo)
    {
        if (string.IsNullOrWhiteSpace(motivo)) return Res<RegistroAdminDto>.Fallo("motivo_requerido");
        var r = await db.Registros.Include(x => x.Empleado).Include(x => x.Obra).FirstOrDefaultAsync(x => x.Id == id);
        if (r is null) return Res<RegistroAdminDto>.Fallo("no_encontrado", 404);
        if (!r.Anulado) return new(Dto(r));

        r.Anulado = false;
        Auditar(adminId, r.Id, "restaurado", "(eliminado)", Resumen(r), motivo);
        await db.SaveChangesAsync();
        return new(Dto(r));
    }

    private static string Resumen(RegistroTiempo r) =>
        $"{r.Empleado?.Nombre} / {r.Obra?.Nombre}{(r.Subtarea is null ? "" : " › " + r.Subtarea.Nombre)} / {Iso(r.InicioUtc)} - {Iso(r.FinUtc)}";

    public async Task<List<EnVivoDto>> EnVivoAsync(string? area = null)
    {
        var now = Ahora;
        var q = db.Registros.AsNoTracking().Where(r => r.Estado == EstadoRegistro.Abierto);
        if (Areas.Normalizar(area) is { } a) q = q.Where(r => r.Empleado!.Area == a);
        var l = await q.OrderBy(r => r.Empleado!.Nombre)
            .Select(r => new { r.EmpleadoId, Empleado = r.Empleado!.Nombre, Area = r.Empleado!.Area, Obra = r.Subtarea == null ? r.Obra!.Nombre : r.Obra!.Nombre + " › " + r.Subtarea.Nombre, r.Equipo, r.InicioUtc, r.UltimoLatidoUtc }).ToListAsync();
        return l.Select(r => new EnVivoDto(r.EmpleadoId, r.Empleado, r.Obra, r.Equipo, r.InicioUtc, r.UltimoLatidoUtc, (long)(now - r.InicioUtc).TotalSeconds, r.Area)).ToList();
    }

    /// <summary>Corrige un registro cerrado. Exige motivo; deja una fila de auditoría por cada campo modificado.</summary>
    public async Task<Res<RegistroAdminDto>> CorregirAsync(int adminId, Guid id, CorreccionRequest req)
    {
        if (string.IsNullOrWhiteSpace(req.Motivo)) return Res<RegistroAdminDto>.Fallo("motivo_requerido");
        var r = await db.Registros.Include(x => x.Empleado).Include(x => x.Obra).Include(x => x.Subtarea).FirstOrDefaultAsync(x => x.Id == id);
        if (r is null) return Res<RegistroAdminDto>.Fallo("no_encontrado", 404);
        if (r.Estado == EstadoRegistro.Abierto) return Res<RegistroAdminDto>.Fallo("registro_abierto", 409);
        if (r.Anulado) return Res<RegistroAdminDto>.Fallo("registro_eliminado", 409);

        var inicio = req.InicioUtc?.ToUniversalTime() ?? r.InicioUtc;
        var fin = req.FinUtc?.ToUniversalTime() ?? r.FinUtc ?? r.UltimoLatidoUtc;
        if (fin <= inicio) return Res<RegistroAdminDto>.Fallo("rango_invalido");
        if (fin > Ahora.AddMinutes(1)) return Res<RegistroAdminDto>.Fallo("fecha_futura");

        // Obra y subtarea destino. Si cambia la obra, la subtarea anterior ya no sirve (salvo que se indique otra de la obra nueva).
        var obraDestino = r.Obra;
        if (req.ObraId is { } oid && oid != r.ObraId)
        {
            obraDestino = await db.Obras.FindAsync(oid);
            if (obraDestino is null) return Res<RegistroAdminDto>.Fallo("obra_invalida");
        }
        var obraCambia = obraDestino!.Id != r.ObraId;
        Subtarea? subtareaDestino = r.Subtarea;
        if (req.QuitarSubtarea || (obraCambia && req.SubtareaId is null)) subtareaDestino = null;
        else if (req.SubtareaId is { } sid)
        {
            subtareaDestino = await db.Subtareas.FindAsync(sid);
            if (subtareaDestino is null || subtareaDestino.ObraId != obraDestino.Id) return Res<RegistroAdminDto>.Fallo("subtarea_invalida");
        }

        var cambios = 0;
        if (inicio != r.InicioUtc) { Auditar(adminId, r.Id, "inicio", Iso(r.InicioUtc), Iso(inicio), req.Motivo); r.InicioUtc = inicio; cambios++; }
        if (fin != r.FinUtc) { Auditar(adminId, r.Id, "fin", Iso(r.FinUtc), Iso(fin), req.Motivo); r.FinUtc = fin; cambios++; }
        if (obraCambia)
        {
            Auditar(adminId, r.Id, "obra", r.Obra?.Nombre, obraDestino.Nombre, req.Motivo);
            r.ObraId = obraDestino.Id;
            r.Obra = obraDestino;
            cambios++;
        }
        if (subtareaDestino?.Id != r.SubtareaId)
        {
            Auditar(adminId, r.Id, "subtarea", r.Subtarea?.Nombre ?? "(sin subtarea)", subtareaDestino?.Nombre ?? "(sin subtarea)", req.Motivo);
            r.SubtareaId = subtareaDestino?.Id;
            r.Subtarea = subtareaDestino;
            cambios++;
        }
        if (cambios == 0) return Res<RegistroAdminDto>.Fallo("sin_cambios");

        r.Estado = EstadoRegistro.Corregido;
        r.RevisarAdmin = false;
        if (r.UltimoLatidoUtc < fin) r.UltimoLatidoUtc = fin;
        await db.SaveChangesAsync();
        return new(Dto(r));
    }

    /// <summary>Alta manual de un registro olvidado (ej. el empleado no pudo usar el panel).</summary>
    public async Task<Res<RegistroAdminDto>> CrearRegistroAsync(int adminId, AltaRegistroRequest req)
    {
        if (string.IsNullOrWhiteSpace(req.Motivo)) return Res<RegistroAdminDto>.Fallo("motivo_requerido");
        var inicio = req.InicioUtc.ToUniversalTime();
        var fin = req.FinUtc.ToUniversalTime();
        if (fin <= inicio) return Res<RegistroAdminDto>.Fallo("rango_invalido");
        if (fin > Ahora.AddMinutes(1)) return Res<RegistroAdminDto>.Fallo("fecha_futura");
        var emp = await db.Empleados.FindAsync(req.EmpleadoId);
        var obra = await db.Obras.FindAsync(req.ObraId);
        if (emp is null || obra is null) return Res<RegistroAdminDto>.Fallo("datos_invalidos");

        // Misma regla que para los empleados: si la obra tiene subtareas activas hay que indicar una (de esa obra).
        Subtarea? subtarea = null;
        if (req.SubtareaId is { } sid)
        {
            subtarea = await db.Subtareas.FindAsync(sid);
            if (subtarea is null || subtarea.ObraId != obra.Id) return Res<RegistroAdminDto>.Fallo("subtarea_invalida");
        }
        else if (await db.Subtareas.AnyAsync(s => s.ObraId == obra.Id && s.Activa && !s.Terminada)) return Res<RegistroAdminDto>.Fallo("subtarea_requerida");

        var solapa = await db.Registros.AnyAsync(x => x.EmpleadoId == emp.Id && !x.Anulado && x.InicioUtc < fin && (x.FinUtc ?? Ahora) > inicio);
        var r = new RegistroTiempo
        {
            Id = Guid.NewGuid(), EmpleadoId = emp.Id, Empleado = emp, ObraId = obra.Id, Obra = obra, SubtareaId = subtarea?.Id, Subtarea = subtarea,
            InicioUtc = inicio, FinUtc = fin,
            UltimoLatidoUtc = fin, Estado = EstadoRegistro.Corregido, Origen = "admin", Equipo = "", RevisarAdmin = solapa,
        };
        db.Registros.Add(r);
        Auditar(adminId, r.Id, "creado", null, $"{emp.Nombre} / {obra.Nombre}{(subtarea is null ? "" : " › " + subtarea.Nombre)} / {Iso(inicio)} - {Iso(fin)}", req.Motivo);
        await db.SaveChangesAsync();
        return new(Dto(r));
    }

    public async Task<List<AuditoriaDto>> AuditoriaAsync(Guid? registroId, int limite = 500)
    {
        var q = db.Auditorias.AsNoTracking().AsQueryable();
        if (registroId is { } rid) q = q.Where(a => a.RegistroId == rid);
        var l = await q.OrderByDescending(a => a.FechaUtc).ThenByDescending(a => a.Id).Take(Math.Clamp(limite, 1, 5000)).ToListAsync();
        var admins = await db.Administradores.AsNoTracking().ToDictionaryAsync(a => a.Id, a => a.Usuario);
        return l.Select(a => new AuditoriaDto(a.Id, a.FechaUtc, a.AdministradorId == 0 ? "Sistema" : admins.GetValueOrDefault(a.AdministradorId, "?"), a.RegistroId, a.Campo, a.ValorAnterior, a.ValorNuevo, a.Motivo)).ToList();
    }

    private RegistroAdminDto Dto(RegistroTiempo r) => new(r.Id, r.EmpleadoId, r.Empleado?.Nombre ?? "", r.ObraId, r.Obra?.Nombre ?? "", r.InicioUtc, r.FinUtc,
        r.Estado.ToString().ToLowerInvariant(), r.Origen, r.Equipo, r.RevisarAdmin, (long)((r.FinUtc ?? Ahora) - r.InicioUtc).TotalSeconds, r.Anulado, r.Empleado?.Area ?? Areas.Oficina, r.Subtarea?.Nombre, r.SubtareaId);

    private static string? Iso(DateTime? d) => d?.ToUniversalTime().ToString("yyyy-MM-dd HH:mm:ss'Z'");

    private void Auditar(int adminId, Guid? registroId, string campo, string? anterior, string? nuevo, string motivo) =>
        db.Auditorias.Add(new Auditoria { FechaUtc = Ahora, AdministradorId = adminId, RegistroId = registroId, Campo = campo, ValorAnterior = anterior, ValorNuevo = nuevo, Motivo = motivo.Trim() });
}
