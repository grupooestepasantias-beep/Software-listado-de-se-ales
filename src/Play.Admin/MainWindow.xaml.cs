using System.Diagnostics;
using System.Globalization;
using System.IO;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Input;
using System.Windows.Threading;
using Microsoft.Win32;
using Play.Client;

namespace Play.Admin;

public partial class MainWindow : Window
{
    private readonly AdminApi _api;
    private readonly DispatcherTimer _timerVivo = new() { Interval = TimeSpan.FromSeconds(15) };

    private List<EmpleadoAdminDto> _empleados = [];
    private List<ObraAdminDto> _obras = [];
    private Guid? _auditoriaRegistro;
    private bool _armandoFiltros = true; // true mientras se preparan los filtros (no buscar)

    private const string TodasLasAreas = "(Todas)";
    private static readonly string[] OpcionesArea = [TodasLasAreas, AreasEmpresa.Oficina, AreasEmpresa.Taller];

    /// <summary>«Oficina» / «Taller», o null si el menú está en «(Todas)».</summary>
    private static string? AreaElegida(ComboBox cb) => cb.SelectedItem is string s && s != TodasLasAreas ? s : null;

    public MainWindow(AdminApi api, string usuario)
    {
        InitializeComponent();
        _api = api;
        TxtUsuario.Text = $"· {usuario}";
        TxtServidor.Text = App.Ajustes.ServidorUrl;
        DpDesde.SelectedDate = DateTime.Today.AddDays(-7);
        DpHasta.SelectedDate = DateTime.Today;
        DpHDesde.SelectedDate = DateTime.Today.AddDays(-30);
        DpHHasta.SelectedDate = DateTime.Today;
        DpFaDesde.SelectedDate = DateTime.Today.AddDays(-30);
        DpFaHasta.SelectedDate = DateTime.Today;
        CmbAsArea.ItemsSource = OpcionesArea; CmbAsArea.SelectedIndex = 0;
        CmbFaArea.ItemsSource = OpcionesArea; CmbFaArea.SelectedIndex = 0;
        CmbFaEstado.ItemsSource = new[] { new OpcionTxt("sin_revisar", "Sin revisar"), new OpcionTxt("injustificada", "Injustificadas"), new OpcionTxt("justificada", "Justificadas"), new OpcionTxt("", "Todas") };
        CmbFaEstado.SelectedIndex = 0;
        foreach (var cb in new[] { CmbVivoArea, CmbFArea, CmbEmpArea })
        {
            cb.ItemsSource = OpcionesArea;
            cb.SelectedIndex = 0;
        }
        _timerVivo.Tick += async (_, _) =>
        {
            if (!IsActive) return;
            if (Pestanas.SelectedItem == TabVivo) await CargarVivoAsync();
            if (Pestanas.SelectedItem == TabAvisos) await CargarAvisosAsync(); else await ActualizarContadorAvisosAsync();
        };
        Loaded += async (_, _) =>
        {
            await CargarMaestrosAsync();
            _armandoFiltros = false;
            _armandoHoras = false;
            _armandoAsistencia = false;
            await CargarVivoAsync();
            await ActualizarContadorAvisosAsync();
            _timerVivo.Start();
        };
    }

    // ================================================================ utilidades

    private void Estado(string texto) => TxtEstado.Text = texto;

    /// <summary>Espera la respuesta del servidor y, si falló, muestra el motivo en castellano y devuelve null.</summary>
    private async Task<T?> Llamar<T>(Task<ApiResult<T>> tarea) where T : class
    {
        var r = await tarea;
        if (r.Ok && r.Valor is not null) return r.Valor;
        if (r.SinRed) Dialogos.Aviso(this, "No hay conexión con el servidor. Revisá que esté encendido y que estés en la misma red.");
        else if ((int?)r.Status == 401)
        {
            Dialogos.Aviso(this, "La sesión venció. Hay que volver a ingresar.");
            App.Reiniciar();
        }
        else Dialogos.Aviso(this, Fmt.Mensaje(r.Codigo));
        return null;
    }

    private static string Quitar(string s) => s.Trim();

    private static bool TryHora(string texto, out TimeSpan hora) =>
        TimeSpan.TryParseExact(texto.Trim(), [@"h\:mm", @"hh\:mm"], CultureInfo.InvariantCulture, out hora) && hora < TimeSpan.FromDays(1);

    private static DateTime ALocalAUtc(DateTime fecha, TimeSpan hora) =>
        TimeZoneInfo.ConvertTimeToUtc(DateTime.SpecifyKind(fecha.Date + hora, DateTimeKind.Unspecified), TimeZoneInfo.Local);

    private static DateTime SinSegundos(DateTime d) => new(d.Year, d.Month, d.Day, d.Hour, d.Minute, 0, d.Kind);

    private async Task CargarMaestrosAsync()
    {
        if (await Llamar(_api.EmpleadosAsync()) is { } e) _empleados = e;
        if (await Llamar(_api.ObrasAsync()) is { } o) _obras = o;

        var obra = (CmbFObra.SelectedItem as Opcion)?.Id ?? 0;
        var opcionesO = new List<Opcion> { new(0, "(Todas)") };
        opcionesO.AddRange(_obras.Select(x => new Opcion(x.Id, x.Activa ? x.Nombre : x.Nombre + " (inactiva)")));
        _armandoFiltros = true; // rearmar los menús no debe disparar una búsqueda
        try
        {
            LlenarFiltroEmpleados();
            CmbFObra.ItemsSource = opcionesO;
            CmbFObra.SelectedItem = opcionesO.FirstOrDefault(x => x.Id == obra) ?? opcionesO[0];
        }
        finally { _armandoFiltros = false; }
    }

    /// <summary>Menú de empleados del filtro: solo los del área elegida (o todos). Conserva la selección si sigue siendo válida.</summary>
    private void LlenarFiltroEmpleados()
    {
        var antes = (CmbFEmpleado.SelectedItem as Opcion)?.Id ?? 0;
        var area = AreaElegida(CmbFArea);
        var opciones = new List<Opcion> { new(0, "(Todos)") };
        opciones.AddRange(_empleados.Where(x => area is null || x.Area == area)
            .Select(x => new Opcion(x.Id, x.Activo ? x.Nombre : x.Nombre + " (inactivo)")));
        CmbFEmpleado.ItemsSource = opciones;
        CmbFEmpleado.SelectedItem = opciones.FirstOrDefault(x => x.Id == antes) ?? opciones[0];
    }

    private void CmbFArea_Cambio(object sender, SelectionChangedEventArgs e)
    {
        if (_armandoFiltros || !IsLoaded) return;
        _armandoFiltros = true;
        try { LlenarFiltroEmpleados(); }
        finally { _armandoFiltros = false; }
        Filtro_Cambio(sender, e);
    }

    private async void CmbVivoArea_Cambio(object sender, SelectionChangedEventArgs e)
    {
        if (!IsLoaded) return;
        await CargarVivoAsync();
    }

    private async void Pestanas_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (!ReferenceEquals(e.OriginalSource, Pestanas) || !IsLoaded) return; // ignora los menús de dentro de las pestañas
        var t = Pestanas.SelectedItem;
        if (_mostrandoPines && t != TabEmpleados) OcultarPines(); // los PIN no quedan a la vista al cambiar de pestaña
        if (t == TabVivo) await CargarVivoAsync();
        else if (t == TabRegistros) await BuscarAsync(); // siempre al día: puede haber registros nuevos
        else if (t == TabHoras) await CargarHorasTabAsync();
        else if (t == TabAsistencia) await CargarAsistenciaAsync();
        else if (t == TabFaltas) await CargarFaltasAsync();
        else if (t == TabEmpleados) await CargarEmpleadosAsync();
        else if (t == TabObras) await CargarObrasAsync();
        else if (t == TabAvisos) await CargarAvisosAsync();
        else if (t == TabAdmins) await CargarAdminsAsync();
        else if (t == TabAuditoria) await CargarAuditoriaAsync();
        else if (t == TabSistema) await CargarBackupsAsync();
        if (t != TabAvisos) await ActualizarContadorAvisosAsync(); // el número de «Avisos» se pone al día al cambiar de pestaña
    }

    private void BtnSalir_Click(object sender, RoutedEventArgs e)
    {
        if (Dialogos.Confirmar(this, "¿Cerrar la sesión y salir?")) App.Reiniciar();
    }

    // ================================================================ En vivo

    private async Task CargarVivoAsync()
    {
        var r = await _api.EnVivoAsync(AreaElegida(CmbVivoArea));
        if (!r.Ok || r.Valor is null)
        {
            Estado(r.SinRed ? "Sin conexión con el servidor." : "No se pudo actualizar «En vivo».");
            return;
        }
        GridVivo.ItemsSource = r.Valor.Select(x => new FilaVivo(x)).ToList();
        TxtVivoResumen.Text = r.Valor.Count == 0 ? "Nadie está registrando horas en este momento." : $"{r.Valor.Count} persona(s) registrando ahora. Se actualiza cada 15 segundos.";
        Estado($"Actualizado a las {DateTime.Now:HH:mm:ss}");
    }

    private async void BtnVivo_Click(object sender, RoutedEventArgs e) => await CargarVivoAsync();

    // ================================================================ Registros

    private int _busquedaId;

    private FiltroAdmin FiltroActual() => new(
        Area: AreaElegida(CmbFArea),
        EmpleadoId: (CmbFEmpleado.SelectedItem as Opcion) is { Id: > 0 } e ? e.Id : null,
        ObraId: (CmbFObra.SelectedItem as Opcion) is { Id: > 0 } o ? o.Id : null,
        Desde: DpDesde.SelectedDate is { } d ? DateOnly.FromDateTime(d) : null,
        Hasta: DpHasta.SelectedDate is { } h ? DateOnly.FromDateTime(h) : null,
        Revisar: ChkRevisar.IsChecked == true ? true : null,
        Eliminados: ChkEliminados.IsChecked == true);

    /// <summary>Texto con los filtros activos, para que se vea qué se está mirando.</summary>
    private string DescribirFiltro()
    {
        var p = new List<string>();
        if (AreaElegida(CmbFArea) is { } area) p.Add($"área {area}");
        if (CmbFEmpleado.SelectedItem is Opcion { Id: > 0 } e) p.Add($"empleado «{e.Nombre}»");
        if (CmbFObra.SelectedItem is Opcion { Id: > 0 } o) p.Add($"obra «{o.Nombre}»");
        if (DpDesde.SelectedDate is { } d) p.Add($"desde el {d:dd/MM/yyyy}");
        if (DpHasta.SelectedDate is { } h) p.Add($"hasta el {h:dd/MM/yyyy}");
        if (ChkRevisar.IsChecked == true) p.Add("solo los que hay que revisar");
        return p.Count == 0 ? "sin filtros" : string.Join(" · ", p);
    }

    private async Task BuscarAsync()
    {
        var f = FiltroActual();
        if (f.Desde > f.Hasta) { Dialogos.Aviso(this, "La fecha «Desde» no puede ser posterior a «Hasta»."); return; }
        var mia = ++_busquedaId; // si el usuario cambia otro filtro mientras tanto, solo vale la última búsqueda
        if (await Llamar(_api.RegistrosAsync(f)) is not { } lista || mia != _busquedaId) return;

        GridRegistros.ItemsSource = lista.Select(x => new FilaRegistro(x)).ToList();
        var filtros = DescribirFiltro();
        if (lista.Count == 0)
        {
            TxtRegistrosResumen.Text = f.Eliminados ? $"No hay registros eliminados ({filtros})." : $"No hay registros para estos filtros: {filtros}.";
        }
        else
        {
            var aRevisar = lista.Count(x => x.RevisarAdmin);
            TxtRegistrosResumen.Text = (f.Eliminados ? $"{lista.Count} registro(s) eliminado(s)" : $"{lista.Count} registro(s) · total {Fmt.Hm(lista.Sum(x => x.Segundos))} h")
                + (aRevisar > 0 && !f.Eliminados ? $" · {aRevisar} para revisar (resaltados)" : "")
                + (lista.Count >= f.Limite ? $" · se muestran los {f.Limite} más recientes: acotá las fechas" : "")
                + $" — Filtros: {filtros}.";
        }
        Estado($"Búsqueda hecha a las {DateTime.Now:HH:mm:ss}");
    }

    private async void BtnBuscar_Click(object sender, RoutedEventArgs e) => await BuscarAsync();

    /// <summary>Cualquier cambio en un filtro busca solo (no hace falta apretar un botón).</summary>
    private async void Filtro_Cambio(object sender, RoutedEventArgs e)
    {
        if (_armandoFiltros || !IsLoaded) return;
        // «Ver eliminados» cambia lo que se puede hacer con la tabla.
        var verEliminados = ChkEliminados.IsChecked == true;
        BtnEliminar.Content = verEliminados ? "Recuperar…" : "Eliminar…";
        BtnCorregir.IsEnabled = BtnAgregar.IsEnabled = BtnExcel.IsEnabled = !verEliminados;
        ChkRevisar.IsEnabled = !verEliminados;
        await BuscarAsync();
    }

    private void BtnLimpiarFiltros_Click(object sender, RoutedEventArgs e)
    {
        _armandoFiltros = true;
        try
        {
            CmbFArea.SelectedIndex = 0;
            LlenarFiltroEmpleados();
            CmbFEmpleado.SelectedIndex = 0;
            CmbFObra.SelectedIndex = 0;
            DpDesde.SelectedDate = DateTime.Today.AddDays(-7);
            DpHasta.SelectedDate = DateTime.Today;
            ChkRevisar.IsChecked = false;
            ChkEliminados.IsChecked = false;
        }
        finally { _armandoFiltros = false; }
        Filtro_Cambio(sender, e);
    }

    private async void GridRegistros_KeyDown(object sender, KeyEventArgs e)
    {
        if (e.Key == Key.Delete && GridRegistros.SelectedItem is FilaRegistro) { e.Handled = true; await EliminarORecuperarAsync(); }
    }

    private async void BtnEliminar_Click(object sender, RoutedEventArgs e) => await EliminarORecuperarAsync();

    /// <summary>
    /// «Eliminar» no borra el registro: lo marca (con motivo, queda en el historial) y deja de contar en totales y reportes.
    /// Con «Ver eliminados» el mismo botón lo recupera.
    /// </summary>
    private async Task EliminarORecuperarAsync()
    {
        var recuperar = ChkEliminados.IsChecked == true;
        if (RegistroElegido(recuperar ? "recuperarlo" : "eliminarlo") is not { } fila) return;
        var d = fila.D;
        if (!recuperar && (d.Estado == "abierto" || d.FinUtc is null))
        {
            Dialogos.Info(this, "Ese registro todavía está en curso, no se puede eliminar. Esperá a que el empleado lo pause (o a que el sistema lo corte si la PC se apagó).");
            return;
        }

        var resumen = $"{d.Empleado} · {d.Obra}\n{d.InicioUtc.ToLocalTime():dd/MM/yyyy HH:mm} a {(d.FinUtc is { } f ? f.ToLocalTime().ToString("HH:mm") : "…")} ({Fmt.Hm(d.Segundos)} h)";
        var motivo = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 58, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        motivo.SetValue(System.Windows.Automation.AutomationProperties.AutomationIdProperty, "TxtMotivo");
        var ok = Dialogos.Formulario(this, recuperar ? "Recuperar registro" : "Eliminar registro",
            new List<(string, FrameworkElement)> { ("Motivo", motivo) },
            () => string.IsNullOrWhiteSpace(motivo.Text) ? "Escribí el motivo: queda registrado en el historial de cambios." : null,
            aceptar: recuperar ? "Recuperar" : "Eliminar", ancho: 480,
            intro: recuperar
                ? $"{resumen}\n\nVuelve a contar en los totales y reportes."
                : $"{resumen}\n\nDeja de contar en totales y reportes. No se borra: queda en el historial de cambios y se puede recuperar con «Ver eliminados».");
        if (!ok) return;

        var r = recuperar ? await Llamar(_api.RecuperarRegistroAsync(d.Id, motivo.Text.Trim())) : await Llamar(_api.EliminarRegistroAsync(d.Id, motivo.Text.Trim()));
        if (r is null) return;
        await BuscarAsync();
        Estado(recuperar ? "Registro recuperado." : "Registro eliminado. Se puede recuperar desde «Ver eliminados».");
    }

    private FilaRegistro? RegistroElegido(string accion)
    {
        if (GridRegistros.SelectedItem is FilaRegistro { EsCarga: true })
        {
            // Las horas cargadas por Taller figuran acá para verlas junto con el resto, pero se corrigen en su propia pestaña.
            Dialogos.Info(this, "Esa fila son horas cargadas a mano por el personal de Taller: se corrigen, eliminan o recuperan en la pestaña «Horas de Taller».");
            Pestanas.SelectedItem = TabHoras;
            return null;
        }
        if (GridRegistros.SelectedItem is FilaRegistro f) return f;
        Dialogos.Info(this, $"Elegí primero un registro de la tabla para {accion}.");
        return null;
    }

    private async void GridRegistros_MouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (ChkEliminados.IsChecked != true && GridRegistros.SelectedItem is FilaRegistro && e.OriginalSource is DependencyObject d && ItemsControl.ContainerFromElement(GridRegistros, d) is DataGridRow)
            await CorregirAsync();
    }

    private async void BtnCorregir_Click(object sender, RoutedEventArgs e) => await CorregirAsync();

    private async Task CorregirAsync()
    {
        if (RegistroElegido("corregirlo") is not { } fila) return;
        var d = fila.D;
        if (d.Estado == "abierto" || d.FinUtc is null) { Dialogos.Info(this, "Ese registro todavía está en curso. Esperá a que el empleado lo pause para poder corregirlo."); return; }

        var iniL = d.InicioUtc.ToLocalTime();
        var finL = d.FinUtc.Value.ToLocalTime();
        var obras = _obras.ToList();
        var cmbObra = new ComboBox { ItemsSource = obras, DisplayMemberPath = "Nombre", SelectedItem = obras.FirstOrDefault(o => o.Id == d.ObraId) };

        // Subtarea: depende de la obra elegida (si se cambia la obra, se vuelve a cargar la lista).
        var cmbSub = new ComboBox { DisplayMemberPath = "Nombre" };
        async Task LlenarSubtareasAsync(int obraId)
        {
            var todas = await SubtareasDeObraAsync(obraId);
            var opciones = new List<Opcion> { new(0, todas.Any(s => s.Activa) ? "(sin subtarea)" : "(la obra no tiene subtareas)") };
            opciones.AddRange(todas.Where(s => s.Activa || s.Id == d.SubtareaId).Select(s => new Opcion(s.Id, s.Terminada ? s.Nombre + " (terminada)" : s.Activa ? s.Nombre : s.Nombre + " (inactiva)")));
            cmbSub.ItemsSource = opciones;
            cmbSub.SelectedItem = (obraId == d.ObraId ? opciones.FirstOrDefault(o => o.Id == d.SubtareaId) : null) ?? opciones[0];
            cmbSub.IsEnabled = opciones.Count > 1;
        }
        await LlenarSubtareasAsync(d.ObraId);
        cmbObra.SelectionChanged += async (_, _) => { if (cmbObra.SelectedItem is ObraAdminDto o) await LlenarSubtareasAsync(o.Id); };
        var fIni = new DatePicker { SelectedDate = iniL.Date };
        var hIni = new TextBox { Text = iniL.ToString("HH:mm"), Width = 70, HorizontalAlignment = HorizontalAlignment.Left };
        var fFin = new DatePicker { SelectedDate = finL.Date };
        var hFin = new TextBox { Text = finL.ToString("HH:mm"), Width = 70, HorizontalAlignment = HorizontalAlignment.Left };
        var motivo = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 58, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };

        DateTime nuevoIni = default, nuevoFin = default;
        var ok = Dialogos.Formulario(this, $"Corregir registro de {d.Empleado}", new List<(string, FrameworkElement)>
        {
            ("Obra", cmbObra), ("Subtarea", cmbSub), ("Fecha de inicio", fIni), ("Hora de inicio (HH:mm)", hIni), ("Fecha de fin", fFin), ("Hora de fin (HH:mm)", hFin),
            ("Motivo del cambio", motivo),
        }, () =>
        {
            if (cmbObra.SelectedItem is null) return "Elegí la obra.";
            if (fIni.SelectedDate is null || fFin.SelectedDate is null) return "Elegí las fechas.";
            if (!TryHora(hIni.Text, out var ti) || !TryHora(hFin.Text, out var tf)) return "Escribí las horas con el formato HH:mm (por ejemplo 08:30).";
            nuevoIni = fIni.SelectedDate.Value.Date + ti;
            nuevoFin = fFin.SelectedDate.Value.Date + tf;
            if (nuevoFin <= nuevoIni) return "La hora de fin tiene que ser posterior a la de inicio.";
            if (string.IsNullOrWhiteSpace(motivo.Text)) return "Escribí el motivo: queda registrado en el historial de cambios.";
            return null;
        }, aceptar: "Guardar corrección", ancho: 500,
        intro: $"{d.Empleado} · {d.Obra} · {iniL:dd/MM/yyyy HH:mm} a {finL:HH:mm}. El cambio queda registrado con tu usuario y el motivo.");
        if (!ok) return;

        // Solo se envía lo que realmente cambió (las horas se editan sin segundos).
        DateTime? iniUtc = nuevoIni != SinSegundos(iniL) ? ALocalAUtc(nuevoIni, nuevoIni.TimeOfDay) : null;
        DateTime? finUtc = nuevoFin != SinSegundos(finL) ? ALocalAUtc(nuevoFin, nuevoFin.TimeOfDay) : null;
        int? obraId = cmbObra.SelectedItem is ObraAdminDto o && o.Id != d.ObraId ? o.Id : null;

        // Subtarea: se envía solo si cambió. «(sin subtarea)» quita la actual (si cambia la obra, el servidor ya la quita).
        var subElegida = (cmbSub.SelectedItem as Opcion)?.Id ?? 0;
        int? subtareaId = null;
        var quitar = false;
        if (subElegida > 0 && subElegida != d.SubtareaId) subtareaId = subElegida;
        else if (subElegida == 0 && d.SubtareaId is not null && obraId is null) quitar = true;
        if (iniUtc is null && finUtc is null && obraId is null && subtareaId is null && !quitar) { Dialogos.Info(this, "No cambiaste nada."); return; }

        if (await Llamar(_api.CorregirAsync(d.Id, iniUtc, finUtc, obraId, motivo.Text.Trim(), subtareaId, quitar)) is null) return;
        await BuscarAsync();
        Estado("Registro corregido. El cambio quedó en el historial.");
    }

    private async void BtnAgregarRegistro_Click(object sender, RoutedEventArgs e)
    {
        var empleados = _empleados.Where(x => x.Activo).ToList();
        var obras = _obras.Where(x => x.Activa).ToList();
        if (empleados.Count == 0 || obras.Count == 0) { Dialogos.Info(this, "Primero tiene que haber al menos un empleado y una obra activos."); return; }

        var cmbEmp = new ComboBox { ItemsSource = empleados, DisplayMemberPath = "Nombre", SelectedIndex = 0 };
        var cmbObra = new ComboBox { ItemsSource = obras, DisplayMemberPath = "Nombre", SelectedIndex = 0 };
        if (CmbFEmpleado.SelectedItem is Opcion { Id: > 0 } oe) cmbEmp.SelectedItem = empleados.FirstOrDefault(x => x.Id == oe.Id) ?? cmbEmp.SelectedItem;
        if (CmbFObra.SelectedItem is Opcion { Id: > 0 } oo) cmbObra.SelectedItem = obras.FirstOrDefault(x => x.Id == oo.Id) ?? cmbObra.SelectedItem;
        // Subtarea: si la obra tiene subtareas activas hay que elegir una (igual que para los empleados).
        var cmbSub = new ComboBox { DisplayMemberPath = "Nombre" };
        var exigeSubtarea = false;
        async Task LlenarSubtareasAsync(int obraId)
        {
            var activas = (await SubtareasDeObraAsync(obraId)).Where(s => s.Activa).ToList();
            exigeSubtarea = activas.Any(s => !s.Terminada);
            var opciones = new List<Opcion> { new(0, exigeSubtarea ? "(elegí una subtarea)" : "(la obra no tiene subtareas pendientes)") };
            opciones.AddRange(activas.Select(s => new Opcion(s.Id, s.Terminada ? s.Nombre + " (terminada)" : s.Nombre)));
            cmbSub.ItemsSource = opciones;
            cmbSub.SelectedIndex = 0;
            cmbSub.IsEnabled = activas.Count > 0;
        }
        await LlenarSubtareasAsync(((ObraAdminDto)cmbObra.SelectedItem).Id);
        cmbObra.SelectionChanged += async (_, _) => { if (cmbObra.SelectedItem is ObraAdminDto o) await LlenarSubtareasAsync(o.Id); };

        var fIni = new DatePicker { SelectedDate = DateTime.Today };
        var hIni = new TextBox { Text = "08:00", Width = 70, HorizontalAlignment = HorizontalAlignment.Left };
        var fFin = new DatePicker { SelectedDate = DateTime.Today };
        var hFin = new TextBox { Text = "17:00", Width = 70, HorizontalAlignment = HorizontalAlignment.Left };
        var motivo = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 58, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };

        DateTime ini = default, fin = default;
        var ok = Dialogos.Formulario(this, "Agregar un registro a mano", new List<(string, FrameworkElement)>
        {
            ("Empleado", cmbEmp), ("Obra", cmbObra), ("Subtarea", cmbSub), ("Fecha de inicio", fIni), ("Hora de inicio (HH:mm)", hIni), ("Fecha de fin", fFin), ("Hora de fin (HH:mm)", hFin),
            ("Motivo", motivo),
        }, () =>
        {
            if (cmbEmp.SelectedItem is null || cmbObra.SelectedItem is null) return "Elegí el empleado y la obra.";
            if (exigeSubtarea && ((cmbSub.SelectedItem as Opcion)?.Id ?? 0) == 0) return "Esa obra tiene subtareas: elegí una.";
            if (fIni.SelectedDate is null || fFin.SelectedDate is null) return "Elegí las fechas.";
            if (!TryHora(hIni.Text, out var ti) || !TryHora(hFin.Text, out var tf)) return "Escribí las horas con el formato HH:mm (por ejemplo 08:30).";
            ini = fIni.SelectedDate.Value.Date + ti;
            fin = fFin.SelectedDate.Value.Date + tf;
            if (fin <= ini) return "La hora de fin tiene que ser posterior a la de inicio.";
            if (fin > DateTime.Now.AddMinutes(1)) return "No se pueden cargar horas en el futuro.";
            if (string.IsNullOrWhiteSpace(motivo.Text)) return "Escribí el motivo (por ejemplo «trabajó sin la PC»).";
            return null;
        }, aceptar: "Agregar", ancho: 500, intro: "Sirve para cargar horas que el empleado no pudo registrar. Queda marcado como creado por un administrador.");
        if (!ok) return;

        var emp = (EmpleadoAdminDto)cmbEmp.SelectedItem;
        var obra = (ObraAdminDto)cmbObra.SelectedItem;
        var subtarea = (cmbSub.SelectedItem as Opcion)?.Id is > 0 and var sid ? sid : (int?)null;
        if (await Llamar(_api.CrearRegistroAsync(emp.Id, obra.Id, ALocalAUtc(ini, ini.TimeOfDay), ALocalAUtc(fin, fin.TimeOfDay), motivo.Text.Trim(), subtarea)) is null) return;
        await BuscarAsync();
        Estado("Registro agregado.");
    }

    private async void BtnHistorial_Click(object sender, RoutedEventArgs e)
    {
        if (RegistroElegido("ver su historial") is not { } fila) return;
        _auditoriaRegistro = fila.D.Id;
        Pestanas.SelectedItem = TabAuditoria; // dispara la carga
        await Task.CompletedTask;
    }

    private async void BtnExcel_Click(object sender, RoutedEventArgs e)
    {
        var f = FiltroActual();
        var nombre = $"horas_{(f.Desde ?? DateOnly.FromDateTime(DateTime.Today)):yyyy-MM-dd}_a_{(f.Hasta ?? DateOnly.FromDateTime(DateTime.Today)):yyyy-MM-dd}.xlsx";
        var dlg = new SaveFileDialog { Title = "Guardar el reporte de horas", Filter = "Excel (*.xlsx)|*.xlsx", FileName = nombre, OverwritePrompt = true };
        if (dlg.ShowDialog(this) != true) return;

        Estado("Generando el Excel…");
        if (await Llamar(_api.ReporteExcelAsync(f)) is not { } bytes) { Estado(""); return; }
        try { await File.WriteAllBytesAsync(dlg.FileName, bytes); }
        catch (IOException ex) { Dialogos.Aviso(this, $"No se pudo guardar el archivo (¿está abierto en Excel?):\n{ex.Message}"); return; }
        Estado($"Excel guardado: {dlg.FileName}");
        if (Dialogos.Confirmar(this, "El reporte se guardó. ¿Querés abrirlo ahora?", "Reporte de horas"))
            Process.Start(new ProcessStartInfo(dlg.FileName) { UseShellExecute = true });
    }

    // ================================================================ Horas de Taller

    private bool _armandoHoras = true;
    private int _busquedaHorasId;
    private List<CargaAdminDto> _cargas = [];

    private List<EmpleadoAdminDto> EmpleadosTaller() => _empleados.Where(e => e.Area == AreasEmpresa.Taller).ToList();

    /// <summary>Al entrar a la pestaña: arma el menú de empleados de Taller (conservando el elegido) y busca.</summary>
    private async Task CargarHorasTabAsync()
    {
        if (await Llamar(_api.EmpleadosAsync()) is { } e) _empleados = e;
        var antes = (CmbHEmpleado.SelectedItem as Opcion)?.Id ?? 0;
        var opciones = new List<Opcion> { new(0, "(Todos)") };
        opciones.AddRange(EmpleadosTaller().Select(x => new Opcion(x.Id, x.Activo ? x.Nombre : x.Nombre + " (inactivo)")));
        _armandoHoras = true;
        try { CmbHEmpleado.ItemsSource = opciones; CmbHEmpleado.SelectedItem = opciones.FirstOrDefault(x => x.Id == antes) ?? opciones[0]; }
        finally { _armandoHoras = false; }
        await CargarHorasAsync();
    }

    private async void HFiltro_Cambio(object sender, RoutedEventArgs e)
    {
        if (_armandoHoras || !IsLoaded) return;
        var ver = ChkHEliminadas.IsChecked == true;
        BtnHEliminar.Content = ver ? "Recuperar horas…" : "Eliminar horas…";
        BtnHCorregir.IsEnabled = BtnHAgregar.IsEnabled = BtnHExcel.IsEnabled = !ver;
        await CargarHorasAsync();
    }

    private async void BtnHActualizar_Click(object sender, RoutedEventArgs e) => await CargarHorasAsync();

    private async Task CargarHorasAsync()
    {
        var empleadoId = (CmbHEmpleado.SelectedItem as Opcion) is { Id: > 0 } o ? o.Id : (int?)null;
        DateOnly? desde = DpHDesde.SelectedDate is { } d ? DateOnly.FromDateTime(d) : null;
        DateOnly? hasta = DpHHasta.SelectedDate is { } h ? DateOnly.FromDateTime(h) : null;
        if (desde > hasta) { Dialogos.Aviso(this, "La fecha «Desde» no puede ser posterior a «Hasta»."); return; }
        var eliminadas = ChkHEliminadas.IsChecked == true;
        var mia = ++_busquedaHorasId; // solo vale la última búsqueda
        if (await Llamar(_api.HorasAsync(empleadoId, desde, hasta, eliminadas)) is not { } lista || mia != _busquedaHorasId) return;
        _cargas = lista;
        GridHoras.ItemsSource = lista.Select(x => new FilaCarga(x)).ToList();
        var filtros = new List<string>();
        if (CmbHEmpleado.SelectedItem is Opcion { Id: > 0 } emp) filtros.Add($"empleado «{emp.Nombre}»");
        if (desde is { } dd) filtros.Add($"desde el {dd:dd/MM/yyyy}");
        if (hasta is { } hh) filtros.Add($"hasta el {hh:dd/MM/yyyy}");
        var texto = filtros.Count == 0 ? "sin filtros" : string.Join(" · ", filtros);
        TxtHResumen.Text = lista.Count == 0
            ? (eliminadas ? $"No hay cargas eliminadas ({texto})." : $"No hay horas cargadas para estos filtros: {texto}.")
            : (eliminadas ? $"{lista.Count} carga(s) eliminada(s)" : $"{lista.Count} carga(s) · total {Fmt.Hm(lista.Sum(x => (long)x.Minutos) * 60)} h")
              + $" — Filtros: {texto}.";
        Estado($"Búsqueda hecha a las {DateTime.Now:HH:mm:ss}");
    }

    private FilaCarga? CargaElegida(string accion)
    {
        if (GridHoras.SelectedItem is FilaCarga f) return f;
        Dialogos.Info(this, $"Elegí primero una carga de la tabla para {accion}.");
        return null;
    }

    private async void GridHoras_MouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (ChkHEliminadas.IsChecked != true && GridHoras.SelectedItem is FilaCarga && e.OriginalSource is DependencyObject d && ItemsControl.ContainerFromElement(GridHoras, d) is DataGridRow)
            await CorregirHorasAsync();
    }

    private async void BtnHAgregar_Click(object sender, RoutedEventArgs e)
    {
        var empleados = EmpleadosTaller().Where(x => x.Activo).ToList();
        if (empleados.Count == 0) { Dialogos.Info(this, "Todavía no hay empleados activos en el área Taller."); return; }
        var cmbEmp = new ComboBox { ItemsSource = empleados, DisplayMemberPath = "Nombre", SelectedIndex = 0 };
        if (CmbHEmpleado.SelectedItem is Opcion { Id: > 0 } oe) cmbEmp.SelectedItem = empleados.FirstOrDefault(x => x.Id == oe.Id) ?? cmbEmp.SelectedItem;
        var fecha = new DatePicker { SelectedDate = DateTime.Today.AddDays(-1) };
        var horas = new TextBox { Text = "8", Width = 90, HorizontalAlignment = HorizontalAlignment.Left };
        var motivo = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 58, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };

        // Obra y subtarea (la obra puede faltar: trabajo general de Taller). Si la obra tiene subtareas pendientes, hay que elegir una.
        var obrasMenu = new List<Opcion> { new(0, "(Sin obra: trabajo general)") };
        obrasMenu.AddRange(_obras.Where(o => o.Activa).Select(o => new Opcion(o.Id, o.Nombre)));
        var cmbObra = new ComboBox { ItemsSource = obrasMenu, DisplayMemberPath = "Nombre", SelectedIndex = 0 };
        var cmbSub = new ComboBox { DisplayMemberPath = "Nombre", IsEnabled = false, ItemsSource = new List<Opcion> { new(0, "(la obra no tiene subtareas)") }, SelectedIndex = 0 };
        var exigeSubtarea = false;
        async Task LlenarSubtareasAsync(int obraId)
        {
            var activas = obraId == 0 ? [] : (await SubtareasDeObraAsync(obraId)).Where(s => s.Activa).ToList();
            exigeSubtarea = activas.Any(s => !s.Terminada);
            var opciones = new List<Opcion> { new(0, exigeSubtarea ? "(elegí una subtarea)" : "(la obra no tiene subtareas pendientes)") };
            opciones.AddRange(activas.Select(s => new Opcion(s.Id, s.Terminada ? s.Nombre + " (terminada)" : s.Nombre)));
            cmbSub.ItemsSource = opciones;
            cmbSub.SelectedIndex = 0;
            cmbSub.IsEnabled = activas.Count > 0;
        }
        cmbObra.SelectionChanged += async (_, _) => { if (cmbObra.SelectedItem is Opcion o) await LlenarSubtareasAsync(o.Id); };

        var minutos = 0;
        var ok = Dialogos.Formulario(this, "Agregar horas de Taller", new List<(string, FrameworkElement)>
        {
            ("Empleado", cmbEmp), ("Día", fecha), ("Obra", cmbObra), ("Subtarea", cmbSub), ("Horas (8, 7,5 o 7:30)", horas), ("Motivo", motivo),
        }, () =>
        {
            if (cmbEmp.SelectedItem is null) return "Elegí el empleado.";
            if (exigeSubtarea && ((cmbSub.SelectedItem as Opcion)?.Id ?? 0) == 0) return "Esa obra tiene subtareas: elegí una.";
            if (fecha.SelectedDate is null) return "Elegí el día.";
            if (fecha.SelectedDate.Value.Date > DateTime.Today) return "No se pueden cargar horas en el futuro.";
            if (!PanelController.TryParseHoras(horas.Text, out minutos)) return "Escribí las horas, por ejemplo 8, 7,5 o 7:30 (entre 1 minuto y 24 horas).";
            if (string.IsNullOrWhiteSpace(motivo.Text)) return "Escribí el motivo (por ejemplo «no pudo cargarlas»).";
            return null;
        }, aceptar: "Agregar", ancho: 500, intro: "Sirve para cargar el día que el empleado no pudo cargar o que ya pasó. Queda marcado como cargado por un administrador y en el historial de cambios.");
        if (!ok) return;

        var emp = (EmpleadoAdminDto)cmbEmp.SelectedItem;
        var obraElegida = (cmbObra.SelectedItem as Opcion)?.Id is > 0 and var oid ? oid : (int?)null;
        var subElegida = (cmbSub.SelectedItem as Opcion)?.Id is > 0 and var sid ? sid : (int?)null;
        if (await Llamar(_api.CrearHorasAsync(emp.Id, DateOnly.FromDateTime(fecha.SelectedDate!.Value), minutos, motivo.Text.Trim(), obraElegida, subElegida)) is null) return;
        await CargarHorasAsync();
        Estado("Horas agregadas.");
    }

    private async void BtnHCorregir_Click(object sender, RoutedEventArgs e) => await CorregirHorasAsync();

    private async Task CorregirHorasAsync()
    {
        if (CargaElegida("corregirla") is not { } fila) return;
        var d = fila.D;
        var horas = new TextBox { Text = Fmt.Hm(d.Minutos * 60L), Width = 90, HorizontalAlignment = HorizontalAlignment.Left };
        var motivo = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 58, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        var minutos = 0;
        var ok = Dialogos.Formulario(this, "Corregir horas de Taller", new List<(string, FrameworkElement)> { ("Horas (8, 7,5 o 7:30)", horas), ("Motivo", motivo) }, () =>
        {
            if (!PanelController.TryParseHoras(horas.Text, out minutos)) return "Escribí las horas, por ejemplo 8, 7,5 o 7:30 (entre 1 minuto y 24 horas).";
            if (minutos == d.Minutos) return "No cambiaste las horas.";
            if (string.IsNullOrWhiteSpace(motivo.Text)) return "Escribí el motivo: queda registrado en el historial de cambios.";
            return null;
        }, aceptar: "Corregir", ancho: 480, intro: $"{d.Empleado} · {d.Fecha:dd/MM/yyyy} · {(d.Obra is null ? "trabajo general" : d.Subtarea is null ? d.Obra : d.Obra + " › " + d.Subtarea)}\nAhora figura con {Fmt.Hm(d.Minutos * 60L)} h. Después de corregirlas, el empleado ya no puede cambiarlas.");
        if (!ok) return;
        if (await Llamar(_api.CorregirHorasAsync(d.Id, minutos, motivo.Text.Trim())) is null) return;
        await CargarHorasAsync();
        Estado("Horas corregidas.");
    }

    private async void BtnHEliminar_Click(object sender, RoutedEventArgs e)
    {
        var recuperar = ChkHEliminadas.IsChecked == true;
        if (CargaElegida(recuperar ? "recuperarla" : "eliminarla") is not { } fila) return;
        var d = fila.D;
        var motivo = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 58, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        var resumen = $"{d.Empleado} · {d.Fecha:dd/MM/yyyy} · {(d.Obra is null ? "trabajo general" : d.Subtarea is null ? d.Obra : d.Obra + " › " + d.Subtarea)} · {Fmt.Hm(d.Minutos * 60L)} h";
        var ok = Dialogos.Formulario(this, recuperar ? "Recuperar horas" : "Eliminar horas", new List<(string, FrameworkElement)> { ("Motivo", motivo) },
            () => string.IsNullOrWhiteSpace(motivo.Text) ? "Escribí el motivo: queda registrado en el historial de cambios." : null,
            aceptar: recuperar ? "Recuperar" : "Eliminar", ancho: 480,
            intro: recuperar ? $"{resumen}\n\nVuelve a contar." : $"{resumen}\n\nDeja de contar. No se borra: queda en el historial de cambios y se puede recuperar con «Ver eliminadas».");
        if (!ok) return;
        var r = recuperar ? await Llamar(_api.RecuperarHorasAsync(d.Id, motivo.Text.Trim())) : await Llamar(_api.EliminarHorasAsync(d.Id, motivo.Text.Trim()));
        if (r is null) return;
        await CargarHorasAsync();
        Estado(recuperar ? "Horas recuperadas." : "Horas eliminadas. Se pueden recuperar desde «Ver eliminadas».");
    }

    private async void BtnHExcel_Click(object sender, RoutedEventArgs e)
    {
        var empleadoId = (CmbHEmpleado.SelectedItem as Opcion) is { Id: > 0 } o ? o.Id : (int?)null;
        DateOnly? desde = DpHDesde.SelectedDate is { } d ? DateOnly.FromDateTime(d) : null;
        DateOnly? hasta = DpHHasta.SelectedDate is { } h ? DateOnly.FromDateTime(h) : null;
        var nombre = $"horas-taller_{(desde ?? DateOnly.FromDateTime(DateTime.Today)):yyyy-MM-dd}_a_{(hasta ?? DateOnly.FromDateTime(DateTime.Today)):yyyy-MM-dd}.xlsx";
        var dlg = new SaveFileDialog { Title = "Guardar el Excel de horas de Taller", Filter = "Excel (*.xlsx)|*.xlsx", FileName = nombre, OverwritePrompt = true };
        if (dlg.ShowDialog(this) != true) return;
        Estado("Generando el Excel…");
        if (await Llamar(_api.HorasExcelAsync(empleadoId, desde, hasta)) is not { } bytes) { Estado(""); return; }
        try { await File.WriteAllBytesAsync(dlg.FileName, bytes); }
        catch (IOException ex) { Dialogos.Aviso(this, $"No se pudo guardar el archivo (¿está abierto en Excel?):\n{ex.Message}"); return; }
        Estado($"Excel guardado: {dlg.FileName}");
        if (Dialogos.Confirmar(this, "El Excel se guardó. ¿Querés abrirlo ahora?", "Horas de Taller"))
            Process.Start(new ProcessStartInfo(dlg.FileName) { UseShellExecute = true });
    }

    // ================================================================ Asistencia (libro mensual) y faltas

    private sealed record OpcionTxt(string Clave, string Texto);

    private bool _armandoAsistencia = true;
    private DateTime _mesAsistencia = new(DateTime.Today.Year, DateTime.Today.Month, 1);
    private AsistenciaMesDto? _asistencia;
    private int _busquedaAsistenciaId, _busquedaFaltasId;

    private static string NombreMes(DateTime d) => d.ToString("MMMM yyyy");

    private async void BtnMesAnterior_Click(object sender, RoutedEventArgs e) { _mesAsistencia = _mesAsistencia.AddMonths(-1); await CargarAsistenciaAsync(); }
    private async void BtnMesSiguiente_Click(object sender, RoutedEventArgs e) { _mesAsistencia = _mesAsistencia.AddMonths(1); await CargarAsistenciaAsync(); }
    private async void BtnMesActual_Click(object sender, RoutedEventArgs e) { _mesAsistencia = new DateTime(DateTime.Today.Year, DateTime.Today.Month, 1); await CargarAsistenciaAsync(); }
    private async void BtnAsActualizar_Click(object sender, RoutedEventArgs e) => await CargarAsistenciaAsync();

    private async void AsFiltro_Cambio(object sender, SelectionChangedEventArgs e)
    {
        if (_armandoAsistencia || !IsLoaded) return;
        await CargarAsistenciaAsync();
    }

    private async Task CargarAsistenciaAsync()
    {
        TxtMes.Text = NombreMes(_mesAsistencia);
        var mia = ++_busquedaAsistenciaId;
        if (await Llamar(_api.AsistenciaAsync(_mesAsistencia.Year, _mesAsistencia.Month, AreaElegida(CmbAsArea))) is not { } mes || mia != _busquedaAsistenciaId) return;
        _asistencia = mes;
        ArmarColumnasAsistencia(mes);
        GridAsistencia.ItemsSource = mes.Filas.Select(f => new FilaAsistencia(f,
            f.Codigos.Select((c, i) => new CeldaAsistencia(c, mes.Dias[i].Fecha)).ToList())).ToList();

        if (mes.ControlDesde is null) TxtAsResumen.Text = "El control de asistencia todavía no empezó.";
        else
        {
            var aus = mes.Filas.Sum(f => f.Ausentes);
            TxtAsResumen.Text = $"{mes.Filas.Count} empleado(s) · {mes.Filas.Sum(f => f.Presentes)} presente(s) · {aus} ausente(s) · {mes.Filas.Sum(f => f.Justificados)} justificado(s). " +
                $"El control empezó el {mes.ControlDesde:dd/MM/yyyy}: los días anteriores figuran sin control. Los días se cierran a las 23:59.";
        }
        Estado($"Asistencia actualizada a las {DateTime.Now:HH:mm:ss}");
    }

    /// <summary>Arma las columnas del libro: empleado, área, un día por columna (con su letra) y los totales.</summary>
    private void ArmarColumnasAsistencia(AsistenciaMesDto mes)
    {
        GridAsistencia.Columns.Clear();
        GridAsistencia.Columns.Add(new DataGridTextColumn { Header = "Empleado", Binding = new System.Windows.Data.Binding("Empleado"), Width = 180 });
        GridAsistencia.Columns.Add(new DataGridTextColumn { Header = "Área", Binding = new System.Windows.Data.Binding("Area"), Width = 62 });
        for (var i = 0; i < mes.Dias.Count; i++)
        {
            var d = mes.Dias[i].Fecha;
            var tb = new FrameworkElementFactory(typeof(TextBlock));
            tb.SetBinding(TextBlock.TextProperty, new System.Windows.Data.Binding($"Celdas[{i}].Texto"));
            tb.SetBinding(TextBlock.BackgroundProperty, new System.Windows.Data.Binding($"Celdas[{i}].Fondo"));
            tb.SetBinding(FrameworkElement.ToolTipProperty, new System.Windows.Data.Binding($"Celdas[{i}].Detalle"));
            tb.SetValue(TextBlock.TextAlignmentProperty, TextAlignment.Center);
            tb.SetValue(TextBlock.PaddingProperty, new Thickness(0, 5, 0, 5));
            tb.SetValue(TextBlock.FontWeightProperty, FontWeights.SemiBold);
            GridAsistencia.Columns.Add(new DataGridTemplateColumn
            {
                Header = $"{d.Day}\n{"DLMMJVS"[(int)d.DayOfWeek]}", Width = 34, CanUserSort = false,
                CellTemplate = new DataTemplate { VisualTree = tb },
            });
        }
        GridAsistencia.Columns.Add(new DataGridTextColumn { Header = "P", Binding = new System.Windows.Data.Binding("Presentes"), Width = 36 });
        GridAsistencia.Columns.Add(new DataGridTextColumn { Header = "A", Binding = new System.Windows.Data.Binding("Ausentes"), Width = 36 });
        GridAsistencia.Columns.Add(new DataGridTextColumn { Header = "J", Binding = new System.Windows.Data.Binding("Justificados"), Width = 36 });
    }

    /// <summary>La celda elegida del libro: el empleado, el día y el código (null si no hay una celda de día elegida).</summary>
    private (FilaAsistencia Fila, DateOnly Dia, string Codigo)? CeldaDeAsistencia()
    {
        if (_asistencia is null || GridAsistencia.SelectedCells.Count == 0) { Dialogos.Info(this, "Elegí primero una celda del libro (un día de un empleado)."); return null; }
        var c = GridAsistencia.SelectedCells[0];
        var i = c.Column.DisplayIndex - 2;
        if (c.Item is not FilaAsistencia fila || i < 0 || i >= _asistencia.Dias.Count) { Dialogos.Info(this, "Elegí una celda de un día (no el nombre ni los totales)."); return null; }
        return (fila, _asistencia.Dias[i].Fecha, fila.D.Codigos[i]);
    }

    private async void GridAsistencia_MouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (e.OriginalSource is DependencyObject d && ItemsControl.ContainerFromElement(GridAsistencia, d) is DataGridRow && GridAsistencia.SelectedCells.Count > 0
            && CeldaDeAsistenciaSilenciosa() is { Codigo: "A" or "J" } c)
            await JustificarFaltaAsync(c.Fila.D.EmpleadoId, c.Fila.D.Empleado, c.Dia);
    }

    private (FilaAsistencia Fila, DateOnly Dia, string Codigo)? CeldaDeAsistenciaSilenciosa()
    {
        if (_asistencia is null || GridAsistencia.SelectedCells.Count == 0) return null;
        var c = GridAsistencia.SelectedCells[0];
        var i = c.Column.DisplayIndex - 2;
        return c.Item is FilaAsistencia fila && i >= 0 && i < _asistencia.Dias.Count ? (fila, _asistencia.Dias[i].Fecha, fila.D.Codigos[i]) : null;
    }

    private async void BtnAsJustificar_Click(object sender, RoutedEventArgs e)
    {
        if (CeldaDeAsistencia() is not { } c) return;
        if (c.Codigo is not ("A" or "J")) { Dialogos.Info(this, ExplicarDia(c.Codigo)); return; }
        await JustificarFaltaAsync(c.Fila.D.EmpleadoId, c.Fila.D.Empleado, c.Dia);
    }

    private async void BtnAsInjustificada_Click(object sender, RoutedEventArgs e)
    {
        if (CeldaDeAsistencia() is not { } c) return;
        if (c.Codigo is not ("A" or "J")) { Dialogos.Info(this, ExplicarDia(c.Codigo)); return; }
        await InjustificarFaltaAsync(c.Fila.D.EmpleadoId, c.Fila.D.Empleado, c.Dia);
    }

    private static string ExplicarDia(string codigo) => codigo switch
    {
        "P" => "Ese empleado estuvo presente ese día: no hay nada que justificar.",
        "S" => "Los sábados y domingos no se controlan.",
        "…" => "Ese día todavía no terminó (se cierra a las 23:59).",
        _ => "Ese día es anterior al control de asistencia.",
    };

    // ---- acciones sobre una falta (las usan el libro y el historial) ----

    private async Task JustificarFaltaAsync(int empleadoId, string empleado, DateOnly dia)
    {
        var motivo = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 70, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        motivo.SetValue(System.Windows.Automation.AutomationProperties.AutomationIdProperty, "TxtMotivo");
        var ok = Dialogos.Formulario(this, "Justificar la falta", new List<(string, FrameworkElement)> { ("Motivo", motivo) },
            () => string.IsNullOrWhiteSpace(motivo.Text) ? "Escribí el motivo (por ejemplo: licencia, enfermedad, ausencia autorizada)." : motivo.Text.Trim().Length > 500 ? "El motivo es demasiado largo (máximo 500 caracteres)." : null,
            aceptar: "Justificar", ancho: 500,
            intro: $"{empleado} · {dia:dddd dd/MM/yyyy}\n\nQueda guardado el motivo y la ausencia figura como JUSTIFICADA (no cuenta como falta injustificada).");
        if (!ok) return;
        if (await Llamar(_api.JustificarFaltaAsync(empleadoId, dia, motivo.Text.Trim())) is null) return;
        await RefrescarAsistenciaYFaltasAsync();
        Estado("Falta justificada.");
    }

    private async Task InjustificarFaltaAsync(int empleadoId, string empleado, DateOnly dia)
    {
        var motivo = new TextBox { AcceptsReturn = true, TextWrapping = TextWrapping.Wrap, Height = 58, VerticalScrollBarVisibility = ScrollBarVisibility.Auto };
        var ok = Dialogos.Formulario(this, "Dejar la falta como injustificada", new List<(string, FrameworkElement)> { ("Observación (opcional)", motivo) },
            () => motivo.Text.Trim().Length > 500 ? "La observación es demasiado larga (máximo 500 caracteres)." : null,
            aceptar: "Dejarla injustificada", ancho: 500,
            intro: $"{empleado} · {dia:dddd dd/MM/yyyy}\n\nLa ausencia queda como INJUSTIFICADA (ya revisada). Si estaba justificada, se quita la justificación.");
        if (!ok) return;
        if (await Llamar(_api.InjustificarFaltaAsync(empleadoId, dia, string.IsNullOrWhiteSpace(motivo.Text) ? null : motivo.Text.Trim())) is null) return;
        await RefrescarAsistenciaYFaltasAsync();
        Estado("Falta registrada como injustificada.");
    }

    private async Task RefrescarAsistenciaYFaltasAsync()
    {
        if (Pestanas.SelectedItem == TabAsistencia) await CargarAsistenciaAsync();
        else if (Pestanas.SelectedItem == TabFaltas) await CargarFaltasAsync();
        await ActualizarContadorAvisosAsync();
    }

    private async void BtnAsExcel_Click(object sender, RoutedEventArgs e)
    {
        var area = AreaElegida(CmbAsArea);
        var dlg = new SaveFileDialog { Title = "Guardar el Excel de asistencia", Filter = "Excel (*.xlsx)|*.xlsx", FileName = $"asistencia_{_mesAsistencia:yyyy-MM}{(area is null ? "" : "_" + area.ToLowerInvariant())}.xlsx", OverwritePrompt = true };
        if (dlg.ShowDialog(this) != true) return;
        Estado("Generando el Excel…");
        if (await Llamar(_api.AsistenciaExcelAsync(_mesAsistencia.Year, _mesAsistencia.Month, area)) is not { } bytes) { Estado(""); return; }
        try { await File.WriteAllBytesAsync(dlg.FileName, bytes); }
        catch (IOException ex) { Dialogos.Aviso(this, $"No se pudo guardar el archivo (¿está abierto en Excel?):\n{ex.Message}"); return; }
        Estado($"Excel guardado: {dlg.FileName}");
        if (Dialogos.Confirmar(this, "El Excel se guardó. ¿Querés abrirlo ahora?", "Asistencia"))
            Process.Start(new ProcessStartInfo(dlg.FileName) { UseShellExecute = true });
    }

    // ---- historial de faltas ----

    private async void FaFiltro_Cambio(object sender, RoutedEventArgs e)
    {
        if (_armandoAsistencia || !IsLoaded) return;
        await CargarFaltasAsync();
    }

    private async void BtnFaActualizar_Click(object sender, RoutedEventArgs e) => await CargarFaltasAsync();

    private async Task CargarFaltasAsync()
    {
        DateOnly? desde = DpFaDesde.SelectedDate is { } d ? DateOnly.FromDateTime(d) : null;
        DateOnly? hasta = DpFaHasta.SelectedDate is { } h ? DateOnly.FromDateTime(h) : null;
        if (desde > hasta) { Dialogos.Aviso(this, "La fecha «Desde» no puede ser posterior a «Hasta»."); return; }
        var clave = (CmbFaEstado.SelectedItem as OpcionTxt)?.Clave;
        var mia = ++_busquedaFaltasId;
        if (await Llamar(_api.FaltasAsync(desde, hasta, null, AreaElegida(CmbFaArea), string.IsNullOrEmpty(clave) ? null : clave)) is not { } lista || mia != _busquedaFaltasId) return;
        GridFaltas.ItemsSource = lista.Select(x => new FilaFalta(x)).ToList();
        var sin = lista.Count(x => x.Estado == "sin_revisar");
        TxtFaResumen.Text = lista.Count == 0
            ? "No hay faltas para estos filtros."
            : $"{lista.Count} falta(s): {sin} sin revisar · {lista.Count(x => x.Estado == "injustificada")} injustificada(s) · {lista.Count(x => x.Estado == "justificada")} justificada(s). Las amarillas están sin revisar.";
        await ActualizarContadorAvisosAsync();
        Estado($"Faltas actualizadas a las {DateTime.Now:HH:mm:ss}");
    }

    private FilaFalta? FaltaElegida()
    {
        if (GridFaltas.SelectedItem is FilaFalta f) return f;
        Dialogos.Info(this, "Elegí primero una falta de la tabla.");
        return null;
    }

    private async void GridFaltas_MouseDoubleClick(object sender, MouseButtonEventArgs e)
    {
        if (GridFaltas.SelectedItem is FilaFalta f && e.OriginalSource is DependencyObject d && ItemsControl.ContainerFromElement(GridFaltas, d) is DataGridRow)
            await JustificarFaltaAsync(f.D.EmpleadoId, f.D.Empleado, f.D.Fecha);
    }

    private async void BtnFaJustificar_Click(object sender, RoutedEventArgs e)
    {
        if (FaltaElegida() is { } f) await JustificarFaltaAsync(f.D.EmpleadoId, f.D.Empleado, f.D.Fecha);
    }

    private async void BtnFaInjustificada_Click(object sender, RoutedEventArgs e)
    {
        if (FaltaElegida() is { } f) await InjustificarFaltaAsync(f.D.EmpleadoId, f.D.Empleado, f.D.Fecha);
    }

    // ================================================================ Empleados

    private List<EmpleadoAdminDto> _empleadosTabla = [];
    private readonly Dictionary<int, string?> _pines = [];
    private bool _mostrandoPines;
    private bool _avisoPinesAceptado;

    private IEnumerable<FilaEmpleado> FilasEmpleados() =>
        _empleadosTabla.Select(x => new FilaEmpleado(x, _pines.GetValueOrDefault(x.Id), _mostrandoPines));

    private bool _excelManda;

    /// <summary>Si los empleados se manejan desde el Excel: avisa en la pestaña y deshabilita lo que se cambia en el Excel.</summary>
    private async Task AplicarModoExcelAsync()
    {
        var r = await _api.EmpleadosExcelAsync();
        if (!r.Ok || r.Valor is not { } x) return;
        _excelManda = x.Configurado;
        foreach (var b in new[] { BtnEmpNuevo, BtnEmpRenombrar, BtnEmpAreaCambiar, BtnEmpActivar, BtnEmpResetPin }) b.IsEnabled = !x.Configurado;
        AvisoExcelEmp.Visibility = x.Configurado ? Visibility.Visible : Visibility.Collapsed;
        if (x.Configurado)
            TxtAvisoExcelEmp.Text = $"Los empleados se manejan desde el Excel «{System.IO.Path.GetFileName(x.Archivo)}». Para agregar o quitar a alguien, o cambiar un PIN o el área, editá el Excel: la app se actualiza sola en unos segundos. Acá podés ver y exportar los PIN."
                + (x.Ok == false ? $"\n⚠ {x.Mensaje}" : x.Errores.Count > 0 ? $"\n⚠ {x.Errores.Count} fila(s) del Excel tienen errores (mirá Sistema)." : "");
    }

    private async Task CargarEmpleadosAsync()
    {
        await AplicarModoExcelAsync();
        if (await Llamar(_api.EmpleadosAsync(AreaElegida(CmbEmpArea))) is not { } lista) return;
        _empleadosTabla = lista;
        GridEmpleados.ItemsSource = FilasEmpleados().ToList();
        var activos = lista.Count(x => x.Activo);
        TxtEmpResumen.Text = $"{lista.Count} empleado(s) · {lista.Count(x => x.Area == AreasEmpresa.Oficina)} de Oficina · {lista.Count(x => x.Area == AreasEmpresa.Taller)} de Taller · {activos} activo(s)."
            + (_mostrandoPines ? " Los PIN están visibles: ocultalos cuando termines." : "");
        await CargarMaestrosAsync(); // actualiza también los filtros de las otras pestañas
    }

    private async void CmbEmpArea_Cambio(object sender, SelectionChangedEventArgs e)
    {
        if (!IsLoaded) return;
        if (_mostrandoPines) OcultarPines(); // los PIN mostrados eran de otra selección
        await CargarEmpleadosAsync();
    }

    private static TextBox CajaNombre(string inicial = "") => new() { Text = inicial, Height = 26, VerticalContentAlignment = VerticalAlignment.Center };

    private static ComboBox CajaArea(string? elegida) => new() { ItemsSource = AreasEmpresa.Todas, SelectedItem = elegida ?? AreasEmpresa.Oficina, Height = 26 };

    private async void BtnEmpNuevo_Click(object sender, RoutedEventArgs e)
    {
        var nombre = CajaNombre();
        var area = CajaArea(AreaElegida(CmbEmpArea)); // por defecto, el área que se está mirando
        if (!Dialogos.Formulario(this, "Nuevo empleado", new List<(string, FrameworkElement)> { ("Nombre y apellido", nombre), ("Área", area) },
            () => string.IsNullOrWhiteSpace(nombre.Text) ? "Escribí el nombre." : null, aceptar: "Crear", ancho: 440)) return;
        if (await Llamar(_api.CrearEmpleadoAsync(nombre.Text.Trim(), (string)area.SelectedItem)) is not { } r) return;
        if (_mostrandoPines) _pines[r.Empleado.Id] = r.PinInicial;
        await CargarEmpleadosAsync();
        Dialogos.MostrarSecreto(this, "Empleado creado", $"{r.Empleado.Nombre} ({r.Empleado.Area})", "PIN inicial", r.PinInicial,
            "En su primer ingreso va a tener que elegir uno propio. Mientras tanto lo ves cuando quieras con «Mostrar PIN».");
    }

    private async void BtnEmpArea_Click(object sender, RoutedEventArgs e)
    {
        if (EmpleadoElegido() is not { } emp) return;
        var area = CajaArea(emp.Area);
        if (!Dialogos.Formulario(this, $"Área de {emp.Nombre}", new List<(string, FrameworkElement)> { ("Área", area) },
            () => (string)area.SelectedItem == emp.Area ? "Elegí un área distinta a la actual." : null, aceptar: "Cambiar", ancho: 400,
            intro: $"Hoy está en {emp.Area}. Sus horas anteriores se conservan; en los reportes figuran con el área actual. El cambio queda en el historial.")) return;
        if (await Llamar(_api.ActualizarEmpleadoAsync(emp.Id, area: (string)area.SelectedItem)) is null) return;
        await CargarEmpleadosAsync();
    }

    // ---- PIN visibles ----

    private void OcultarPines()
    {
        _mostrandoPines = false;
        _pines.Clear();
        BtnMostrarPin.Content = "Mostrar PIN";
        GridEmpleados.ItemsSource = FilasEmpleados().ToList();
    }

    private async void BtnMostrarPin_Click(object sender, RoutedEventArgs e)
    {
        if (_mostrandoPines) { OcultarPines(); await CargarEmpleadosAsync(); return; }

        if (!_avisoPinesAceptado)
        {
            if (!Dialogos.Confirmar(this, "Vas a ver los PIN de ingreso de los empleados.\n\nQueda registrado en el historial de cambios (quién y cuándo). Los PIN se ocultan solos al salir de esta pestaña.\n\n¿Continuar?", "Mostrar PIN")) return;
            _avisoPinesAceptado = true;
        }
        if (await Llamar(_api.PinesAsync(AreaElegida(CmbEmpArea))) is not { } lista) return;
        _pines.Clear();
        foreach (var p in lista) _pines[p.Id] = p.Pin;
        _mostrandoPines = true;
        BtnMostrarPin.Content = "Ocultar PIN";
        await CargarEmpleadosAsync();
        Estado("PIN visibles. Ocultalos cuando termines.");
    }

    private async void BtnExportarPines_Click(object sender, RoutedEventArgs e)
    {
        var area = AreaElegida(CmbEmpArea);
        if (!Dialogos.Confirmar(this, $"El Excel va a contener los PIN de ingreso de {(area is null ? "TODOS los empleados" : $"los empleados de {area}")}.\n\nGuardalo en un lugar privado y borralo cuando ya no lo necesites. La exportación queda registrada en el historial de cambios.\n\n¿Continuar?", "Exportar PIN a Excel")) return;

        var dlg = new SaveFileDialog { Title = "Guardar el Excel de PIN", Filter = "Excel (*.xlsx)|*.xlsx", FileName = area is null ? "pines.xlsx" : $"pines_{area.ToLowerInvariant()}.xlsx", OverwritePrompt = true };
        if (dlg.ShowDialog(this) != true) return;

        Estado("Generando el Excel…");
        if (await Llamar(_api.PinesExcelAsync(area)) is not { } bytes) { Estado(""); return; }
        try { await File.WriteAllBytesAsync(dlg.FileName, bytes); }
        catch (IOException ex) { Dialogos.Aviso(this, $"No se pudo guardar el archivo (¿está abierto en Excel?):\n{ex.Message}"); return; }
        Estado($"Excel de PIN guardado: {dlg.FileName}");
        if (Dialogos.Confirmar(this, "El Excel se guardó. ¿Querés abrirlo ahora?", "PIN exportados"))
            Process.Start(new ProcessStartInfo(dlg.FileName) { UseShellExecute = true });
    }

    private EmpleadoAdminDto? EmpleadoElegido()
    {
        if (GridEmpleados.SelectedItem is FilaEmpleado f) return f.D;
        Dialogos.Info(this, "Elegí primero un empleado de la tabla.");
        return null;
    }

    private async void BtnEmpRenombrar_Click(object sender, RoutedEventArgs e)
    {
        if (EmpleadoElegido() is not { } emp) return;
        var nombre = CajaNombre(emp.Nombre);
        if (!Dialogos.Formulario(this, "Renombrar empleado", new List<(string, FrameworkElement)> { ("Nombre y apellido", nombre) },
            () => string.IsNullOrWhiteSpace(nombre.Text) ? "Escribí el nombre." : null, ancho: 420)) return;
        if (await Llamar(_api.ActualizarEmpleadoAsync(emp.Id, nombre: nombre.Text.Trim())) is null) return;
        await CargarEmpleadosAsync();
    }

    private async void BtnEmpActivar_Click(object sender, RoutedEventArgs e)
    {
        if (EmpleadoElegido() is not { } emp) return;
        var pregunta = emp.Activo
            ? $"¿Desactivar a {emp.Nombre}?\n\nDeja de aparecer en el panel y no puede ingresar. Sus horas anteriores se conservan. Si está registrando ahora, su registro se corta solo en unos minutos."
            : $"¿Volver a activar a {emp.Nombre}?";
        if (!Dialogos.Confirmar(this, pregunta)) return;
        if (await Llamar(_api.ActualizarEmpleadoAsync(emp.Id, activo: !emp.Activo)) is null) return;
        await CargarEmpleadosAsync();
    }

    private async void BtnEmpPin_Click(object sender, RoutedEventArgs e)
    {
        if (EmpleadoElegido() is not { } emp) return;
        if (!Dialogos.Confirmar(this, $"¿Resetear el PIN de {emp.Nombre}?\n\nSe genera un PIN nuevo y el anterior deja de funcionar.")) return;
        if (await Llamar(_api.ResetearPinAsync(emp.Id)) is not { } r) return;
        if (_mostrandoPines) _pines[emp.Id] = r.PinInicial;
        await CargarEmpleadosAsync();
        Dialogos.MostrarSecreto(this, "PIN reseteado", emp.Nombre, "PIN nuevo", r.PinInicial,
            "Al ingresar va a tener que elegir uno propio. Mientras tanto lo ves cuando quieras con «Mostrar PIN».");
    }

    // ================================================================ Obras

    private async Task CargarObrasAsync()
    {
        var elegida = (GridObras.SelectedItem as FilaObra)?.D.Id; // se conserva la selección al recargar
        if (await Llamar(_api.ObrasAsync()) is not { } lista) return;
        _obras = lista;
        GridObras.ItemsSource = lista.Select(x => new FilaObra(x)).ToList();
        if (elegida is { } id) GridObras.SelectedItem = GridObras.ItemsSource.Cast<FilaObra>().FirstOrDefault(f => f.D.Id == id);
        else await CargarSubtareasAsync();
        await CargarMaestrosAsync();
    }

    // ---- Subtareas de la obra elegida ----

    private void GridObras_SelectionChanged(object sender, SelectionChangedEventArgs e)
    {
        if (IsLoaded) _ = CargarSubtareasAsync();
    }

    private async Task CargarSubtareasAsync()
    {
        var obra = (GridObras.SelectedItem as FilaObra)?.D;
        var hay = obra is not null;
        BtnSubNueva.IsEnabled = BtnSubRenombrar.IsEnabled = BtnSubActivar.IsEnabled = BtnSubTerminar.IsEnabled = hay;
        if (obra is null)
        {
            GridSubtareas.ItemsSource = null;
            TxtSubtareasTitulo.Text = "Subtareas";
            TxtSubtareasAyuda.Text = "Elegí una obra de la lista para ver y editar sus subtareas.";
            return;
        }

        TxtSubtareasTitulo.Text = $"Subtareas de «{obra.Nombre}»";
        if (await Llamar(_api.SubtareasAsync(obra.Id)) is not { } lista) return;
        if ((GridObras.SelectedItem as FilaObra)?.D.Id != obra.Id) return; // mientras tanto eligió otra obra
        GridSubtareas.ItemsSource = lista.Select(x => new FilaSubtarea(x)).ToList();
        var pendientes = lista.Count(x => x.Activa && !x.Terminada);
        TxtSubtareasAyuda.Text = pendientes == 0
            ? "Esta obra no tiene subtareas pendientes: los empleados registran las horas directamente en la obra. Si agregás una, van a tener que elegir una subtarea al presionar Play."
            : $"{pendientes} subtarea(s) pendiente(s): quien registre horas en esta obra DEBE elegir una. Las terminadas (tachadas) y las desactivadas dejan de ofrecerse pero se conservan en los registros anteriores.";
    }

    private SubtareaAdminDto? SubtareaElegida()
    {
        if (GridSubtareas.SelectedItem is FilaSubtarea f) return f.D;
        Dialogos.Info(this, "Elegí primero una subtarea de la tabla.");
        return null;
    }

    private async void BtnSubNueva_Click(object sender, RoutedEventArgs e)
    {
        if ((GridObras.SelectedItem as FilaObra)?.D is not { } obra) return;
        var nombre = CajaNombre();
        if (!Dialogos.Formulario(this, $"Nueva subtarea en «{obra.Nombre}»", new List<(string, FrameworkElement)> { ("Nombre de la subtarea", nombre) },
            () => string.IsNullOrWhiteSpace(nombre.Text) ? "Escribí el nombre." : null, aceptar: "Crear", ancho: 440,
            intro: obra.SubtareasActivas == 0 ? "Atención: al crear la primera subtarea, los empleados van a tener que elegir una para registrar horas en esta obra." : null)) return;
        if (await Llamar(_api.CrearSubtareaAsync(obra.Id, nombre.Text.Trim())) is null) return;
        await CargarObrasAsync(); // actualiza también el conteo de la obra
        await CargarSubtareasAsync();
    }

    private async void BtnSubRenombrar_Click(object sender, RoutedEventArgs e)
    {
        if (SubtareaElegida() is not { } sub) return;
        var nombre = CajaNombre(sub.Nombre);
        if (!Dialogos.Formulario(this, "Renombrar subtarea", new List<(string, FrameworkElement)> { ("Nombre de la subtarea", nombre) },
            () => string.IsNullOrWhiteSpace(nombre.Text) ? "Escribí el nombre." : null, ancho: 440)) return;
        if (await Llamar(_api.ActualizarSubtareaAsync(sub.Id, nombre: nombre.Text.Trim())) is null) return;
        await CargarSubtareasAsync();
    }

    private async void BtnSubActivar_Click(object sender, RoutedEventArgs e)
    {
        if (SubtareaElegida() is not { } sub) return;
        var obra = (GridObras.SelectedItem as FilaObra)?.D;
        var pregunta = sub.Activa
            ? $"¿Desactivar la subtarea «{sub.Nombre}»?\n\nDeja de ofrecerse a los empleados. Las horas ya registradas con ella se conservan." +
              (obra?.SubtareasActivas == 1 ? "\n\nEs la ÚLTIMA subtarea activa de la obra: desde ahora se podrá registrar directamente en la obra, sin elegir subtarea." : "")
            : $"¿Volver a activar la subtarea «{sub.Nombre}»?";
        if (!Dialogos.Confirmar(this, pregunta)) return;
        if (await Llamar(_api.ActualizarSubtareaAsync(sub.Id, activa: !sub.Activa)) is null) return;
        await CargarObrasAsync();
        await CargarSubtareasAsync();
    }

    private async void BtnSubTerminar_Click(object sender, RoutedEventArgs e)
    {
        if (SubtareaElegida() is not { } sub) return;
        var obra = (GridObras.SelectedItem as FilaObra)?.D;
        string pregunta;
        if (sub.Terminada) pregunta = $"¿Reabrir la subtarea «{sub.Nombre}»?\n\nVuelve a ser una tarea pendiente y se ofrece de nuevo a los empleados.";
        else
        {
            pregunta = $"¿Marcar como terminada la subtarea «{sub.Nombre}»?\n\nVa a verse tachada y deja de ofrecerse a los empleados. Las horas ya registradas con ella se conservan. Podés reabrirla cuando quieras.";
            if (sub.Activa && obra?.SubtareasActivas == 1)
                pregunta += "\n\nEs la ÚLTIMA subtarea pendiente de la obra: desde ahora se podrá registrar directamente en la obra, sin elegir subtarea.";
        }
        if (!Dialogos.Confirmar(this, pregunta)) return;
        if (await Llamar(_api.ActualizarSubtareaAsync(sub.Id, terminada: !sub.Terminada)) is null) return;
        await CargarObrasAsync();
        await CargarSubtareasAsync();
        await ActualizarContadorAvisosAsync(); // terminarla resuelve los avisos pendientes de esa subtarea
    }

    // ================================================================ Avisos de «terminé esta subtarea»

    private void MostrarContadorAvisos(int nuevos) => TabAvisos.Header = nuevos > 0 ? $"Avisos ({nuevos})" : "Avisos";

    /// <summary>Actualiza en silencio el número de la pestaña (lo llama el reloj: no muestra errores).</summary>
    private async Task ActualizarContadorAvisosAsync()
    {
        var r = await _api.AvisosAsync();
        if (r.Ok && r.Valor is not null) MostrarContadorAvisos(r.Valor.Count);
        var f = await _api.AlertasFaltasAsync();
        if (f.Ok && f.Valor is not null) TabFaltas.Header = f.Valor.SinRevisar > 0 ? $"Faltas ({f.Valor.SinRevisar})" : "Faltas";
    }

    private async Task CargarAvisosAsync()
    {
        var todos = ChkAvisosTodos.IsChecked == true;
        var elegido = (GridAvisos.SelectedItem as FilaAviso)?.D.Id;
        if (await Llamar(_api.AvisosAsync(todos ? "todos" : null)) is not { } lista) return;
        GridAvisos.ItemsSource = lista.Select(x => new FilaAviso(x)).ToList();
        if (elegido is { } id) GridAvisos.SelectedItem = GridAvisos.ItemsSource.Cast<FilaAviso>().FirstOrDefault(f => f.D.Id == id);
        var nuevos = lista.Count(x => x.Estado == "nuevo");
        if (!todos || lista.Count == 0 || nuevos == lista.Count) MostrarContadorAvisos(nuevos); else await ActualizarContadorAvisosAsync();
        Estado(nuevos == 0 ? "No hay avisos sin revisar." : $"{nuevos} aviso(s) sin revisar.");
    }

    private async void BtnAvisosActualizar_Click(object sender, RoutedEventArgs e) => await CargarAvisosAsync();

    private async void ChkAvisosTodos_Cambio(object sender, RoutedEventArgs e)
    {
        if (IsLoaded) await CargarAvisosAsync();
    }

    private FilaAviso? AvisoElegido()
    {
        if (GridAvisos.SelectedItem is not FilaAviso f) { Dialogos.Info(this, "Elegí primero un aviso de la tabla."); return null; }
        if (f.D.Estado != "nuevo") { Dialogos.Info(this, "Ese aviso ya fue revisado."); return null; }
        return f;
    }

    private async void BtnAvisoAceptar_Click(object sender, RoutedEventArgs e)
    {
        if (AvisoElegido() is not { } f) return;
        if (!Dialogos.Confirmar(this, $"¿Marcar como terminada la subtarea «{f.D.Subtarea}» de «{f.D.Obra}»?\n\n{f.D.Empleado} avisó que la terminó. Va a verse tachada y deja de ofrecerse a los empleados (podés reabrirla desde Obras).")) return;
        if (await Llamar(_api.AceptarAvisoAsync(f.D.Id)) is null) return;
        await CargarAvisosAsync();
    }

    private async void BtnAvisoDescartar_Click(object sender, RoutedEventArgs e)
    {
        if (AvisoElegido() is not { } f) return;
        if (!Dialogos.Confirmar(this, $"¿Descartar el aviso de {f.D.Empleado}?\n\nLa subtarea «{f.D.Subtarea}» de «{f.D.Obra}» sigue pendiente.")) return;
        if (await Llamar(_api.DescartarAvisoAsync(f.D.Id)) is null) return;
        await CargarAvisosAsync();
    }

    /// <summary>Subtareas de una obra para los cuadros de corrección y alta (siempre desde el servidor, para que estén al día).</summary>
    private async Task<List<SubtareaAdminDto>> SubtareasDeObraAsync(int obraId) =>
        await Llamar(_api.SubtareasAsync(obraId)) ?? [];

    private ObraAdminDto? ObraElegida()
    {
        if (GridObras.SelectedItem is FilaObra f) return f.D;
        Dialogos.Info(this, "Elegí primero una obra de la tabla.");
        return null;
    }

    private async void BtnObraNueva_Click(object sender, RoutedEventArgs e)
    {
        var nombre = CajaNombre();
        if (!Dialogos.Formulario(this, "Nueva obra", new List<(string, FrameworkElement)> { ("Nombre de la obra", nombre) },
            () => string.IsNullOrWhiteSpace(nombre.Text) ? "Escribí el nombre." : null, aceptar: "Crear", ancho: 420)) return;
        if (await Llamar(_api.CrearObraAsync(nombre.Text.Trim())) is null) return;
        await CargarObrasAsync();
    }

    private async void BtnObraRenombrar_Click(object sender, RoutedEventArgs e)
    {
        if (ObraElegida() is not { } obra) return;
        var nombre = CajaNombre(obra.Nombre);
        if (!Dialogos.Formulario(this, "Renombrar obra", new List<(string, FrameworkElement)> { ("Nombre de la obra", nombre) },
            () => string.IsNullOrWhiteSpace(nombre.Text) ? "Escribí el nombre." : null, ancho: 420)) return;
        if (await Llamar(_api.ActualizarObraAsync(obra.Id, nombre: nombre.Text.Trim())) is null) return;
        await CargarObrasAsync();
    }

    private async void BtnObraActivar_Click(object sender, RoutedEventArgs e)
    {
        if (ObraElegida() is not { } obra) return;
        var pregunta = obra.Activa
            ? $"¿Desactivar la obra «{obra.Nombre}»?\n\nDeja de aparecer en el panel para elegirla. Las horas ya registradas se conservan."
            : $"¿Volver a activar la obra «{obra.Nombre}»?";
        if (!Dialogos.Confirmar(this, pregunta)) return;
        if (await Llamar(_api.ActualizarObraAsync(obra.Id, activo: !obra.Activa)) is null) return;
        await CargarObrasAsync();
    }

    // ================================================================ Administradores

    private async Task CargarAdminsAsync()
    {
        if (await Llamar(_api.AdministradoresAsync()) is not { } lista) return;
        GridAdmins.ItemsSource = lista.Select(x => new FilaAdmin(x)).ToList();
    }

    private AdminDto? AdminElegido()
    {
        if (GridAdmins.SelectedItem is FilaAdmin f) return f.D;
        Dialogos.Info(this, "Elegí primero un administrador de la tabla.");
        return null;
    }

    private async void BtnAdmNuevo_Click(object sender, RoutedEventArgs e)
    {
        var usuario = CajaNombre();
        var nombre = CajaNombre();
        if (!Dialogos.Formulario(this, "Nuevo administrador", new List<(string, FrameworkElement)> { ("Usuario", usuario), ("Nombre completo", nombre) },
            () => string.IsNullOrWhiteSpace(usuario.Text) ? "Escribí el usuario." : null, aceptar: "Crear", ancho: 440,
            intro: "Cada administrador tiene su propio usuario: así el historial de cambios dice quién hizo cada corrección.")) return;
        if (await Llamar(_api.CrearAdministradorAsync(usuario.Text.Trim(), nombre.Text.Trim())) is not { } r) return;
        await CargarAdminsAsync();
        Dialogos.MostrarSecreto(this, "Administrador creado", r.Administrador.Usuario, "Clave temporal", r.ClaveTemporal,
            "Entregásela a la persona. En su primer ingreso va a tener que elegir una clave propia.");
    }

    private async void BtnAdmActivar_Click(object sender, RoutedEventArgs e)
    {
        if (AdminElegido() is not { } a) return;
        if (!Dialogos.Confirmar(this, a.Activo ? $"¿Desactivar al administrador «{a.Usuario}»?" : $"¿Volver a activar al administrador «{a.Usuario}»?")) return;
        if (await Llamar(_api.ActivarAdministradorAsync(a.Id, !a.Activo)) is null) return;
        await CargarAdminsAsync();
    }

    private async void BtnAdmClave_Click(object sender, RoutedEventArgs e)
    {
        if (AdminElegido() is not { } a) return;
        if (!Dialogos.Confirmar(this, $"¿Resetear la clave de «{a.Usuario}»?\n\nSe genera una clave temporal y la anterior deja de funcionar.")) return;
        if (await Llamar(_api.ResetearClaveAdminAsync(a.Id)) is not { } r) return;
        Dialogos.MostrarSecreto(this, "Clave reseteada", a.Usuario, "Clave temporal", r.ClaveTemporal, "Entregásela a la persona. Al ingresar va a tener que elegir una propia.");
    }

    // ================================================================ Auditoría

    private async Task CargarAuditoriaAsync()
    {
        if (await Llamar(_api.AuditoriaAsync(_auditoriaRegistro)) is not { } lista) return;
        GridAuditoria.ItemsSource = lista.Select(x => new FilaAuditoria(x)).ToList();
        BtnAudQuitar.Visibility = _auditoriaRegistro is null ? Visibility.Collapsed : Visibility.Visible;
        TxtAudFiltro.Text = _auditoriaRegistro is null
            ? (lista.Count == 0 ? "Todavía no hay cambios registrados." : $"{lista.Count} cambio(s) registrados.")
            : (lista.Count == 0 ? "Ese registro nunca fue modificado por un administrador." : $"Historial del registro elegido: {lista.Count} cambio(s).");
    }

    private async void BtnAudActualizar_Click(object sender, RoutedEventArgs e) => await CargarAuditoriaAsync();

    private async void BtnAudQuitar_Click(object sender, RoutedEventArgs e)
    {
        _auditoriaRegistro = null;
        await CargarAuditoriaAsync();
    }

    // ================================================================ Sistema

    private async Task MostrarEstadoExcelAsync()
    {
        var r = await _api.EmpleadosExcelAsync();
        if (!r.Ok || r.Valor is not { } x) { TxtExcelEstado.Text = r.SinRed ? "No se pudo consultar al servidor." : "No se pudo consultar el estado."; return; }
        BtnExcelSincronizar.IsEnabled = x.Configurado;
        if (!x.Configurado) { TxtExcelEstado.Text = "Los empleados se manejan desde esta app (no hay un Excel de empleados configurado en el servidor)."; return; }
        var t = new System.Text.StringBuilder();
        t.Append($"Archivo: {x.Archivo}\n");
        t.Append(x.UltimaUtc is { } u ? $"Última sincronización: {u.ToLocalTime():dd/MM/yyyy HH:mm:ss} — {(x.Ok == true ? "correcta" : "con problemas")}.\n" : "Todavía no se sincronizó.\n");
        if (!string.IsNullOrWhiteSpace(x.Mensaje)) t.Append(x.Mensaje + "\n");
        t.Append($"{x.Empleados} empleado(s) activo(s) · {x.Administradores} administrador(es) activo(s). El servidor revisa el archivo cada 10 segundos y se actualiza solo cuando cambia.");
        foreach (var err in x.Errores.Take(15)) t.Append($"\n⚠ Fila {err.Fila}: {err.Mensaje}");
        if (x.Errores.Count > 15) t.Append($"\n⚠ …y {x.Errores.Count - 15} más.");
        TxtExcelEstado.Text = t.ToString();
    }

    private async void BtnExcelSincronizar_Click(object sender, RoutedEventArgs e)
    {
        Estado("Sincronizando con el Excel…");
        if (await Llamar(_api.SincronizarEmpleadosExcelAsync()) is null) { Estado(""); return; }
        await MostrarEstadoExcelAsync();
        Estado("Sincronización terminada.");
    }

    private async Task CargarBackupsAsync()
    {
        await MostrarEstadoExcelAsync();
        var v = await _api.VersionPanelAsync();
        TxtPanelPublicado.Text = v.Ok && v.Valor is { } p
            ? $"Versión publicada: {p.Version} ({p.Bytes / 1024 / 1024} MB, publicada el {p.PublicadoUtc.ToLocalTime():dd/MM/yyyy HH:mm}). Los paneles de los empleados se actualizan solos a esta versión: se bajan en segundo plano y se instalan cuando no hay un registro en curso."
            : v.SinRed ? "No se pudo consultar al servidor." : "Todavía no hay un Play.exe publicado en el servidor (carpeta datos\\descargas).";
        if (await Llamar(_api.BackupsAsync()) is not { } r) return;
        TxtBackupCarpeta.Text = $"Carpeta en el servidor: {r.Carpeta}";
        GridBackups.ItemsSource = r.Backups.Select(x => new FilaBackup(x)).ToList();
    }

    private async void BtnBackupLista_Click(object sender, RoutedEventArgs e) => await CargarBackupsAsync();

    private async void BtnBackup_Click(object sender, RoutedEventArgs e)
    {
        Estado("Haciendo la copia…");
        if (await Llamar(_api.HacerBackupAsync()) is not { } r) { Estado(""); return; }
        Estado($"Copia creada: {r.Archivo}");
        await CargarBackupsAsync();
    }

    private void BtnServidor_Click(object sender, RoutedEventArgs e)
    {
        var url = Dialogos.PedirServidor(this, App.Ajustes.ServidorUrl);
        if (url is null || url == App.Ajustes.ServidorUrl) return;
        App.Ajustes.ServidorUrl = url;
        App.GuardarAjustes();
        App.Reiniciar();
    }
}
