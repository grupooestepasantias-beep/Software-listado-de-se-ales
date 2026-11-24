using System.Globalization;
using System.Security.Cryptography;
using System.Text;
using ClosedXML.Excel;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Play.Server.Data;

namespace Play.Server.Services;

public record ErrorFilaExcel(int Fila, string Mensaje);

/// <summary>Estado de la última sincronización con el Excel de empleados (lo muestra la Administración).</summary>
public record EmpleadosExcelEstadoDto(bool Configurado, string? Archivo, DateTime? UltimaUtc, bool? Ok, string? Mensaje,
    int Empleados, int Administradores, int Creados, int Actualizados, int Desactivados, List<ErrorFilaExcel> Errores);

/// <summary>Estado en memoria de la última sincronización (compartido por el servicio de cada pedido y por el proceso de fondo).</summary>
public sealed class EmpleadosExcelEstado
{
    public DateTime? UltimaUtc { get; set; }
    public bool? Ok { get; set; }
    public string? Mensaje { get; set; }
    public int Empleados { get; set; }
    public int Administradores { get; set; }
    public int Creados { get; set; }
    public int Actualizados { get; set; }
    public int Desactivados { get; set; }
    public List<ErrorFilaExcel> Errores { get; set; } = [];
    /// <summary>Huella del último contenido aplicado: si el archivo no cambió, no se vuelve a procesar.</summary>
    public string? HuellaAplicada { get; set; }
    /// <summary>Marca (fecha + tamaño) del archivo ya procesado, para que el proceso de fondo detecte cambios sin leerlo.</summary>
    public string? MarcaProcesada { get; set; }
}

/// <summary>
/// El Excel de empleados es la base de datos de empleados (y de administradores): columnas Empleado, Contraseña y Área
/// (Oficina, Taller o Administrador). Cada vez que el archivo cambia se sincroniza: altas, bajas (se desactivan, nunca se
/// borran), cambios de PIN y de área. La PRIMERA vez que se usa el Excel se eliminan todos los empleados anteriores y sus
/// datos (pedido de la usuaria), con una copia de seguridad previa.
/// </summary>
public class EmpleadosExcelService(PlayDb db, TimeProvider time, IOptions<PlayOptions> options, IHostEnvironment env,
    EmpleadosExcelEstado estado, ILogger<EmpleadosExcelService> log)
{
    private const string AjusteInicializado = "empleados_excel_inicializado";
    private static readonly SemaphoreSlim Candado = new(1, 1);

    private DateTime Ahora => time.GetUtcNow().UtcDateTime;
    public string Ruta => options.Value.EmpleadosExcel?.Trim() ?? "";
    public bool Configurado => Ruta.Length > 0;

    public EmpleadosExcelEstadoDto Dto() => new(Configurado, Configurado ? Ruta : null, estado.UltimaUtc, estado.Ok, estado.Mensaje,
        estado.Empleados, estado.Administradores, estado.Creados, estado.Actualizados, estado.Desactivados, estado.Errores.ToList());

    /// <summary>Marca (fecha de modificación + tamaño) del archivo, o null si no existe.</summary>
    public string? MarcaDelArchivo()
    {
        try
        {
            var f = new FileInfo(Ruta);
            return f.Exists ? $"{f.LastWriteTimeUtc.Ticks}:{f.Length}" : null;
        }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return null; }
    }

    // ---------------------------------------------------------------- lectura del Excel

    private sealed record FilaEmpleado(int Fila, string Nombre, string Secreto, string Area);

    private static string SinTildes(string s)
    {
        var d = s.Normalize(NormalizationForm.FormD);
        var sb = new StringBuilder();
        foreach (var c in d) if (CharUnicodeInfo.GetUnicodeCategory(c) != UnicodeCategory.NonSpacingMark) sb.Append(c);
        return sb.ToString().ToLowerInvariant().Trim();
    }

    /// <summary>«  Vera   Diego  » → «Vera Diego».</summary>
    private static string Nombre(string? s) => string.Join(' ', (s ?? "").Split([' ', '\t', ' '], StringSplitOptions.RemoveEmptyEntries));

    /// <summary>El PIN del Excel puede traer un apóstrofe (de escribirlo como texto para no perder el cero: «0187'») o espacios.</summary>
    private static string LimpiarSecreto(string? s) => new string((s ?? "").Where(c => !char.IsWhiteSpace(c) && c is not ('\'' or '’' or '‘' or '`' or '"')).ToArray());

    private static (List<FilaEmpleado> Filas, string? Error, string Huella) Leer(string ruta)
    {
        byte[] bytes;
        using (var fs = new FileStream(ruta, FileMode.Open, FileAccess.Read, FileShare.ReadWrite | FileShare.Delete))
        using (var ms = new MemoryStream())
        {
            fs.CopyTo(ms);
            bytes = ms.ToArray();
        }
        var huella = Convert.ToHexString(SHA256.HashData(bytes));
        using var wb = new XLWorkbook(new MemoryStream(bytes));
        var ws = wb.Worksheets.First();
        var cabecera = ws.Row(1);
        int ColDe(params string[] nombres)
        {
            for (var c = 1; c <= Math.Max(ws.LastColumnUsed()?.ColumnNumber() ?? 1, 6); c++)
                if (nombres.Contains(SinTildes(cabecera.Cell(c).GetString()))) return c;
            return 0;
        }
        var cNombre = ColDe("empleado", "nombre", "empleados");
        var cSecreto = ColDe("contrasena", "clave", "pin", "password");
        var cArea = ColDe("area");
        if (cNombre == 0 || cSecreto == 0 || cArea == 0)
            return ([], "El Excel tiene que tener las columnas «Empleado», «Contraseña» y «Área» en la primera fila.", huella);

        var filas = new List<FilaEmpleado>();
        var ultima = ws.LastRowUsed()?.RowNumber() ?? 1;
        for (var r = 2; r <= ultima; r++)
        {
            var nombre = Nombre(ws.Cell(r, cNombre).GetFormattedString());
            var secreto = LimpiarSecreto(ws.Cell(r, cSecreto).GetFormattedString());
            var area = Nombre(ws.Cell(r, cArea).GetFormattedString());
            if (nombre.Length == 0 && secreto.Length == 0 && area.Length == 0) continue;
            filas.Add(new FilaEmpleado(r, nombre, secreto, area));
        }
        return (filas, null, huella);
    }

    // ---------------------------------------------------------------- sincronización

    /// <summary>Usuario de un administrador a partir de su nombre «Apellido Nombre»: el nombre de pila con la primera letra en mayúscula (Garcia Gabriel Gines → Gabriel).</summary>
    public static string UsuarioDe(string nombreCompleto)
    {
        var partes = Nombre(nombreCompleto).Split(' ');
        var token = partes.Length >= 2 ? partes[1] : partes[0];
        token = new string(token.Where(char.IsLetterOrDigit).ToArray());
        return token.Length == 0 ? "Admin" : char.ToUpperInvariant(token[0]) + token[1..].ToLowerInvariant();
    }

    /// <summary>
    /// Sincroniza la base con el Excel. Si <paramref name="forzar"/> es false y el contenido no cambió desde la última vez, no hace nada.
    /// Si el archivo no se puede leer o no tiene empleados válidos, no se toca nada (se conserva lo que había).
    /// </summary>
    public async Task<EmpleadosExcelEstadoDto> SincronizarAsync(bool forzar = false)
    {
        if (!Configurado) return Dto();
        await Candado.WaitAsync();
        try
        {
            var marca = MarcaDelArchivo();
            string huella;
            List<FilaEmpleado> filas;
            try
            {
                if (marca is null) return Fallo($"No se encontró el Excel de empleados: {Ruta}");
                string? errorLectura;
                (filas, errorLectura, huella) = Leer(Ruta);
                if (errorLectura is not null) { estado.MarcaProcesada = marca; return Fallo(errorLectura); }
            }
            catch (IOException ex)
            {
                // Casi siempre: el archivo está siendo guardado o sincronizado por OneDrive. Se reintenta solo.
                log.LogWarning("No se pudo leer el Excel de empleados (¿en uso?): {Msg}", ex.Message);
                return Fallo("No se pudo leer el Excel (¿está siendo guardado?). Se reintenta solo.", reintentar: true);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                log.LogError(ex, "El Excel de empleados no se pudo interpretar.");
                estado.MarcaProcesada = marca;
                return Fallo("El archivo no es un Excel válido (.xlsx) o está dañado.");
            }

            if (!forzar && estado.HuellaAplicada == huella && estado.Ok is not null)
            {
                // El archivo se guardó pero con el mismo contenido: no hay nada que cambiar.
                estado.MarcaProcesada = marca;
                estado.UltimaUtc = Ahora;
                estado.Ok = true;
                estado.Mensaje = "Todo al día: el Excel y la app coinciden.";
                return Dto();
            }
            var resultado = await AplicarAsync(filas);
            estado.MarcaProcesada = marca;
            if (resultado) estado.HuellaAplicada = huella;
            return Dto();
        }
        finally { Candado.Release(); }
    }

    private EmpleadosExcelEstadoDto Fallo(string mensaje, bool reintentar = false)
    {
        estado.UltimaUtc = Ahora;
        estado.Ok = false;
        estado.Mensaje = mensaje + " Se conserva lo que ya estaba cargado.";
        estado.Errores = [];
        if (reintentar) estado.MarcaProcesada = null;
        return Dto();
    }

    private async Task<bool> AplicarAsync(List<FilaEmpleado> filas)
    {
        var errores = new List<ErrorFilaExcel>();
        var empleados = new List<FilaEmpleado>();
        var admins = new List<FilaEmpleado>();
        var presentes = new HashSet<string>(StringComparer.OrdinalIgnoreCase); // nombres de empleados que figuran (aunque su fila tenga un error)
        var vistos = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var vistosAdmin = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

        foreach (var f in filas)
        {
            if (f.Nombre.Length == 0) { errores.Add(new(f.Fila, "Falta el nombre del empleado.")); continue; }
            var esAdmin = SinTildes(f.Area) is "administrador" or "administradora" or "admin" or "administradores";
            var area = Areas.Normalizar(f.Area);
            if (!esAdmin && area is null) { errores.Add(new(f.Fila, $"«{f.Nombre}»: el área «{f.Area}» no es válida (tiene que ser Oficina, Taller o Administrador).")); presentes.Add(f.Nombre); continue; } // figura en el Excel: no se lo da de baja por un error en su área

            if (esAdmin)
            {
                if (!vistosAdmin.Add(f.Nombre)) { errores.Add(new(f.Fila, $"«{f.Nombre}» figura más de una vez como administrador.")); continue; }
                if (f.Secreto.Length < 4) { errores.Add(new(f.Fila, $"«{f.Nombre}»: la contraseña del administrador tiene que tener al menos 4 caracteres.")); continue; }
                admins.Add(f);
                continue;
            }

            presentes.Add(f.Nombre);
            if (!vistos.Add(f.Nombre)) { errores.Add(new(f.Fila, $"«{f.Nombre}» figura más de una vez como empleado.")); continue; }
            if (!AuthService.PinValido(f.Secreto)) { errores.Add(new(f.Fila, $"«{f.Nombre}»: el PIN tiene que ser de 4 números (figura «{f.Secreto}»). Se conserva el anterior.")); empleados.Add(f with { Secreto = "" }); continue; }
            empleados.Add(f with { Area = area! });
        }

        if (empleados.Count(e => e.Secreto.Length > 0) == 0)
        {
            estado.UltimaUtc = Ahora;
            estado.Ok = false;
            estado.Mensaje = "El Excel no tiene ningún empleado válido: no se cambió nada.";
            estado.Errores = errores;
            return false;
        }

        var altas = new List<string>(); var bajas = new List<string>(); var pines = new List<string>(); var areas = new List<string>(); var reactivados = new List<string>();
        var adminsNuevos = new List<string>();
        var primera = await db.Ajustes.FindAsync(AjusteInicializado) is null;
        string? purgados = null;
        if (primera) await CopiaDeSeguridadAsync(); // antes de tocar nada (VACUUM no puede correr dentro de una transacción)

        // Todo o nada: si algo falla a la mitad, no queda la base a medio cambiar.
        await using var tx = await db.Database.BeginTransactionAsync();
        if (primera) purgados = await PurgarEmpleadosAnterioresAsync();

        var existentes = await db.Empleados.ToListAsync();
        var porNombre = new Dictionary<string, Empleado>(StringComparer.OrdinalIgnoreCase);
        foreach (var e in existentes.OrderByDescending(e => e.Activo)) porNombre.TryAdd(Nombre(e.Nombre), e);
        var hoy = DateOnly.FromDateTime(TimeZoneInfo.ConvertTimeFromUtc(Ahora, Zona.De(options.Value)));

        foreach (var f in empleados)
        {
            if (porNombre.TryGetValue(f.Nombre, out var e))
            {
                if (!e.Activo) { e.Activo = true; reactivados.Add(f.Nombre); }
                if (f.Secreto.Length == 0) continue; // PIN inválido en el Excel: se conserva el anterior
                if (e.Area != f.Area) { e.Area = f.Area; areas.Add($"{f.Nombre} → {f.Area}"); }
                var cambioPin = e.PinVisible is null ? !PinHasher.Verify(f.Secreto, e.PinHash) : e.PinVisible != f.Secreto;
                if (cambioPin)
                {
                    e.PinHash = PinHasher.Hash(f.Secreto);
                    e.PinVisible = f.Secreto;
                    e.IntentosFallidos = 0;
                    e.BloqueadoHastaUtc = null;
                    pines.Add(f.Nombre);
                    await db.Sesiones.Where(s => s.Tipo == "empleado" && s.UsuarioId == e.Id).ExecuteDeleteAsync(); // con un PIN nuevo hay que volver a ingresar
                }
                else if (e.PinVisible != f.Secreto) e.PinVisible = f.Secreto;
                e.DebeCambiarPin = false;
            }
            else if (f.Secreto.Length > 0)
            {
                var nuevo = new Empleado { Nombre = f.Nombre, Area = f.Area, PinHash = PinHasher.Hash(f.Secreto), PinVisible = f.Secreto, DebeCambiarPin = false, CreadoFecha = hoy };
                db.Empleados.Add(nuevo);
                porNombre[f.Nombre] = nuevo;
                altas.Add(f.Nombre);
            }
        }

        // Los que ya no figuran en el Excel se desactivan (nunca se borran): conservan su historial.
        foreach (var e in existentes.Where(e => e.Activo && !presentes.Contains(Nombre(e.Nombre))))
        {
            e.Activo = false;
            bajas.Add(e.Nombre);
            await db.Sesiones.Where(s => s.Tipo == "empleado" && s.UsuarioId == e.Id).ExecuteDeleteAsync();
        }

        // Administradores: se crean con la contraseña del Excel como TEMPORAL (la tienen que cambiar al entrar). Los que ya existen
        // solo actualizan el nombre; su clave y su estado no se tocan (el Excel nunca desactiva a un administrador).
        var adminsExistentes = await db.Administradores.ToListAsync();
        foreach (var f in admins)
        {
            var existente = adminsExistentes.FirstOrDefault(a => string.Equals(Nombre(a.NombreCompleto), f.Nombre, StringComparison.OrdinalIgnoreCase))
                ?? adminsExistentes.FirstOrDefault(a => string.Equals(a.Usuario, UsuarioDe(f.Nombre), StringComparison.OrdinalIgnoreCase));
            if (existente is not null)
            {
                if (!string.Equals(existente.NombreCompleto, f.Nombre, StringComparison.Ordinal)) existente.NombreCompleto = f.Nombre;
                continue;
            }
            var usuario = UsuarioDe(f.Nombre);
            var partes = Nombre(f.Nombre).Split(' ');
            var candidatos = new[] { usuario, usuario + char.ToUpperInvariant(partes[0][0]), usuario + "2" };
            usuario = candidatos.FirstOrDefault(c => !adminsExistentes.Any(a => string.Equals(a.Usuario, c, StringComparison.OrdinalIgnoreCase))) ?? usuario + Guid.NewGuid().ToString("N")[..4];
            var nuevo = new Administrador { Usuario = usuario, NombreCompleto = f.Nombre, PassHash = PinHasher.Hash(f.Secreto), DebeCambiarPass = true };
            db.Administradores.Add(nuevo);
            adminsExistentes.Add(nuevo);
            adminsNuevos.Add($"{f.Nombre} (usuario {usuario})");
        }

        var cambios = altas.Count + bajas.Count + pines.Count + areas.Count + reactivados.Count + adminsNuevos.Count;
        if (primera) db.Ajustes.Add(new Ajuste { Clave = AjusteInicializado, Valor = Ahora.ToString("O") });
        if (cambios > 0 || primera)
        {
            var resumen = new List<string>();
            if (purgados is not null) resumen.Add($"Primera vez: se eliminaron los empleados anteriores y sus datos ({purgados})");
            if (altas.Count > 0) resumen.Add($"Altas: {string.Join(", ", altas)}");
            if (reactivados.Count > 0) resumen.Add($"Reactivados: {string.Join(", ", reactivados)}");
            if (bajas.Count > 0) resumen.Add($"Bajas (desactivados): {string.Join(", ", bajas)}");
            if (pines.Count > 0) resumen.Add($"PIN cambiado: {string.Join(", ", pines)}");
            if (areas.Count > 0) resumen.Add($"Área: {string.Join(", ", areas)}");
            if (adminsNuevos.Count > 0) resumen.Add($"Administradores nuevos: {string.Join(", ", adminsNuevos)}");
            var texto = string.Join(" · ", resumen);
            db.Auditorias.Add(new Auditoria { FechaUtc = Ahora, AdministradorId = 0, Campo = "empleados_excel", ValorNuevo = texto.Length > 3000 ? texto[..3000] + "…" : texto, Motivo = "Sincronización con el Excel de empleados" });
        }
        await db.SaveChangesAsync();
        await tx.CommitAsync();

        estado.UltimaUtc = Ahora;
        estado.Ok = true;
        estado.Empleados = await db.Empleados.CountAsync(e => e.Activo);
        estado.Administradores = await db.Administradores.CountAsync(a => a.Activo);
        estado.Creados = altas.Count + adminsNuevos.Count;
        estado.Actualizados = pines.Count + areas.Count + reactivados.Count;
        estado.Desactivados = bajas.Count;
        estado.Errores = errores;
        estado.Mensaje = errores.Count == 0
            ? (cambios == 0 && !primera ? "Todo al día: el Excel y la app coinciden." : "Sincronizado con el Excel.")
            : $"Sincronizado con el Excel, pero {errores.Count} fila(s) tienen errores y se saltearon.";
        if (cambios > 0 || primera) log.LogInformation("Empleados sincronizados con el Excel: {Altas} altas, {Bajas} bajas, {Pines} PIN, {Areas} áreas.", altas.Count, bajas.Count, pines.Count, areas.Count);
        return true;
    }

    // ---------------------------------------------------------------- primera vez: eliminar los empleados anteriores

    private async Task CopiaDeSeguridadAsync()
    {
        var dir = Path.Combine(Path.GetFullPath(options.Value.DataDir, env.ContentRootPath), "backups");
        Directory.CreateDirectory(dir);
        var copia = Path.Combine(dir, $"play-antes-de-importar-excel-{DateTime.Now:yyyyMMdd-HHmmss}.db");
        await db.Database.ExecuteSqlRawAsync($"VACUUM INTO '{copia.Replace("'", "''")}'");
    }

    /// <summary>
    /// Borra TODOS los empleados que había y todo lo que dependía de ellos: registros de Play, horas de Taller, faltas, avisos de
    /// subtareas, sesiones y las constancias de la auditoría que los nombran. No toca obras, subtareas ni administradores.
    /// </summary>
    private async Task<string> PurgarEmpleadosAnterioresAsync()
    {
        var emps = await db.Empleados.AsNoTracking().Select(e => new { e.Id, e.Nombre }).ToListAsync();
        if (emps.Count == 0) return "no había ninguno";
        var ids = emps.Select(e => e.Id).ToList();
        var nombres = emps.Select(e => e.Nombre).ToList();
        var regIds = (await db.Registros.AsNoTracking().Where(r => ids.Contains(r.EmpleadoId)).Select(r => r.Id).ToListAsync()).ToHashSet();

        var registros = regIds.Count;
        var cargas = await db.CargasHoras.CountAsync(c => ids.Contains(c.EmpleadoId));
        await db.AvisosSubtarea.Where(a => ids.Contains(a.EmpleadoId)).ExecuteDeleteAsync();
        await db.Faltas.Where(f => ids.Contains(f.EmpleadoId)).ExecuteDeleteAsync();
        await db.CargasHoras.Where(c => ids.Contains(c.EmpleadoId)).ExecuteDeleteAsync();
        await db.Registros.Where(r => ids.Contains(r.EmpleadoId)).ExecuteDeleteAsync();
        await db.Sesiones.Where(s => s.Tipo == "empleado").ExecuteDeleteAsync();

        var aud = await db.Auditorias.AsNoTracking().ToListAsync();
        var borrar = aud.Where(a => (a.RegistroId is { } rid && regIds.Contains(rid))
            || nombres.Any(n => (a.ValorAnterior?.Contains(n, StringComparison.OrdinalIgnoreCase) ?? false) || (a.ValorNuevo?.Contains(n, StringComparison.OrdinalIgnoreCase) ?? false)))
            .Select(a => a.Id).ToList();
        if (borrar.Count > 0) await db.Auditorias.Where(a => borrar.Contains(a.Id)).ExecuteDeleteAsync();

        await db.Empleados.Where(e => ids.Contains(e.Id)).ExecuteDeleteAsync();
        db.ChangeTracker.Clear();
        return $"{emps.Count} empleado(s), {registros} registro(s) de Play, {cargas} carga(s) de horas";
    }
}

/// <summary>Cada pocos segundos mira si el Excel de empleados cambió y, si cambió, sincroniza (espera a que termine de guardarse).</summary>
public class EmpleadosExcelWorker(IServiceScopeFactory scopes, EmpleadosExcelEstado estado, IOptions<PlayOptions> options, ILogger<EmpleadosExcelWorker> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromSeconds(Math.Max(1, options.Value.EmpleadosExcelSegundos)));
        while (await timer.WaitForNextTickAsync(ct))
        {
            try
            {
                using var scope = scopes.CreateScope();
                var svc = scope.ServiceProvider.GetRequiredService<EmpleadosExcelService>();
                if (!svc.Configurado) continue;
                var marca = svc.MarcaDelArchivo();
                if (marca is not null && marca == estado.MarcaProcesada) continue; // sin cambios
                if (marca is not null)
                {
                    // Excel/OneDrive escriben el archivo de a poco: se espera unos segundos a que quede quieto.
                    await Task.Delay(TimeSpan.FromSeconds(3), ct);
                    if (svc.MarcaDelArchivo() != marca) continue;
                }
                await svc.SincronizarAsync();
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                log.LogError(ex, "Error al sincronizar los empleados con el Excel.");
            }
        }
    }
}
