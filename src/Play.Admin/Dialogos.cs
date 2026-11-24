using System.Net.Http;
using System.Text.RegularExpressions;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;

namespace Play.Admin;

/// <summary>Ventanas auxiliares armadas por código.</summary>
internal static class Dialogos
{
    public static string? NormalizarServidor(string? texto)
    {
        texto = (texto ?? "").Trim().TrimEnd('/');
        if (texto.Length == 0) return null;
        if (!texto.Contains("://")) texto = "http://" + texto;
        if (!Regex.IsMatch(texto, @"^https?://[^/]+:\d+$")) texto += ":8080";
        return Uri.TryCreate(texto, UriKind.Absolute, out var uri) && uri.Scheme is "http" or "https" ? uri.GetLeftPart(UriPartial.Authority) : null;
    }

    private static Window Ventana(Window? owner, string titulo, double ancho, UIElement contenido) => new()
    {
        Title = titulo, Width = ancho, SizeToContent = SizeToContent.Height, ResizeMode = ResizeMode.NoResize,
        WindowStartupLocation = owner is null ? WindowStartupLocation.CenterScreen : WindowStartupLocation.CenterOwner,
        Owner = owner, Content = contenido, ShowInTaskbar = owner is null,
    };

    public static string? PedirServidor(Window? owner, string? actual)
    {
        var caja = new TextBox { Text = actual ?? "", Height = 26, VerticalContentAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 8, 0, 4) };
        var error = new TextBlock { Foreground = Brushes.Firebrick, TextWrapping = TextWrapping.Wrap, Visibility = Visibility.Collapsed, Margin = new Thickness(0, 0, 0, 6) };
        var ok = new Button { Content = "Probar y guardar", IsDefault = true };
        var cancelar = new Button { Content = "Cancelar", IsCancel = true };
        var fila = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
        fila.Children.Add(cancelar);
        fila.Children.Add(ok);
        ok.Margin = new Thickness(0);
        var panel = new StackPanel { Margin = new Thickness(16) };
        panel.Children.Add(new TextBlock { Text = "Dirección del servidor de Play (por ejemplo 192.168.1.50:8080).", TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(caja);
        panel.Children.Add(error);
        panel.Children.Add(fila);
        var ventana = Ventana(owner, "Servidor de Play", 400, panel);

        string? resultado = null;
        ok.Click += async (_, _) =>
        {
            var url = NormalizarServidor(caja.Text);
            if (url is null) { error.Text = "La dirección no es válida."; error.Visibility = Visibility.Visible; return; }
            ok.IsEnabled = false;
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
                error.Text = $"No se pudo conectar a {url}. Revisá la dirección y que el servidor esté encendido.";
                error.Visibility = Visibility.Visible;
                ok.IsEnabled = true;
            }
        };
        caja.Loaded += (_, _) => { caja.Focus(); caja.SelectAll(); };
        ventana.ShowDialog();
        return resultado;
    }

    /// <summary>Formulario simple: etiquetas + controles. «validar» devuelve un mensaje de error o null si está todo bien.</summary>
    public static bool Formulario(Window? owner, string titulo, IList<(string Etiqueta, FrameworkElement Control)> campos, Func<string?> validar,
        string aceptar = "Guardar", double ancho = 460, string? intro = null)
    {
        var grilla = new Grid { Margin = new Thickness(0, 4, 0, 6) };
        grilla.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(110) });
        grilla.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        for (var i = 0; i < campos.Count; i++)
        {
            grilla.RowDefinitions.Add(new RowDefinition { Height = GridLength.Auto });
            var etiqueta = new TextBlock { Text = campos[i].Etiqueta, VerticalAlignment = VerticalAlignment.Center, Margin = new Thickness(0, 4, 8, 4) };
            var control = campos[i].Control;
            control.Margin = new Thickness(0, 4, 0, 4);
            Grid.SetRow(etiqueta, i);
            Grid.SetRow(control, i);
            Grid.SetColumn(control, 1);
            grilla.Children.Add(etiqueta);
            grilla.Children.Add(control);
        }

        var error = new TextBlock { Foreground = Brushes.Firebrick, TextWrapping = TextWrapping.Wrap, Visibility = Visibility.Collapsed, Margin = new Thickness(0, 0, 0, 6) };
        var ok = new Button { Content = aceptar, IsDefault = true, Margin = new Thickness(0) };
        var cancelar = new Button { Content = "Cancelar", IsCancel = true };
        var fila = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
        fila.Children.Add(cancelar);
        fila.Children.Add(ok);

        var panel = new StackPanel { Margin = new Thickness(16) };
        if (intro is not null) panel.Children.Add(new TextBlock { Text = intro, TextWrapping = TextWrapping.Wrap, Margin = new Thickness(0, 0, 0, 6) });
        panel.Children.Add(grilla);
        panel.Children.Add(error);
        panel.Children.Add(fila);
        var ventana = Ventana(owner, titulo, ancho, panel);

        ok.Click += (_, _) =>
        {
            var e = validar();
            if (e is null) { ventana.DialogResult = true; return; }
            error.Text = e;
            error.Visibility = Visibility.Visible;
        };
        ventana.Loaded += (_, _) => campos[0].Control.Focus();
        return ventana.ShowDialog() == true;
    }

    /// <summary>Muestra un dato que solo se ve una vez (PIN o clave temporal) con botón para copiarlo.</summary>
    public static void MostrarSecreto(Window? owner, string titulo, string quien, string etiqueta, string valor, string nota)
    {
        var caja = new TextBox { Text = valor, IsReadOnly = true, FontSize = 26, FontFamily = new FontFamily("Consolas"), HorizontalContentAlignment = HorizontalAlignment.Center, Margin = new Thickness(0, 8, 0, 8) };
        var copiar = new Button { Content = "Copiar" };
        var cerrar = new Button { Content = "Listo", IsDefault = true, Margin = new Thickness(0) };
        copiar.Click += (_, _) => { Clipboard.SetText(valor); copiar.Content = "Copiado"; };
        var fila = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right };
        fila.Children.Add(copiar);
        fila.Children.Add(cerrar);
        var panel = new StackPanel { Margin = new Thickness(16) };
        panel.Children.Add(new TextBlock { Text = $"{etiqueta} de {quien}:", FontWeight = FontWeights.SemiBold });
        panel.Children.Add(caja);
        panel.Children.Add(new TextBlock { Text = nota, TextWrapping = TextWrapping.Wrap, Foreground = Brushes.DimGray, Margin = new Thickness(0, 0, 0, 10) });
        panel.Children.Add(fila);
        var ventana = Ventana(owner, titulo, 420, panel);
        cerrar.Click += (_, _) => ventana.Close();
        ventana.ShowDialog();
    }

    /// <summary>Pregunta Sí / No con una ventana propia (igual que las demás del programa; el «No» es lo que se elige con Esc).</summary>
    public static bool Confirmar(Window? owner, string texto, string titulo = "Confirmar")
    {
        var si = new Button { Content = "Sí", IsDefault = true, MinWidth = 80 };
        var no = new Button { Content = "No", IsCancel = true, MinWidth = 80, Margin = new Thickness(0) };
        var fila = new StackPanel { Orientation = Orientation.Horizontal, HorizontalAlignment = HorizontalAlignment.Right, Margin = new Thickness(0, 16, 0, 0) };
        fila.Children.Add(si);
        fila.Children.Add(no);
        var panel = new StackPanel { Margin = new Thickness(18) };
        panel.Children.Add(new TextBlock { Text = texto, TextWrapping = TextWrapping.Wrap });
        panel.Children.Add(fila);
        var ventana = Ventana(owner, titulo, 460, panel);
        si.Click += (_, _) => ventana.DialogResult = true;
        return ventana.ShowDialog() == true;
    }

    public static void Info(Window? owner, string texto, string titulo = "Play Administración") =>
        MessageBox.Show(owner!, texto, titulo, MessageBoxButton.OK, MessageBoxImage.Information);

    public static void Aviso(Window? owner, string texto, string titulo = "Play Administración") =>
        MessageBox.Show(owner!, texto, titulo, MessageBoxButton.OK, MessageBoxImage.Warning);
}
