using System.Windows;
using System.Windows.Controls;
using System.Windows.Media;
using Play.Client;

namespace Play.Admin;

/// <summary>Ingreso del administrador. Si tiene clave temporal, obliga a elegir una nueva.</summary>
public sealed class LoginWindow : Window
{
    private readonly AdminApi _api;
    private readonly TextBox _usuario = new() { Height = 26, VerticalContentAlignment = VerticalAlignment.Center };
    private readonly PasswordBox _clave = new() { Height = 26, VerticalContentAlignment = VerticalAlignment.Center };
    private readonly TextBlock _error = new() { Foreground = Brushes.Firebrick, TextWrapping = TextWrapping.Wrap, Visibility = Visibility.Collapsed, Margin = new Thickness(0, 6, 0, 0) };
    private readonly Button _entrar = new() { Content = "Ingresar", IsDefault = true, Margin = new Thickness(0), Padding = new Thickness(18, 5, 18, 5) };

    public string Usuario { get; private set; } = "";

    public LoginWindow(AdminApi api)
    {
        _api = api;
        Title = "Play · Administración";
        Width = 360;
        SizeToContent = SizeToContent.Height;
        ResizeMode = ResizeMode.NoResize;
        WindowStartupLocation = WindowStartupLocation.CenterScreen;

        var servidor = new Button { Content = "Servidor…", ToolTip = "Cambiar la dirección del servidor" };
        servidor.Click += (_, _) =>
        {
            var url = Dialogos.PedirServidor(this, App.Ajustes.ServidorUrl);
            if (url is null || url == App.Ajustes.ServidorUrl) return;
            App.Ajustes.ServidorUrl = url;
            App.GuardarAjustes();
            App.Reiniciar();
        };
        var fila = new Grid { Margin = new Thickness(0, 12, 0, 0) };
        fila.ColumnDefinitions.Add(new ColumnDefinition { Width = new GridLength(1, GridUnitType.Star) });
        fila.ColumnDefinitions.Add(new ColumnDefinition { Width = GridLength.Auto });
        var servidorTexto = new TextBlock { Text = App.Ajustes.ServidorUrl, Foreground = Brushes.Gray, VerticalAlignment = VerticalAlignment.Center, TextTrimming = TextTrimming.CharacterEllipsis };
        Grid.SetColumn(_entrar, 1);
        fila.Children.Add(servidorTexto);
        fila.Children.Add(_entrar);

        var panel = new StackPanel { Margin = new Thickness(20) };
        panel.Children.Add(new TextBlock { Text = "Administración de horas", FontSize = 18, FontWeight = FontWeights.SemiBold, Margin = new Thickness(0, 0, 0, 12) });
        panel.Children.Add(new TextBlock { Text = "Usuario" });
        panel.Children.Add(_usuario);
        panel.Children.Add(new TextBlock { Text = "Clave", Margin = new Thickness(0, 8, 0, 0) });
        panel.Children.Add(_clave);
        panel.Children.Add(_error);
        panel.Children.Add(fila);
        panel.Children.Add(servidor);
        servidor.HorizontalAlignment = HorizontalAlignment.Left;
        servidor.Margin = new Thickness(0, 10, 0, 0);
        Content = panel;

        _usuario.Text = App.Ajustes.UltimoUsuario ?? "";
        Loaded += (_, _) => (string.IsNullOrEmpty(_usuario.Text) ? (Control)_usuario : _clave).Focus();
        _entrar.Click += async (_, _) => await EntrarAsync();
    }

    private void MostrarError(string texto)
    {
        _error.Text = texto;
        _error.Visibility = Visibility.Visible;
    }

    private async Task EntrarAsync()
    {
        var usuario = _usuario.Text.Trim();
        if (usuario.Length == 0 || _clave.Password.Length == 0) { MostrarError("Ingresá el usuario y la clave."); return; }

        _entrar.IsEnabled = false;
        _error.Visibility = Visibility.Collapsed;
        try
        {
            var r = await _api.LoginAsync(usuario, _clave.Password);
            if (r.SinRed) { MostrarError($"No hay conexión con el servidor ({App.Ajustes.ServidorUrl}). Revisá que esté encendido y que estés en la misma red."); return; }
            if ((int?)r.Status == 423) { MostrarError("Demasiados intentos. Esperá unos minutos."); return; }
            if (!r.Ok || r.Valor is null) { MostrarError("Usuario o clave incorrectos."); _clave.Clear(); _clave.Focus(); return; }

            _api.Token = r.Valor.Token;
            if (r.Valor.DebeCambiarClave && !await CambiarClaveObligatoriaAsync(_clave.Password)) { _api.Token = null; _clave.Clear(); return; }

            Usuario = usuario;
            App.Ajustes.UltimoUsuario = usuario;
            App.GuardarAjustes();
            DialogResult = true;
        }
        finally { _entrar.IsEnabled = true; }
    }

    /// <summary>La clave temporal solo sirve para entrar: hay que elegir una propia antes de seguir.</summary>
    private async Task<bool> CambiarClaveObligatoriaAsync(string claveActual)
    {
        var nueva = new PasswordBox { Height = 26, VerticalContentAlignment = VerticalAlignment.Center };
        var repetir = new PasswordBox { Height = 26, VerticalContentAlignment = VerticalAlignment.Center };
        var campos = new List<(string, FrameworkElement)> { ("Clave nueva", nueva), ("Repetir", repetir) };
        string? error = null;
        while (true)
        {
            var aceptado = Dialogos.Formulario(this, "Elegí tu clave", campos, () =>
                nueva.Password.Length < 8 ? "La clave debe tener al menos 8 caracteres."
                : nueva.Password != repetir.Password ? "Las dos claves no coinciden."
                : nueva.Password == claveActual ? "Elegí una clave distinta a la temporal."
                : null,
                aceptar: "Guardar clave", intro: "Es tu primer ingreso (o te resetearon la clave). Elegí una clave propia de al menos 8 caracteres.");
            if (!aceptado) return false;

            var r = await _api.CambiarClaveAsync(claveActual, nueva.Password);
            if (r.Ok) return true;
            error = r.SinRed ? "Se cortó la conexión con el servidor." : "No se pudo cambiar la clave. Probá de nuevo.";
            Dialogos.Aviso(this, error);
        }
    }
}
