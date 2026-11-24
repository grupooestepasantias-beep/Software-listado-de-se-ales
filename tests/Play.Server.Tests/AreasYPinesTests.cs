using System.Net;
using ClosedXML.Excel;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Play.Client;
using Play.Server.Data;
using Play.Server.Services;
using Xunit;
using RegistroAdminDto = Play.Client.RegistroAdminDto;

namespace Play.Server.Tests;

/// <summary>Áreas (Oficina / Taller) y PIN visibles para el administrador.</summary>
public class AreasYPinesTests : IClassFixture<ServerFixture>
{
    private readonly ServerFixture _s;
    public AreasYPinesTests(ServerFixture s) => _s = s;

    private async Task<AdminApi> Admin(string usuario)
    {
        _s.CrearAdmin(usuario, "clave-segura-1");
        var api = new AdminApi(new ApiClient(_s.CreateClient(), _s.Time));
        api.Token = (await api.LoginAsync(usuario, "clave-segura-1")).Valor!.Token;
        return api;
    }

    // ---------------------------------------------------------------- áreas

    [Fact]
    public async Task Los_empleados_nuevos_son_de_Oficina_salvo_que_se_indique_Taller_y_el_area_se_valida()
    {
        var api = await Admin("adm-ar1");
        Assert.Equal("Oficina", (await api.CrearEmpleadoAsync("ArOficina1")).Valor!.Empleado.Area);
        Assert.Equal("Taller", (await api.CrearEmpleadoAsync("ArTaller1", "taller")).Valor!.Empleado.Area); // mayúsculas/minúsculas da igual
        Assert.Equal("area_invalida", (await api.CrearEmpleadoAsync("ArRaro", "Cocina")).Codigo);
    }

    [Fact]
    public async Task La_lista_publica_de_empleados_trae_el_area_para_que_el_panel_filtre()
    {
        var api = await Admin("adm-ar2");
        await api.CrearEmpleadoAsync("ArPublico T", "Taller");
        await api.CrearEmpleadoAsync("ArPublico O", "Oficina");

        var panel = new ApiClient(_s.CreateClient(), _s.Time);
        var lista = (await panel.EmpleadosAsync()).Valor!;
        Assert.Equal("Taller", lista.First(e => e.Nombre == "ArPublico T").Area);
        Assert.Equal("Oficina", lista.First(e => e.Nombre == "ArPublico O").Area);
    }

    [Fact]
    public async Task Cambiar_un_empleado_de_area_deja_constancia_y_se_puede_filtrar_por_area()
    {
        var api = await Admin("adm-ar3");
        var emp = (await api.CrearEmpleadoAsync("ArCambio")).Valor!.Empleado;
        Assert.Equal("Taller", (await api.ActualizarEmpleadoAsync(emp.Id, area: "Taller")).Valor!.Area);
        Assert.Equal("area_invalida", (await api.ActualizarEmpleadoAsync(emp.Id, area: "Nada")).Codigo);

        Assert.Contains((await api.EmpleadosAsync("Taller")).Valor!, e => e.Id == emp.Id);
        Assert.DoesNotContain((await api.EmpleadosAsync("Oficina")).Valor!, e => e.Id == emp.Id);

        var aud = (await api.AuditoriaAsync()).Valor!.First(a => a.Campo == "area" && a.ValorNuevo!.Contains("ArCambio"));
        Assert.Equal("adm-ar3", aud.Administrador);
        Assert.Contains("Oficina", aud.ValorAnterior);
        Assert.Contains("Taller", aud.ValorNuevo);
    }

    [Fact]
    public async Task Registros_en_vivo_y_Excel_se_filtran_por_area_y_el_Excel_trae_la_columna_y_la_hoja_por_area()
    {
        var api = await Admin("adm-ar4");
        var (_, obra, _) = _s.CrearDatos("ArObra");
        var ofi = (await api.CrearEmpleadoAsync("ArEmpOfi", "Oficina")).Valor!.Empleado;
        var tal = (await api.CrearEmpleadoAsync("ArEmpTal", "Taller")).Valor!.Empleado;
        var fin = _s.Time.GetUtcNow().UtcDateTime.AddMinutes(-10);
        await api.CrearRegistroAsync(ofi.Id, obra, fin.AddHours(-2), fin, "Carga");
        await api.CrearRegistroAsync(tal.Id, obra, fin.AddHours(-3), fin, "Carga");

        var soloTaller = (await api.RegistrosAsync(new FiltroAdmin(Area: "Taller", Desde: new DateOnly(2026, 11, 18), Hasta: new DateOnly(2026, 11, 18)))).Valor!;
        Assert.All(soloTaller, r => Assert.Equal("Taller", r.Area));
        Assert.Contains(soloTaller, r => r.Empleado == "ArEmpTal");
        Assert.DoesNotContain(soloTaller, r => r.Empleado == "ArEmpOfi");

        using var wb = new XLWorkbook(new MemoryStream((await api.ReporteExcelAsync(new FiltroAdmin(Area: "Taller"))).Valor!));
        var detalle = wb.Worksheet("Detalle").RowsUsed().Skip(1).ToList();
        Assert.Equal("Área", wb.Worksheet("Detalle").Cell(1, 3).GetString());
        Assert.All(detalle, f => Assert.Equal("Taller", f.Cell(3).GetString()));
        var porArea = wb.Worksheet("Por área").RowsUsed().Where(f => f.Cell(1).GetString() is "Taller" or "Oficina").ToList();
        Assert.Equal(["Taller"], porArea.Select(f => f.Cell(1).GetString()).ToArray());
    }

    [Fact]
    public async Task En_vivo_se_puede_filtrar_por_area()
    {
        var api = await Admin("adm-ar5");
        var (_, obra, _) = _s.CrearDatos("ArVivoObra");
        var tal = (await api.CrearEmpleadoAsync("ArVivoTal", "Taller")).Valor!;
        var panel = new PanelController(new ApiClient(_s.CreateClient(), _s.Time), new LocalStore(Path.Combine(Path.GetTempPath(), "play-cli-" + Guid.NewGuid().ToString("N"))), _s.Time, "PC-TALLER");
        await panel.CargarListasAsync();
        Assert.Null(await panel.LoginAsync(tal.Empleado.Id, tal.PinInicial));
        await panel.PlayAsync(obra);

        Assert.Contains((await api.EnVivoAsync("Taller")).Valor!, v => v.Empleado == "ArVivoTal" && v.Area == "Taller");
        Assert.DoesNotContain((await api.EnVivoAsync("Oficina")).Valor!, v => v.Empleado == "ArVivoTal");
    }

    // ---------------------------------------------------------------- PIN visibles

    [Fact]
    public async Task El_administrador_ve_el_PIN_inicial_y_el_que_elige_despues_el_empleado_y_cada_consulta_queda_registrada()
    {
        var api = await Admin("adm-pin1");
        var nuevo = (await api.CrearEmpleadoAsync("PinVisible1")).Valor!;
        string Pin() => (api.PinesAsync().Result.Valor!).First(p => p.Id == nuevo.Empleado.Id).Pin!;

        Assert.Equal(nuevo.PinInicial, Pin());

        // El empleado elige su PIN propio: el administrador pasa a ver ese.
        var empleado = new ApiClient(_s.CreateClient(), _s.Time);
        empleado.Token = (await empleado.LoginAsync(nuevo.Empleado.Id, nuevo.PinInicial)).Valor!.Token;
        Assert.True((await empleado.CambiarPinAsync(nuevo.PinInicial, "7391")).Ok);
        Assert.Equal("7391", Pin());

        // Reseteo: el PIN nuevo también se ve.
        var reset = (await api.ResetearPinAsync(nuevo.Empleado.Id)).Valor!.PinInicial;
        Assert.Equal(reset, Pin());

        var aud = (await api.AuditoriaAsync()).Valor!;
        Assert.True(aud.Count(a => a.Campo == "pines_consultados" && a.Administrador == "adm-pin1") >= 3);
    }

    [Fact]
    public async Task Un_PIN_elegido_antes_de_guardarse_legible_figura_como_no_disponible_hasta_resetearlo()
    {
        var api = await Admin("adm-pin2");
        var (emp, _, _) = _s.CrearDatos("PinViejo"); // creado «a la antigua»: solo con el hash

        var p = (await api.PinesAsync()).Valor!.First(x => x.Id == emp);
        Assert.Null(p.Pin);
        Assert.False((await api.EmpleadosAsync()).Valor!.First(x => x.Id == emp).PinConocido);

        await api.ResetearPinAsync(emp);
        Assert.NotNull((await api.PinesAsync()).Valor!.First(x => x.Id == emp).Pin);
        Assert.True((await api.EmpleadosAsync()).Valor!.First(x => x.Id == emp).PinConocido);
    }

    [Fact]
    public async Task El_Excel_de_PIN_trae_empleado_area_y_PIN_como_texto_se_filtra_por_area_y_deja_constancia()
    {
        var api = await Admin("adm-pin3");
        var a = (await api.CrearEmpleadoAsync("PinXlsOfi", "Oficina")).Valor!;
        var b = (await api.CrearEmpleadoAsync("PinXlsTal", "Taller")).Valor!;
        var (viejo, _, _) = _s.CrearDatos("PinXlsViejo");

        var todos = await api.PinesExcelAsync();
        Assert.True(todos.Ok);
        using (var wb = new XLWorkbook(new MemoryStream(todos.Valor!)))
        {
            var filas = wb.Worksheet("PIN").RowsUsed().Skip(1).Where(f => f.Cell(1).GetString().StartsWith("PinXls")).ToList();
            Assert.Equal(3, filas.Count);
            var fa = filas.First(f => f.Cell(1).GetString() == "PinXlsOfi");
            Assert.Equal("Oficina", fa.Cell(2).GetString());
            Assert.Equal(a.PinInicial, fa.Cell(4).GetString());                       // el PIN, como texto
            Assert.Equal("Taller", filas.First(f => f.Cell(1).GetString() == "PinXlsTal").Cell(2).GetString());
            var fv = filas.First(f => f.Cell(1).GetString() == "PinXlsViejo");
            Assert.Equal("No disponible", fv.Cell(4).GetString());                    // PIN anterior: hay que resetearlo
        }

        using (var wb = new XLWorkbook(new MemoryStream((await api.PinesExcelAsync("Taller")).Valor!)))
        {
            var nombres = wb.Worksheet("PIN").RowsUsed().Skip(1).Select(f => f.Cell(2).GetString()).Where(x => x is "Oficina" or "Taller").Distinct().ToList();
            Assert.Equal(["Taller"], nombres);
        }

        var aud = (await api.AuditoriaAsync()).Valor!;
        Assert.Equal(2, aud.Count(x => x.Campo == "pines_exportados" && x.Administrador == "adm-pin3"));
    }

    [Fact]
    public async Task Solo_un_administrador_puede_ver_o_exportar_los_PIN()
    {
        var (emp, _, _) = _s.CrearDatos("PinSeguridad");
        var cliente = _s.CreateClient();
        Assert.Equal(HttpStatusCode.Unauthorized, (await cliente.GetAsync("/api/admin/pines")).StatusCode);
        Assert.Equal(HttpStatusCode.Unauthorized, (await cliente.GetAsync("/api/admin/pines.xlsx")).StatusCode);

        // Ni siquiera con la sesión de un empleado.
        var empleado = await _s.ClienteAsync(emp);
        Assert.Equal(HttpStatusCode.Unauthorized, (await empleado.GetAsync("/api/admin/pines")).StatusCode);
    }

    // ---------------------------------------------------------------- base vieja

    [Fact]
    public async Task Una_base_anterior_a_las_areas_se_actualiza_y_todos_los_empleados_quedan_en_Oficina()
    {
        var dir = Path.Combine(Path.GetTempPath(), "play-esquema-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        var opciones = new DbContextOptionsBuilder<PlayDb>().UseSqlite($"Data Source={Path.Combine(dir, "vieja.db")};Pooling=False").Options;

        await using (var db = new PlayDb(opciones))
        {
            await db.Database.EnsureCreatedAsync();
            db.Empleados.AddRange(new Empleado { Nombre = "Ana", PinHash = "x" }, new Empleado { Nombre = "Beto", PinHash = "x" });
            await db.SaveChangesAsync();
            await db.Database.ExecuteSqlRawAsync("ALTER TABLE Empleados DROP COLUMN Area");
            await db.Database.ExecuteSqlRawAsync("ALTER TABLE Empleados DROP COLUMN PinVisible");
        }

        await using (var db = new PlayDb(opciones))
        {
            Assert.Equal(2, await Esquema.ActualizarAsync(db, dir)); // las dos columnas nuevas
            var emps = await db.Empleados.AsNoTracking().OrderBy(e => e.Nombre).ToListAsync();
            Assert.Equal(["Ana", "Beto"], emps.Select(e => e.Nombre).ToArray());
            Assert.All(emps, e => { Assert.Equal("Oficina", e.Area); Assert.Null(e.PinVisible); });
            Assert.Single(Directory.GetFiles(Path.Combine(dir, "backups"), "play-antes-de-actualizar-*.db"));
        }
        SqliteConnection.ClearAllPools();
    }
}
