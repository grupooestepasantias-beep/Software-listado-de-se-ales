using System.Net;
using System.Net.Http.Json;
using Xunit;

namespace Play.Server.Tests;

public class RegistroTests : IClassFixture<ServerFixture>
{
    private readonly ServerFixture _s;
    public RegistroTests(ServerFixture s) => _s = s;

    private static object Iniciar(Guid id, int obraId) => new { id, obraId, equipo = "PC-TEST" };

    [Fact]
    public async Task Sin_token_devuelve_401()
    {
        var r = await _s.CreateClient().GetAsync("/api/resumen");
        Assert.Equal(HttpStatusCode.Unauthorized, r.StatusCode);
    }

    [Fact]
    public async Task Pin_incorrecto_5_veces_bloquea()
    {
        var (emp, _, _) = _s.CrearDatos("Bloqueo");
        var c = _s.CreateClient();
        for (var i = 0; i < 4; i++)
            Assert.Equal(HttpStatusCode.Unauthorized, (await c.PostAsJsonAsync("/api/login", new { empleadoId = emp, pin = "0000" })).StatusCode);
        Assert.Equal((HttpStatusCode)423, (await c.PostAsJsonAsync("/api/login", new { empleadoId = emp, pin = "0000" })).StatusCode);
        // Aun con el PIN correcto sigue bloqueado.
        Assert.Equal((HttpStatusCode)423, (await c.PostAsJsonAsync("/api/login", new { empleadoId = emp, pin = "1234" })).StatusCode);
        _s.Time.Advance(TimeSpan.FromMinutes(6));
        Assert.Equal(HttpStatusCode.OK, (await c.PostAsJsonAsync("/api/login", new { empleadoId = emp, pin = "1234" })).StatusCode);
    }

    [Fact]
    public async Task Doble_registro_se_bloquea_y_reenviar_el_mismo_id_es_idempotente()
    {
        var (emp, obra, _) = _s.CrearDatos("Doble");
        var c = await _s.ClienteAsync(emp);
        var id = Guid.NewGuid();

        Assert.Equal(HttpStatusCode.Created, (await c.PostAsJsonAsync("/api/registros", Iniciar(id, obra))).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await c.PostAsJsonAsync("/api/registros", Iniciar(id, obra))).StatusCode); // reenvío

        var otro = await c.PostAsJsonAsync("/api/registros", Iniciar(Guid.NewGuid(), obra));
        Assert.Equal(HttpStatusCode.Conflict, otro.StatusCode);
        var body = await otro.Json();
        Assert.Equal("registro_activo", body.GetProperty("codigo").GetString());
        Assert.Equal("PC-TEST", body.GetProperty("equipo").GetString());
    }

    [Fact]
    public async Task Iniciar_en_paralelo_deja_un_solo_registro_abierto()
    {
        var (emp, obra, _) = _s.CrearDatos("Paralelo");
        var c = await _s.ClienteAsync(emp);
        var respuestas = await Task.WhenAll(Enumerable.Range(0, 15).Select(_ => c.PostAsJsonAsync("/api/registros", Iniciar(Guid.NewGuid(), obra))));
        Assert.Equal(1, respuestas.Count(r => r.StatusCode == HttpStatusCode.Created));
        Assert.All(respuestas.Where(r => r.StatusCode != HttpStatusCode.Created), r => Assert.Equal(HttpStatusCode.Conflict, r.StatusCode));
    }

    [Fact]
    public async Task Cambiar_de_obra_cierra_la_anterior_y_abre_la_nueva()
    {
        var (emp, a, b) = _s.CrearDatos("Cambio");
        var c = await _s.ClienteAsync(emp);
        var id1 = Guid.NewGuid();
        await c.PostAsJsonAsync("/api/registros", Iniciar(id1, a));
        _s.Time.Advance(TimeSpan.FromMinutes(30));

        var id2 = Guid.NewGuid();
        var r = await c.PostAsJsonAsync("/api/registros/cambiar-obra", Iniciar(id2, b));
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);

        var activo = await (await c.GetAsync("/api/registro-activo")).Json();
        Assert.Equal(id2, activo.GetProperty("id").GetGuid());
        Assert.Equal(b, activo.GetProperty("obraId").GetInt32());

        var resumen = await (await c.GetAsync("/api/resumen")).Json();
        var obraA = resumen.GetProperty("hoy").GetProperty("porObra").EnumerateArray().First(x => x.GetProperty("obraId").GetInt32() == a);
        Assert.Equal(1800, obraA.GetProperty("segundos").GetInt64());
    }

    [Fact]
    public async Task Cerrar_es_idempotente_y_acepta_fin_anterior_a_ahora()
    {
        var (emp, obra, _) = _s.CrearDatos("Cerrar");
        var c = await _s.ClienteAsync(emp);
        var id = Guid.NewGuid();
        await c.PostAsJsonAsync("/api/registros", Iniciar(id, obra));
        var inicio = _s.Time.GetUtcNow().UtcDateTime;
        _s.Time.Advance(TimeSpan.FromMinutes(20)); // pasan 20 min, pero el empleado estuvo inactivo desde el minuto 5

        var r1 = await c.PostAsJsonAsync($"/api/registros/{id}/cerrar", new { finUtc = inicio.AddMinutes(5) });
        var j1 = await r1.Json();
        Assert.Equal("cerrado", j1.GetProperty("estado").GetString());
        Assert.Equal(inicio.AddMinutes(5), j1.GetProperty("finUtc").GetDateTime());

        var r2 = await c.PostAsJsonAsync($"/api/registros/{id}/cerrar", new { });
        Assert.Equal(inicio.AddMinutes(5), (await r2.Json()).GetProperty("finUtc").GetDateTime()); // no cambia
    }

    [Fact]
    public async Task Sin_latidos_el_servidor_corta_el_registro_en_el_ultimo_latido()
    {
        var (emp, obra, _) = _s.CrearDatos("Corte");
        var c = await _s.ClienteAsync(emp);
        var id = Guid.NewGuid();
        await c.PostAsJsonAsync("/api/registros", Iniciar(id, obra));
        _s.Time.Advance(TimeSpan.FromSeconds(30));
        await c.PostAsync($"/api/registros/{id}/latido", null);
        var ultimoLatido = _s.Time.GetUtcNow().UtcDateTime;

        _s.Time.Advance(TimeSpan.FromMinutes(5)); // la PC se apagó
        await _s.CerrarAbandonadosAsync();

        Assert.Equal(HttpStatusCode.NoContent, (await c.GetAsync("/api/registro-activo")).StatusCode);
        var latido = await c.PostAsync($"/api/registros/{id}/latido", null);
        Assert.Equal(HttpStatusCode.Conflict, latido.StatusCode);
        Assert.Equal(ultimoLatido, (await latido.Json()).GetProperty("finUtc").GetDateTime());

        // El empleado puede volver a empezar.
        Assert.Equal(HttpStatusCode.Created, (await c.PostAsJsonAsync("/api/registros", Iniciar(Guid.NewGuid(), obra))).StatusCode);
    }

    [Fact]
    public async Task Sincronizar_es_idempotente_y_no_pierde_registros_solapados()
    {
        var (emp, obra, _) = _s.CrearDatos("Sync");
        var c = await _s.ClienteAsync(emp);
        var ahora = _s.Time.GetUtcNow().UtcDateTime;
        var id = Guid.NewGuid();
        var item = new { id, obraId = obra, inicioUtc = ahora.AddHours(-3), finUtc = (DateTime?)ahora.AddHours(-2), equipo = "PC-X" };

        var r1 = await (await c.PostAsJsonAsync("/api/registros/sincronizar", new { registros = new[] { item } })).Json();
        Assert.Equal("insertado", r1[0].GetProperty("resultado").GetString());
        var r2 = await (await c.PostAsJsonAsync("/api/registros/sincronizar", new { registros = new[] { item } })).Json();
        Assert.Equal("duplicado", r2[0].GetProperty("resultado").GetString());

        // Otro registro que solapa con el anterior: se guarda igual, marcado para revisión.
        var solapado = new { id = Guid.NewGuid(), obraId = obra, inicioUtc = ahora.AddHours(-2.5), finUtc = (DateTime?)ahora.AddHours(-1), equipo = "PC-X" };
        var r3 = await (await c.PostAsJsonAsync("/api/registros/sincronizar", new { registros = new[] { solapado } })).Json();
        Assert.Equal("insertado_revisar", r3[0].GetProperty("resultado").GetString());

        // Fecha futura o inválida: rechazada.
        var futuro = new { id = Guid.NewGuid(), obraId = obra, inicioUtc = ahora.AddHours(5), finUtc = (DateTime?)ahora.AddHours(6), equipo = "PC-X" };
        var r4 = await (await c.PostAsJsonAsync("/api/registros/sincronizar", new { registros = new[] { futuro } })).Json();
        Assert.Equal("invalido", r4[0].GetProperty("resultado").GetString());
    }

    [Fact]
    public async Task Sincronizar_extiende_un_registro_cortado_si_el_panel_trabajo_mas_tarde()
    {
        var (emp, obra, _) = _s.CrearDatos("Extender");
        var c = await _s.ClienteAsync(emp);
        var id = Guid.NewGuid();
        await c.PostAsJsonAsync("/api/registros", Iniciar(id, obra));
        var inicio = _s.Time.GetUtcNow().UtcDateTime;
        _s.Time.Advance(TimeSpan.FromMinutes(10)); // se cae la red; sin latidos
        await _s.CerrarAbandonadosAsync();
        _s.Time.Advance(TimeSpan.FromMinutes(5));  // vuelve la red; el panel cuenta 15 min de trabajo

        var item = new { id, obraId = obra, inicioUtc = inicio, finUtc = (DateTime?)inicio.AddMinutes(14), equipo = "PC-TEST" };
        var r = await (await c.PostAsJsonAsync("/api/registros/sincronizar", new { registros = new[] { item } })).Json();
        Assert.Equal("actualizado", r[0].GetProperty("resultado").GetString());

        var resumen = await (await c.GetAsync("/api/resumen")).Json();
        Assert.Equal(14 * 60, resumen.GetProperty("hoy").GetProperty("totalSegundos").GetInt64());
    }

    [Fact]
    public async Task Resumen_suma_tiempo_de_hoy_y_semana_incluyendo_el_registro_en_curso()
    {
        var (emp, obra, _) = _s.CrearDatos("Resumen");
        var c = await _s.ClienteAsync(emp);
        await c.PostAsJsonAsync("/api/registros", Iniciar(Guid.NewGuid(), obra));
        _s.Time.Advance(TimeSpan.FromHours(1));
        var r = await (await c.GetAsync("/api/resumen")).Json();
        Assert.Equal(3600, r.GetProperty("hoy").GetProperty("totalSegundos").GetInt64());
        Assert.Equal(3600, r.GetProperty("semana").GetProperty("totalSegundos").GetInt64());
    }
}
