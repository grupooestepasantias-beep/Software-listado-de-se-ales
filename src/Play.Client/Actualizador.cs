using System.Diagnostics;
using System.IO;
using System.Security.Cryptography;

namespace Play.Client;

/// <summary>Versión de Play.exe publicada en el servidor (<c>GET /api/panel/version</c>).</summary>
public record VersionPanelDto(string Version, string Sha256, long Bytes, string Archivo, DateTime PublicadoUtc);

/// <summary>
/// Piezas de la actualización automática del panel, sin interfaz gráfica (para poder probarlas):
/// comparar versiones, descargar y verificar, reemplazar el .exe en uso (Windows permite RENOMBRAR un programa que está
/// corriendo, pero no pisarlo) y volver atrás si lo nuevo no arranca.
/// </summary>
public static class Actualizador
{
    public static string RutaNueva(string exe) => exe + ".nuevo";
    public static string RutaVieja(string exe) => exe + ".viejo";
    private static string RutaParcial(string exe) => exe + ".nuevo.parcial";

    public static bool EsMasNueva(string? versionServidor, Version actual) =>
        Version.TryParse(versionServidor, out var v) && v > actual;

    /// <summary>
    /// Descarga <c>/descargar/{archivo}</c> a <c>{exe}.nuevo</c> y verifica tamaño, huella SHA-256, que sea un ejecutable
    /// de Windows y que su versión sea la anunciada. Si algo no coincide, borra lo descargado y lanza <see cref="InvalidDataException"/>.
    /// </summary>
    public static async Task<string> DescargarAsync(HttpClient http, VersionPanelDto info, string exeActual, CancellationToken ct = default)
    {
        var destino = RutaNueva(exeActual);
        var parcial = RutaParcial(exeActual);
        try
        {
            using var resp = await http.GetAsync("descargar/" + Uri.EscapeDataString(info.Archivo), HttpCompletionOption.ResponseHeadersRead, ct);
            resp.EnsureSuccessStatusCode();
            await using (var origen = await resp.Content.ReadAsStreamAsync(ct))
            await using (var fs = new FileStream(parcial, FileMode.Create, FileAccess.Write, FileShare.None, 1 << 16, useAsync: true))
                await origen.CopyToAsync(fs, 1 << 16, ct);

            await VerificarAsync(parcial, info, ct);
            File.Move(parcial, destino, overwrite: true);
            return destino;
        }
        catch
        {
            TryDelete(parcial);
            throw;
        }
    }

    /// <summary>Comprueba que el archivo es exactamente lo que el servidor anunció. Lanza <see cref="InvalidDataException"/> si no.</summary>
    public static async Task VerificarAsync(string archivo, VersionPanelDto info, CancellationToken ct = default)
    {
        var largo = new FileInfo(archivo).Length;
        if (largo != info.Bytes) throw new InvalidDataException($"Tamaño distinto: {largo} en lugar de {info.Bytes} bytes.");

        string sha;
        await using (var fs = new FileStream(archivo, FileMode.Open, FileAccess.Read, FileShare.Read, 1 << 16, useAsync: true))
            sha = Convert.ToHexString(await SHA256.HashDataAsync(fs, ct));
        if (!string.Equals(sha, info.Sha256, StringComparison.OrdinalIgnoreCase)) throw new InvalidDataException("La huella SHA-256 no coincide: la descarga está dañada.");

        await using (var fs = File.OpenRead(archivo))
            if (fs.ReadByte() != 'M' || fs.ReadByte() != 'Z') throw new InvalidDataException("No es un ejecutable de Windows.");

        var version = FileVersionInfo.GetVersionInfo(archivo).FileVersion;
        if (!string.IsNullOrWhiteSpace(version) && !string.Equals(version.Trim(), info.Version, StringComparison.Ordinal))
            throw new InvalidDataException($"La versión del archivo ({version}) no es la anunciada ({info.Version}).");
    }

    /// <summary>
    /// Pone el .exe nuevo (<c>.nuevo</c>) en el lugar del actual, que queda como <c>.viejo</c>. Si algo falla a mitad, deja todo como estaba.
    /// </summary>
    public static void Reemplazar(string exeActual)
    {
        var nuevo = RutaNueva(exeActual);
        var viejo = RutaVieja(exeActual);
        if (!File.Exists(nuevo)) throw new FileNotFoundException("No hay una versión nueva descargada.", nuevo);

        if (File.Exists(viejo)) File.Delete(viejo); // resto de una actualización anterior
        File.Move(exeActual, viejo);
        try { File.Move(nuevo, exeActual); }
        catch
        {
            File.Move(viejo, exeActual); // no se pudo: vuelve a como estaba
            throw;
        }
    }

    /// <summary>Deshace <see cref="Reemplazar"/>: el .exe nuevo (que no arrancó, y ya debe estar cerrado) se descarta y vuelve el viejo.</summary>
    public static void Revertir(string exeActual)
    {
        var viejo = RutaVieja(exeActual);
        if (!File.Exists(viejo)) return;
        if (File.Exists(exeActual)) File.Delete(exeActual);
        File.Move(viejo, exeActual);
    }

    /// <summary>Borra los restos de una actualización (el .exe anterior, si ya no está en uso, y descargas incompletas).</summary>
    public static bool LimpiarRestos(string exeActual)
    {
        TryDelete(RutaParcial(exeActual));
        var viejo = RutaVieja(exeActual);
        if (!File.Exists(viejo)) return true;
        try { File.Delete(viejo); return true; }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { return false; } // el programa anterior todavía se está cerrando
    }

    private static void TryDelete(string ruta)
    {
        try { if (File.Exists(ruta)) File.Delete(ruta); }
        catch (Exception ex) when (ex is IOException or UnauthorizedAccessException) { }
    }
}

/// <summary>Cuándo es seguro reiniciar el panel para instalar una versión nueva (nunca con el cronómetro andando).</summary>
public static class PoliticaActualizacion
{
    public static bool DebeAplicarAhora(EstadoPanel estado, TimeSpan inactivo, bool alArrancar) => estado switch
    {
        EstadoPanel.Registrando => false,
        _ when alArrancar => true,                       // recién abierto, todavía sin usuario: es el mejor momento
        EstadoPanel.SinSesion => inactivo >= TimeSpan.FromSeconds(30),
        _ => inactivo >= TimeSpan.FromMinutes(2),        // en pausa: solo si el empleado se alejó (almuerzo, reunión)
    };
}
