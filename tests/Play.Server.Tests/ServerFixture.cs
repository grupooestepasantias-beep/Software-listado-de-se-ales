using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.DependencyInjection.Extensions;
using Microsoft.Extensions.Time.Testing;
using Play.Server.Data;
using Play.Server.Services;

namespace Play.Server.Tests;

/// <summary>Servidor real en memoria con base SQLite temporal y reloj controlable.</summary>
public sealed class ServerFixture : WebApplicationFactory<Program>
{
    private readonly string _dir = Path.Combine(Path.GetTempPath(), "play-tests-" + Guid.NewGuid().ToString("N"));
    public string DataDir => _dir;
    public FakeTimeProvider Time { get; }

    /// <summary>Reloj iniciado el 18/11/2026 a las 12:00 en Argentina (15:00 UTC).</summary>
    public ServerFixture() : this(new DateTimeOffset(2026, 11, 18, 15, 0, 0, TimeSpan.Zero)) { }

    internal ServerFixture(DateTimeOffset inicio) => Time = new FakeTimeProvider(inicio);

    private string? _excel;

    /// <summary>Servidor en el que el Excel de empleados (ruta indicada) es la base de datos de empleados. El proceso de fondo casi no corre: las pruebas sincronizan a mano.</summary>
    internal ServerFixture(DateTimeOffset inicio, string excel) : this(inicio) => _excel = excel;

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        builder.ConfigureAppConfiguration((_, cfg) => cfg.AddInMemoryCollection(new Dictionary<string, string?>
        {
            ["Play:DataDir"] = _dir,
            ["Play:Seed:Empleados:0"] = "Semilla Uno",
            ["Play:EmpleadosExcel"] = _excel ?? "",
            ["Play:EmpleadosExcelSegundos"] = "3600",
        }));
        builder.ConfigureServices(s =>
        {
            s.RemoveAll<TimeProvider>();
            s.AddSingleton<TimeProvider>(Time);
        });
    }

    public (int EmpleadoId, int ObraId, int ObraId2) CrearDatos(string nombre)
    {
        using var scope = Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<PlayDb>();
        var e = new Empleado { Nombre = nombre, PinHash = PinHasher.Hash("1234"), DebeCambiarPin = false };
        var o1 = new Obra { Nombre = "Obra A " + nombre };
        var o2 = new Obra { Nombre = "Obra B " + nombre };
        db.AddRange(e, o1, o2);
        db.SaveChanges();
        return (e.Id, o1.Id, o2.Id);
    }

    public int CrearAdmin(string usuario, string clave, bool debeCambiar = false)
    {
        using var scope = Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<PlayDb>();
        var a = new Administrador { Usuario = usuario, NombreCompleto = usuario, PassHash = PinHasher.Hash(clave), DebeCambiarPass = debeCambiar };
        db.Add(a);
        db.SaveChanges();
        return a.Id;
    }

    public async Task<HttpClient> ClienteAdminAsync(string usuario, string clave)
    {
        var c = CreateClient();
        var r = await c.PostAsJsonAsync("/api/admin/login", new { usuario, password = clave });
        r.EnsureSuccessStatusCode();
        var token = (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("token").GetString();
        c.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return c;
    }

    public async Task<HttpClient> ClienteAsync(int empleadoId, string pin = "1234")
    {
        var c = CreateClient();
        var r = await c.PostAsJsonAsync("/api/login", new { empleadoId, pin });
        r.EnsureSuccessStatusCode();
        var token = (await r.Content.ReadFromJsonAsync<JsonElement>()).GetProperty("token").GetString();
        c.DefaultRequestHeaders.Authorization = new AuthenticationHeaderValue("Bearer", token);
        return c;
    }

    public async Task CerrarAbandonadosAsync()
    {
        using var scope = Services.CreateScope();
        await scope.ServiceProvider.GetRequiredService<RegistroService>().CerrarAbandonadosAsync();
    }

    protected override void Dispose(bool disposing)
    {
        base.Dispose(disposing);
        try { Directory.Delete(_dir, true); } catch { /* archivo aún en uso: se ignora */ }
    }
}

public static class Http
{
    public static async Task<JsonElement> Json(this HttpResponseMessage r) => await r.Content.ReadFromJsonAsync<JsonElement>();
}
