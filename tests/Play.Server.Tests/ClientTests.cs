using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Play.Client;
using Play.Server.Data;
using Xunit;

namespace Play.Server.Tests;

/// <summary>API simulada que puede «cortar la red» sobre un cliente real.</summary>
internal sealed class RedIntermitente(IPlayApi inner) : IPlayApi
{
    public bool Caida { get; set; }
    public string? Token { get => inner.Token; set => inner.Token = value; }
    public TimeSpan Desfase => inner.Desfase;
    private Task<ApiResult<T>> W<T>(Func<Task<ApiResult<T>>> f) => Caida ? Task.FromResult(ApiResult<T>.Red) : f();

    public Task<ApiResult<ConfigServidor>> ConfigAsync() => W(inner.ConfigAsync);
    public Task<ApiResult<List<ItemLista>>> EmpleadosAsync() => W(inner.EmpleadosAsync);
    public Task<ApiResult<List<ObraPublica>>> ObrasAsync() => W(inner.ObrasAsync);
    public Task<ApiResult<LoginResponse>> LoginAsync(int e, string p) => W(() => inner.LoginAsync(e, p));
    public Task<ApiResult<Vacio>> CambiarPinAsync(string a, string n) => W(() => inner.CambiarPinAsync(a, n));
    public Task<ApiResult<RegistroDto>> IniciarAsync(Guid id, int o, int? s, string e) => W(() => inner.IniciarAsync(id, o, s, e));
    public Task<ApiResult<RegistroDto>> CambiarObraAsync(Guid id, int o, int? s, string e) => W(() => inner.CambiarObraAsync(id, o, s, e));
    public Task<ApiResult<RegistroDto>> LatidoAsync(Guid id) => W(() => inner.LatidoAsync(id));
    public Task<ApiResult<RegistroDto>> CerrarAsync(Guid id, DateTime? f) => W(() => inner.CerrarAsync(id, f));
    public Task<ApiResult<List<SincronizarResultado>>> SincronizarAsync(List<SincronizarItem> i) => W(() => inner.SincronizarAsync(i));
    public Task<ApiResult<ResumenDto>> ResumenAsync() => W(inner.ResumenAsync);
    public Task<ApiResult<Vacio>> AvisarSubtareaAsync(int subtareaId) => W(() => inner.AvisarSubtareaAsync(subtareaId));
    public Task<ApiResult<Vacio>> RetirarAvisoAsync(int subtareaId) => W(() => inner.RetirarAvisoAsync(subtareaId));
    public Task<ApiResult<List<int>>> MisAvisosAsync() => W(inner.MisAvisosAsync);
    public Task<ApiResult<MisHorasDto>> MisHorasAsync() => W(inner.MisHorasAsync);
    public Task<ApiResult<CargaDto>> CargarHorasAsync(DateOnly f, int m, int? o = null, int? s = null) => W(() => inner.CargarHorasAsync(f, m, o, s));
    public Task<ApiResult<Vacio>> RetirarHorasAsync(DateOnly f, int? o = null, int? s = null) => W(() => inner.RetirarHorasAsync(f, o, s));
}

public class ClientTests : IClassFixture<ServerFixture>
{
    private readonly ServerFixture _s;
    public ClientTests(ServerFixture s) => _s = s;

    private sealed record Cliente(PanelController C, RedIntermitente Red, LocalStore Store, string Carpeta);

    private Cliente NuevoCliente(string equipo = "PC-1", string? carpeta = null)
    {
        carpeta ??= Path.Combine(Path.GetTempPath(), "play-cli-" + Guid.NewGuid().ToString("N"));
        var red = new RedIntermitente(new ApiClient(_s.CreateClient(), _s.Time));
        var store = new LocalStore(carpeta);
        return new Cliente(new PanelController(red, store, _s.Time, equipo), red, store, carpeta);
    }

    private async Task<Cliente> ConSesion(int empleadoId, string equipo = "PC-1")
    {
        var c = NuevoCliente(equipo);
        Assert.True(await c.C.CargarListasAsync());
        Assert.Null(await c.C.LoginAsync(empleadoId, "1234"));
        return c;
    }

    /// <summary>Avanza el reloj de a 30 s, llamando al tick del panel en cada paso (como la interfaz real).</summary>
    private async Task Pasar(Cliente c, TimeSpan total)
    {
        for (var t = TimeSpan.Zero; t < total; t += TimeSpan.FromSeconds(30))
        {
            _s.Time.Advance(TimeSpan.FromSeconds(30));
            await c.C.TickAsync();
        }
    }

    private List<RegistroTiempo> Registros(int empleadoId)
    {
        using var scope = _s.Services.CreateScope();
        return scope.ServiceProvider.GetRequiredService<PlayDb>().Registros.AsNoTracking()
            .Where(r => r.EmpleadoId == empleadoId).OrderBy(r => r.InicioUtc).ToList();
    }

    private static double Segundos(RegistroTiempo r) => (r.FinUtc!.Value - r.InicioUtc).TotalSeconds;

    // ---------------------------------------------------------------- flujo normal

    [Fact]
    public async Task Play_y_Pause_registran_el_tiempo_y_mandan_latidos()
    {
        var (emp, obra, _) = _s.CrearDatos("CliNormal");
        var c = await ConSesion(emp);
        Assert.Equal(EstadoPanel.Pausado, c.C.Estado);

        await c.C.PlayAsync(obra);
        Assert.Equal(EstadoPanel.Registrando, c.C.Estado);
        await Pasar(c, TimeSpan.FromMinutes(10));
        Assert.Equal(TimeSpan.FromMinutes(10), c.C.Transcurrido);
        await c.C.PauseAsync();

        Assert.Equal(EstadoPanel.Pausado, c.C.Estado);
        var r = Assert.Single(Registros(emp));
        Assert.Equal(EstadoRegistro.Cerrado, r.Estado);
        Assert.Equal(600, Segundos(r));
        Assert.True(r.UltimoLatidoUtc > r.InicioUtc.AddMinutes(9)); // hubo latidos durante el trabajo

        var resumen = await c.C.ObtenerResumenAsync();
        Assert.Equal(600, resumen!.Hoy.TotalSegundos);
    }

    [Fact]
    public async Task PIN_incorrecto_no_inicia_sesion()
    {
        var (emp, _, _) = _s.CrearDatos("CliPin");
        var c = NuevoCliente();
        await c.C.CargarListasAsync();
        Assert.Equal("PIN incorrecto.", await c.C.LoginAsync(emp, "9999"));
        Assert.Equal(EstadoPanel.SinSesion, c.C.Estado);
    }

    [Fact]
    public async Task Cambiar_de_obra_cierra_la_anterior_y_abre_la_nueva()
    {
        var (emp, a, b) = _s.CrearDatos("CliCambio");
        var c = await ConSesion(emp);
        await c.C.PlayAsync(a);
        await Pasar(c, TimeSpan.FromMinutes(5));
        await c.C.CambiarObraAsync(b);
        Assert.Equal(b, c.C.ObraActualId);
        await Pasar(c, TimeSpan.FromMinutes(3));
        await c.C.PauseAsync();

        var regs = Registros(emp);
        Assert.Equal(2, regs.Count);
        Assert.Equal((a, 300.0), (regs[0].ObraId, Segundos(regs[0])));
        Assert.Equal((b, 180.0), (regs[1].ObraId, Segundos(regs[1])));
    }

    [Fact]
    public async Task Segundo_Play_desde_otra_PC_se_bloquea_y_avisa_donde_esta_el_registro()
    {
        var (emp, obra, _) = _s.CrearDatos("CliDoble");
        var pc1 = await ConSesion(emp, "PC-OFICINA");
        var pc2 = await ConSesion(emp, "PC-OBRA");
        await pc1.C.PlayAsync(obra);

        await pc2.C.PlayAsync(obra);
        Assert.Equal(EstadoPanel.Pausado, pc2.C.Estado);
        Assert.Contains("PC-OFICINA", pc2.C.Aviso);
        Assert.Single(Registros(emp));
    }

    // ---------------------------------------------------------------- cierres inesperados

    [Fact]
    public async Task Si_el_programa_se_cerro_con_el_cronometro_andando_al_volver_cierra_en_el_ultimo_latido()
    {
        var (emp, obra, _) = _s.CrearDatos("CliCrash");
        var antes = await ConSesion(emp, "PC-1");
        await antes.C.PlayAsync(obra);
        var inicio = _s.Time.GetUtcNow().UtcDateTime;
        await Pasar(antes, TimeSpan.FromMinutes(2)); // último latido a los 2 min; después «se cierra el programa»

        var despues = await ConSesion(emp, "PC-1"); // reabre el programa en la misma PC
        Assert.Equal(EstadoPanel.Pausado, despues.C.Estado);
        Assert.NotNull(despues.C.Aviso);
        var r = Assert.Single(Registros(emp));
        Assert.Equal(EstadoRegistro.Cerrado, r.Estado);
        Assert.Equal(inicio.AddMinutes(2), r.FinUtc);
    }

    [Fact]
    public async Task Si_la_PC_se_suspende_el_registro_termina_en_el_ultimo_momento_activo()
    {
        var (emp, obra, _) = _s.CrearDatos("CliSuspension");
        var c = await ConSesion(emp);
        await c.C.PlayAsync(obra);
        await Pasar(c, TimeSpan.FromMinutes(5));

        _s.Time.Advance(TimeSpan.FromHours(8)); // la PC durmió toda la noche
        await c.C.TickAsync();

        Assert.Equal(EstadoPanel.Pausado, c.C.Estado);
        Assert.Contains("suspendida", c.C.Aviso);
        var r = Assert.Single(Registros(emp));
        Assert.Equal(EstadoRegistro.Cerrado, r.Estado);
        Assert.Equal(300, Segundos(r));
    }

    // ---------------------------------------------------------------- sin conexión

    [Fact]
    public async Task Play_sin_conexion_se_guarda_en_la_PC_y_se_envia_cuando_vuelve_la_red()
    {
        var (emp, obra, _) = _s.CrearDatos("CliOffline1");
        var c = await ConSesion(emp);
        c.Red.Caida = true;

        await c.C.PlayAsync(obra);
        Assert.Equal(EstadoPanel.Registrando, c.C.Estado);
        Assert.Single(c.Store.Pendientes);
        await Pasar(c, TimeSpan.FromMinutes(5));
        Assert.False(c.C.Conectado);
        Assert.Empty(Registros(emp)); // el servidor todavía no sabe nada

        c.Red.Caida = false;
        await Pasar(c, TimeSpan.FromMinutes(1));
        Assert.True(c.C.Conectado);
        Assert.Empty(c.Store.Pendientes);
        Assert.Equal(EstadoRegistro.Abierto, Assert.Single(Registros(emp)).Estado);

        await c.C.PauseAsync();
        var r = Assert.Single(Registros(emp));
        Assert.Equal(EstadoRegistro.Cerrado, r.Estado);
        Assert.Equal(360, Segundos(r)); // 6 minutos, sin perder los 5 que pasaron sin red
    }

    [Fact]
    public async Task Pause_sin_conexion_se_envia_despues_con_la_hora_en_que_se_presiono()
    {
        var (emp, obra, _) = _s.CrearDatos("CliOffline2");
        var c = await ConSesion(emp);
        await c.C.PlayAsync(obra);
        c.Red.Caida = true;
        await Pasar(c, TimeSpan.FromMinutes(3));
        await c.C.PauseAsync(); // sin red

        c.Red.Caida = false;
        await Pasar(c, TimeSpan.FromMinutes(1));

        Assert.Empty(c.Store.Pendientes);
        var r = Assert.Single(Registros(emp));
        Assert.Equal(EstadoRegistro.Cerrado, r.Estado);
        Assert.Equal(180, Segundos(r)); // 3 min, no los 4 que pasaron hasta reconectar
    }

    [Fact]
    public async Task Si_el_servidor_corto_el_registro_por_falta_de_latidos_y_el_panel_siguio_contando_se_recupera_todo()
    {
        var (emp, obra, _) = _s.CrearDatos("CliCorte");
        var c = await ConSesion(emp);
        await c.C.PlayAsync(obra);
        c.Red.Caida = true;
        await Pasar(c, TimeSpan.FromMinutes(10));
        await _s.CerrarAbandonadosAsync(); // el servidor lo corta en el último latido
        Assert.Equal(EstadoRegistro.Cortado, Assert.Single(Registros(emp)).Estado);

        c.Red.Caida = false;
        await Pasar(c, TimeSpan.FromMinutes(1)); // vuelve la red: el panel extiende el registro y sigue en uno nuevo
        Assert.Equal(EstadoPanel.Registrando, c.C.Estado);
        await c.C.PauseAsync();

        var regs = Registros(emp);
        Assert.Equal(2, regs.Count);
        Assert.Equal(EstadoRegistro.Cerrado, regs[0].Estado);
        Assert.True(regs[0].RevisarAdmin); // quedó marcado para que lo vea el administrador
        Assert.Equal(660, regs.Sum(Segundos)); // 11 minutos en total: no se perdió ninguno
    }

    [Fact]
    public async Task Los_pendientes_sobreviven_a_cerrar_y_abrir_el_programa()
    {
        var (emp, obra, _) = _s.CrearDatos("CliPersist");
        var c = await ConSesion(emp);
        c.Red.Caida = true;
        await c.C.PlayAsync(obra);

        var recargado = new LocalStore(c.Carpeta); // «reinicio»
        var p = Assert.Single(recargado.Pendientes);
        Assert.Equal(emp, p.EmpleadoId);
        Assert.Null(p.FinUtc);
    }

    // ---------------------------------------------------------------- listas de usuarios y obras

    [Fact]
    public async Task Los_usuarios_y_obras_nuevos_aparecen_al_refrescar_sin_reiniciar_el_panel()
    {
        _s.CrearDatos("CliListas");
        var c = NuevoCliente();
        Assert.True(await c.C.CargarListasAsync());
        Assert.DoesNotContain(c.C.Empleados, e => e.Nombre == "CliListasNuevo");

        _s.CrearDatos("CliListasNuevo"); // el administrador lo crea mientras el panel sigue abierto
        Assert.True(await c.C.CargarListasAsync(tocarConexion: false));
        Assert.Contains(c.C.Empleados, e => e.Nombre == "CliListasNuevo");
        Assert.Contains(c.C.Obras, o => o.Nombre == "Obra A CliListasNuevo");
    }

    [Fact]
    public async Task Refrescar_las_listas_sin_red_conserva_las_anteriores_y_no_toca_el_indicador_de_conexion()
    {
        var (emp, _, _) = _s.CrearDatos("CliListas2");
        var c = await ConSesion(emp);
        var antes = c.C.Empleados.Count;
        c.Red.Caida = true;

        Assert.False(await c.C.CargarListasAsync(tocarConexion: false));
        Assert.True(c.C.Conectado);
        Assert.Equal(antes, c.C.Empleados.Count);
    }

    // ---------------------------------------------------------------- inactividad (2 horas)

    [Fact]
    public async Task Inactividad_pregunta_al_volver_y_descontar_pausa_donde_empezo()
    {
        var (emp, obra, _) = _s.CrearDatos("CliInactivo1");
        var c = await ConSesion(emp);
        await c.C.PlayAsync(obra);
        await Pasar(c, TimeSpan.FromMinutes(140));

        c.C.ReportarInactividad(TimeSpan.FromMinutes(130)); // lleva 130 min sin tocar nada (desde el minuto 10)
        Assert.True(c.C.Inactivo);
        Assert.False(c.C.PreguntarInactividad);
        c.C.ReportarInactividad(TimeSpan.FromSeconds(2)); // volvió
        Assert.True(c.C.PreguntarInactividad);

        await c.C.ResolverInactividadAsync(descontar: true);
        Assert.Equal(EstadoPanel.Pausado, c.C.Estado);
        Assert.Equal(600, Segundos(Assert.Single(Registros(emp)))); // solo los 10 min trabajados
    }

    [Fact]
    public async Task Inactividad_contar_como_trabajo_sigue_registrando()
    {
        var (emp, obra, _) = _s.CrearDatos("CliInactivo2");
        var c = await ConSesion(emp);
        await c.C.PlayAsync(obra);
        await Pasar(c, TimeSpan.FromMinutes(130));
        c.C.ReportarInactividad(TimeSpan.FromMinutes(125));
        c.C.ReportarInactividad(TimeSpan.FromSeconds(1));

        await c.C.ResolverInactividadAsync(descontar: false);
        Assert.Equal(EstadoPanel.Registrando, c.C.Estado);
        Assert.False(c.C.PreguntarInactividad);
        Assert.False(c.C.Inactivo);
    }

    [Fact]
    public async Task Menos_de_dos_horas_sin_actividad_no_molesta()
    {
        var (emp, obra, _) = _s.CrearDatos("CliInactivo3");
        var c = await ConSesion(emp);
        await c.C.PlayAsync(obra);
        c.C.ReportarInactividad(TimeSpan.FromMinutes(119));
        Assert.False(c.C.Inactivo);
    }
}
