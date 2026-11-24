using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Text.Json;
using System.Windows;
using Play.Client;

namespace Play.Admin;

public sealed class AjustesAdmin
{
    public string? ServidorUrl { get; set; }
    public string? UltimoUsuario { get; set; }
}

public partial class App : Application
{
    private static string? _carpetaAlternativa;
    private static string CarpetaDatos => _carpetaAlternativa ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "PlayAdmin");
    private static string RutaAjustes => Path.Combine(CarpetaDatos, "ajustes.json");

    public static AjustesAdmin Ajustes { get; private set; } = new();
    private static Mutex? _mutex;

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);
        DispatcherUnhandledException += (_, ex) =>
        {
            RegistrarError(ex.Exception);
            MessageBox.Show($"Ocurrió un error inesperado:\n\n{ex.Exception.Message}\n\nSe guardó el detalle en {Path.Combine(CarpetaDatos, "errores.log")}.", "Play Administración", MessageBoxButton.OK, MessageBoxImage.Warning);
            ex.Handled = true;
        };

        var i = Array.IndexOf(e.Args, "--datos");
        if (i >= 0 && i + 1 < e.Args.Length) _carpetaAlternativa = e.Args[i + 1];

        // string.GetHashCode() cambia en cada ejecución: con --datos se usa un hash estable.
        var sufijo = _carpetaAlternativa is null ? "" : "." + Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(_carpetaAlternativa)))[..12];
        // «Primera» = quien logra tomar el mutex (no quien lo crea): así, al soltarlo (reinicio), la nueva copia puede tomarlo.
        _mutex = new Mutex(false, @"Local\Play.Admin.UnaSolaInstancia" + sufijo);
        bool primera;
        try { primera = _mutex.WaitOne(0); }
        catch (AbandonedMutexException) { primera = true; }
        if (!primera) { MessageBox.Show("Play Administración ya está abierto.", "Play Administración"); Shutdown(); return; }

        Directory.CreateDirectory(CarpetaDatos);
        try { Ajustes = JsonSerializer.Deserialize<AjustesAdmin>(File.ReadAllText(RutaAjustes), new JsonSerializerOptions(JsonSerializerDefaults.Web)) ?? new(); }
        catch (Exception ex) when (ex is IOException or JsonException) { Ajustes = new(); }

        if (string.IsNullOrWhiteSpace(Ajustes.ServidorUrl))
        {
            var url = Dialogos.PedirServidor(null, "localhost:8080");
            if (url is null) { Shutdown(); return; }
            Ajustes.ServidorUrl = url;
            GuardarAjustes();
        }

        var http = new HttpClient { BaseAddress = new Uri(Ajustes.ServidorUrl!.TrimEnd('/') + "/"), Timeout = Timeout.InfiniteTimeSpan };
        var api = new AdminApi(new ApiClient(http, timeout: TimeSpan.FromSeconds(15)));

        var login = new LoginWindow(api);
        if (login.ShowDialog() != true) { Shutdown(); return; }

        var principal = new MainWindow(api, login.Usuario);
        MainWindow = principal;
        ShutdownMode = ShutdownMode.OnMainWindowClose;
        principal.Show();
    }

    public static void GuardarAjustes()
    {
        try
        {
            Directory.CreateDirectory(CarpetaDatos);
            File.WriteAllText(RutaAjustes, JsonSerializer.Serialize(Ajustes, new JsonSerializerOptions(JsonSerializerDefaults.Web) { WriteIndented = true }));
        }
        catch (IOException) { }
    }

    /// <summary>Se vuelve a abrir el programa (cambió el servidor o venció la sesión).</summary>
    public static void Reiniciar()
    {
        try { _mutex?.ReleaseMutex(); } catch (ApplicationException) { }
        if (Environment.ProcessPath is { } exe)
        {
            var args = _carpetaAlternativa is null ? "" : $"--datos \"{_carpetaAlternativa}\"";
            Process.Start(new ProcessStartInfo(exe, args) { UseShellExecute = false });
        }
        Current.Shutdown();
    }

    private static void RegistrarError(Exception ex)
    {
        try
        {
            Directory.CreateDirectory(CarpetaDatos);
            File.AppendAllText(Path.Combine(CarpetaDatos, "errores.log"), $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {ex}\n\n");
        }
        catch (IOException) { }
    }
}
