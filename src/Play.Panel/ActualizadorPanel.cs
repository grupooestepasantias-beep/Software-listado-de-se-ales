using System.Diagnostics;
using System.IO;
using System.Net.Http;
using System.Windows;
using Play.Client;

namespace Play.Panel;

/// <summary>
/// Mantiene el panel al día sin que nadie tenga que bajar nada:
/// 1) al abrirse y cada 10 minutos pregunta al servidor qué versión está publicada;
/// 2) si es más nueva, la descarga en segundo plano y la verifica (tamaño, huella SHA-256, versión);
/// 3) la instala solo cuando es seguro (nunca con el cronómetro andando; con el panel en pausa, cuando el empleado se alejó);
/// 4) arranca la versión nueva y espera su confirmación: si no arranca bien, vuelve a la anterior y no insiste con esa versión.
/// Todo queda anotado en %AppData%\Play\actualizaciones.log.
/// </summary>
public sealed class ActualizadorPanel
{
    private readonly HttpClient _http;
    private readonly ApiClient _api;
    private readonly LocalStore _store;
    private readonly Func<EstadoPanel> _estado;
    private readonly Func<TimeSpan> _inactivo;
    private readonly Action<string> _avisar;
    private readonly string _exe;
    private readonly Version _actual;

    private VersionPanelDto? _info;
    private bool _descargando, _listo, _aplicando;
    private DateTime _ultimaConsulta = DateTime.MinValue;

    public bool Habilitado { get; }
    public Version VersionActual => _actual;

    public ActualizadorPanel(HttpClient http, ApiClient api, LocalStore store, Func<EstadoPanel> estado, Func<TimeSpan> inactivo,
        Action<string> avisar, bool aislado, bool forzar)
    {
        _http = http;
        _api = api;
        _store = store;
        _estado = estado;
        _inactivo = inactivo;
        _avisar = avisar;
        _exe = Environment.ProcessPath ?? "";
        _actual = typeof(App).Assembly.GetName().Version ?? new Version(0, 0, 0, 0);

        // Solo se actualiza el .exe único publicado (Play.exe): no las compilaciones de desarrollo ni las pruebas aisladas.
#pragma warning disable IL3000 // en un .exe único Assembly.Location está vacío: justamente lo que se quiere detectar
        var esUnicoPublicado = string.IsNullOrEmpty(typeof(App).Assembly.Location);
#pragma warning restore IL3000
        Habilitado = esUnicoPublicado && string.Equals(Path.GetFileName(_exe), "Play.exe", StringComparison.OrdinalIgnoreCase) && (!aislado || forzar);
    }

    private string RutaLog => Path.Combine(_store.Carpeta, "actualizaciones.log");

    private void Registrar(string texto)
    {
        try { File.AppendAllText(RutaLog, $"{DateTime.Now:yyyy-MM-dd HH:mm:ss} {texto}\n"); }
        catch (IOException) { }
    }

    /// <summary>Se llama cada segundo desde la ventana; casi siempre no hace nada (solo consulta cada 10 min).</summary>
    public async Task ComprobarAsync(bool alArrancar)
    {
        if (!Habilitado || _aplicando) return;
        try
        {
            if (_info is null)
            {
                if (!alArrancar && DateTime.UtcNow - _ultimaConsulta < TimeSpan.FromMinutes(10)) return;
                _ultimaConsulta = DateTime.UtcNow;

                var r = await _api.LlamarAsync<VersionPanelDto>(HttpMethod.Get, "api/panel/version");
                if (!r.Ok || r.Valor is null) return;
                if (!Actualizador.EsMasNueva(r.Valor.Version, _actual) || r.Valor.Version == _store.Ajustes.VersionRechazada) return;
                _info = r.Valor;
                Registrar($"Hay una versión nueva: {_actual} → {_info.Version} ({_info.Bytes / 1024 / 1024} MB).");
            }

            if (!_listo && !_descargando) _ = DescargarAsync(alArrancar);

            // La decisión se toma con el estado de AHORA (puede haber pasado tiempo desde que empezó la descarga).
            if (_listo && PoliticaActualizacion.DebeAplicarAhora(_estado(), _inactivo(), alArrancar && _estado() == EstadoPanel.SinSesion))
                await AplicarAsync();
        }
        catch (Exception ex)
        {
            Registrar($"Error al comprobar actualizaciones: {ex.Message}");
        }
    }

    private async Task DescargarAsync(bool alArrancar)
    {
        _descargando = true;
        var info = _info!;
        try
        {
            var nuevo = Actualizador.RutaNueva(_exe);
            if (File.Exists(nuevo))
            {
                // Quedó descargada de una vez anterior: si está íntegra, no se baja de nuevo.
                try { await Actualizador.VerificarAsync(nuevo, info); _listo = true; Registrar("Versión nueva ya descargada y verificada."); return; }
                catch (InvalidDataException) { File.Delete(nuevo); }
            }

            // Escalonado: si todas las PCs se encienden juntas, no deben bajar 140 MB al mismo tiempo.
            await Task.Delay(Random.Shared.Next(0, alArrancar ? 15_000 : 90_000));
            using var limite = new CancellationTokenSource(TimeSpan.FromMinutes(20));
            await Actualizador.DescargarAsync(_http, info, _exe, limite.Token);
            _listo = true;
            Registrar($"Versión {info.Version} descargada y verificada.");
        }
        catch (Exception ex)
        {
            Registrar($"No se pudo descargar la versión {info.Version}: {ex.Message}. Se reintenta en unos minutos.");
            _info = null; // vuelve a consultar en la próxima vuelta
        }
        finally { _descargando = false; }
    }

    private async Task AplicarAsync()
    {
        _aplicando = true;
        var info = _info!;
        Process? nuevo = null;
        var reemplazado = false;
        try
        {
            _avisar($"Instalando la versión nueva ({info.Version})…");
            Actualizador.Reemplazar(_exe);
            reemplazado = true;

            // Se arranca la versión nueva y se espera a que confirme que levantó bien.
            var nombreAck = @"Local\Play.Panel.Actualizado." + Guid.NewGuid().ToString("N");
            using var ack = new EventWaitHandle(false, EventResetMode.ManualReset, nombreAck);
            App.SoltarInstanciaUnica();
            nuevo = Process.Start(new ProcessStartInfo(_exe, ArgumentosParaLaNueva(nombreAck)) { UseShellExecute = false });
            if (nuevo is null) throw new InvalidOperationException("No se pudo iniciar la versión nueva.");
            var espera = Task.Run(() => ack.WaitOne(TimeSpan.FromSeconds(40)));
            var salio = nuevo.WaitForExitAsync();
            var primero = await Task.WhenAny(espera, salio); // si la nueva se cierra sola, no hace falta esperar los 40 s
            if (primero != espera || !await espera) throw new InvalidOperationException(primero == salio ? $"La versión nueva se cerró sola (código {nuevo.ExitCode})." : "La versión nueva no confirmó que arrancó bien.");

            Registrar($"Actualizado a {info.Version}.");
            Application.Current.Shutdown(); // la nueva ya está en marcha; borrará el .exe anterior cuando este termine
        }
        catch (Exception ex)
        {
            Registrar($"FALLÓ la actualización a {info.Version}: {ex.Message}. Se vuelve a la versión anterior.");
            _store.Ajustes.VersionRechazada = info.Version;
            _store.GuardarAjustes();
            try { if (nuevo is { HasExited: false }) { nuevo.Kill(entireProcessTree: true); nuevo.WaitForExit(5000); } } catch (Exception) { }
            try { if (reemplazado) Actualizador.Revertir(_exe); } catch (Exception e2) { Registrar($"No se pudo revertir: {e2.Message}"); }
            App.TomarInstanciaUnica();
            _avisar("No se pudo instalar la versión nueva; sigue la actual.");
            _info = null;
            _listo = false;
            _aplicando = false;
        }
    }

    /// <summary>Los mismos argumentos con los que se abrió este panel, más el aviso de «vengo de una actualización».</summary>
    private static string ArgumentosParaLaNueva(string nombreAck)
    {
        var args = Environment.GetCommandLineArgs().Skip(1).ToList();
        var i = args.IndexOf("--actualizado");
        if (i >= 0) args.RemoveRange(i, Math.Min(2, args.Count - i));
        args.Add("--actualizado");
        args.Add(nombreAck);
        return string.Join(" ", args.Select(a => a.Contains(' ') ? $"\"{a}\"" : a));
    }
}
