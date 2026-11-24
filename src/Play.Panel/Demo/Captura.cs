using System.IO;
using System.Windows;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using Play.Client;

namespace Play.Panel.Demo;

/// <summary>
/// Herramienta de desarrollo: <c>Play.exe --captura carpeta</c> abre la interfaz con una API de ejemplo, recorre sus estados
/// y guarda una imagen PNG de cada uno. No toca el servidor ni los ajustes reales.
/// </summary>
internal static class Captura
{
    public static async Task EjecutarAsync(string carpeta)
    {
        Directory.CreateDirectory(carpeta);
        var reloj = new RelojManual(new DateTimeOffset(2026, 11, 18, 15, 0, 0, TimeSpan.Zero));
        var api = new DemoApi(reloj);
        var tmp = Path.Combine(Path.GetTempPath(), "play-captura-" + Guid.NewGuid().ToString("N"));
        var store = new LocalStore(tmp);
        var c = new PanelController(api, store, reloj, "PC-DEMO");
        var w = new MainWindow(c, store, demo: true) { Left = 40, Top = 40 };
        w.Show();
        await Esperar(w);

        // 1) Elige usuario: aparece el campo PIN.
        w.FindName("CmbUsuario").Seleccionar(0);
        await Esperar(w); Guardar(w, carpeta, "01-pin");

        // 2) Ingresa (pepe, 1234): en pausa con la obra elegida.
        await c.LoginAsync(1, "1234");
        await c.ObtenerResumenAsync();
        w.FindName("CmbObra").Seleccionar(0);
        await Esperar(w);
        w.FindName("CmbSubtarea").Seleccionar(1); // Senillosa tiene subtareas: hay que elegir una (acá, «Estructura»)
        await Esperar(w); Guardar(w, carpeta, "02-en-pausa");

        // 3) Play y 1 h 23 min 45 s después.
        await c.PlayAsync(1, 11);
        for (var i = 0; i < 167; i++) { reloj.Avanzar(TimeSpan.FromSeconds(30)); await c.TickAsync(); } // 1 h 23 min 30 s, con latidos
        reloj.Avanzar(TimeSpan.FromSeconds(15));
        w.Actualizar();
        await Esperar(w); Guardar(w, carpeta, "03-registrando");

        // 4) Se cae la red.
        api.Caida = true;
        reloj.Avanzar(TimeSpan.FromSeconds(40));
        await c.TickAsync();
        await Esperar(w); Guardar(w, carpeta, "04-sin-conexion");
        api.Caida = false;

        // 5) Aviso del sistema.
        c.Aviso = "Tu registro anterior se cerró a las 17:42. Presioná Play para continuar.";
        w.Actualizar();
        await Esperar(w); Guardar(w, carpeta, "05-aviso");

        // 6) Contraído.
        w.AplicarContraccion(true);
        await Esperar(w); Guardar(w, carpeta, "06-contraido");
        w.AplicarContraccion(false);

        // 7) Pausa y primer ingreso de otro usuario (debe elegir PIN).
        await c.PauseAsync();
        c.CerrarSesion();
        await c.LoginAsync(3, "1234");
        await Esperar(w); Guardar(w, carpeta, "07-primer-ingreso");

        // 8) Cambia al área Taller: la lista de nombres muestra solo a la gente del taller.
        c.CerrarSesion();
        w.FindName("CmbArea").Seleccionar(1);
        await Esperar(w);
        w.FindName("CmbUsuario").Seleccionar(0);
        await Esperar(w); Guardar(w, carpeta, "08-area-taller");

        // 9) «Avisar que terminé una subtarea…»: el cuadro es modal, así que se lo abre en el hilo de la interfaz y se lo fotografía desde afuera.
        c.CerrarSesion();
        w.FindName("CmbArea").Seleccionar(0);
        await c.LoginAsync(1, "1234");
        w.Actualizar();
        _ = w.Dispatcher.InvokeAsync(() => Dialogos.AvisarSubtareaTerminada(w, c));
        await Task.Delay(700);
        var dlg = Application.Current.Windows.OfType<Window>().FirstOrDefault(x => x.Title == "Avisar que terminé una subtarea");
        if (dlg?.Content is System.Windows.Controls.StackPanel sp)
        {
            ((System.Windows.Controls.ComboBox)sp.Children[2]).SelectedIndex = 0;
            ((System.Windows.Controls.ComboBox)sp.Children[4]).SelectedIndex = 1;
            await Esperar(dlg); Guardar(dlg, carpeta, "09-avisar-subtarea");
            ((System.Windows.Controls.Button)((System.Windows.Controls.StackPanel)sp.Children[^1]).Children[0]).RaiseEvent(new RoutedEventArgs(System.Windows.Controls.Primitives.ButtonBase.ClickEvent));
            await Task.Delay(500);
            Guardar(dlg, carpeta, "10-avisar-subtarea-listo");
            dlg.Close();
        }

        // 11) Personal de Taller: en lugar de Obra/Play, «Cargar horas».
        c.CerrarSesion();
        w.FindName("CmbArea").Seleccionar(1);
        await Esperar(w);
        await c.LoginAsync(4, "1234");
        w.Actualizar();
        await Esperar(w); Guardar(w, carpeta, "11-taller-cargar-horas");
        // Horas por obra y tarea: 5:30 en Senillosa › Estructura y 2:00 en Ape; además marca la tarea como terminada.
        w.FindName("CmbObra").Seleccionar(1);                  // 0 = «(Sin obra)», 1 = Senillosa
        await Esperar(w);
        w.FindName("CmbSubtarea").Seleccionar(1);               // Estructura
        await Esperar(w);
        ((System.Windows.Controls.TextBox)w.FindName("TxtHoras")).Text = "5,5";
        ((System.Windows.Controls.Button)w.FindName("BtnGuardarHoras")).RaiseEvent(new RoutedEventArgs(System.Windows.Controls.Primitives.ButtonBase.ClickEvent));
        await Task.Delay(600); await Esperar(w);
        w.FindName("CmbObra").Seleccionar(2);                  // Ape
        await Esperar(w);
        ((System.Windows.Controls.TextBox)w.FindName("TxtHoras")).Text = "2";
        ((System.Windows.Controls.Button)w.FindName("BtnGuardarHoras")).RaiseEvent(new RoutedEventArgs(System.Windows.Controls.Primitives.ButtonBase.ClickEvent));
        await Task.Delay(600);
        await Esperar(w); Guardar(w, carpeta, "12-taller-guardado");
        w.FindName("CmbObra").Seleccionar(1);
        await Esperar(w);
        w.FindName("CmbSubtarea").Seleccionar(1);
        await Esperar(w); Guardar(w, carpeta, "13-taller-obra-tarea-terminada");

        Application.Current.Shutdown();
    }

    private static void Seleccionar(this object? combo, int indice)
    {
        if (combo is System.Windows.Controls.ComboBox cb) cb.SelectedIndex = indice;
    }

    private static async Task Esperar(Window w)
    {
        await w.Dispatcher.InvokeAsync(() => { }, DispatcherPriority.ApplicationIdle);
        await Task.Delay(120);
    }

    private static void Guardar(Window w, string carpeta, string nombre)
    {
        w.UpdateLayout();
        const double escala = 2;
        var rtb = new RenderTargetBitmap((int)Math.Ceiling(w.ActualWidth * escala), (int)Math.Ceiling(w.ActualHeight * escala), 96 * escala, 96 * escala, PixelFormats.Pbgra32);
        rtb.Render(w);
        var enc = new PngBitmapEncoder();
        enc.Frames.Add(BitmapFrame.Create(rtb));
        using var fs = File.Create(Path.Combine(carpeta, nombre + ".png"));
        enc.Save(fs);
    }
}
