using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Windows;
using Play.Client;
using Play.Panel.Demo;

namespace Play.Panel;

public partial class App : Application
{
    private static Mutex? _mutex;
    private static EventWaitHandle _eventoMostrar = null!;

    private static string? _carpetaAlternativa;

    /// <summary>%AppData%\Play, o la carpeta indicada con <c>--datos</c> (pruebas: no toca los ajustes reales ni el inicio con Windows).</summary>
    private static string CarpetaDatos => _carpetaAlternativa ?? Path.Combine(Environment.GetFolderPath(Environment.SpecialFolder.ApplicationData), "Play");

    protected override void OnStartup(StartupEventArgs e)
    {
        base.OnStartup(e);

        // Un panel que corre todo el día no debe cerrarse por un error inesperado: se registra y se sigue.
        DispatcherUnhandledException += (_, ex) =>
        {
            RegistrarError(ex.Exception);
            ex.Handled = true;
        };

        // Modo de desarrollo: genera capturas de la interfaz con datos de ejemplo (ver docs).
        if (e.Args.Length == 2 && e.Args[0] == "--captura")
        {
            _ = Captura.EjecutarAsync(e.Args[1]);
            return;
        }

        var iDatos = Array.IndexOf(e.Args, "--datos");
        if (iDatos >= 0 && iDatos + 1 < e.Args.Length) _carpetaAlternativa = e.Args[iDatos + 1];

        // Con --datos (pruebas) cada carpeta es una «instalación» distinta. string.GetHashCode() cambia en cada ejecución: se usa un hash estable.
        var sufijo = _carpetaAlternativa is null ? "" : "." + Convert.ToHexString(System.Security.Cryptography.SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(_carpetaAlternativa)))[..12];
        var nombreEvento = @"Local\Play.Panel.Mostrar" + sufijo;
        // «Primera» = quien logra tomar el mutex (no quien lo crea): así, al soltarlo (actualización, cambio de servidor), otra copia puede tomarlo.
        _mutex = new Mutex(false, @"Local\Play.Panel.UnaSolaInstancia" + sufijo);
        bool esLaPrimera;
        try { esLaPrimera = _mutex.WaitOne(0); }
        catch (AbandonedMutexException) { esLaPrimera = true; } // el panel anterior se cerró sin soltarlo
        if (!esLaPrimera)
        {
            // Ya hay un panel abierto en esta sesión (cerrar su ventana solo la contrae): se le avisa para que se muestre y se actualice.
            try { using var aviso = EventWaitHandle.OpenExisting(nombreEvento); aviso.Set(); }
            catch (Exception ex) when (ex is WaitHandleCannotBeOpenedException or UnauthorizedAccessException) { }
            Shutdown();
            return;
        }
        _eventoMostrar = new EventWaitHandle(false, EventResetMode.AutoReset, nombreEvento);

        var store = new LocalStore(CarpetaDatos);
        var url = store.Ajustes.ServidorUrl;
        if (string.IsNullOrWhiteSpace(url))
        {
            url = Dialogos.PedirServidor(null, null);
            if (url is null) { Shutdown(); return; }
            store.Ajustes.ServidorUrl = url;
            store.GuardarAjustes();
        }

        var http = new HttpClient { BaseAddress = new Uri(url.TrimEnd('/') + "/"), Timeout = Timeout.InfiniteTimeSpan };
        var api = new ApiClient(http);
        var controlador = new PanelController(api, store, TimeProvider.System, Environment.MachineName);

        // Actualización automática (en pruebas aisladas con --datos solo si se pide con --permitir-actualizacion).
        var iAct = Array.IndexOf(e.Args, "--actualizado");
        _eventoActualizado = iAct >= 0 && iAct + 1 < e.Args.Length ? e.Args[iAct + 1] : null;
        MainWindow? ventana = null;
        var actualizador = new ActualizadorPanel(http, api, store, () => controlador.Estado, Native.TiempoInactivo,
            texto => ventana?.MostrarAvisoPublico(texto), aislado: _carpetaAlternativa is not null, forzar: e.Args.Contains("--permitir-actualizacion"));
        ventana = new MainWindow(controlador, store, sinRegistro: _carpetaAlternativa is not null, actualizador: actualizador);

        // Al apagar o cerrar sesión en Windows: pausa lo antes posible para que el registro termine a la hora exacta.
        SessionEnding += (_, _) =>
        {
            try { Task.Run(controlador.SalirAsync).Wait(3000); } catch (Exception ex) { RegistrarError(ex); }
        };

        ventana.Show();

        var escucha = new Thread(() =>
        {
            while (_eventoMostrar.WaitOne()) ventana.Dispatcher.InvokeAsync(ventana.MostrarYRefrescar);
        }) { IsBackground = true, Name = "Play.Mostrar" };
        escucha.Start();
    }

    /// <summary>Cambió la dirección del servidor: se abre una instancia nueva (con los mismos argumentos) y se cierra esta.</summary>
    public static void Reiniciar()
    {
        SoltarInstanciaUnica();
        if (Environment.ProcessPath is { } exe)
        {
            var args = Environment.GetCommandLineArgs().Skip(1).ToList();
            var i = args.IndexOf("--actualizado");
            if (i >= 0) args.RemoveRange(i, Math.Min(2, args.Count - i));
            Process.Start(new ProcessStartInfo(exe, string.Join(" ", args.Select(a => a.Contains(' ') ? $"\"{a}\"" : a))) { UseShellExecute = false });
        }
        Current.Shutdown();
    }

    private static bool _instanciaSoltada;

    /// <summary>Libera el «solo un panel por sesión» para que otra copia (la versión nueva) pueda tomarlo.</summary>
    public static void SoltarInstanciaUnica()
    {
        if (_instanciaSoltada) return;
        try { _mutex?.ReleaseMutex(); _instanciaSoltada = true; }
        catch (ApplicationException ex) { throw new InvalidOperationException("No se pudo liberar el «un solo panel por sesión»: " + ex.Message, ex); }
    }

    /// <summary>Si la actualización falló y este panel sigue vivo, vuelve a ser el único.</summary>
    public static void TomarInstanciaUnica()
    {
        if (!_instanciaSoltada) return;
        try { _instanciaSoltada = !(_mutex?.WaitOne(0) ?? true); } catch (AbandonedMutexException) { _instanciaSoltada = false; }
    }

    private static string? _eventoActualizado;

    /// <summary>
    /// Si este panel arrancó porque el anterior se estaba actualizando, le confirma que levantó bien (si no, el anterior vuelve atrás),
    /// avisa en pantalla y borra el .exe anterior en cuanto ese proceso termine.
    /// </summary>
    public static void ConfirmarActualizacion(Action<string> avisar)
    {
        var exe = Environment.ProcessPath;
        if (exe is null || !string.Equals(Path.GetFileName(exe), "Play.exe", StringComparison.OrdinalIgnoreCase)) return;

        if (_eventoActualizado is not null)
        {
            try { using var ack = EventWaitHandle.OpenExisting(_eventoActualizado); ack.Set(); }
            catch (Exception ex) when (ex is WaitHandleCannotBeOpenedException or UnauthorizedAccessException) { }
            avisar($"Programa actualizado a la versión {typeof(App).Assembly.GetName().Version}.");
        }

        // Limpieza de restos (el .exe anterior mientras siga cerrándose); sin bloquear la ventana.
        _ = Task.Run(async () =>
        {
            for (var i = 0; i < 30; i++)
            {
                if (Actualizador.LimpiarRestos(exe)) return;
                await Task.Delay(1000);
            }
        });
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
