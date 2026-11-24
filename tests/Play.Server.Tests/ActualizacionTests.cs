using System.Diagnostics;
using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using Play.Client;
using Xunit;

namespace Play.Server.Tests;

/// <summary>Actualización automática del panel: aviso del servidor, descarga verificada, reemplazo y vuelta atrás.</summary>
public class ActualizacionTests : IClassFixture<ServerFixture>
{
    private readonly ServerFixture _s;
    public ActualizacionTests(ServerFixture s) => _s = s;

    /// <summary>Cualquier ejecutable real de Windows con versión (el de las propias pruebas) sirve como «Play.exe» de ejemplo.</summary>
    private static string ExeDeEjemplo => Environment.ProcessPath!;

    private string Publicar(byte[]? contenido = null)
    {
        _s.CreateClient(); // arranca el servidor (crea datos\descargas)
        var destino = Path.Combine(_s.DataDir, "descargas", "Play.exe");
        if (contenido is null) File.Copy(ExeDeEjemplo, destino, overwrite: true);
        else File.WriteAllBytes(destino, contenido);
        return destino;
    }

    private static string CarpetaTemporal()
    {
        var d = Path.Combine(Path.GetTempPath(), "play-upd-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(d);
        return d;
    }

    private async Task<VersionPanelDto> InfoDelServidor() =>
        (await _s.CreateClient().GetFromJsonAsync<VersionPanelDto>("/api/panel/version",
            new System.Text.Json.JsonSerializerOptions(System.Text.Json.JsonSerializerDefaults.Web)))!;

    // ---------------------------------------------------------------- servidor

    [Fact]
    public async Task Sin_Play_exe_publicado_la_version_da_404_y_con_uno_publicado_informa_version_y_huella()
    {
        using var s = new ServerFixture();
        var c = s.CreateClient();
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync("/api/panel/version")).StatusCode);

        var exe = Path.Combine(s.DataDir, "descargas", "Play.exe");
        File.Copy(ExeDeEjemplo, exe);
        var info = (await c.GetFromJsonAsync<VersionPanelDto>("/api/panel/version", new System.Text.Json.JsonSerializerOptions(System.Text.Json.JsonSerializerDefaults.Web)))!;
        Assert.Equal(FileVersionInfo.GetVersionInfo(exe).FileVersion!.Trim(), info.Version);
        Assert.Equal(new FileInfo(exe).Length, info.Bytes);
        Assert.Equal(Convert.ToHexString(SHA256.HashData(File.ReadAllBytes(exe))), info.Sha256, ignoreCase: true);
        Assert.Equal("Play.exe", info.Archivo);
    }

    [Fact]
    public async Task Al_publicar_otro_Play_exe_la_huella_se_recalcula()
    {
        using var s = new ServerFixture();
        var c = s.CreateClient();
        var exe = Path.Combine(s.DataDir, "descargas", "Play.exe");
        File.Copy(ExeDeEjemplo, exe);
        var opciones = new System.Text.Json.JsonSerializerOptions(System.Text.Json.JsonSerializerDefaults.Web);
        var antes = (await c.GetFromJsonAsync<VersionPanelDto>("/api/panel/version", opciones))!;

        File.AppendAllText(exe, "x"); // «publicación» nueva: cambia el contenido
        var despues = (await c.GetFromJsonAsync<VersionPanelDto>("/api/panel/version", opciones))!;
        Assert.NotEqual(antes.Sha256, despues.Sha256);
        Assert.Equal(antes.Bytes + 1, despues.Bytes);
    }

    // ---------------------------------------------------------------- descarga verificada

    [Fact]
    public async Task La_descarga_correcta_queda_en_el_archivo_nuevo_y_coincide_byte_a_byte()
    {
        var publicado = Publicar();
        var info = await InfoDelServidor();
        var carpeta = CarpetaTemporal();
        var exeActual = Path.Combine(carpeta, "Play.exe");
        File.WriteAllText(exeActual, "version vieja");

        var nuevo = await Actualizador.DescargarAsync(_s.CreateClient(), info, exeActual);

        Assert.Equal(Actualizador.RutaNueva(exeActual), nuevo);
        Assert.Equal(File.ReadAllBytes(publicado), File.ReadAllBytes(nuevo));
        Assert.Equal("version vieja", File.ReadAllText(exeActual)); // el actual no se toca hasta reemplazar
        Assert.Single(Directory.GetFiles(carpeta, "*.nuevo*"));      // sin archivos a medias
    }

    [Fact]
    public async Task Una_descarga_con_huella_tamano_o_version_distintos_se_rechaza_y_no_deja_restos()
    {
        Publicar();
        var info = await InfoDelServidor();
        var carpeta = CarpetaTemporal();
        var exeActual = Path.Combine(carpeta, "Play.exe");

        var malas = new[]
        {
            info with { Sha256 = new string('0', 64) },
            info with { Bytes = info.Bytes + 5 },
            info with { Version = "99.99.99.99" },
        };
        foreach (var mala in malas)
        {
            await Assert.ThrowsAsync<InvalidDataException>(() => Actualizador.DescargarAsync(_s.CreateClient(), mala, exeActual));
            Assert.Empty(Directory.GetFiles(carpeta));
        }
    }

    [Fact]
    public async Task Un_archivo_que_no_es_un_ejecutable_se_rechaza_aunque_la_huella_coincida()
    {
        Publicar("esto no es un programa, es texto"u8.ToArray());
        var info = await InfoDelServidor(); // el servidor anuncia lo que hay, la huella es correcta
        var carpeta = CarpetaTemporal();

        var ex = await Assert.ThrowsAsync<InvalidDataException>(() => Actualizador.DescargarAsync(_s.CreateClient(), info, Path.Combine(carpeta, "Play.exe")));
        Assert.Contains("ejecutable", ex.Message);
        Assert.Empty(Directory.GetFiles(carpeta));
    }

    [Fact]
    public async Task Si_el_servidor_no_responde_la_descarga_falla_sin_dejar_restos()
    {
        var carpeta = CarpetaTemporal();
        var info = new VersionPanelDto("1.0.0.1", "00", 1, "Play.exe", DateTime.UtcNow);
        var sinServidor = new HttpClient { BaseAddress = new Uri("http://127.0.0.1:1/"), Timeout = TimeSpan.FromSeconds(3) };
        await Assert.ThrowsAnyAsync<Exception>(() => Actualizador.DescargarAsync(sinServidor, info, Path.Combine(carpeta, "Play.exe")));
        Assert.Empty(Directory.GetFiles(carpeta));
    }

    // ---------------------------------------------------------------- reemplazo y vuelta atrás

    [Fact]
    public void Reemplazar_deja_el_nuevo_en_su_lugar_y_el_actual_como_viejo_y_Revertir_lo_deshace()
    {
        var carpeta = CarpetaTemporal();
        var exe = Path.Combine(carpeta, "Play.exe");
        File.WriteAllText(exe, "VIEJO");
        File.WriteAllText(Actualizador.RutaNueva(exe), "NUEVO");

        Actualizador.Reemplazar(exe);
        Assert.Equal("NUEVO", File.ReadAllText(exe));
        Assert.Equal("VIEJO", File.ReadAllText(Actualizador.RutaVieja(exe)));
        Assert.False(File.Exists(Actualizador.RutaNueva(exe)));

        Actualizador.Revertir(exe); // «lo nuevo no arrancó»
        Assert.Equal("VIEJO", File.ReadAllText(exe));
        Assert.False(File.Exists(Actualizador.RutaVieja(exe)));
    }

    [Fact]
    public void Reemplazar_sin_version_descargada_no_toca_nada()
    {
        var carpeta = CarpetaTemporal();
        var exe = Path.Combine(carpeta, "Play.exe");
        File.WriteAllText(exe, "VIEJO");
        Assert.Throws<FileNotFoundException>(() => Actualizador.Reemplazar(exe));
        Assert.Equal("VIEJO", File.ReadAllText(exe));
    }

    [Fact]
    public void Si_el_programa_anterior_sigue_corriendo_su_archivo_no_se_borra_hasta_que_termine()
    {
        var carpeta = CarpetaTemporal();
        var exe = Path.Combine(carpeta, "Play.exe");
        File.WriteAllText(exe, "VIEJO");
        File.WriteAllText(Actualizador.RutaNueva(exe), "NUEVO");
        Actualizador.Reemplazar(exe);

        // «el proceso anterior aún lo tiene abierto»
        using (new FileStream(Actualizador.RutaVieja(exe), FileMode.Open, FileAccess.Read, FileShare.Read))
            Assert.False(Actualizador.LimpiarRestos(exe));
        Assert.True(File.Exists(Actualizador.RutaVieja(exe)));

        Assert.True(Actualizador.LimpiarRestos(exe)); // ya terminó
        Assert.False(File.Exists(Actualizador.RutaVieja(exe)));
        Assert.Equal("NUEVO", File.ReadAllText(exe));
    }

    // ---------------------------------------------------------------- decisiones

    [Theory]
    [InlineData("1.2611.1812.10", "1.2611.1812.9", true)]   // 10 > 9: se compara como número, no como texto
    [InlineData("1.2612.101.0", "1.2611.1812.35", true)]
    [InlineData("1.2611.1812.9", "1.2611.1812.9", false)]   // igual
    [InlineData("1.2611.1812.8", "1.2611.1812.9", false)]   // más vieja: no se «baja» sola
    [InlineData("basura", "1.0.0.0", false)]
    [InlineData(null, "1.0.0.0", false)]
    public void Solo_se_actualiza_a_una_version_mas_nueva(string? servidor, string actual, bool esperado) =>
        Assert.Equal(esperado, Actualizador.EsMasNueva(servidor, Version.Parse(actual)));

    [Theory]
    [InlineData(EstadoPanel.Registrando, 0, true, false)]      // nunca con el cronómetro andando
    [InlineData(EstadoPanel.Registrando, 9999, false, false)]
    [InlineData(EstadoPanel.SinSesion, 0, true, true)]         // recién abierto
    [InlineData(EstadoPanel.SinSesion, 5, false, false)]       // alguien lo está usando
    [InlineData(EstadoPanel.SinSesion, 40, false, true)]
    [InlineData(EstadoPanel.Pausado, 60, false, false)]        // en pausa, pero sigue frente a la PC
    [InlineData(EstadoPanel.Pausado, 180, false, true)]        // se fue a almorzar
    public void La_politica_nunca_reinicia_el_panel_en_medio_de_un_registro_ni_mientras_se_usa(EstadoPanel estado, int inactivoSegundos, bool alArrancar, bool esperado) =>
        Assert.Equal(esperado, PoliticaActualizacion.DebeAplicarAhora(estado, TimeSpan.FromSeconds(inactivoSegundos), alArrancar));
}
