using System.Net.Http;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Play.Client;

namespace Play.Panel;

/// <summary>Ventanas auxiliares armadas por código (pocas y simples).</summary>
internal static class Dialogos
{
    /// <summary>«192.168.1.50» → «http://192.168.1.50:8080». Devuelve null si no es una dirección válida.</summary>
    public static string? NormalizarServidor(string? texto)
    {
        texto = (texto ?? "").Trim().TrimEnd('/');
        if (texto.Length == 0) return null;
        if (!texto.Contains("://")) texto = "http://" + texto;
        if (!Regex.IsMatch(texto, @"^https?://[^/]+:\d+$")) texto += ":8080";
        return Uri.TryCreate(texto, UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https" ? uri.GetLeftPart(UriPartial.Authority) : null;
    }

    /// <summary>Pide la dirección del servidor y comprueba que responda. Devuelve la dirección guardable o null si se cancela.</summary>
    public static string? PedirServidor(Window? owner, string? actual)
    {
        var caja = new TextBox { Text = actual ?? "", Height = 26, VerticalContentAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 8, 0, 4) };
        var error = new TextBlock { Foreground = Brushes.Firebrick, TextWrapping = TextWrapping.Wrap, Visibility = Visibility.Collapsed, Margin = new Thickness(0, 0, 0, 6) };
        var boton = new Button { Content = "Probar y guardar", IsDefault = true, Padding = new Thickness(14, 4, 14, 4), HorizontalAlignment = HorizontalAlignment.Right };
        var cancelar = new Button { Content = "Cancelar", IsCancel = true, Padding = new Thickness(14, 4, 14, 4), Margin = new Thickness(0, 0, 8, 0) };
        var fila = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
        fila.Children.Add(cancelar);
        fila.Children.Add(boton);

        var panel = new StackPanel { Margin = new Thickness(16) };
        panel.Children.Add(new TextBlock { Text = "Escribí la dirección del servidor de la empresa.\nTe la da el administrador (por ejemplo 192.168.1.50:8080).", TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(caja);
        panel.Children.Add(error);
        panel.Children.Add(fila);

        var ventana = new Window
        {
            Title = "Servidor de Play", Width = 400, SizeToContent = SizeToContent.Height, ResizeMode = ResizeMode.NoResize, Topmost = true,
            WindowStartupLocation = owner is null ? WindowStartupLocation.CenterScreen : WindowStartupLocation.CenterOwner,
            Owner = owner, Content = panel,
        };

        string? resultado = null;
        boton.Click += async (_, _) =>
        {
            var url = NormalizarServidor(caja.Text);
            if (url is null) { error.Text = "La dirección no es válida."; error.Visibility = Visibility.Visible; return; }
            boton.IsEnabled = false;
            error.Visibility = Visibility.Collapsed;
            try
            {
                using var http = new HttpClient { Timeout = TimeSpan.FromSeconds(5) };
                using var r = await http.GetAsync(url + "/api/estado");
                if (!r.IsSuccessStatusCode) throw new HttpRequestException();
                resultado = url;
                ventana.DialogResult = true;
            }
            catch (Exception ex) when (ex is HttpRequestException or TaskCanceledException)
            {
                error.Text = $"No se pudo conectar a {url}. Revisá la dirección y que estés en la red de la empresa.";
                error.Visibility = Visibility.Visible;
                boton.IsEnabled = true;
            }
        };
        caja.Loaded += (_, _) => { caja.Focus(); caja.SelectAll(); };
        ventana.ShowDialog();
        return resultado;
    }

    /// <summary>
    /// Confirma el cambio a una obra que tiene subtareas y obliga a elegir una en el mismo cuadro.
    /// Devuelve (true, subtarea) si aceptó, o (false, null) si canceló.
    /// </summary>
    public static (bool Ok, int? SubtareaId) ConfirmarCambioConSubtarea(Window owner, string obraActual, string obraNueva, List<ItemLista> subtareas)
    {
        var combo = new ComboBox { ItemsSource = subtareas, DisplayMemberPath = "Nombre", Margin = new Thickness(0, 10, 0, 0), Height = 26 };
        var error = new TextBlock { Foreground = Brushes.Firebrick, Visibility = Visibility.Collapsed, Margin = new Thickness(0, 6, 0, 0) };
        var cambiar = new Button { Content = "Cambiar", IsDefault = true, Padding = new Thickness(14, 4, 14, 4), Margin = new Thickness(0, 0, 8, 0) };
        var cancelar = new Button { Content = "Cancelar", IsCancel = true, Padding = new Thickness(14, 4, 14, 4) };
        var fila = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 14, 0, 0) };
        fila.Children.Add(cambiar);
        fila.Children.Add(cancelar);

        var panel = new StackPanel { Margin = new Thickness(16) };
        panel.Children.Add(new TextBlock { Text = $"¿Cambiar a «{obraNueva}»?\n\nSe cierra el registro de «{obraActual}» y empieza uno nuevo.", TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = "Esta obra tiene subtareas: elegí una.", FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 10, 0, 0) });
        panel.Children.Add(combo);
        panel.Children.Add(error);
        panel.Children.Add(fila);

        var ventana = new Window
        {
            Title = "Cambiar de obra", Width = 380, SizeToContent = SizeToContent.Height, ResizeMode = ResizeMode.NoResize, Topmost = true,
            WindowStartupLocation = WindowStartupLocation.CenterOwner, Owner = owner, Content = panel, ShowInTaskbar = false,
        };
        cambiar.Click += (_, _) =>
        {
            if (combo.SelectedItem is null) { error.Text = "Elegí una subtarea."; error.Visibility = Visibility.Visible; return; }
            ventana.DialogResult = true;
        };
        var acepto = ventana.ShowDialog() == true;
        return acepto ? (true, (combo.SelectedItem as ItemLista)?.Id) : (false, null);
    }

    /// <summary>
    /// «Avisar que terminé una subtarea»: el empleado elige obra y subtarea y le avisa al administrador.
    /// No tacha nada: el administrador revisa el aviso y decide.
    /// </summary>
    public static void AvisarSubtareaTerminada(Window owner, PanelController c)
    {
        var obras = c.ObrasConSubtareas();
        var panel = new StackPanel { Margin = new Thickness(16) };
        var cerrar = new Button { Content = "Cerrar", IsCancel = true, Padding = new Thickness(14, 4, 14, 4) };
        var ventana = new Window
        {
            Title = "Avisar que terminé una subtarea", Width = 380, SizeToContent = SizeToContent.Height, ResizeMode = ResizeMode.NoResize, Topmost = true,
            WindowStartupLocation = WindowStartupLocation.CenterOwner, Owner = owner, Content = panel, ShowInTaskbar = false,
        };

        if (obras.Count == 0)
        {
            panel.Children.Add(new TextBlock { Text = "Todavía no hay subtareas cargadas para avisar.", TextWrapping = TextWrapping.Wrap });
            cerrar.HorizontalAlignment = HorizontalAlignment.Right;
            cerrar.Margin = new Thickness(0, 14, 0, 0);
            panel.Children.Add(cerrar);
            ventana.ShowDialog();
            return;
        }

        var cmbObra = new ComboBox { ItemsSource = obras, DisplayMemberPath = "Nombre", Height = 26, Margin = new Thickness(0, 4, 0, 8) };
        var cmbSub = new ComboBox { DisplayMemberPath = "Nombre", Height = 26, Margin = new Thickness(0, 4, 0, 0) };
        var resultado = new TextBlock { TextWrapping = TextWrapping.Wrap, Visibility = Visibility.Collapsed, Margin = new Thickness(0, 10, 0, 0) };
        var avisar = new Button { Content = "Avisar", IsDefault = true, Padding = new Thickness(14, 4, 14, 4), Margin = new Thickness(0, 0, 8, 0) };
        var fila = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 14, 0, 0) };
        fila.Children.Add(avisar);
        fila.Children.Add(cerrar);

        panel.Children.Add(new TextBlock { Text = "Elegí la obra y la subtarea que terminaste. El administrador lo va a revisar.", TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = "Obra", FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 10, 0, 0) });
        panel.Children.Add(cmbObra);
        panel.Children.Add(new TextBlock { Text = "Subtarea", FontWeight = FontWeights.SemiBold });
        panel.Children.Add(cmbSub);
        panel.Children.Add(resultado);
        panel.Children.Add(fila);

        cmbObra.SelectionChanged += (_, _) =>
        {
            cmbSub.ItemsSource = cmbObra.SelectedItem is ItemLista o ? c.SubtareasDe(o.Id) : null;
            cmbSub.SelectedIndex = -1;
            resultado.Visibility = Visibility.Collapsed;
            avisar.IsEnabled = true;
        };
        // Si está registrando en una obra con subtareas, se sugiere esa.
        if (c.ObraActualId is { } actual && obras.FirstOrDefault(o => o.Id == actual) is { } sugerida)
        {
            cmbObra.SelectedItem = sugerida;
            cmbSub.SelectedItem = c.SubtareasDe(actual).FirstOrDefault(s => s.Id == c.SubtareaActualId);
        }

        avisar.Click += async (_, _) =>
        {
            if (cmbSub.SelectedItem is not ItemLista sub)
            {
                resultado.Foreground = Brushes.Firebrick; resultado.Text = "Elegí la obra y la subtarea."; resultado.Visibility = Visibility.Visible;
                return;
            }
            avisar.IsEnabled = false;
            var (ok, mensaje) = await c.AvisarSubtareaAsync(sub.Id);
            resultado.Foreground = ok ? Brushes.ForestGreen : Brushes.Firebrick;
            resultado.Text = mensaje;
            resultado.Visibility = Visibility.Visible;
            avisar.IsEnabled = !ok; // si ya avisó, no hace falta repetir; si falló, puede reintentar
        };
        ventana.ShowDialog();
    }

    /// <summary>Pregunta qué hacer con el tiempo inactivo. true = descontarlo y pausar; false = contarlo como trabajo.</summary>
    public static bool PreguntarInactividad(TimeSpan duracion, DateTime? desde)
    {
        var horas = duracion.TotalHours >= 1 ? $"{(int)duracion.TotalHours} h {duracion.Minutes} min" : $"{(int)duracion.TotalMinutes} min";
        var cuando = desde is { } d ? $" (desde las {d:HH:mm})" : "";
        var descontar = new Button { Content = "Descontarlo y pausar", IsDefault = true, Padding = new Thickness(12, 5, 12, 5), Margin = new Thickness(0, 0, 8, 0) };
        var contar = new Button { Content = "Contarlo como trabajo", Padding = new Thickness(12, 5, 12, 5) };
        var fila = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 14, 0, 0) };
        fila.Children.Add(descontar);
        fila.Children.Add(contar);

        var panel = new StackPanel { Margin = new Thickness(16) };
        panel.Children.Add(new TextBlock { Text = $"Estuviste {horas} sin usar la computadora{cuando}.", FontWeight = FontWeights.SemiBold, TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(new TextBlock { Text = "¿Qué hacemos con ese tiempo?", Margin = new Thickness(0, 6, 0, 0) });
        panel.Children.Add(fila);

        var ventana = new Window
        {
            Title = "Play: ¿seguís trabajando?", Width = 420, SizeToContent = SizeToContent.Height, ResizeMode = ResizeMode.NoResize,
            Topmost = true, WindowStartupLocation = WindowStartupLocation.CenterScreen, Content = panel, ShowInTaskbar = true,
        };
        bool? eleccion = null;
        descontar.Click += (_, _) => { eleccion = true; ventana.Close(); };
        contar.Click += (_, _) => { eleccion = false; ventana.Close(); };
        // No se puede cerrar sin elegir: así no se pierde ni se infla tiempo por accidente.
        ventana.Closing += (_, e) => e.Cancel = eleccion is null;
        ventana.Loaded += (_, _) => ventana.Activate();
        ventana.ShowDialog();
        return eleccion == true;
    }
}
