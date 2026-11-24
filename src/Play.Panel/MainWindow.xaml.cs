using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Media;
using System.Windows.Threading;
using Play.Client;

namespace Play.Panel;

public partial class MainWindow : Window
{
    private static readonly Brush Verde = Pincel("#2E9E4F");
    private static readonly Brush Naranja = Pincel("#F0A030");
    private static readonly Brush Gris = Pincel("#808080");
    private static readonly Brush Rojo = Pincel("#E05050");
    private static readonly Geometry GeoPlay = Geometry.Parse("M0,0 L11,7 L0,14 Z");
    private static readonly Geometry GeoPause = Geometry.Parse("M0,0 H4 V14 H0 Z M7,0 H11 V14 H7 Z");

    private readonly PanelController _c;
    private readonly LocalStore _store;
    private readonly bool _demo;
    private readonly DispatcherTimer _timer = new() { Interval = TimeSpan.FromSeconds(1) };
    private readonly DispatcherTimer _guardarPosicion = new() { Interval = TimeSpan.FromMilliseconds(600) };

    private bool _actualizando;
    private bool _dialogoAbierto;
    private bool _saliendo;
    private bool _recargando;
    private bool _resumenEnCurso;
    private string? _pinUsado;
    private DateTime _avisoHastaUtc;
    private DateTime _ultimoIntentoListas = DateTime.MinValue;
    private DateTime _ultimaCargaListas = DateTime.MinValue;
    private DateTime _ultimoResumen = DateTime.MinValue;

    private readonly bool _sinRegistro;

    /// <param name="demo">Interfaz con datos de ejemplo (capturas).</param>
    /// <param name="sinRegistro">No toca el registro de Windows (pruebas con --datos).</param>
    private readonly ActualizadorPanel? _actualizador;
    private bool _comprobandoActualizacion;

    public MainWindow(PanelController controlador, LocalStore store, bool demo = false, bool sinRegistro = false, ActualizadorPanel? actualizador = null)
    {
        InitializeComponent();
        _c = controlador;
        _store = store;
        _demo = demo;
        _sinRegistro = sinRegistro || demo;
        _actualizador = demo ? null : actualizador;

        _c.Cambio += Actualizar;
        Loaded += async (_, _) => await IniciarAsync();
        LocationChanged += (_, _) => { _guardarPosicion.Stop(); _guardarPosicion.Start(); };
        _guardarPosicion.Tick += (_, _) => { _guardarPosicion.Stop(); GuardarPosicion(); };
        _timer.Tick += async (_, _) => await TickAsync();
        // Cerrar la ventana (Alt+F4) solo la contrae: el registro sigue corriendo.
        Closing += (_, e) =>
        {
            if (_saliendo) return;
            e.Cancel = true;
            Contraer(true);
        };
    }

    public PanelController Controlador => _c;

    /// <summary>
    /// Se llama cuando el empleado vuelve a abrir Play.exe y el panel ya estaba corriendo: se muestra expandido y se refrescan las listas.
    /// </summary>
    public async void MostrarYRefrescar()
    {
        Contraer(false);
        Topmost = false;
        Topmost = true;
        Activate();
        await RecargarListasAsync(silencioso: true);
    }

    private static Brush Pincel(string hex) => (Brush)new BrushConverter().ConvertFromString(hex)!;

    // ================================================================ arranque y posición

    private async Task IniciarAsync()
    {
        ColocarVentana();
        Contraer(_store.Ajustes.Contraida, guardar: false);
        if (!_sinRegistro)
        {
            if (!_store.Ajustes.PrimeraEjecucionHecha)
            {
                Native.InicioConWindows(true); // por defecto el panel inicia con Windows (en pausa)
                _store.Ajustes.PrimeraEjecucionHecha = true;
                _store.GuardarAjustes();
            }
            MnuInicio.IsChecked = Native.InicioConWindows();
        }
        await RecargarListasAsync();
        _timer.Start();
        Actualizar();

        if (!_demo)
        {
            App.ConfirmarActualizacion(t => MostrarAviso(t, 20)); // si este arranque viene de una actualización
            await ComprobarActualizacionAsync(alArrancar: true);
        }
    }

    public void MostrarAvisoPublico(string texto) => MostrarAviso(texto, 20);

    /// <summary>Busca (y si corresponde instala) una versión nueva del programa. Casi siempre vuelve enseguida sin hacer nada.</summary>
    private async Task ComprobarActualizacionAsync(bool alArrancar)
    {
        if (_actualizador is null || _comprobandoActualizacion) return;
        _comprobandoActualizacion = true;
        try { await _actualizador.ComprobarAsync(alArrancar); }
        finally { _comprobandoActualizacion = false; }
    }

    private void ColocarVentana()
    {
        var area = SystemParameters.WorkArea;
        double x = area.Right - ActualWidth - 12, y = area.Top + 12; // esquina superior derecha
        if (_store.Ajustes is { X: { } sx, Y: { } sy } && EstaVisible(sx, sy)) { x = sx; y = sy; }
        Left = x;
        Top = y;
    }

    private bool EstaVisible(double x, double y) =>
        x > SystemParameters.VirtualScreenLeft - 20 && x < SystemParameters.VirtualScreenLeft + SystemParameters.VirtualScreenWidth - 40 &&
        y > SystemParameters.VirtualScreenTop - 5 && y < SystemParameters.VirtualScreenTop + SystemParameters.VirtualScreenHeight - 30;

    private void GuardarPosicion()
    {
        if (_demo) return;
        _store.Ajustes.X = Left;
        _store.Ajustes.Y = Top;
        _store.GuardarAjustes();
    }

    private void Marco_MouseLeftButtonDown(object sender, MouseButtonEventArgs e)
    {
        if (e.ButtonState != MouseButtonState.Pressed) return;
        try { DragMove(); } catch (InvalidOperationException) { }
    }

    // ================================================================ contraer / expandir

    private void Contraer(bool contraer, bool guardar = true)
    {
        var derecha = Left + ActualWidth; // la esquina derecha se mantiene fija al cambiar de tamaño
        Expandido.Visibility = contraer ? Visibility.Collapsed : Visibility.Visible;
        Contraido.Visibility = contraer ? Visibility.Visible : Visibility.Collapsed;
        UpdateLayout();
        if (IsLoaded && ActualWidth > 0) Left = derecha - ActualWidth;
        if (guardar && !_demo)
        {
            _store.Ajustes.Contraida = contraer;
            _store.GuardarAjustes();
        }
    }

    public void AplicarContraccion(bool contraer) => Contraer(contraer, guardar: false);
    private void BtnContraer_Click(object sender, RoutedEventArgs e) => Contraer(true);
    private void BtnExpandir_Click(object sender, RoutedEventArgs e) => Contraer(false);

    // ================================================================ listas y estado

    /// <summary>
    /// Vuelve a pedir usuarios y obras al servidor. «silencioso» = refresco automático: no avisa si falla ni toca el indicador de conexión,
    /// y solo cambia los menús si la lista realmente cambió (para no cerrarlos ni perder la selección).
    /// </summary>
    private async Task RecargarListasAsync(bool silencioso = false)
    {
        if (_recargando) return;
        _recargando = true;
        try
        {
            var ok = await _c.CargarListasAsync(tocarConexion: !silencioso);
            _ultimaCargaListas = DateTime.UtcNow;
            _actualizando = true;
            try
            {
                ElegirAreaInicial();
                var delArea = EmpleadosDelArea();
                if (CmbUsuario.ItemsSource is not List<ItemLista> usuariosActuales || !usuariosActuales.SequenceEqual(delArea))
                {
                    var u = (CmbUsuario.SelectedItem as ItemLista)?.Id ?? (_c.EmpleadoId != 0 ? _c.EmpleadoId : _store.Ajustes.EmpleadoIdUltimo);
                    CmbUsuario.ItemsSource = delArea;
                    CmbUsuario.SelectedItem = delArea.FirstOrDefault(x => x.Id == u);
                }
                var menuObras = ObrasDelMenu();
                if (CmbObra.ItemsSource is not List<ItemLista> obrasActuales || !obrasActuales.SequenceEqual(menuObras))
                {
                    var o = (CmbObra.SelectedItem as ItemLista)?.Id ?? _store.Ajustes.ObraIdUltima;
                    CmbObra.ItemsSource = menuObras;
                    CmbObra.SelectedItem = menuObras.FirstOrDefault(x => x.Id == o);
                }
            }
            finally { _actualizando = false; }
            if (!ok && !silencioso) MostrarAviso("No hay conexión con el servidor. Reintentando…");
        }
        finally { _recargando = false; }
        Actualizar();
    }

    // ---- Áreas (Oficina / Taller): se elige el área y después el nombre ----

    private string _areaActual = AreasEmpresa.Oficina;
    private bool _areaInicializada;

    private List<ItemLista> EmpleadosDelArea() => _c.Empleados.Where(x => AreasEmpresa.De(x) == _areaActual).ToList();

    /// <summary>
    /// La primera vez que hay datos: el área del último usuario que ingresó en esta PC; si no, la última área elegida; si no, Oficina.
    /// </summary>
    private void ElegirAreaInicial()
    {
        if (CmbArea.ItemsSource is null) CmbArea.ItemsSource = AreasEmpresa.Todas;
        if (_areaInicializada || _c.Empleados.Count == 0) return;
        var ultimo = _c.EmpleadoId != 0 ? _c.EmpleadoId : _store.Ajustes.EmpleadoIdUltimo;
        var empleado = _c.Empleados.FirstOrDefault(x => x.Id == ultimo);
        _areaActual = empleado is not null ? AreasEmpresa.De(empleado)
            : _store.Ajustes.AreaUltima is { } a && AreasEmpresa.Todas.Contains(a) ? a : AreasEmpresa.Oficina;
        CmbArea.SelectedItem = _areaActual;
        _areaInicializada = true;
    }

    private void CmbArea_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_actualizando || CmbArea.SelectedItem is not string area || area == _areaActual) return;
        if (_c.Estado == EstadoPanel.Pausado) _c.CerrarSesion(); // otra área = otra persona
        _areaActual = area;
        _store.Ajustes.AreaUltima = area;
        if (!_demo) _store.GuardarAjustes();

        _actualizando = true;
        try
        {
            CmbUsuario.ItemsSource = EmpleadosDelArea();
            CmbUsuario.SelectedItem = null;
        }
        finally { _actualizando = false; }
        TxtErrorPin.Visibility = Visibility.Collapsed;
        Actualizar();
        CmbUsuario.Focus();
    }

    private void MostrarAviso(string texto, int segundos = 15)
    {
        TxtAviso.Text = texto;
        TxtAviso.Visibility = Visibility.Visible;
        _avisoHastaUtc = DateTime.UtcNow.AddSeconds(segundos);
    }

    private static string Hms(TimeSpan t) => $"{(int)t.TotalHours:00}:{t.Minutes:00}:{t.Seconds:00}";
    private static string Hm(long segundos) { var t = TimeSpan.FromSeconds(segundos); return $"{(int)t.TotalHours}:{t.Minutes:00}"; }

    /// <summary>Refleja el estado del controlador en la pantalla.</summary>
    public void Actualizar()
    {
        _actualizando = true;
        try
        {
            var e = _c.Estado;
            var conSesion = e != EstadoPanel.SinSesion;
            var nuevoPin = conSesion && _c.DebeCambiarPin;

            PanelPin.Visibility = !conSesion && CmbUsuario.SelectedItem is not null ? Visibility.Visible : Visibility.Collapsed;
            PanelNuevoPin.Visibility = nuevoPin ? Visibility.Visible : Visibility.Collapsed;
            // El personal de Taller no usa Obra/Play: carga las horas de hoy o de ayer.
            var taller = conSesion && !nuevoPin && _c.EsTaller;
            FilaObra.Visibility = conSesion && !nuevoPin ? Visibility.Visible : Visibility.Collapsed; // Taller también elige obra y tarea
            FilaControl.Visibility = conSesion && !nuevoPin && !taller ? Visibility.Visible : Visibility.Collapsed;
            PanelHoras.Visibility = taller ? Visibility.Visible : Visibility.Collapsed;
            CmbUsuario.IsEnabled = e != EstadoPanel.Registrando;
            CmbArea.IsEnabled = e != EstadoPanel.Registrando;
            CmbObra.IsEnabled = _c.Obras.Count > 0;

            if (conSesion && (CmbUsuario.SelectedItem as ItemLista)?.Id != _c.EmpleadoId)
                CmbUsuario.SelectedItem = (CmbUsuario.ItemsSource as List<ItemLista>)?.FirstOrDefault(x => x.Id == _c.EmpleadoId);
            if (e == EstadoPanel.Registrando && _c.ObraActualId is { } oa && (CmbObra.SelectedItem as ItemLista)?.Id != oa)
                CmbObra.SelectedItem = _c.Obras.FirstOrDefault(x => x.Id == oa);
            // El menú de obras de Taller trae además «(Sin obra)»; se cambia solo si el usuario es de Taller o dejó de serlo.
            var menuObras = ObrasDelMenu();
            if (CmbObra.ItemsSource is not List<ItemLista> obrasMenu || !obrasMenu.SequenceEqual(menuObras))
            {
                var antes = (CmbObra.SelectedItem as ItemLista)?.Id;
                CmbObra.ItemsSource = menuObras;
                CmbObra.SelectedItem = menuObras.FirstOrDefault(x => x.Id == antes) ?? menuObras.FirstOrDefault(x => x.Id == _store.Ajustes.ObraIdUltima) ?? (taller ? menuObras[0] : null);
            }
            ActualizarSubtareas();
            if (taller) ActualizarHoras();

            var tiempo = Hms(_c.Transcurrido);
            TxtTiempo.Text = tiempo;
            TxtTiempoC.Text = tiempo;

            Brush color = e switch
            {
                EstadoPanel.Registrando => _c.Inactivo ? Rojo : Verde,
                EstadoPanel.Pausado => taller ? Gris : Naranja,
                _ => Gris,
            };
            Punto.Fill = color;
            PuntoC.Fill = color;
            Marco.BorderBrush = color;
            var estadoTexto = e switch
            {
                EstadoPanel.Registrando => _c.Inactivo ? "Registrando (sin actividad)" : "Registrando",
                EstadoPanel.Pausado => taller ? "Carga de horas" : "En pausa",
                _ => "Sin usuario",
            };
            Punto.ToolTip = PuntoC.ToolTip = estadoTexto;

            var registrando = e == EstadoPanel.Registrando;
            BtnPlay.Background = registrando ? Naranja : Verde;
            IconoPlay.Data = registrando ? GeoPause : GeoPlay;
            BtnPlay.ToolTip = registrando ? "Pausar" : "Play: empezar a registrar";

            // Conexión
            var sinConexion = conSesion && !_c.Conectado;
            TxtConexion.Visibility = sinConexion ? Visibility.Visible : Visibility.Collapsed;
            if (sinConexion)
            {
                Punto.Fill = PuntoC.Fill = Gris;
                TxtConexion.Text = _c.SesionVencida
                    ? "La sesión venció. Elegí tu usuario e ingresá el PIN."
                    : $"Sin conexión: se guarda en esta PC{(_c.PendientesSinEnviar > 0 ? $" ({_c.PendientesSinEnviar} pendiente)" : "")}.";
            }

            // Resumen de horas (hoy / semana)
            if (taller && _c.Horas is { } hs)
            {
                var lunes = hs.Hoy.AddDays(-(((int)hs.Hoy.DayOfWeek + 6) % 7));
                TxtResumen.Text = $"Esta semana: {Hm(hs.Cargas.Where(c => c.Fecha >= lunes).Sum(c => c.Minutos * 60L))} h";
                TxtResumen.Visibility = Visibility.Visible;
            }
            else if (conSesion && !nuevoPin && _c.UltimoResumen is { } r)
            {
                TxtResumen.Text = $"Hoy {Hm(r.Hoy.TotalSegundos)} · Semana {Hm(r.Semana.TotalSegundos)}";
                TxtResumen.Visibility = Visibility.Visible;
            }
            else TxtResumen.Visibility = Visibility.Collapsed;

            // Avisos del controlador
            if (_c.Aviso is { } aviso)
            {
                MostrarAviso(aviso);
                _c.Aviso = null;
            }
            if (TxtAviso.Visibility == Visibility.Visible && DateTime.UtcNow > _avisoHastaUtc)
                TxtAviso.Visibility = Visibility.Collapsed;

            MnuCambiarUsuario.IsEnabled = e == EstadoPanel.Pausado;
            MnuResumen.IsEnabled = conSesion;
            MnuAvisar.IsEnabled = conSesion && !nuevoPin;
        }
        finally { _actualizando = false; }

        if (_c.PreguntarInactividad && !_dialogoAbierto && !_demo) _ = PreguntarInactividadAsync();
    }

    // ================================================================ reloj de 1 segundo

    private async Task TickAsync()
    {
        if (!_demo) _c.ReportarInactividad(Native.TiempoInactivo());
        await _c.TickAsync();

        var ahora = DateTime.UtcNow;
        if (_c.Estado == EstadoPanel.SinSesion && (_c.Empleados.Count == 0 || _c.Obras.Count == 0) && (ahora - _ultimoIntentoListas).TotalSeconds >= 4)
        {
            _ultimoIntentoListas = ahora;
            await RecargarListasAsync();
        }
        if ((ahora - _ultimaCargaListas).TotalSeconds >= 30 && !_demo) await RecargarListasAsync(silencioso: true); // usuarios u obras nuevos
        if (!_demo) await ComprobarActualizacionAsync(alArrancar: false); // versión nueva del programa
        if (_c.Estado != EstadoPanel.SinSesion && !_resumenEnCurso && (ahora - _ultimoResumen).TotalSeconds >= 60)
            await RefrescarResumenAsync();
        Actualizar();
    }

    private async Task RefrescarResumenAsync()
    {
        _resumenEnCurso = true;
        _ultimoResumen = DateTime.UtcNow;
        try { await _c.ObtenerResumenAsync(); }
        finally { _resumenEnCurso = false; }
    }

    // ================================================================ usuario y PIN

    private void CmbUsuario_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_actualizando || CmbUsuario.SelectedItem is not ItemLista elegido) return;
        if (_c.Estado == EstadoPanel.Pausado && elegido.Id != _c.EmpleadoId) _c.CerrarSesion(); // cambio de usuario
        TxtErrorPin.Visibility = Visibility.Collapsed;
        Actualizar();
        if (_c.Estado == EstadoPanel.SinSesion) TxtPin.Focus();
    }

    private void Pin_PreviewTextInput(object sender, TextCompositionEventArgs e) => e.Handled = !e.Text.All(char.IsAsciiDigit);

    private async void TxtPin_PasswordChanged(object sender, RoutedEventArgs e)
    {
        if (TxtPin.Password.Length == 4) await EntrarAsync();
    }

    private async void BtnEntrar_Click(object sender, RoutedEventArgs e) => await EntrarAsync();

    private async Task EntrarAsync()
    {
        if (CmbUsuario.SelectedItem is not ItemLista usuario || TxtPin.Password.Length != 4) return;
        var pin = TxtPin.Password;
        TxtPin.Clear();
        var error = await _c.LoginAsync(usuario.Id, pin);
        if (error is not null)
        {
            TxtErrorPin.Text = error;
            TxtErrorPin.Visibility = Visibility.Visible;
            TxtPin.Focus();
            return;
        }
        TxtErrorPin.Visibility = Visibility.Collapsed;
        _pinUsado = pin;
        await RefrescarResumenAsync();
        Actualizar();
        if (_c.DebeCambiarPin) TxtPinNuevo.Focus();
    }

    private async void BtnGuardarPin_Click(object sender, RoutedEventArgs e)
    {
        var nuevo = TxtPinNuevo.Password;
        string? error = null;
        if (nuevo.Length != 4) error = "El PIN debe tener 4 números.";
        else if (nuevo != TxtPinNuevo2.Password) error = "Los dos PIN no coinciden.";
        else if (nuevo == _pinUsado) error = "Elegí un PIN distinto al que te dieron.";
        else if (!await _c.CambiarPinAsync(_pinUsado ?? "", nuevo)) error = "No se pudo guardar el PIN. Probá de nuevo.";

        TxtErrorNuevo.Text = error;
        TxtErrorNuevo.Visibility = error is null ? Visibility.Collapsed : Visibility.Visible;
        if (error is null)
        {
            _pinUsado = null;
            TxtPinNuevo.Clear();
            TxtPinNuevo2.Clear();
        }
        Actualizar();
    }

    // ================================================================ obra, Play y Pause

    private async void CmbObra_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_actualizando || CmbObra.SelectedItem is not ItemLista obra) return;
        _store.Ajustes.ObraIdUltima = obra.Id;
        if (!_demo) _store.GuardarAjustes();

        if (_c.Estado == EstadoPanel.Registrando && _c.ObraActualId != obra.Id)
        {
            var actual = _c.Obras.FirstOrDefault(x => x.Id == _c.ObraActualId)?.Nombre ?? "la obra actual";
            var subs = _c.SubtareasDe(obra.Id);
            bool acepto;
            int? subtareaId = null;
            if (subs.Count == 0)
            {
                acepto = MessageBox.Show(this, $"¿Cambiar a «{obra.Nombre}»?\n\nSe cierra el registro de «{actual}» y empieza uno nuevo.",
                    "Cambiar de obra", MessageBoxButton.YesNo, MessageBoxImage.Question) == MessageBoxResult.Yes;
            }
            else
            {
                // La obra nueva tiene subtareas: se elige en el mismo cuadro de confirmación.
                (acepto, subtareaId) = Dialogos.ConfirmarCambioConSubtarea(this, actual, obra.Nombre, subs);
            }
            if (acepto) await _c.CambiarObraAsync(obra.Id, subtareaId);
        }
        _horasClave = null; // Taller: otra obra muestra lo que ya hay cargado en esa obra
        Actualizar(); // si dijo que no, vuelve a mostrar la obra actual; en pausa, arma la lista de subtareas de la obra elegida
    }

    private async void CmbSubtarea_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_actualizando || CmbSubtarea.SelectedItem is not ItemLista sub) return;
        _store.Ajustes.SubtareaIdUltima = sub.Id;
        if (!_demo) _store.GuardarAjustes();

        // Con el cronómetro andando, cambiar de subtarea (misma obra) es como cambiar de obra: se cierra un registro y se abre otro.
        if (_c.Estado == EstadoPanel.Registrando && CmbObra.SelectedItem is ItemLista obra && obra.Id == _c.ObraActualId && _c.SubtareaActualId != sub.Id)
        {
            var r = MessageBox.Show(this, $"¿Cambiar a la subtarea «{sub.Nombre}»?\n\nSe cierra el registro actual y empieza uno nuevo.",
                "Cambiar de subtarea", MessageBoxButton.YesNo, MessageBoxImage.Question);
            if (r == MessageBoxResult.Yes) await _c.CambiarObraAsync(obra.Id, sub.Id);
            Actualizar(); // si dijo que no, vuelve a mostrar la subtarea actual
        }
        else if (_c.EsTaller)
        {
            _horasClave = null; // Taller: otra tarea muestra lo que ya hay cargado en esa tarea
            Actualizar();
        }
    }

    /// <summary>Muestra u oculta el menú de subtarea según la obra elegida y lo mantiene en sintonía con el registro en curso.</summary>
    private void ActualizarSubtareas()
    {
        var obra = CmbObra.SelectedItem as ItemLista;
        var subs = obra is null ? [] : _c.SubtareasDe(obra.Id);
        var anteriorId = (CmbSubtarea.SelectedItem as ItemLista)?.Id;

        var estabaActualizando = _actualizando;
        _actualizando = true;
        try
        {
            if (CmbSubtarea.ItemsSource is not List<ItemLista> actuales || !actuales.SequenceEqual(subs)) CmbSubtarea.ItemsSource = subs;

            ItemLista? elegida;
            if (_c.Estado == EstadoPanel.Registrando && obra?.Id == _c.ObraActualId)
                elegida = subs.FirstOrDefault(x => x.Id == _c.SubtareaActualId);
            else
                elegida = subs.FirstOrDefault(x => x.Id == anteriorId)
                    ?? (obra?.Id == _store.Ajustes.ObraIdUltima ? subs.FirstOrDefault(x => x.Id == _store.Ajustes.SubtareaIdUltima) : null);
            if (!Equals(CmbSubtarea.SelectedItem, elegida)) CmbSubtarea.SelectedItem = elegida;
        }
        finally { _actualizando = estabaActualizando; }

        FilaSubtarea.Visibility = subs.Count > 0 && FilaObra.Visibility == Visibility.Visible ? Visibility.Visible : Visibility.Collapsed;

        // La casilla vale para la subtarea elegida; refleja si ya avisó (y el administrador todavía no lo revisó).
        var sel = CmbSubtarea.SelectedItem as ItemLista;
        ChkTerminada.Visibility = FilaSubtarea.Visibility == Visibility.Visible && sel is not null ? Visibility.Visible : Visibility.Collapsed;
        if (sel is not null && !_chkEnCurso) ChkTerminada.IsChecked = _c.SubtareaAvisada(sel.Id);
    }

    // ================================================================ horas de Taller

    private sealed record DiaItem(DateOnly Fecha, string Texto);

    private DateOnly? _horasHoy;                       // «hoy» con el que se armó el menú de días
    private (DateOnly Dia, int Obra, int Sub)? _horasClave; // día, obra y tarea para los que está escrito el cuadro de horas (para no pisar lo que se tipea)
    private bool _guardandoHoras;

    private static string TextoDia(string prefijo, DateOnly f)
    {
        System.Globalization.CultureInfo cultura;
        try { cultura = new System.Globalization.CultureInfo("es-AR"); } catch (System.Globalization.CultureNotFoundException) { cultura = System.Globalization.CultureInfo.CurrentCulture; }
        return $"{prefijo} · {f.ToString("ddd dd/MM", cultura)}";
    }

    /// <summary>Las obras del menú: las de siempre, y para el personal de Taller además «(Sin obra)» (trabajo general).</summary>
    private List<ItemLista> ObrasDelMenu() => _c.EsTaller && _c.Estado != EstadoPanel.SinSesion ? _c.ObrasParaCarga : _c.Obras;

    private static string NombreDeLinea(CargaDto c) => c.Obra is null ? "Trabajo general" : c.Subtarea is null ? c.Obra : $"{c.Obra} › {c.Subtarea}";

    /// <summary>Refleja las cargas del servidor en el menú de día, el cuadro de horas y el texto de abajo.</summary>
    private void ActualizarHoras()
    {
        if (_c.Horas is not { } h)
        {
            TxtHorasInfo.Text = "Cargando…";
            BtnGuardarHoras.IsEnabled = false;
            BtnQuitarHoras.Visibility = Visibility.Collapsed;
            return;
        }
        if (_horasHoy != h.Hoy)
        {
            _horasHoy = h.Hoy;
            var dias = new List<DiaItem> { new(h.Hoy, TextoDia("Hoy", h.Hoy)), new(h.Hoy.AddDays(-1), TextoDia("Ayer", h.Hoy.AddDays(-1))) };
            var anterior = (CmbDia.SelectedItem as DiaItem)?.Fecha;
            CmbDia.ItemsSource = dias;
            CmbDia.SelectedItem = dias.FirstOrDefault(d => d.Fecha == anterior) ?? dias[0];
            _horasClave = null;
        }
        if (CmbDia.SelectedItem is not DiaItem dia) return;

        var obra = (CmbObra.SelectedItem as ItemLista)?.Id ?? 0;
        var sub = (CmbSubtarea.SelectedItem as ItemLista)?.Id ?? 0;
        var delDia = h.Cargas.Where(c => c.Fecha == dia.Fecha).ToList();
        var linea = delDia.FirstOrDefault(c => (c.ObraId ?? 0) == obra && (c.SubtareaId ?? 0) == sub);
        var deAdmin = linea?.Origen == "admin";
        var faltaTarea = obra != 0 && _c.SubtareasDe(obra).Count > 0 && sub == 0; // la obra tiene subtareas y todavía no eligió una

        var clave = (dia.Fecha, obra, sub);
        if (_horasClave != clave)
        {
            _horasClave = clave;
            TxtHoras.Text = linea is null ? "" : Hm(linea.Minutos * 60L);
        }
        TxtHoras.IsEnabled = BtnGuardarHoras.IsEnabled = !deAdmin && !_guardandoHoras && !faltaTarea;
        BtnQuitarHoras.Visibility = linea is not null && !deAdmin ? Visibility.Visible : Visibility.Collapsed;

        var texto = new System.Text.StringBuilder();
        texto.Append(faltaTarea ? "Elegí la tarea para cargar las horas."
            : linea is null ? "Todavía no cargaste horas en esta tarea."
            : deAdmin ? $"Esta tarea: {Hm(linea.Minutos * 60L)} h (la cargó o corrigió el administrador)."
            : $"Esta tarea: {Hm(linea.Minutos * 60L)} h. Podés corregirla.");
        if (delDia.Count > 0)
        {
            texto.Append($"\nEse día: {Hm(delDia.Sum(c => c.Minutos * 60L))} h en total");
            foreach (var c in delDia.Take(5)) texto.Append($"\n· {NombreDeLinea(c)}: {Hm(c.Minutos * 60L)}");
            if (delDia.Count > 5) texto.Append($"\n· y {delDia.Count - 5} más…");
        }
        TxtHorasInfo.Text = texto.ToString();
    }

    private void CmbDia_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (_actualizando) return;
        _horasClave = null; // elegir otro día muestra lo que ya hay cargado para ese día
        ActualizarHoras();
    }

    private void TxtHoras_KeyDown(object sender, System.Windows.Input.KeyEventArgs e)
    {
        if (e.Key == System.Windows.Input.Key.Enter && BtnGuardarHoras.IsEnabled) { BtnGuardarHoras_Click(sender, e); e.Handled = true; }
    }

    private async void BtnGuardarHoras_Click(object sender, RoutedEventArgs e)
    {
        if (CmbDia.SelectedItem is not DiaItem dia) return;
        if (!PanelController.TryParseHoras(TxtHoras.Text, out var minutos))
        {
            MostrarAviso("Escribí las horas, por ejemplo 8, 7,5 o 7:30 (entre 1 minuto y 24 horas).", 8);
            return;
        }
        var obra = (CmbObra.SelectedItem as ItemLista)?.Id ?? 0;
        var sub = (CmbSubtarea.SelectedItem as ItemLista)?.Id ?? 0;
        _guardandoHoras = true;
        BtnGuardarHoras.IsEnabled = false;
        try
        {
            var (ok, mensaje) = await _c.CargarHorasAsync(dia.Fecha, minutos, obra == 0 ? null : obra, sub == 0 ? null : sub);
            MostrarAviso(mensaje, 6);
            if (ok) _horasClave = null; // vuelve a escribir el valor guardado, ya normalizado (p. ej. «7,5» → «7:30»)
        }
        finally { _guardandoHoras = false; }
        Actualizar();
    }

    private async void BtnQuitarHoras_Click(object sender, RoutedEventArgs e)
    {
        if (CmbDia.SelectedItem is not DiaItem dia) return;
        var obra = (CmbObra.SelectedItem as ItemLista)?.Id ?? 0;
        var sub = (CmbSubtarea.SelectedItem as ItemLista)?.Id ?? 0;
        if (MessageBox.Show(this, "¿Quitar las horas cargadas en esta tarea para ese día?", "Quitar horas", MessageBoxButton.YesNo, MessageBoxImage.Question) != MessageBoxResult.Yes) return;
        var (ok, mensaje) = await _c.QuitarHorasAsync(dia.Fecha, obra == 0 ? null : obra, sub == 0 ? null : sub);
        MostrarAviso(mensaje, 6);
        if (ok) _horasClave = null;
        Actualizar();
    }
    private bool _chkEnCurso;

    private async void ChkTerminada_Click(object sender, RoutedEventArgs e)
    {
        if (CmbSubtarea.SelectedItem is not ItemLista sub) return;
        var tildada = ChkTerminada.IsChecked == true;
        _chkEnCurso = true;
        try
        {
            var (ok, mensaje) = await _c.MarcarTerminadaAsync(sub.Id, tildada);
            if (!ok) ChkTerminada.IsChecked = !tildada; // no se pudo: vuelve a como estaba
            MostrarAviso(mensaje, 6);
        }
        finally { _chkEnCurso = false; }
    }

    private async void BtnPlay_Click(object sender, RoutedEventArgs e)
    {
        if (_c.Estado == EstadoPanel.Pausado)
        {
            if (CmbObra.SelectedItem is not ItemLista obra) { MostrarAviso("Elegí una obra antes de presionar Play.", 6); return; }
            var subtarea = CmbSubtarea.SelectedItem as ItemLista;
            if (_c.SubtareasDe(obra.Id).Count > 0 && subtarea is null) { MostrarAviso("Esta obra tiene subtareas: elegí una antes de presionar Play.", 6); CmbSubtarea.Focus(); return; }
            await _c.PlayAsync(obra.Id, subtarea?.Id);
        }
        else if (_c.Estado == EstadoPanel.Registrando)
        {
            await _c.PauseAsync();
        }
        await RefrescarResumenAsync();
        Actualizar();
    }

    // ================================================================ inactividad

    private async Task PreguntarInactividadAsync()
    {
        _dialogoAbierto = true;
        try
        {
            var desde = _c.InactivoDesdeUtc?.ToLocalTime();
            var descontar = Dialogos.PreguntarInactividad(_c.DuracionInactividad, desde);
            await _c.ResolverInactividadAsync(descontar);
        }
        finally { _dialogoAbierto = false; }
        Actualizar();
    }

    // ================================================================ menú contextual y salida

    private void MnuResumen_Click(object sender, RoutedEventArgs e)
    {
        if (_c.EsTaller)
        {
            var cargas = _c.Horas?.Cargas ?? [];
            var texto = cargas.Count == 0 ? "Todavía no cargaste horas." : string.Join("\n", cargas.Select(c => $"  {c.Fecha:dd/MM/yyyy} · {NombreDeLinea(c)}: {Hm(c.Minutos * 60L)} h"));
            MessageBox.Show(this, "Horas cargadas (últimos 14 días):\n\n" + texto, $"Mis horas · {_c.Nombre}", MessageBoxButton.OK, MessageBoxImage.Information);
            return;
        }
        var r = _c.UltimoResumen;
        if (r is null) { MessageBox.Show(this, "Todavía no hay datos de horas.", "Mi resumen"); return; }
        static string Lineas(PeriodoResumen p) => p.PorObra.Count == 0 ? "  (sin registros)\n" : string.Concat(p.PorObra.Select(o => $"  {o.Obra}: {Hm(o.Segundos)}\n"));
        MessageBox.Show(this, $"Hoy: {Hm(r.Hoy.TotalSegundos)}\n{Lineas(r.Hoy)}\nEsta semana: {Hm(r.Semana.TotalSegundos)}\n{Lineas(r.Semana)}",
            $"Mi resumen · {_c.Nombre}", MessageBoxButton.OK, MessageBoxImage.Information);
    }

    private void MnuAvisar_Click(object sender, RoutedEventArgs e)
    {
        _dialogoAbierto = true; // mientras está abierto no se dispara otro cuadro (p. ej. el de inactividad)
        try { Dialogos.AvisarSubtareaTerminada(this, _c); }
        finally { _dialogoAbierto = false; }
        Actualizar();
    }

    private void MnuCambiarUsuario_Click(object sender, RoutedEventArgs e)
    {
        if (!_c.CerrarSesion()) { MostrarAviso("Pausá el registro antes de cambiar de usuario.", 6); return; }
        _actualizando = true;
        CmbUsuario.SelectedItem = null;
        _actualizando = false;
        Actualizar();
        CmbUsuario.Focus();
    }

    private void MnuInicio_Click(object sender, RoutedEventArgs e)
    {
        if (!_sinRegistro) Native.InicioConWindows(MnuInicio.IsChecked);
    }

    private void MnuServidor_Click(object sender, RoutedEventArgs e)
    {
        if (_c.Estado == EstadoPanel.Registrando) { MostrarAviso("Pausá el registro antes de cambiar el servidor.", 6); return; }
        var url = Dialogos.PedirServidor(this, _store.Ajustes.ServidorUrl);
        if (url is null || url == _store.Ajustes.ServidorUrl) return;
        _store.Ajustes.ServidorUrl = url;
        _store.GuardarAjustes();
        App.Reiniciar();
    }

    private async void MnuSalir_Click(object sender, RoutedEventArgs e)
    {
        if (_c.Estado == EstadoPanel.Registrando)
        {
            var r = MessageBox.Show(this, "Estás registrando tiempo.\n\n¿Pausar el registro y salir del programa?",
                "Salir", MessageBoxButton.YesNo, MessageBoxImage.Question);
            if (r != MessageBoxResult.Yes) return;
            await _c.SalirAsync();
        }
        Salir();
    }

    public void Salir()
    {
        _saliendo = true;
        _timer.Stop();
        Application.Current.Shutdown();
    }
}
