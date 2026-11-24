using System.Net;
using System.Net.Http.Json;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.DependencyInjection;
using Play.Server.Services;
using Xunit;

namespace Play.Server.Tests;

public class BackupDescargaTests
{
    private static async Task<T> ConBackup<T>(ServerFixture s, Func<BackupService, Task<T>> f)
    {
        s.CreateClient(); // arranca el servidor
        using var scope = s.Services.CreateScope();
        return await f(scope.ServiceProvider.GetRequiredService<BackupService>());
    }

    /// <summary>Al arrancar, el servidor hace por sí solo el backup del día si corresponde. Espera a que termine.</summary>
    private static async Task EsperarBackupInicialAsync(ServerFixture s)
    {
        for (var i = 0; i < 100; i++)
        {
            if ((await ConBackup(s, async b => b.Listar())).Count > 0) return;
            await Task.Delay(100);
        }
        throw new TimeoutException("El servidor no hizo el backup inicial.");
    }

    private static long ContarEmpleados(string archivo)
    {
        using var c = new SqliteConnection($"Data Source={archivo};Mode=ReadOnly;Pooling=False");
        c.Open();
        using var cmd = c.CreateCommand();
        cmd.CommandText = "SELECT COUNT(*) FROM Empleados";
        return (long)cmd.ExecuteScalar()!;
    }

    [Fact]
    public async Task Backup_manual_desde_admin_crea_una_copia_valida_con_los_datos()
    {
        using var s = new ServerFixture();
        s.CrearAdmin("adm-bk", "clave-segura-1");
        var a = await s.ClienteAdminAsync("adm-bk", "clave-segura-1");
        s.CrearDatos("ParaBackup");

        var r = await a.PostAsync("/api/admin/backups", null);
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var nombre = (await r.Json()).GetProperty("archivo").GetString()!;

        var lista = await (await a.GetAsync("/api/admin/backups")).Json();
        var carpeta = lista.GetProperty("carpeta").GetString()!;
        Assert.Contains(lista.GetProperty("backups").EnumerateArray(), b => b.GetProperty("archivo").GetString() == nombre);
        Assert.True(ContarEmpleados(Path.Combine(carpeta, nombre)) >= 2); // semilla + el creado
    }

    [Fact]
    public async Task El_backup_diario_se_hace_una_vez_por_dia_despues_de_la_hora_configurada()
    {
        using var s = new ServerFixture(); // reloj: 12:00 locales, BackupHour = 2
        // El servidor estaba «apagado a las 02:00»: al encender hace el backup de hoy por su cuenta.
        await EsperarBackupInicialAsync(s);
        Assert.False(await ConBackup(s, async b => b.DebeHacerBackup()));

        s.Time.Advance(TimeSpan.FromHours(24)); // al día siguiente vuelve a tocar
        Assert.True(await ConBackup(s, async b => b.DebeHacerBackup()));
        await ConBackup(s, b => b.HacerBackupAsync());
        Assert.False(await ConBackup(s, async b => b.DebeHacerBackup()));
        Assert.Equal(2, (await ConBackup(s, async b => b.Listar())).Count);
    }

    [Fact]
    public async Task No_se_hace_backup_antes_de_la_hora_configurada()
    {
        using var s = new ServerFixture(new DateTimeOffset(2026, 11, 18, 4, 0, 0, TimeSpan.Zero)); // 01:00 en Argentina
        Assert.False(await ConBackup(s, async b => b.DebeHacerBackup()));
        await Task.Delay(500); // da tiempo al arranque: no debe haber creado ningún backup
        Assert.Empty(await ConBackup(s, async b => b.Listar()));
    }

    [Fact]
    public async Task La_limpieza_borra_backups_viejos_pero_conserva_el_mas_reciente()
    {
        using var s = new ServerFixture();
        await EsperarBackupInicialAsync(s);
        var info = (await ConBackup(s, async b => b.Listar()))[0];
        var carpeta = await ConBackup(s, async b => b.Carpeta);

        var viejo = Path.Combine(carpeta, "play-20260901-020000.db");
        File.WriteAllText(viejo, "viejo");
        File.SetLastWriteTimeUtc(viejo, new DateTime(2026, 9, 1, 5, 0, 0, DateTimeKind.Utc));

        var borrados = await ConBackup(s, async b => b.LimpiarAntiguos());
        Assert.Equal(1, borrados);
        Assert.False(File.Exists(viejo));
        Assert.True(File.Exists(Path.Combine(carpeta, info.Archivo)));

        // Aunque TODO sea viejo, el último se conserva.
        s.Time.Advance(TimeSpan.FromDays(90));
        await ConBackup(s, async b => b.LimpiarAntiguos());
        Assert.True(File.Exists(Path.Combine(carpeta, info.Archivo)));
    }

    [Fact]
    public async Task Pagina_de_descarga_lista_el_programa_y_permite_bajarlo()
    {
        using var s = new ServerFixture();
        var c = s.CreateClient();

        var vacia = await (await c.GetAsync("/")).Content.ReadAsStringAsync();
        Assert.Contains("Todavía no hay ningún programa", vacia);

        var bytes = Enumerable.Range(0, 5000).Select(i => (byte)(i % 251)).ToArray();
        var carpeta = Path.Combine(s.DataDir, "descargas");
        File.WriteAllBytes(Path.Combine(carpeta, "Play.exe"), bytes);
        File.WriteAllText(Path.Combine(carpeta, "notas.txt"), "no se publica");

        var pagina = await c.GetAsync("/");
        Assert.Equal("text/html", pagina.Content.Headers.ContentType!.MediaType);
        var html = await pagina.Content.ReadAsStringAsync();
        Assert.Contains("Descargar Play.exe", html);
        Assert.DoesNotContain("notas.txt", html);

        var descarga = await c.GetAsync("/descargar/Play.exe");
        Assert.Equal(HttpStatusCode.OK, descarga.StatusCode);
        Assert.Equal(bytes, await descarga.Content.ReadAsByteArrayAsync());

        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync("/descargar/notas.txt")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync("/descargar/..%2Fplay.db")).StatusCode);
        Assert.Equal(HttpStatusCode.NotFound, (await c.GetAsync("/descargar/play.db")).StatusCode);
    }
}
