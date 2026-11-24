namespace Play.Client;

public enum EstadoPanel { SinSesion, Pausado, Registrando }

/// <summary>
/// Lógica del panel del empleado, sin interfaz gráfica. Garantías:
/// - nunca cuenta tiempo sin que el empleado presione Play;
/// - un corte de red no pierde horas: se sigue contando y se sincroniza después (idempotente);
/// - si la PC se suspende o se apaga, el registro termina en el último momento en que el panel estuvo vivo.
/// </summary>
public sealed class PanelController
{
    private sealed class Tramo
    {
        public Guid Id { get; init; }
        public int ObraId { get; init; }
        public int? SubtareaId { get; init; }
        public DateTime InicioUtc { get; init; }
    }

    /// <summary>Si pasan más de estos segundos entre dos ticks, se considera que la PC estuvo suspendida.</summary>
    private const int SegundosParaSuspension = 90;
    private const int SegundosEntreSincronizaciones = 30;

    private readonly IPlayApi _api;
    private readonly LocalStore _store;
    private readonly TimeProvider _time;
    private readonly string _equipo;

    private ConfigServidor _cfg = new(30, 120);
    private Tramo? _actual;
    private DateTime _ultimoTick;
    private DateTime _ultimoLatido;
    private DateTime _ultimaSync;
    private bool _enRed;
    private bool _inactivo;

    public PanelController(IPlayApi api, LocalStore store, TimeProvider time, string equipo)
    {
        _api = api;
        _store = store;
        _time = time;
        _equipo = equipo;
    }

    public EstadoPanel Estado { get; private set; } = EstadoPanel.SinSesion;
    public int EmpleadoId { get; private set; }
    public string Nombre { get; private set; } = "";
    public bool DebeCambiarPin { get; private set; }
    public bool Conectado { get; private set; } = true;
    public bool SesionVencida { get; private set; }
    public List<ItemLista> Empleados { get; private set; } = [];
    public List<ItemLista> Obras { get; private set; } = [];
    public ResumenDto? UltimoResumen { get; private set; }

    /// <summary>Mensaje para mostrar al empleado; la interfaz lo borra después de mostrarlo.</summary>
    public string? Aviso { get; set; }

    public bool PreguntarInactividad { get; private set; }
    public DateTime? InactivoDesdeUtc { get; private set; }
    /// <summary>Hay inactividad detectada pero el empleado todavía no volvió.</summary>
    public bool Inactivo => _inactivo && !PreguntarInactividad;

    public int? ObraActualId => _actual?.ObraId;
    public int? SubtareaActualId => _actual?.SubtareaId;

    private Dictionary<int, List<ItemLista>> _subtareas = [];

    /// <summary>Subtareas activas de una obra (vacío si no tiene: entonces no hay que elegir ninguna; si tiene, es obligatorio).</summary>
    public List<ItemLista> SubtareasDe(int obraId) => _subtareas.TryGetValue(obraId, out var l) ? l : [];
    /// <summary>Obras que tienen subtareas pendientes (son las que se ofrecen en «Avisar que terminé una subtarea»).</summary>
    public List<ItemLista> ObrasConSubtareas() => Obras.Where(o => SubtareasDe(o.Id).Count > 0).ToList();

    /// <summary>
    /// El empleado avisa al administrador que terminó una subtarea. No la cierra ni la tacha: eso lo decide el administrador.
    /// Devuelve si salió bien y el texto para mostrarle.
    /// </summary>
    public async Task<(bool Ok, string Mensaje)> AvisarSubtareaAsync(int subtareaId)
    {
        var r = await _api.AvisarSubtareaAsync(subtareaId);
        if (r.SinRed) return (false, "No hay conexión con el servidor. Probá de nuevo en un rato.");
        if (r.Ok) return (true, "Listo: le avisaste al administrador.");
        return r.Codigo == "subtarea_terminada"
            ? (false, "Esa subtarea ya figura como terminada.")
            : (false, "No se pudo avisar. Probá de nuevo.");
    }

    // ---- Horas de Taller: los empleados de Taller cargan horas a mano en lugar de usar el cronómetro ----

    /// <summary>true si el empleado que ingresó es del área Taller (entonces el panel muestra «Cargar horas» y no Play).</summary>
    public bool EsTaller => Empleados.FirstOrDefault(e => e.Id == EmpleadoId)?.Area == AreasEmpresa.Taller;

    /// <summary>Obras para cargar horas: primero «(Sin obra)» (trabajo general de Taller), después las obras.</summary>
    public List<ItemLista> ObrasParaCarga => [new ItemLista(0, "(Sin obra: trabajo general)"), .. Obras];

    /// <summary>Las cargas recientes y la fecha de hoy del servidor (null si todavía no se pudieron pedir).</summary>
    public MisHorasDto? Horas { get; private set; }

    public async Task RefrescarHorasAsync()
    {
        var r = await _api.MisHorasAsync();
        if (r.Ok && r.Valor is not null) { Horas = r.Valor; Notificar(); }
    }

    /// <summary>
    /// Interpreta lo que escribe el empleado: «8», «7,5», «7.5», «7:30», «8 h», «8hs». Devuelve minutos (de 1 min a 24 h).
    /// </summary>
    public static bool TryParseHoras(string? texto, out int minutos)
    {
        minutos = 0;
        var t = (texto ?? "").Trim().ToLowerInvariant();
        foreach (var sufijo in new[] { "horas", "hs", "h" }) if (t.EndsWith(sufijo)) { t = t[..^sufijo.Length].Trim(); break; }
        if (t.Length == 0) return false;
        double horas;
        if (t.Contains(':'))
        {
            var partes = t.Split(':');
            if (partes.Length != 2 || !int.TryParse(partes[0], out var h) || !int.TryParse(partes[1], out var m) || h < 0 || m is < 0 or > 59) return false;
            horas = h + m / 60.0;
        }
        else if (!double.TryParse(t.Replace(',', '.'), System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out horas) || double.IsNaN(horas)) return false;
        var min = (int)Math.Round(horas * 60);
        if (min < 1 || min > 24 * 60) return false;
        minutos = min;
        return true;
    }

    /// <summary>Carga las horas de hoy o de ayer. Devuelve si salió bien y el texto para mostrarle.</summary>
    public async Task<(bool Ok, string Mensaje)> CargarHorasAsync(DateOnly fecha, int minutos, int? obraId = null, int? subtareaId = null)
    {
        if (obraId == 0) obraId = null; // «(Sin obra)»
        if (obraId is null) subtareaId = null;
        if (obraId is { } oid && SubtareasDe(oid).Count > 0 && (subtareaId is null || !SubtareasDe(oid).Any(s => s.Id == subtareaId)))
            return (false, "Esta obra tiene subtareas: elegí una.");
        if (obraId is { } oid2 && SubtareasDe(oid2).Count == 0) subtareaId = null;
        var r = await _api.CargarHorasAsync(fecha, minutos, obraId, subtareaId);
        if (r.SinRed) return (false, "No hay conexión con el servidor. Las horas no se guardaron: probá de nuevo cuando haya red.");
        if (!r.Ok)
        {
            return (false, r.Codigo switch
            {
                "cargada_por_admin" => "Esas horas las cargó o corrigió el administrador: pedile que las cambie.",
                "fecha_no_permitida" => "Solo se puede cargar hoy o ayer.",
                "horas_invalidas" => "Las horas tienen que estar entre 1 minuto y 24 horas (y el día no puede pasar de 24 horas en total).",
                "solo_taller" => "Cargar horas es solo para el personal de Taller.",
                "obra_invalida" => "Esa obra no está disponible. Elegí otra.",
                "subtarea_requerida" => "Esta obra tiene subtareas: elegí una.",
                "subtarea_invalida" => "Esa subtarea no corresponde a la obra elegida.",
                _ => "No se pudieron guardar las horas. Probá de nuevo.",
            });
        }
        await RefrescarHorasAsync();
        return (true, "Listo: horas guardadas.");
    }

    /// <summary>Quita la línea de horas de ese día, obra y subtarea. Devuelve si salió bien y el texto para mostrarle.</summary>
    public async Task<(bool Ok, string Mensaje)> QuitarHorasAsync(DateOnly fecha, int? obraId, int? subtareaId)
    {
        if (obraId == 0) obraId = null;
        var r = await _api.RetirarHorasAsync(fecha, obraId, subtareaId);
        if (r.SinRed) return (false, "No hay conexión con el servidor. Probá de nuevo en un rato.");
        if (!r.Ok) return (false, r.Codigo == "cargada_por_admin" ? "Esas horas las cargó o corrigió el administrador: pedile que las cambie." : "No se pudieron quitar las horas. Probá de nuevo.");
        await RefrescarHorasAsync();
        return (true, "Listo: quitaste esas horas.");
    }

    // ---- Casilla «tarea terminada»: tildar avisa al administrador; destildar retira el aviso (si todavía no lo revisó) ----
    private HashSet<int> _avisadas = [];

    /// <summary>true si el empleado ya marcó esta subtarea como terminada y el administrador todavía no la revisó.</summary>
    public bool SubtareaAvisada(int subtareaId) => _avisadas.Contains(subtareaId);

    /// <summary>Vuelve a pedir al servidor qué avisos siguen pendientes (si el administrador los resolvió, se destilda solo).</summary>
    public async Task RefrescarAvisosAsync()
    {
        var r = await _api.MisAvisosAsync();
        if (r.Ok && r.Valor is not null) _avisadas = [.. r.Valor];
    }

    /// <summary>Tilda o destilda la casilla de una subtarea. Devuelve si salió bien y el texto para mostrarle.</summary>
    public async Task<(bool Ok, string Mensaje)> MarcarTerminadaAsync(int subtareaId, bool terminada)
    {
        if (terminada)
        {
            var (ok, mensaje) = await AvisarSubtareaAsync(subtareaId);
            if (ok) _avisadas.Add(subtareaId);
            return (ok, mensaje);
        }
        var r = await _api.RetirarAvisoAsync(subtareaId);
        if (r.SinRed) return (false, "No hay conexión con el servidor. Probá de nuevo en un rato.");
        if (!r.Ok) return (false, "No se pudo retirar el aviso. Probá de nuevo.");
        _avisadas.Remove(subtareaId);
        return (true, "Listo: retiraste el aviso.");
    }

    public int PendientesSinEnviar => _store.Pendientes.Count;
    public event Action? Cambio;

    private DateTime Ahora => _time.GetUtcNow().UtcDateTime + _api.Desfase;
    private DateTime AhoraLocalReloj => _time.GetUtcNow().UtcDateTime;

    public TimeSpan Transcurrido => _actual is null ? TimeSpan.Zero : Max(TimeSpan.Zero, Ahora - _actual.InicioUtc);
    public TimeSpan DuracionInactividad => InactivoDesdeUtc is { } d ? Max(TimeSpan.Zero, Ahora - d) : TimeSpan.Zero;

    private static TimeSpan Max(TimeSpan a, TimeSpan b) => a > b ? a : b;
    private void Notificar() => Cambio?.Invoke();

    // ------------------------------------------------------------------ listas y sesión

    /// <summary>
    /// Pide al servidor la lista de empleados y obras (y la configuración). Se repite cada tanto para que los empleados u obras
    /// que crea el administrador aparezcan sin reabrir el panel. Con <paramref name="tocarConexion"/> en false no cambia el
    /// indicador «sin conexión» (que lo decide el latido del registro en curso).
    /// </summary>
    public async Task<bool> CargarListasAsync(bool tocarConexion = true)
    {
        var emp = await _api.EmpleadosAsync();
        var obras = await _api.ObrasAsync();
        var cfg = await _api.ConfigAsync();
        if (cfg.Ok && cfg.Valor is not null) _cfg = cfg.Valor;
        if (emp.Ok && emp.Valor is not null) Empleados = emp.Valor;
        if (obras.Ok && obras.Valor is not null)
        {
            Obras = obras.Valor.Select(o => new ItemLista(o.Id, o.Nombre)).ToList();
            _subtareas = obras.Valor.Where(o => o.Subtareas is { Count: > 0 }).ToDictionary(o => o.Id, o => o.Subtareas!);
        }
        if (tocarConexion) Conectado = emp.Ok || obras.Ok;
        if (Estado != EstadoPanel.SinSesion) { await RefrescarAvisosAsync(); if (EsTaller) await RefrescarHorasAsync(); }
        Notificar();
        return emp.Ok && obras.Ok;
    }

    /// <summary>Devuelve el texto del error, o null si ingresó bien.</summary>
    public async Task<string?> LoginAsync(int empleadoId, string pin)
    {
        var r = await _api.LoginAsync(empleadoId, pin);
        if (r.SinRed) return "No hay conexión con el servidor.";
        if ((int?)r.Status == 423)
        {
            var hasta = r.Prop("hastaUtc") is { ValueKind: System.Text.Json.JsonValueKind.String } p && p.TryGetDateTime(out var d)
                ? $" hasta las {d.ToLocalTime():HH:mm}" : "";
            return $"Demasiados intentos. Bloqueado{hasta}.";
        }
        if (!r.Ok || r.Valor is null) return "PIN incorrecto.";

        var login = r.Valor;
        _api.Token = login.Token;
        Conectado = true;
        SesionVencida = false;

        // Renovación de sesión del mismo empleado que está registrando: solo se renueva el token.
        if (Estado == EstadoPanel.Registrando && EmpleadoId == login.EmpleadoId)
        {
            await SincronizarPendientesAsync();
            Notificar();
            return null;
        }

        EmpleadoId = login.EmpleadoId;
        Nombre = login.Nombre;
        DebeCambiarPin = login.DebeCambiarPin;
        Estado = EstadoPanel.Pausado;
        _actual = null;
        _ultimoTick = AhoraLocalReloj;
        _store.Ajustes.EmpleadoIdUltimo = login.EmpleadoId;
        _store.GuardarAjustes();

        if (login.RegistroActivo is { } previo) await ManejarRegistroPrevioAsync(previo);
        await SincronizarPendientesAsync();
        await RefrescarAvisosAsync();
        Horas = null;
        if (EsTaller) await RefrescarHorasAsync();
        Notificar();
        return null;
    }

    private async Task ManejarRegistroPrevioAsync(RegistroDto previo)
    {
        if (string.Equals(previo.Equipo, _equipo, StringComparison.OrdinalIgnoreCase))
        {
            // El programa se cerró (o la PC se reinició) con el cronómetro andando: termina en el último aviso de vida.
            await _api.CerrarAsync(previo.Id, previo.UltimoLatidoUtc);
            Aviso = $"Tu registro anterior se cerró a las {previo.UltimoLatidoUtc.ToLocalTime():HH:mm}. Presioná Play para continuar.";
        }
        else
        {
            Aviso = $"Ya tenés un registro activo en {(string.IsNullOrEmpty(previo.Equipo) ? "otra PC" : previo.Equipo)}. Pausalo allí antes de iniciar acá.";
        }
    }

    /// <summary>Cambio de usuario: solo con el cronómetro en pausa.</summary>
    public bool CerrarSesion()
    {
        if (Estado == EstadoPanel.Registrando) return false;
        _api.Token = null;
        Estado = EstadoPanel.SinSesion;
        EmpleadoId = 0;
        Nombre = "";
        DebeCambiarPin = false;
        UltimoResumen = null;
        Notificar();
        return true;
    }

    public async Task<bool> CambiarPinAsync(string pinActual, string pinNuevo)
    {
        var r = await _api.CambiarPinAsync(pinActual, pinNuevo);
        if (r.Ok) DebeCambiarPin = false;
        Notificar();
        return r.Ok;
    }

    public async Task<ResumenDto?> ObtenerResumenAsync()
    {
        if (Estado == EstadoPanel.SinSesion) return null;
        var r = await _api.ResumenAsync();
        if (r.Ok && r.Valor is not null) UltimoResumen = r.Valor;
        else if (r.SinRed) Conectado = false;
        Notificar();
        return UltimoResumen;
    }

    // ------------------------------------------------------------------ Play / Pause / cambio de obra

    public async Task PlayAsync(int obraId, int? subtareaId = null)
    {
        if (Estado != EstadoPanel.Pausado) return;

        // Si la obra tiene subtareas, hay que elegir una (se vuelve a comprobar en el servidor).
        if (SubtareasDe(obraId).Count > 0 && (subtareaId is null || !SubtareasDe(obraId).Any(s => s.Id == subtareaId)))
        {
            Aviso = "Esta obra tiene subtareas: elegí una antes de presionar Play.";
            Notificar();
            return;
        }
        if (SubtareasDe(obraId).Count == 0) subtareaId = null;

        var id = Guid.NewGuid();
        var r = await _api.IniciarAsync(id, obraId, subtareaId, _equipo);

        if (r.Ok && r.Valor is not null)
        {
            Conectado = true;
            ComenzarTramo(r.Valor.Id, obraId, r.Valor.InicioUtc, subtareaId);
        }
        else if (r.SinRed || (int?)r.Status == 401)
        {
            // Sin conexión (o sesión vencida): se empieza igual y se guarda en esta PC para enviarlo después.
            Conectado = false;
            SesionVencida = (int?)r.Status == 401;
            var inicio = Ahora;
            ComenzarTramo(id, obraId, inicio, subtareaId);
            _store.Guardar(new PendienteLocal { Id = id, EmpleadoId = EmpleadoId, ObraId = obraId, SubtareaId = subtareaId, InicioUtc = inicio, Equipo = _equipo });
            Aviso = "Sin conexión: el registro se guarda en esta PC y se envía solo cuando vuelva.";
        }
        else if ((int?)r.Status == 409 && r.Codigo == "registro_activo")
        {
            var donde = r.Prop("equipo")?.GetString();
            Aviso = $"Ya tenés un registro activo en {(string.IsNullOrEmpty(donde) ? "otra PC" : donde)}. Pausalo allí primero.";
        }
        else if (r.Codigo is "subtarea_requerida" or "subtarea_invalida")
        {
            // El administrador cambió las subtareas de la obra mientras tanto: se actualizan las listas para que elija de nuevo.
            Aviso = "Las subtareas de esta obra cambiaron: elegí una de la lista y presioná Play de nuevo.";
            await CargarListasAsync();
        }
        else
        {
            Aviso = "No se pudo iniciar el registro (la obra ya no está disponible).";
            await CargarListasAsync();
        }
        Notificar();
    }

    private void ComenzarTramo(Guid id, int obraId, DateTime inicioUtc, int? subtareaId = null)
    {
        _actual = new Tramo { Id = id, ObraId = obraId, SubtareaId = subtareaId, InicioUtc = inicioUtc };
        Estado = EstadoPanel.Registrando;
        _ultimoLatido = AhoraLocalReloj;
        _ultimoTick = AhoraLocalReloj;
        _inactivo = false;
        PreguntarInactividad = false;
        InactivoDesdeUtc = null;
    }

    /// <summary>Pause. finUtc opcional (p. ej. inicio de la inactividad o último aviso antes de una suspensión).</summary>
    public async Task PauseAsync(DateTime? finUtc = null, string? aviso = null)
    {
        if (Estado != EstadoPanel.Registrando || _actual is null) return;
        var t = _actual;
        var ahora = Ahora;
        var fin = finUtc ?? ahora;
        if (fin > ahora) fin = ahora;
        if (fin < t.InicioUtc) fin = t.InicioUtc;

        _actual = null;
        Estado = EstadoPanel.Pausado;
        _inactivo = false;
        PreguntarInactividad = false;
        InactivoDesdeUtc = null;
        if (aviso is not null) Aviso = aviso;

        if (_store.Pendiente(t.Id) is { } pend)
        {
            pend.FinUtc = fin;
            _store.Guardar(pend);
            await SincronizarPendientesAsync();
        }
        else
        {
            var r = await _api.CerrarAsync(t.Id, fin);
            if (r.Ok && r.Valor is not null)
            {
                Conectado = true;
                // El servidor lo cortó antes por falta de latidos, pero el panel siguió contando: se extiende.
                if (r.Valor.Estado == "cortado" && r.Valor.FinUtc is { } finServidor && fin - finServidor > TimeSpan.FromSeconds(_cfg.LatidoSegundos * 1.5))
                    await EncolarYSincronizarAsync(t, fin);
            }
            else if (r.SinRed || (int?)r.Status is 401 or 404)
            {
                if (r.SinRed) Conectado = false;
                if ((int?)r.Status == 401) { SesionVencida = true; Conectado = false; }
                await EncolarYSincronizarAsync(t, fin);
            }
        }
        Notificar();
    }

    private async Task EncolarYSincronizarAsync(Tramo t, DateTime fin)
    {
        _store.Guardar(new PendienteLocal { Id = t.Id, EmpleadoId = EmpleadoId, ObraId = t.ObraId, SubtareaId = t.SubtareaId, InicioUtc = t.InicioUtc, FinUtc = fin, Equipo = _equipo });
        await SincronizarPendientesAsync();
    }

    /// <summary>
    /// Cambio de obra o de subtarea con el cronómetro andando (la interfaz ya pidió confirmación): cierra el tramo y abre otro sin huecos.
    /// </summary>
    public async Task CambiarObraAsync(int obraId, int? subtareaId = null)
    {
        if (Estado != EstadoPanel.Registrando || _actual is null) return;
        if (SubtareasDe(obraId).Count == 0) subtareaId = null;
        if (obraId == _actual.ObraId && subtareaId == _actual.SubtareaId) return;
        if (SubtareasDe(obraId).Count > 0 && (subtareaId is null || !SubtareasDe(obraId).Any(s => s.Id == subtareaId)))
        {
            Aviso = "Esta obra tiene subtareas: elegí una.";
            Notificar();
            return;
        }

        var id = Guid.NewGuid();
        var ahoraAntes = Ahora;
        var anterior = _actual;
        var r = _store.Pendiente(anterior.Id) is null ? await _api.CambiarObraAsync(id, obraId, subtareaId, _equipo) : null;

        if (r is { Ok: true, Valor: not null })
        {
            Conectado = true;
            ComenzarTramo(r.Valor.Id, obraId, r.Valor.InicioUtc, subtareaId);
        }
        else if (r is { SinRed: true } or { Status: System.Net.HttpStatusCode.Unauthorized })
        {
            // Sin red: se cierra el tramo anterior y se abre uno nuevo, ambos guardados en esta PC.
            Conectado = false;
            SesionVencida = r.Status == System.Net.HttpStatusCode.Unauthorized;
            await CerrarYAbrirLocalAsync(anterior, id, obraId, subtareaId, ahoraAntes);
        }
        else
        {
            // El servidor no tiene el registro abierto (lo cortó, o se empezó sin conexión): se pausa y se inicia de nuevo.
            await PauseAsync();
            await PlayAsync(obraId, subtareaId);
            return;
        }
        Notificar();
    }

    private async Task CerrarYAbrirLocalAsync(Tramo anterior, Guid nuevoId, int obraId, int? subtareaId, DateTime ahora)
    {
        var pend = _store.Pendiente(anterior.Id) ?? new PendienteLocal
        {
            Id = anterior.Id, EmpleadoId = EmpleadoId, ObraId = anterior.ObraId, SubtareaId = anterior.SubtareaId, InicioUtc = anterior.InicioUtc, Equipo = _equipo,
        };
        pend.FinUtc = ahora;
        _store.Guardar(pend);
        _store.Guardar(new PendienteLocal { Id = nuevoId, EmpleadoId = EmpleadoId, ObraId = obraId, SubtareaId = subtareaId, InicioUtc = ahora, Equipo = _equipo });
        ComenzarTramo(nuevoId, obraId, ahora, subtareaId);
        await Task.CompletedTask;
    }

    // ------------------------------------------------------------------ latidos, sincronización y suspensión

    /// <summary>Se llama una vez por segundo desde la interfaz.</summary>
    public async Task TickAsync()
    {
        var local = AhoraLocalReloj;
        var previo = _ultimoTick;
        _ultimoTick = local;

        // Un salto grande entre ticks = la PC estuvo suspendida/hibernada: el registro termina en el último tick vivo.
        if (Estado == EstadoPanel.Registrando && previo != default && (local - previo).TotalSeconds > SegundosParaSuspension)
        {
            await PauseAsync(previo + _api.Desfase,
                $"La PC estuvo suspendida o sin respuesta desde las {(previo + (Ahora - local)).ToLocalTime():HH:mm}. El registro terminó ahí.");
            _ultimoTick = AhoraLocalReloj;
            return;
        }

        if (Estado == EstadoPanel.SinSesion || _enRed) { Notificar(); return; }
        _enRed = true;
        try { await MantenimientoAsync(local); }
        finally { _enRed = false; }
        Notificar();
    }

    private async Task MantenimientoAsync(DateTime local)
    {
        if (Estado == EstadoPanel.Registrando && _actual is { } t)
        {
            if ((local - _ultimoLatido).TotalSeconds < _cfg.LatidoSegundos) return;
            _ultimoLatido = local;

            if (_store.Pendiente(t.Id) is not null)
            {
                await SincronizarPendientesAsync(); // el servidor todavía no conoce este registro
                return;
            }

            var r = await _api.LatidoAsync(t.Id);
            if (r.Ok)
            {
                Conectado = true;
                SesionVencida = false;
                if (_store.Pendientes.Count > 0) await SincronizarPendientesAsync();
            }
            else if (r.SinRed) Conectado = false;
            else if ((int?)r.Status == 401) { SesionVencida = true; Conectado = false; }
            else if ((int?)r.Status == 409) await ReanudarTrasCorteAsync(t);
            else if ((int?)r.Status == 404)
            {
                _store.Guardar(new PendienteLocal { Id = t.Id, EmpleadoId = EmpleadoId, ObraId = t.ObraId, SubtareaId = t.SubtareaId, InicioUtc = t.InicioUtc, Equipo = _equipo });
                await SincronizarPendientesAsync();
            }
        }
        else if (Estado == EstadoPanel.Pausado && _store.Pendientes.Count > 0 && (local - _ultimaSync).TotalSeconds >= SegundosEntreSincronizaciones)
        {
            _ultimaSync = local;
            await SincronizarPendientesAsync();
        }
    }

    /// <summary>El servidor cortó el registro (sin latidos) pero el panel siguió contando: se extiende y se continúa en un tramo nuevo.</summary>
    private async Task ReanudarTrasCorteAsync(Tramo t)
    {
        var fin = Ahora;
        var s = await _api.SincronizarAsync([new SincronizarItem(t.Id, t.ObraId, t.InicioUtc, fin, _equipo, t.SubtareaId)]);
        if (!s.Ok)
        {
            Conectado = !s.SinRed;
            return; // se reintenta en el próximo latido
        }

        var nuevoId = Guid.NewGuid();
        var r = await _api.IniciarAsync(nuevoId, t.ObraId, t.SubtareaId, _equipo);
        if (r.Ok && r.Valor is not null)
        {
            Conectado = true;
            ComenzarTramo(r.Valor.Id, t.ObraId, r.Valor.InicioUtc, t.SubtareaId);
        }
        else if (r.SinRed || r.Codigo is "subtarea_requerida" or "subtarea_invalida")
        {
            // Sin red (o el administrador cambió las subtareas mientras tanto): se sigue contando y se envía después; lo que no
            // coincida queda marcado para revisión en el servidor, sin perder ni un minuto.
            Conectado = !r.SinRed;
            ComenzarTramo(nuevoId, t.ObraId, fin, t.SubtareaId);
            _store.Guardar(new PendienteLocal { Id = nuevoId, EmpleadoId = EmpleadoId, ObraId = t.ObraId, SubtareaId = t.SubtareaId, InicioUtc = fin, Equipo = _equipo });
        }
        else
        {
            _actual = null;
            Estado = EstadoPanel.Pausado;
            Aviso = "Se cortó la conexión y ahora tenés un registro activo en otra PC. Este se cerró.";
        }
    }

    public async Task SincronizarPendientesAsync()
    {
        if (_api.Token is null || EmpleadoId == 0) return;
        var lista = _store.PendientesDe(EmpleadoId).ToList();
        if (lista.Count == 0) return;

        var r = await _api.SincronizarAsync(lista.Select(p => new SincronizarItem(p.Id, p.ObraId, p.InicioUtc, p.FinUtc, p.Equipo, p.SubtareaId)).ToList());
        if (r.SinRed) { Conectado = false; return; }
        if ((int?)r.Status == 401) { SesionVencida = true; Conectado = false; return; }
        if (!r.Ok || r.Valor is null) return;

        Conectado = true;
        SesionVencida = false;
        foreach (var res in r.Valor)
        {
            var p = lista.FirstOrDefault(x => x.Id == res.Id);
            if (p is null) continue;

            switch (res.Resultado)
            {
                case "conflicto_abierto":
                    // El empleado tiene otro registro abierto en otra PC: este se cierra ahora y se envía como cerrado.
                    p.FinUtc = Ahora;
                    _store.Guardar(p);
                    if (_actual?.Id == p.Id)
                    {
                        _actual = null;
                        Estado = EstadoPanel.Pausado;
                        Aviso = "Ya tenés un registro activo en otra PC, así que este se cerró.";
                    }
                    break;
                case "invalido":
                    _store.Rechazar(p);
                    Aviso = "Un registro guardado sin conexión no pudo enviarse; queda archivado en esta PC para revisarlo.";
                    break;
                default: // insertado, insertado_revisar, duplicado, actualizado
                    _store.Quitar(p.Id);
                    break;
            }
        }
    }

    // ------------------------------------------------------------------ inactividad

    /// <summary>La interfaz informa cada pocos segundos cuánto hace que no hay mouse/teclado.</summary>
    public void ReportarInactividad(TimeSpan inactivo)
    {
        if (Estado != EstadoPanel.Registrando)
        {
            if (_inactivo || PreguntarInactividad) { _inactivo = false; PreguntarInactividad = false; InactivoDesdeUtc = null; }
            return;
        }

        var umbral = TimeSpan.FromMinutes(_cfg.InactividadMinutos);
        if (!_inactivo && inactivo >= umbral)
        {
            _inactivo = true;
            InactivoDesdeUtc = Ahora - inactivo;
            Notificar();
        }
        else if (_inactivo && !PreguntarInactividad && inactivo < TimeSpan.FromSeconds(15))
        {
            PreguntarInactividad = true; // el empleado volvió: hay que preguntarle qué hacer con ese tiempo
            Notificar();
        }
    }

    /// <summary>descontar = pausa el registro en el momento en que empezó la inactividad; si no, el tiempo cuenta como trabajo.</summary>
    public async Task ResolverInactividadAsync(bool descontar)
    {
        var desde = InactivoDesdeUtc;
        PreguntarInactividad = false;
        _inactivo = false;
        InactivoDesdeUtc = null;
        if (descontar && desde is { } d)
            await PauseAsync(d, "Se pausó el registro y se descontó el tiempo inactivo.");
        Notificar();
    }

    /// <summary>Al apagar Windows o salir: pausa lo más rápido posible.</summary>
    public Task SalirAsync() => PauseAsync();
}
