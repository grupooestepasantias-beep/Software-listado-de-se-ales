using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Play.Server.Data;

namespace Play.Server.Services;

public record BackupInfo(string Archivo, long Bytes, DateTime FechaUtc);

/// <summary>Copias de seguridad de la base con VACUUM INTO (consistente aunque haya usuarios escribiendo).</summary>
public class BackupService(TimeProvider time, IOptions<PlayOptions> options, IHostEnvironment env, ILogger<BackupService> log)
{
    private readonly PlayOptions _o = options.Value;

    public string Carpeta => string.IsNullOrWhiteSpace(_o.BackupDir)
        ? Path.Combine(Path.GetFullPath(_o.DataDir, env.ContentRootPath), "backups")
        : Path.GetFullPath(_o.BackupDir, env.ContentRootPath);

    private DateTime LocalAhora => TimeZoneInfo.ConvertTimeFromUtc(time.GetUtcNow().UtcDateTime, Zona.De(_o));

    /// <summary>True si ya pasó la hora del backup y todavía no hay uno de hoy.</summary>
    public bool DebeHacerBackup()
    {
        var local = LocalAhora;
        if (local.Hour < _o.BackupHour) return false;
        if (!Directory.Exists(Carpeta)) return true;
        return !Directory.EnumerateFiles(Carpeta, $"play-{local:yyyyMMdd}-*.db").Any();
    }

    public async Task<BackupInfo> HacerBackupAsync()
    {
        Directory.CreateDirectory(Carpeta);
        var path = Path.Combine(Carpeta, $"play-{LocalAhora:yyyyMMdd-HHmmss}.db");
        if (File.Exists(path)) File.Delete(path);

        await using (var conn = new SqliteConnection($"Data Source={Path.Combine(Path.GetFullPath(_o.DataDir, env.ContentRootPath), "play.db")};Pooling=False"))
        {
            await conn.OpenAsync();
            await using var cmd = conn.CreateCommand();
            cmd.CommandText = $"VACUUM INTO '{path.Replace("'", "''")}'";
            await cmd.ExecuteNonQueryAsync();
        }

        // Verifica que la copia se pueda abrir y esté íntegra; si no, se descarta.
        await using (var check = new SqliteConnection($"Data Source={path};Mode=ReadOnly;Pooling=False"))
        {
            await check.OpenAsync();
            await using var cmd = check.CreateCommand();
            cmd.CommandText = "PRAGMA quick_check";
            var r = (string?)await cmd.ExecuteScalarAsync();
            if (r != "ok")
            {
                await check.CloseAsync();
                File.Delete(path);
                throw new InvalidOperationException($"El backup no pasó la verificación de integridad: {r}");
            }
        }

        var fi = new FileInfo(path);
        log.LogInformation("Backup creado: {Ruta} ({Kb} KB)", path, fi.Length / 1024);
        return new BackupInfo(fi.Name, fi.Length, fi.LastWriteTimeUtc);
    }

    /// <summary>Borra backups más viejos que la retención, conservando siempre el más reciente.</summary>
    public int LimpiarAntiguos()
    {
        if (!Directory.Exists(Carpeta)) return 0;
        var limite = time.GetUtcNow().UtcDateTime.AddDays(-_o.BackupRetentionDays);
        var archivos = new DirectoryInfo(Carpeta).GetFiles("play-*.db").OrderByDescending(f => f.LastWriteTimeUtc).ToList();
        var borrar = archivos.Skip(1).Where(f => f.LastWriteTimeUtc < limite).ToList();
        foreach (var f in borrar) f.Delete();
        return borrar.Count;
    }

    public List<BackupInfo> Listar() =>
        !Directory.Exists(Carpeta) ? [] :
        new DirectoryInfo(Carpeta).GetFiles("play-*.db").OrderByDescending(f => f.LastWriteTimeUtc)
            .Select(f => new BackupInfo(f.Name, f.Length, f.LastWriteTimeUtc)).ToList();
}

/// <summary>Cada 10 minutos revisa si corresponde el backup diario y limpia los viejos.</summary>
public class BackupWorker(IServiceScopeFactory scopes, ILogger<BackupWorker> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        using var timer = new PeriodicTimer(TimeSpan.FromMinutes(10));
        do
        {
            try
            {
                using var scope = scopes.CreateScope();
                var b = scope.ServiceProvider.GetRequiredService<BackupService>();
                if (b.DebeHacerBackup()) await b.HacerBackupAsync();
                var borrados = b.LimpiarAntiguos();
                if (borrados > 0) log.LogInformation("{N} backup(s) antiguo(s) eliminado(s).", borrados);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                log.LogError(ex, "Error en el backup diario.");
            }
        } while (await timer.WaitForNextTickAsync(ct));
    }
}
