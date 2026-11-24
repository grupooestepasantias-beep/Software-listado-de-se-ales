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

/// <summary>Subtareas propias de cada obra: obligatorias si la obra tiene alguna activa.</summary>
public class SubtareasTests : IClassFixture<ServerFixture>
{
    private readonly ServerFixture _s;
    public SubtareasTests(ServerFixture s) => _s = s;

    private async Task<AdminApi> Admin(string usuario)
    {
        _s.CrearAdmin(usuario, "clave-segura-1");
        var api = new AdminApi(new ApiClient(_s.CreateClient(), _s.Time));
        api.Token = (await api.LoginAsync(usuario, "clave-segura-1")).Valor!.Token;
        return api;
    }

    private sealed record Cliente(PanelController C, RedIntermitente Red, ApiClient Api);

    private async Task<Cliente> Panel(int empleadoId, string equipo = "PC-1")
    {
        var red = new RedIntermitente(new ApiClient(_s.CreateClient(), _s.Time));
        var c = new PanelController(red, new LocalStore(Path.Combine(Path.GetTempPath(), "play-cli-" + Guid.NewGuid().ToString("N"))), _s.Time, equipo);
        Assert.True(await c.CargarListasAsync());
        Assert.Null(await c.LoginAsync(empleadoId, "1234"));
        return new Cliente(c, red, new ApiClient(_s.CreateClient(), _s.Time));
    }

    private List<RegistroTiempo> Registros(int empleadoId)
    {
        using var scope = _s.Services.Scope();
        return scope.Db.Registros.AsNoTracking().Where(r => r.EmpleadoId == empleadoId).OrderBy(r => r.InicioUtc).ToList();
    }

    private async Task Pasar(Cliente c, TimeSpan total)
    {
        for (var t = TimeSpan.Zero; t < total; t += TimeSpan.FromSeconds(30))
        {
            _s.Time.Advance(TimeSpan.FromSeconds(30));
            await c.C.TickAsync();
        }
    }

    // ---------------------------------------------------------------- administración

    [Fact]
    public async Task El_administrador_crea_renombra_y_desactiva_subtareas_de_una_obra_sin_nombres_repetidos()
    {
        var api = await Admin("adm-st1");
        var (_, obra, otraObra) = _s.CrearDatos("StAdmin");

        var a = (await api.CrearSubtareaAsync(obra, "Fundación")).Valor!;
        Assert.Equal("nombre_duplicado", (await api.CrearSubtareaAsync(obra, "Fundación")).Codigo);
        Assert.True((await api.CrearSubtareaAsync(otraObra, "Fundación")).Ok); // el mismo nombre en OTRA obra sí se puede
        Assert.Equal("nombre_requerido", (await api.CrearSubtareaAsync(obra, "  ")).Codigo);
        Assert.Equal(404, (int)(await api.CrearSubtareaAsync(99999, "X")).Status!);

        Assert.Equal("Cimientos", (await api.ActualizarSubtareaAsync(a.Id, nombre: "Cimientos")).Valor!.Nombre);
        Assert.Equal(1, (await api.ObrasAsync()).Valor!.First(o => o.Id == obra).SubtareasActivas);
        Assert.False((await api.ActualizarSubtareaAsync(a.Id, activa: false)).Valor!.Activa);
        Assert.Equal(0, (await api.ObrasAsync()).Valor!.First(o => o.Id == obra).SubtareasActivas);
        Assert.Contains((await api.SubtareasAsync(obra)).Valor!, s => s.Id == a.Id && !s.Activa); // las inactivas se siguen listando
    }

    [Fact]
    public async Task La_lista_publica_de_obras_trae_solo_las_subtareas_activas()
    {
        var api = await Admin("adm-st2");
        var (_, obra, sinSubtareas) = _s.CrearDatos("StPublica");
        var activa = (await api.CrearSubtareaAsync(obra, "Estructura")).Valor!;
        var inactiva = (await api.CrearSubtareaAsync(obra, "Vieja")).Valor!;
        await api.ActualizarSubtareaAsync(inactiva.Id, activa: false);

        var obras = (await new ApiClient(_s.CreateClient(), _s.Time).ObrasAsync()).Valor!;
        Assert.Equal(["Estructura"], obras.First(o => o.Id == obra).Subtareas!.Select(s => s.Nombre).ToArray());
        Assert.Empty(obras.First(o => o.Id == sinSubtareas).Subtareas ?? []);
        _ = activa;
    }

    // ---------------------------------------------------------------- obligatoriedad (servidor)

    [Fact]
    public async Task Si_la_obra_tiene_subtareas_Play_exige_una_valida_de_esa_obra()
    {
        var api = await Admin("adm-st3");
        var (emp, obra, otraObra) = _s.CrearDatos("StReglas");
        var propia = (await api.CrearSubtareaAsync(obra, "Soldadura")).Valor!;
        var ajena = (await api.CrearSubtareaAsync(otraObra, "Pintura")).Valor!;
        await api.ActualizarSubtareaAsync(ajena.Id, activa: false); // otraObra queda sin subtareas ACTIVAS

        var empleado = new ApiClient(_s.CreateClient(), _s.Time);
        empleado.Token = (await empleado.LoginAsync(emp, "1234")).Valor!.Token;

        Assert.Equal("subtarea_requerida", (await empleado.IniciarAsync(Guid.NewGuid(), obra, null, "PC")).Codigo);
        Assert.Equal("subtarea_invalida", (await empleado.IniciarAsync(Guid.NewGuid(), obra, ajena.Id, "PC")).Codigo);   // de otra obra
        Assert.Equal("subtarea_invalida", (await empleado.IniciarAsync(Guid.NewGuid(), otraObra, propia.Id, "PC")).Codigo); // obra sin subtareas
        Assert.Empty(Registros(emp)); // ninguno de esos intentos dejó nada

        var ok = await empleado.IniciarAsync(Guid.NewGuid(), obra, propia.Id, "PC");
        Assert.True(ok.Ok);
        Assert.Equal(propia.Id, ok.Valor!.SubtareaId);
        Assert.Equal(propia.Id, Registros(emp).Single().SubtareaId);
    }

    [Fact]
    public async Task Al_desactivar_todas_las_subtareas_la_obra_deja_de_exigirlas()
    {
        var api = await Admin("adm-st4");
        var (emp, obra, _) = _s.CrearDatos("StDesactivar");
        var s = (await api.CrearSubtareaAsync(obra, "Única")).Valor!;
        var empleado = new ApiClient(_s.CreateClient(), _s.Time);
        empleado.Token = (await empleado.LoginAsync(emp, "1234")).Valor!.Token;
        Assert.Equal("subtarea_requerida", (await empleado.IniciarAsync(Guid.NewGuid(), obra, null, "PC")).Codigo);

        await api.ActualizarSubtareaAsync(s.Id, activa: false);
        Assert.True((await empleado.IniciarAsync(Guid.NewGuid(), obra, null, "PC")).Ok);
    }

    // ---------------------------------------------------------------- panel

    [Fact]
    public async Task El_panel_no_deja_presionar_Play_sin_subtarea_y_registra_la_elegida()
    {
        var api = await Admin("adm-st5");
        var (emp, obra, _) = _s.CrearDatos("StPanel");
        var sub = (await api.CrearSubtareaAsync(obra, "Armado")).Valor!;
        var p = await Panel(emp);

        Assert.Single(p.C.SubtareasDe(obra));
        await p.C.PlayAsync(obra); // sin elegir
        Assert.Equal(EstadoPanel.Pausado, p.C.Estado);
        Assert.Contains("subtarea", p.C.Aviso);
        Assert.Empty(Registros(emp)); // ni siquiera llegó al servidor

        await p.C.PlayAsync(obra, sub.Id);
        Assert.Equal(EstadoPanel.Registrando, p.C.Estado);
        Assert.Equal(sub.Id, p.C.SubtareaActualId);
        await Pasar(p, TimeSpan.FromMinutes(5));
        await p.C.PauseAsync();

        var r = Registros(emp).Single();
        Assert.Equal(sub.Id, r.SubtareaId);
        Assert.Equal(300, (r.FinUtc!.Value - r.InicioUtc).TotalSeconds);
    }

    [Fact]
    public async Task Cambiar_de_subtarea_en_la_misma_obra_cierra_una_y_abre_la_otra_sin_huecos_y_el_resumen_las_separa()
    {
        var api = await Admin("adm-st6");
        var (emp, obra, _) = _s.CrearDatos("StCambio");
        var a = (await api.CrearSubtareaAsync(obra, "Corte")).Valor!;
        var b = (await api.CrearSubtareaAsync(obra, "Pintura")).Valor!;
        var p = await Panel(emp);

        await p.C.PlayAsync(obra, a.Id);
        await Pasar(p, TimeSpan.FromMinutes(10));
        await p.C.CambiarObraAsync(obra, b.Id); // misma obra, otra subtarea
        Assert.Equal(b.Id, p.C.SubtareaActualId);
        await Pasar(p, TimeSpan.FromMinutes(4));
        await p.C.PauseAsync();

        var regs = Registros(emp);
        Assert.Equal(2, regs.Count);
        Assert.Equal((a.Id, 600.0), (regs[0].SubtareaId, (regs[0].FinUtc!.Value - regs[0].InicioUtc).TotalSeconds));
        Assert.Equal((b.Id, 240.0), (regs[1].SubtareaId, (regs[1].FinUtc!.Value - regs[1].InicioUtc).TotalSeconds));
        Assert.Equal(regs[0].FinUtc, regs[1].InicioUtc); // sin huecos ni solapes

        var resumen = (await p.C.ObtenerResumenAsync())!.Hoy.PorObra;
        Assert.Equal(600, resumen.First(x => x.Obra.EndsWith("› Corte")).Segundos);
        Assert.Equal(240, resumen.First(x => x.Obra.EndsWith("› Pintura")).Segundos);
    }

    [Fact]
    public async Task Sin_conexion_la_subtarea_se_guarda_en_la_PC_y_llega_al_servidor_al_volver_la_red()
    {
        var api = await Admin("adm-st7");
        var (emp, obra, _) = _s.CrearDatos("StOffline");
        var sub = (await api.CrearSubtareaAsync(obra, "Montaje")).Valor!;
        var p = await Panel(emp);
        p.Red.Caida = true;

        await p.C.PlayAsync(obra, sub.Id);
        await Pasar(p, TimeSpan.FromMinutes(3));
        await p.C.PauseAsync(); // sin red
        p.Red.Caida = false;
        await Pasar(p, TimeSpan.FromMinutes(1));

        var r = Registros(emp).Single();
        Assert.Equal(sub.Id, r.SubtareaId);
        Assert.Equal(180, (r.FinUtc!.Value - r.InicioUtc).TotalSeconds);
    }

    [Fact]
    public async Task Un_registro_hecho_sin_conexion_cuando_la_obra_ya_exige_subtarea_se_guarda_igual_y_queda_para_revisar()
    {
        var api = await Admin("adm-st8");
        var (emp, obra, _) = _s.CrearDatos("StSync");
        await api.CrearSubtareaAsync(obra, "Nueva exigencia"); // el administrador la agregó mientras el panel estaba sin red
        var empleado = new ApiClient(_s.CreateClient(), _s.Time);
        empleado.Token = (await empleado.LoginAsync(emp, "1234")).Valor!.Token;
        var ahora = _s.Time.GetUtcNow().UtcDateTime;
        var item = new SincronizarItem(Guid.NewGuid(), obra, ahora.AddHours(-2), ahora.AddHours(-1), "PC-X"); // sin subtarea

        var r = await empleado.SincronizarAsync([item]);
        Assert.Equal("insertado_revisar", r.Valor![0].Resultado); // no se pierden las horas
        var guardado = Registros(emp).Single();
        Assert.Null(guardado.SubtareaId);
        Assert.True(guardado.RevisarAdmin);
    }

    // ---------------------------------------------------------------- administración de registros y reportes

    [Fact]
    public async Task El_administrador_corrige_la_subtarea_de_un_registro_y_queda_constancia_y_al_cambiar_de_obra_se_quita()
    {
        var api = await Admin("adm-st9");
        var (emp, obra, otraObra) = _s.CrearDatos("StCorreccion");
        var a = (await api.CrearSubtareaAsync(obra, "Primera")).Valor!;
        var b = (await api.CrearSubtareaAsync(obra, "Segunda")).Valor!;
        var ajena = (await api.CrearSubtareaAsync(otraObra, "Ajena")).Valor!;
        var fin = _s.Time.GetUtcNow().UtcDateTime.AddMinutes(-10);

        Assert.Equal("subtarea_requerida", (await api.CrearRegistroAsync(emp, obra, fin.AddHours(-2), fin, "Carga")).Codigo);
        Assert.Equal("subtarea_invalida", (await api.CrearRegistroAsync(emp, obra, fin.AddHours(-2), fin, "Carga", ajena.Id)).Codigo);
        var reg = (await api.CrearRegistroAsync(emp, obra, fin.AddHours(-2), fin, "Carga", a.Id)).Valor!;
        Assert.Equal("Primera", reg.Subtarea);

        var corregido = (await api.CorregirAsync(reg.Id, null, null, null, "Era la segunda", b.Id)).Valor!;
        Assert.Equal("Segunda", corregido.Subtarea);
        Assert.Equal("subtarea_invalida", (await api.CorregirAsync(reg.Id, null, null, null, "x", ajena.Id)).Codigo);

        var aud = (await api.AuditoriaAsync(reg.Id)).Valor!.First(x => x.Campo == "subtarea");
        Assert.Equal(("Primera", "Segunda"), (aud.ValorAnterior, aud.ValorNuevo));

        // Cambiar de obra sin indicar subtarea: la subtarea anterior ya no corresponde y se quita.
        var enOtraObra = (await api.CorregirAsync(reg.Id, null, null, otraObra, "Era otra obra")).Valor!;
        Assert.Null(enOtraObra.SubtareaId);
        Assert.Equal(otraObra, enOtraObra.ObraId);
    }

    [Fact]
    public async Task La_lista_de_registros_el_en_vivo_y_el_Excel_muestran_la_subtarea()
    {
        var api = await Admin("adm-st10");
        var (emp, obra, _) = _s.CrearDatos("StReportes");
        var sub = (await api.CrearSubtareaAsync(obra, "Terminaciones")).Valor!;
        var p = await Panel(emp);
        await p.C.PlayAsync(obra, sub.Id);

        Assert.Equal("Obra A StReportes › Terminaciones", (await api.EnVivoAsync()).Valor!.First(v => v.Empleado == "StReportes").Obra);
        await Pasar(p, TimeSpan.FromMinutes(90));
        await p.C.PauseAsync();

        var reg = (await api.RegistrosAsync(new FiltroAdmin(EmpleadoId: emp))).Valor!.Single();
        Assert.Equal("Terminaciones", reg.Subtarea);

        using var wb = new XLWorkbook(new MemoryStream((await api.ReporteExcelAsync(new FiltroAdmin(EmpleadoId: emp))).Valor!));
        var det = wb.Worksheet("Detalle");
        Assert.Equal("Subtarea", det.Cell(1, 5).GetString());
        Assert.Equal("Terminaciones", det.RowsUsed().Skip(1).First().Cell(5).GetString());
        var porSub = wb.Worksheet("Por subtarea").RowsUsed().Skip(1).First(f => f.Cell(2).GetString() == "Terminaciones");
        Assert.Equal("Obra A StReportes", porSub.Cell(1).GetString());
        Assert.Equal(1.5, porSub.Cell(3).GetDouble(), 2);
    }

    // ---------------------------------------------------------------- base vieja

    [Fact]
    public async Task Una_base_anterior_a_las_subtareas_se_actualiza_y_conserva_los_datos()
    {
        var dir = Path.Combine(Path.GetTempPath(), "play-esquema-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        var cs = $"Data Source={Path.Combine(dir, "antigua.db")};Pooling=False";

        // Base «de antes»: las tablas mínimas sin áreas, PIN legible ni subtareas, con una obra y un registro.
        await using (var cn = new SqliteConnection(cs))
        {
            await cn.OpenAsync();
            foreach (var sql in new[]
            {
                "CREATE TABLE Empleados (Id INTEGER PRIMARY KEY AUTOINCREMENT, Nombre TEXT NOT NULL)",
                "CREATE TABLE Obras (Id INTEGER PRIMARY KEY AUTOINCREMENT, Nombre TEXT NOT NULL, Activa INTEGER NOT NULL)",
                "CREATE TABLE Registros (Id TEXT PRIMARY KEY, EmpleadoId INTEGER NOT NULL, ObraId INTEGER NOT NULL)",
                "INSERT INTO Empleados (Nombre) VALUES ('Ana')",
                "INSERT INTO Obras (Nombre, Activa) VALUES ('Vieja', 1)",
                "INSERT INTO Registros (Id, EmpleadoId, ObraId) VALUES ('11111111-1111-1111-1111-111111111111', 1, 1)",
            })
            {
                await using var cmd = cn.CreateCommand();
                cmd.CommandText = sql;
                await cmd.ExecuteNonQueryAsync();
            }
        }

        var opciones = new DbContextOptionsBuilder<PlayDb>().UseSqlite(cs).Options;
        await using (var db = new PlayDb(opciones))
        {
            // Anulado + Area + PinVisible + SubtareaId + Terminada + TerminadaUtc (columnas) + CreadoFecha + las tablas Subtareas, Faltas, Ajustes, CargasHoras y AvisosSubtarea
            Assert.Equal(14, await Esquema.ActualizarAsync(db, dir));
            Assert.Single(Directory.GetFiles(Path.Combine(dir, "backups"), "play-antes-de-actualizar-*.db"));
            Assert.Equal(0, await Esquema.ActualizarAsync(db, dir)); // idempotente
        }

        await using (var cn = new SqliteConnection(cs))
        {
            await cn.OpenAsync();
            async Task<long> Contar(string sql) { await using var c = cn.CreateCommand(); c.CommandText = sql; return Convert.ToInt64(await c.ExecuteScalarAsync()); }
            await using (var ins = cn.CreateCommand())
            {
                ins.CommandText = "INSERT INTO Subtareas (ObraId, Nombre, Activa) VALUES (1, 'Fundación', 1)";
                await ins.ExecuteNonQueryAsync();
            }
            Assert.Equal(1, await Contar("SELECT COUNT(*) FROM Subtareas"));
            Assert.Equal(1, await Contar("SELECT COUNT(*) FROM pragma_table_info('Registros') WHERE name = 'SubtareaId'"));
            Assert.Equal(1, await Contar("SELECT COUNT(*) FROM Registros WHERE SubtareaId IS NULL")); // el registro de antes sigue ahí, sin subtarea
            Assert.Equal(1, await Contar("SELECT COUNT(*) FROM Empleados WHERE Area = 'Oficina'"));
        }
        SqliteConnection.ClearAllPools();
    }
}

/// <summary>Atajo para usar la base del servidor de pruebas desde un ámbito de servicios.</summary>
internal static class ScopeExtensions
{
    public sealed class Ambito(Microsoft.Extensions.DependencyInjection.IServiceScope scope) : IDisposable
    {
        public PlayDb Db { get; } = scope.ServiceProvider.GetService(typeof(PlayDb)) is PlayDb d ? d : throw new InvalidOperationException();
        public void Dispose() => scope.Dispose();
    }

    public static Ambito Scope(this IServiceProvider sp) => new(Microsoft.Extensions.DependencyInjection.ServiceProviderServiceExtensions.CreateScope(sp));
}
