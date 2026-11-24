using System.Net;
using System.Net.Http.Json;
using ClosedXML.Excel;
using Xunit;

namespace Play.Server.Tests;

public class AdminTests : IClassFixture<ServerFixture>
{
    private readonly ServerFixture _s;
    public AdminTests(ServerFixture s) => _s = s;

    private async Task<HttpClient> AdminAsync(string nombre)
    {
        _s.CrearAdmin(nombre, "clave-segura-1");
        return await _s.ClienteAdminAsync(nombre, "clave-segura-1");
    }

    [Fact]
    public async Task Sin_token_o_con_clave_incorrecta_se_rechaza()
    {
        Assert.Equal(HttpStatusCode.Unauthorized, (await _s.CreateClient().GetAsync("/api/admin/empleados")).StatusCode);
        _s.CrearAdmin("adm-mal", "clave-segura-1");
        var r = await _s.CreateClient().PostAsJsonAsync("/api/admin/login", new { usuario = "adm-mal", password = "otra" });
        Assert.Equal(HttpStatusCode.Unauthorized, r.StatusCode);
        // Un empleado no puede entrar a la administración con su token.
        var (emp, _, _) = _s.CrearDatos("NoAdmin");
        var ce = await _s.ClienteAsync(emp);
        Assert.Equal(HttpStatusCode.Unauthorized, (await ce.GetAsync("/api/admin/empleados")).StatusCode);
    }

    [Fact]
    public async Task Con_clave_temporal_solo_se_puede_cambiarla()
    {
        _s.CrearAdmin("adm-temp", "temporal-123", debeCambiar: true);
        var c = await _s.ClienteAdminAsync("adm-temp", "temporal-123");
        Assert.Equal(HttpStatusCode.Forbidden, (await c.GetAsync("/api/admin/empleados")).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await c.PostAsJsonAsync("/api/admin/clave", new { claveActual = "temporal-123", claveNueva = "corta" })).StatusCode);
        Assert.Equal(HttpStatusCode.NoContent, (await c.PostAsJsonAsync("/api/admin/clave", new { claveActual = "temporal-123", claveNueva = "nueva-clave-9" })).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await c.GetAsync("/api/admin/empleados")).StatusCode);
    }

    [Fact]
    public async Task Crear_empleado_devuelve_pin_inicial_y_desactivarlo_impide_el_ingreso()
    {
        var a = await AdminAsync("adm-emp");
        var r = await a.PostAsJsonAsync("/api/admin/empleados", new { nombre = "Nuevo Empleado" });
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        var j = await r.Json();
        var id = j.GetProperty("empleado").GetProperty("id").GetInt32();
        var pin = j.GetProperty("pinInicial").GetString()!;
        Assert.Equal(4, pin.Length);

        Assert.Equal(HttpStatusCode.Conflict, (await a.PostAsJsonAsync("/api/admin/empleados", new { nombre = "Nuevo Empleado" })).StatusCode);

        var login = await _s.CreateClient().PostAsJsonAsync("/api/login", new { empleadoId = id, pin });
        Assert.Equal(HttpStatusCode.OK, login.StatusCode);
        Assert.True((await login.Json()).GetProperty("debeCambiarPin").GetBoolean());

        await a.PutAsJsonAsync($"/api/admin/empleados/{id}", new { activo = false });
        Assert.Equal(HttpStatusCode.Unauthorized, (await _s.CreateClient().PostAsJsonAsync("/api/login", new { empleadoId = id, pin })).StatusCode);
        var menu = await (await _s.CreateClient().GetAsync("/api/empleados")).Json();
        Assert.DoesNotContain(menu.EnumerateArray(), x => x.GetProperty("id").GetInt32() == id);
    }

    [Fact]
    public async Task Resetear_pin_invalida_el_anterior()
    {
        var a = await AdminAsync("adm-pin");
        var (emp, _, _) = _s.CrearDatos("ResetPin");
        var j = await (await a.PostAsync($"/api/admin/empleados/{emp}/reset-pin", null)).Json();
        var nuevo = j.GetProperty("pinInicial").GetString()!;
        if (nuevo == "1234") return; // improbable: el PIN aleatorio coincidió con el anterior
        Assert.Equal(HttpStatusCode.Unauthorized, (await _s.CreateClient().PostAsJsonAsync("/api/login", new { empleadoId = emp, pin = "1234" })).StatusCode);
        Assert.Equal(HttpStatusCode.OK, (await _s.CreateClient().PostAsJsonAsync("/api/login", new { empleadoId = emp, pin = nuevo })).StatusCode);
    }

    [Fact]
    public async Task Corregir_exige_motivo_y_deja_auditoria()
    {
        var a = await AdminAsync("adm-corr");
        var (emp, obra, obra2) = _s.CrearDatos("Corregir");
        var c = await _s.ClienteAsync(emp);
        var id = Guid.NewGuid();
        await c.PostAsJsonAsync("/api/registros", new { id, obraId = obra, equipo = "PC" });

        // Un registro abierto no se corrige.
        var abierto = await a.PutAsJsonAsync($"/api/admin/registros/{id}", new { obraId = obra2, motivo = "x" });
        Assert.Equal(HttpStatusCode.Conflict, abierto.StatusCode);

        var inicio = _s.Time.GetUtcNow().UtcDateTime;
        _s.Time.Advance(TimeSpan.FromHours(2));
        await c.PostAsync($"/api/registros/{id}/cerrar", null);

        Assert.Equal(HttpStatusCode.BadRequest, (await a.PutAsJsonAsync($"/api/admin/registros/{id}", new { obraId = obra2, motivo = " " })).StatusCode);
        Assert.Equal(HttpStatusCode.BadRequest, (await a.PutAsJsonAsync($"/api/admin/registros/{id}", new { motivo = "sin cambios" })).StatusCode);

        var ok = await a.PutAsJsonAsync($"/api/admin/registros/{id}", new { finUtc = inicio.AddHours(1), obraId = obra2, motivo = "Se olvidó de pausar" });
        Assert.Equal(HttpStatusCode.OK, ok.StatusCode);
        var j = await ok.Json();
        Assert.Equal("corregido", j.GetProperty("estado").GetString());
        Assert.Equal(3600, j.GetProperty("segundos").GetInt64());

        var aud = await (await a.GetAsync($"/api/admin/auditoria?registroId={id}")).Json();
        Assert.Equal(2, aud.GetArrayLength()); // fin y obra
        Assert.All(aud.EnumerateArray(), x =>
        {
            Assert.Equal("adm-corr", x.GetProperty("administrador").GetString());
            Assert.Equal("Se olvidó de pausar", x.GetProperty("motivo").GetString());
        });
    }

    [Fact]
    public async Task Alta_manual_y_filtros_de_consulta()
    {
        var a = await AdminAsync("adm-alta");
        var (emp, obra, _) = _s.CrearDatos("Alta");
        var (otro, _, _) = _s.CrearDatos("Alta2");
        var ahora = _s.Time.GetUtcNow().UtcDateTime;

        var sinMotivo = await a.PostAsJsonAsync("/api/admin/registros", new { empleadoId = emp, obraId = obra, inicioUtc = ahora.AddHours(-3), finUtc = ahora.AddHours(-1), motivo = "" });
        Assert.Equal(HttpStatusCode.BadRequest, sinMotivo.StatusCode);
        var ok = await a.PostAsJsonAsync("/api/admin/registros", new { empleadoId = emp, obraId = obra, inicioUtc = ahora.AddHours(-3), finUtc = ahora.AddHours(-1), motivo = "Trabajó sin PC" });
        Assert.Equal(HttpStatusCode.OK, ok.StatusCode);

        var lista = await (await a.GetAsync($"/api/admin/registros?empleadoId={emp}&obraId={obra}&desde=2026-11-18&hasta=2026-11-18")).Json();
        Assert.Equal(1, lista.GetArrayLength());
        Assert.Equal(7200, lista[0].GetProperty("segundos").GetInt64());
        var vacio = await (await a.GetAsync($"/api/admin/registros?empleadoId={otro}")).Json();
        Assert.Equal(0, vacio.GetArrayLength());
    }

    [Fact]
    public async Task En_vivo_muestra_quien_esta_registrando()
    {
        var a = await AdminAsync("adm-vivo");
        var (emp, obra, _) = _s.CrearDatos("EnVivo");
        var c = await _s.ClienteAsync(emp);
        await c.PostAsJsonAsync("/api/registros", new { id = Guid.NewGuid(), obraId = obra, equipo = "PC-9" });
        var vivo = await (await a.GetAsync("/api/admin/en-vivo")).Json();
        Assert.Contains(vivo.EnumerateArray(), x => x.GetProperty("empleado").GetString() == "EnVivo" && x.GetProperty("equipo").GetString() == "PC-9");
    }

    [Fact]
    public async Task Excel_tiene_las_hojas_las_horas_correctas_y_reparte_por_dia()
    {
        var a = await AdminAsync("adm-xls");
        var (emp, obra, obra2) = _s.CrearDatos("Excel");
        var ahora = _s.Time.GetUtcNow().UtcDateTime; // 2026-11-18 15:00Z = 12:00 en Argentina (UTC-3)

        // Cruza la medianoche local: 17/11 23:00 local (02:00Z del 18) a 18/11 01:00 local (04:00Z): 1 h + 1 h.
        var inicio = new DateTime(2026, 11, 18, 2, 0, 0, DateTimeKind.Utc);
        await a.PostAsJsonAsync("/api/admin/registros", new { empleadoId = emp, obraId = obra, inicioUtc = inicio, finUtc = inicio.AddHours(2), motivo = "Guardia nocturna" });
        // 1,5 h en otra obra.
        await a.PostAsJsonAsync("/api/admin/registros", new { empleadoId = emp, obraId = obra2, inicioUtc = ahora.AddHours(-3), finUtc = ahora.AddHours(-1.5), motivo = "Carga" });

        var r = await a.GetAsync("/api/admin/reporte.xlsx");
        Assert.Equal(HttpStatusCode.OK, r.StatusCode);
        using var wb = new XLWorkbook(new MemoryStream(await r.Content.ReadAsByteArrayAsync()));
        Assert.Equal(["Detalle", "Por empleado", "Por área", "Por obra", "Por subtarea", "Empleado x Obra"], wb.Worksheets.Select(w => w.Name).ToArray());

        var detalle = wb.Worksheet("Detalle").RowsUsed().Skip(1).Where(f => f.Cell(2).GetString() == "Excel").ToList();
        Assert.Equal(3, detalle.Count); // 2 tramos de la guardia (uno por día) + 1
        Assert.Equal(2, detalle.Count(f => f.Cell(4).GetString() == "Obra A Excel")); // columnas: Fecha, Empleado, Área, Obra...
        Assert.All(detalle, f => Assert.Equal("Oficina", f.Cell(3).GetString()));    // los empleados nuevos son de Oficina por defecto

        var porEmp = wb.Worksheet("Por empleado").RowsUsed().First(f => f.Cell(1).GetString() == "Excel");
        Assert.Equal(3.5, porEmp.Cell(2).GetDouble(), 2);
        // Columna hh:mm: ClosedXML la lee como fecha por su formato; el valor guardado equivale a 03:30.
        Assert.Equal(3.5, porEmp.Cell(3).Value.GetDateTime().TimeOfDay.TotalHours, 3);
        Assert.Equal("[h]:mm", porEmp.Cell(3).Style.NumberFormat.Format);

        // El filtro de fechas deja solo el día 17: 1 h de la guardia.
        var filtrado = await a.GetAsync($"/api/admin/reporte.xlsx?empleadoId={emp}&desde=2026-11-17&hasta=2026-11-17");
        using var wb2 = new XLWorkbook(new MemoryStream(await filtrado.Content.ReadAsByteArrayAsync()));
        Assert.Equal(1.0, wb2.Worksheet("Por empleado").RowsUsed().First(f => f.Cell(1).GetString() == "Excel").Cell(2).GetDouble(), 2);
    }
}
