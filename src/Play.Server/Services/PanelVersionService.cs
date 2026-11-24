using System.Diagnostics;
using System.Security.Cryptography;

namespace Play.Server.Services;

public record InfoPanel(string Version, string Sha256, long Bytes, string Archivo, DateTime PublicadoUtc);

/// <summary>
/// Dice qué versión de Play.exe está publicada en datos/descargas (la lee del propio .exe) y su huella SHA-256,
/// para que cada panel decida si debe actualizarse y verifique lo que descarga. Se recalcula solo si el archivo cambia.
/// </summary>
public class PanelVersionService
{
    private readonly SemaphoreSlim _candado = new(1, 1);
    private (string Ruta, long Largo, long Ticks, InfoPanel Info)? _cache;

    public async Task<InfoPanel?> LeerAsync(FileInfo? archivo, CancellationToken ct = default)
    {
        if (archivo is null || !archivo.Exists) return null;
        archivo.Refresh();

        await _candado.WaitAsync(ct);
        try
        {
            if (_cache is { } c && c.Ruta == archivo.FullName && c.Largo == archivo.Length && c.Ticks == archivo.LastWriteTimeUtc.Ticks)
                return c.Info;

            string sha;
            await using (var fs = new FileStream(archivo.FullName, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 16, useAsync: true))
                sha = Convert.ToHexString(await SHA256.HashDataAsync(fs, ct));

            var version = FileVersionInfo.GetVersionInfo(archivo.FullName).FileVersion;
            if (string.IsNullOrWhiteSpace(version)) version = "0.0.0.0";

            var info = new InfoPanel(version.Trim(), sha, archivo.Length, archivo.Name, archivo.LastWriteTimeUtc);
            _cache = (archivo.FullName, archivo.Length, archivo.LastWriteTimeUtc.Ticks, info);
            return info;
        }
        finally { _candado.Release(); }
    }
}
