using System.Net;
using ClosedXML.Excel;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Play.Client;
using Play.Server.Data;
using Play.Server.Services;
using Xunit;
using RegistroAdminDto = Play.Client.RegistroAdminDto;
using SincronizarItem = Play.Client.SincronizarItem;

namespace Play.Server.Tests;

/// <summary>Eliminar / recuperar registros (se marcan, no se borran) y actualización de bases viejas.</summary>
public class EliminarRegistrosTests : IClassFixture<ServerFixture>
{
    private readonly ServerFixture _s;
    public EliminarRegistrosTests(ServerFixture s) => _s = s;

    private async Task<AdminApi> Admin(string usuario)
    {
        _s.CrearAdmin(usuario, "clave-segura-1");
        var api = new AdminApi(new ApiClient(_s.CreateClient(), _s.Time));
        api.Token = (await api.LoginAsync(usuario, "clave-segura-1")).Valor!.Token;
        return api;
    }

    private async Task<RegistroAdminDto> CrearRegistro(AdminApi api, int emp, int obra, int horas = 2)
    {
        var fin = _s.Time.GetUtcNow().UtcDateTime.AddMinutes(-10);
        return (await api.CrearRegistroAsync(emp, obra, fin.AddHours(-horas), fin, "Carga de prueba")).Valor!;
    }

    private static FiltroAdmin Todos(int emp, bool eliminados = false) => new(EmpleadoId: emp, Eliminados: eliminados);

    [Fact]
    public async Task Eliminar_exige_motivo_oculta_el_registro_y_lo_deja_en_la_lista_de_eliminados()
    {
        var api = await Admin("adm-del1");
        var (emp, obra, _) = _s.CrearDatos("DelUno");
        var reg = await CrearRegistro(api, emp, obra);

        Assert.Equal("motivo_requerido", (await api.EliminarRegistroAsync(reg.Id, "  ")).Codigo);
        var ok = await api.EliminarRegistroAsync(reg.Id, "Lo cargué por error");
        Assert.True(ok.Ok);
        Assert.True(ok.Valor!.Anulado);

        Assert.Empty((await api.RegistrosAsync(Todos(emp))).Valor!);
        var eliminados = (await api.RegistrosAsync(Todos(emp, eliminados: true))).Valor!;
        Assert.Equal(reg.Id, Assert.Single(eliminados).Id);
        Assert.True(eliminados[0].Anulado);

        // Queda constancia: quién, cuándo y por qué (y con qué datos).
        var aud = (await api.AuditoriaAsync(reg.Id)).Valor!;
        var fila = aud.First(a => a.Campo == "anulado");
        Assert.Equal("adm-del1", fila.Administrador);
        Assert.Equal("Lo cargué por error", fila.Motivo);
        Assert.Contains("DelUno", fila.ValorAnterior);
    }

    [Fact]
    public async Task Un_registro_eliminado_no_cuenta_en_el_resumen_del_empleado_ni_en_el_Excel()
    {
        var api = await Admin("adm-del2");
        var (emp, obra, _) = _s.CrearDatos("DelDos");
        var reg = await CrearRegistro(api, emp, obra, horas: 2);

        var panel = new PanelController(new ApiClient(_s.CreateClient(), _s.Time), new LocalStore(Path.Combine(Path.GetTempPath(), "play-cli-" + Guid.NewGuid().ToString("N"))), _s.Time, "PC-1");
        Assert.True(await panel.CargarListasAsync());
        Assert.Null(await panel.LoginAsync(emp, "1234"));
        Assert.Equal(7200, (await panel.ObtenerResumenAsync())!.Hoy.TotalSegundos);
        Assert.Equal(1, FilasDeExcel(await api.ReporteExcelAsync(new FiltroAdmin(EmpleadoId: emp)), "DelDos"));

        await api.EliminarRegistroAsync(reg.Id, "Duplicado");
        Assert.Equal(0, (await panel.ObtenerResumenAsync())!.Hoy.TotalSegundos);
        Assert.Equal(0, FilasDeExcel(await api.ReporteExcelAsync(new FiltroAdmin(EmpleadoId: emp)), "DelDos"));

        // Al recuperarlo vuelve a contar.
        Assert.False((await api.RecuperarRegistroAsync(reg.Id, " ")).Ok);
        Assert.False((await api.RecuperarRegistroAsync(reg.Id, "Estaba bien")).Valor!.Anulado);
        Assert.Equal(7200, (await panel.ObtenerResumenAsync())!.Hoy.TotalSegundos);
        Assert.Equal(1, FilasDeExcel(await api.ReporteExcelAsync(new FiltroAdmin(EmpleadoId: emp)), "DelDos"));
        Assert.Contains((await api.AuditoriaAsync(reg.Id)).Valor!, a => a.Campo == "restaurado" && a.Motivo == "Estaba bien");
    }

    private static int FilasDeExcel(ApiResult<byte[]> r, string empleado)
    {
        using var wb = new XLWorkbook(new MemoryStream(r.Valor!));
        return wb.Worksheet("Detalle").RowsUsed().Skip(1).Count(f => f.Cell(2).GetString() == empleado);
    }

    [Fact]
    public async Task No_se_puede_eliminar_un_registro_en_curso()
    {
        var api = await Admin("adm-del3");
        var (emp, obra, _) = _s.CrearDatos("DelTres");
        var panel = new PanelController(new ApiClient(_s.CreateClient(), _s.Time), new LocalStore(Path.Combine(Path.GetTempPath(), "play-cli-" + Guid.NewGuid().ToString("N"))), _s.Time, "PC-1");
        await panel.CargarListasAsync();
        await panel.LoginAsync(emp, "1234");
        await panel.PlayAsync(obra);

        var vivo = (await api.RegistrosAsync(Todos(emp))).Valor!.Single();
        var r = await api.EliminarRegistroAsync(vivo.Id, "Prueba");
        Assert.Equal(HttpStatusCode.Conflict, r.Status);
        Assert.Equal("registro_abierto", r.Codigo);
        Assert.Equal(EstadoPanel.Registrando, panel.Estado); // el empleado no se entera de nada
    }

    [Fact]
    public async Task Un_registro_eliminado_no_se_corrige_ni_se_resucita_por_sincronizacion()
    {
        var api = await Admin("adm-del4");
        var (emp, obra, _) = _s.CrearDatos("DelCuatro");
        var reg = await CrearRegistro(api, emp, obra);
        await api.EliminarRegistroAsync(reg.Id, "Error");

        var corr = await api.CorregirAsync(reg.Id, null, null, null, "x");
        Assert.Equal("registro_eliminado", corr.Codigo);

        // El panel de ese empleado reenvía el mismo registro (por ejemplo desde su cola sin conexión): no revive.
        var empleadoApi = new ApiClient(_s.CreateClient(), _s.Time);
        empleadoApi.Token = (await empleadoApi.LoginAsync(emp, "1234")).Valor!.Token;
        var envio = await empleadoApi.SincronizarAsync([new SincronizarItem(reg.Id, obra, reg.InicioUtc, reg.FinUtc, "PC-1")]);
        Assert.Equal("duplicado", envio.Valor![0].Resultado);
        Assert.Empty((await api.RegistrosAsync(Todos(emp))).Valor!);
    }

    [Fact]
    public async Task Una_base_creada_por_una_version_anterior_se_actualiza_sin_perder_datos_y_con_copia_previa()
    {
        var dir = Path.Combine(Path.GetTempPath(), "play-esquema-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        var cs = $"Data Source={Path.Combine(dir, "vieja.db")};Pooling=False";
        var opciones = new DbContextOptionsBuilder<PlayDb>().UseSqlite(cs).Options;

        // 1) base «vieja»: sin la columna Anulado, con un registro adentro
        await using (var db = new PlayDb(opciones))
        {
            await db.Database.EnsureCreatedAsync();
            var e = new Empleado { Nombre = "Viejo", PinHash = "x" };
            var o = new Obra { Nombre = "Vieja" };
            db.AddRange(e, o);
            await db.SaveChangesAsync();
            db.Registros.Add(new RegistroTiempo { Id = Guid.NewGuid(), EmpleadoId = e.Id, ObraId = o.Id, InicioUtc = DateTime.UtcNow.AddHours(-2), FinUtc = DateTime.UtcNow.AddHours(-1), Estado = EstadoRegistro.Cerrado });
            await db.SaveChangesAsync();
            await db.Database.ExecuteSqlRawAsync("ALTER TABLE Registros DROP COLUMN Anulado");
        }

        // 2) arranque de la versión nueva: agrega la columna, hace copia antes y conserva el registro
        await using (var db = new PlayDb(opciones))
        {
            Assert.Equal(1, await Esquema.ActualizarAsync(db, dir));
            Assert.Single(Directory.GetFiles(Path.Combine(dir, "backups"), "play-antes-de-actualizar-*.db"));
            var registros = await db.Registros.AsNoTracking().ToListAsync();
            Assert.Single(registros);
            Assert.False(registros[0].Anulado);
            Assert.Equal(0, await Esquema.ActualizarAsync(db, dir)); // idempotente
        }
        SqliteConnection.ClearAllPools();
    }
}
