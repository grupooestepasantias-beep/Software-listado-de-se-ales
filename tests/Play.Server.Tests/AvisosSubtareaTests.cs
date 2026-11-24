using Play.Client;
using Xunit;

namespace Play.Server.Tests;

/// <summary>
/// «Terminé esta subtarea»: el empleado avisa, el administrador revisa. Una subtarea terminada se ve tachada (no es pendiente)
/// pero no desaparece; el aviso solo no cierra nada.
/// </summary>
public class AvisosSubtareaTests : IClassFixture<ServerFixture>
{
    private readonly ServerFixture _s;
    public AvisosSubtareaTests(ServerFixture s) => _s = s;

    private async Task<AdminApi> Admin(string usuario)
    {
        _s.CrearAdmin(usuario, "clave-segura-1");
        var api = new AdminApi(new ApiClient(_s.CreateClient(), _s.Time));
        api.Token = (await api.LoginAsync(usuario, "clave-segura-1")).Valor!.Token;
        return api;
    }

    private async Task<ApiClient> Empleado(int empleadoId)
    {
        var c = new ApiClient(_s.CreateClient(), _s.Time);
        c.Token = (await c.LoginAsync(empleadoId, "1234")).Valor!.Token;
        return c;
    }

    [Fact]
    public async Task El_aviso_del_empleado_le_llega_al_administrador_sin_cerrar_la_subtarea_y_no_se_duplica()
    {
        var adm = await Admin("adm-av1");
        var (emp, obra, _) = _s.CrearDatos("AvBasico");
        var sub = (await adm.CrearSubtareaAsync(obra, "Estructura")).Valor!;
        var e = await Empleado(emp);

        var r1 = await e.AvisarSubtareaAsync(sub.Id);
        Assert.Equal(201, (int)r1.Status!);
        var r2 = await e.AvisarSubtareaAsync(sub.Id); // el mismo empleado, otra vez: no se duplica
        Assert.Equal(200, (int)r2.Status!);

        var avisos = (await adm.AvisosAsync()).Valor!.Where(a => a.SubtareaId == sub.Id).ToList();
        var aviso = Assert.Single(avisos);
        Assert.Equal(("AvBasico", "Obra A AvBasico", "Estructura", "nuevo"), (aviso.Empleado, aviso.Obra, aviso.Subtarea, aviso.Estado));

        // El aviso por sí solo NO termina la subtarea: sigue pendiente y se sigue ofreciendo.
        Assert.False((await adm.SubtareasAsync(obra)).Valor!.Single().Terminada);
        var publicas = (await new ApiClient(_s.CreateClient(), _s.Time).ObrasAsync()).Valor!;
        Assert.Contains(publicas.First(o => o.Id == obra).Subtareas!, s => s.Id == sub.Id);
    }

    [Fact]
    public async Task Al_aceptar_el_aviso_la_subtarea_queda_terminada_tachada_al_final_y_ya_no_se_ofrece_pero_las_horas_se_conservan()
    {
        var adm = await Admin("adm-av2");
        var (emp, obra, _) = _s.CrearDatos("AvAceptar");
        var a = (await adm.CrearSubtareaAsync(obra, "Aaa primera")).Valor!;
        var b = (await adm.CrearSubtareaAsync(obra, "Bbb segunda")).Valor!;
        var e = await Empleado(emp);

        // Horas ya registradas con la subtarea que después se termina.
        var reg = await e.IniciarAsync(Guid.NewGuid(), obra, a.Id, "PC");
        Assert.True(reg.Ok);
        Assert.True((await e.CerrarAsync(reg.Valor!.Id, null)).Ok);

        await e.AvisarSubtareaAsync(a.Id);
        var aviso = (await adm.AvisosAsync()).Valor!.Single(x => x.SubtareaId == a.Id);
        var aceptado = (await adm.AceptarAvisoAsync(aviso.Id)).Valor!;
        Assert.Equal("aceptado", aceptado.Estado);
        Assert.True(aceptado.SubtareaTerminada);

        // Admin: sigue en la lista pero al final y marcada como terminada (la pantalla la tacha).
        var lista = (await adm.SubtareasAsync(obra)).Valor!;
        Assert.Equal(["Bbb segunda", "Aaa primera"], lista.Select(x => x.Nombre).ToArray());
        Assert.True(lista[1].Terminada);
        Assert.Empty((await adm.AvisosAsync()).Valor!.Where(x => x.SubtareaId == a.Id)); // ya no está entre los sin revisar

        // Empleados: ya no se ofrece, y no se puede iniciar sobre ella.
        var publicas = (await new ApiClient(_s.CreateClient(), _s.Time).ObrasAsync()).Valor!;
        Assert.Equal([b.Id], publicas.First(o => o.Id == obra).Subtareas!.Select(s => s.Id).ToArray());
        Assert.Equal("subtarea_invalida", (await e.IniciarAsync(Guid.NewGuid(), obra, a.Id, "PC")).Codigo);
        Assert.Equal("subtarea_terminada", (await e.AvisarSubtareaAsync(a.Id)).Codigo);

        // Las horas ya registradas se conservan con su subtarea.
        var registros = (await adm.RegistrosAsync(new FiltroAdmin(EmpleadoId: emp))).Valor!;
        Assert.Equal("Aaa primera", registros.Single().Subtarea);

        // Constancia en la auditoría y no se puede resolver dos veces.
        Assert.Contains((await adm.AuditoriaAsync()).Valor!, x => x.Campo == "subtarea_terminada" && x.ValorNuevo == "Obra A AvAceptar › Aaa primera");
        Assert.Equal("aviso_resuelto", (await adm.AceptarAvisoAsync(aviso.Id)).Codigo);
    }

    [Fact]
    public async Task Descartar_el_aviso_deja_la_subtarea_pendiente()
    {
        var adm = await Admin("adm-av3");
        var (emp, obra, _) = _s.CrearDatos("AvDescartar");
        var sub = (await adm.CrearSubtareaAsync(obra, "Pintura")).Valor!;
        var e = await Empleado(emp);
        await e.AvisarSubtareaAsync(sub.Id);
        var aviso = (await adm.AvisosAsync()).Valor!.Single(x => x.SubtareaId == sub.Id);

        var d = (await adm.DescartarAvisoAsync(aviso.Id)).Valor!;
        Assert.Equal("descartado", d.Estado);
        Assert.False((await adm.SubtareasAsync(obra)).Valor!.Single().Terminada);
        Assert.Equal("aviso_resuelto", (await adm.DescartarAvisoAsync(aviso.Id)).Codigo);
        Assert.Equal(404, (int)(await adm.DescartarAvisoAsync(99999)).Status!);
        // Con «todos» se sigue viendo, ya revisado.
        Assert.Contains((await adm.AvisosAsync("todos")).Valor!, x => x.Id == aviso.Id && x.Estado == "descartado");
        // Y el empleado puede volver a avisar más adelante.
        Assert.Equal(201, (int)(await e.AvisarSubtareaAsync(sub.Id)).Status!);
    }

    [Fact]
    public async Task Terminar_la_subtarea_desde_Obras_resuelve_los_avisos_pendientes_y_se_puede_reabrir()
    {
        var adm = await Admin("adm-av4");
        var (emp, obra, _) = _s.CrearDatos("AvDirecto");
        var sub = (await adm.CrearSubtareaAsync(obra, "Cableado")).Valor!;
        await (await Empleado(emp)).AvisarSubtareaAsync(sub.Id);

        var t = (await adm.ActualizarSubtareaAsync(sub.Id, terminada: true)).Valor!;
        Assert.True(t.Terminada);
        Assert.Empty((await adm.AvisosAsync()).Valor!.Where(x => x.SubtareaId == sub.Id));
        Assert.Contains((await adm.AvisosAsync("todos")).Valor!, x => x.SubtareaId == sub.Id && x.Estado == "aceptado");

        var r = (await adm.ActualizarSubtareaAsync(sub.Id, terminada: false)).Valor!;
        Assert.False(r.Terminada);
        var publicas = (await new ApiClient(_s.CreateClient(), _s.Time).ObrasAsync()).Valor!;
        Assert.Contains(publicas.First(o => o.Id == obra).Subtareas!, s => s.Id == sub.Id); // vuelve a ofrecerse
        Assert.Contains((await adm.AuditoriaAsync()).Valor!, x => x.Campo == "subtarea_reabierta");
    }

    [Fact]
    public async Task Si_se_terminan_todas_las_subtareas_la_obra_deja_de_exigir_subtarea()
    {
        var adm = await Admin("adm-av5");
        var (emp, obra, _) = _s.CrearDatos("AvTodas");
        var sub = (await adm.CrearSubtareaAsync(obra, "Única")).Valor!;
        var e = await Empleado(emp);
        Assert.Equal("subtarea_requerida", (await e.IniciarAsync(Guid.NewGuid(), obra, null, "PC")).Codigo);
        Assert.Equal(1, (await adm.ObrasAsync()).Valor!.First(o => o.Id == obra).SubtareasActivas);

        await adm.ActualizarSubtareaAsync(sub.Id, terminada: true);
        Assert.Equal(0, (await adm.ObrasAsync()).Valor!.First(o => o.Id == obra).SubtareasActivas);
        Assert.True((await e.IniciarAsync(Guid.NewGuid(), obra, null, "PC")).Ok);
    }

    [Fact]
    public async Task Solo_el_administrador_resuelve_avisos_y_hay_que_estar_identificado_para_avisar()
    {
        var adm = await Admin("adm-av6");
        var (emp, obra, _) = _s.CrearDatos("AvPermisos");
        var sub = (await adm.CrearSubtareaAsync(obra, "Soldadura")).Valor!;

        Assert.Equal(401, (int)(await new ApiClient(_s.CreateClient(), _s.Time).AvisarSubtareaAsync(sub.Id)).Status!); // sin sesión

        // Un empleado con su token no puede usar las rutas del administrador.
        var comoEmpleado = new AdminApi(await Empleado(emp));
        Assert.Equal(401, (int)(await comoEmpleado.AvisosAsync()).Status!);
        Assert.Equal(401, (int)(await comoEmpleado.AceptarAvisoAsync(1)).Status!);
        Assert.Equal(401, (int)(await comoEmpleado.ActualizarSubtareaAsync(sub.Id, terminada: true)).Status!);
        Assert.False((await adm.SubtareasAsync(obra)).Valor!.Single().Terminada);

        Assert.Equal(404, (int)(await (await Empleado(emp)).AvisarSubtareaAsync(99999)).Status!);
    }

    [Fact]
    public async Task La_casilla_del_panel_tilda_para_avisar_destilda_para_retirar_y_se_destilda_sola_cuando_el_administrador_resuelve()
    {
        var adm = await Admin("adm-av8");
        var (emp, obra, _) = _s.CrearDatos("AvCasilla");
        var a = (await adm.CrearSubtareaAsync(obra, "Armado")).Valor!;
        var b = (await adm.CrearSubtareaAsync(obra, "Pintura")).Valor!;
        var c = new PanelController(new ApiClient(_s.CreateClient(), _s.Time), new LocalStore(Path.Combine(Path.GetTempPath(), "play-cli-" + Guid.NewGuid().ToString("N"))), _s.Time, "PC-CHK");
        Assert.True(await c.CargarListasAsync());
        Assert.Null(await c.LoginAsync(emp, "1234"));
        Assert.False(c.SubtareaAvisada(a.Id));

        // Tildar = avisar.
        Assert.True((await c.MarcarTerminadaAsync(a.Id, true)).Ok);
        Assert.True(c.SubtareaAvisada(a.Id));
        Assert.Single((await adm.AvisosAsync()).Valor!.Where(x => x.SubtareaId == a.Id));

        // Destildar = retirar el aviso (el administrador ya no lo ve sin revisar; con «todos» queda como retirado).
        Assert.True((await c.MarcarTerminadaAsync(a.Id, false)).Ok);
        Assert.False(c.SubtareaAvisada(a.Id));
        Assert.Empty((await adm.AvisosAsync()).Valor!.Where(x => x.SubtareaId == a.Id));
        Assert.Contains((await adm.AvisosAsync("todos")).Valor!, x => x.SubtareaId == a.Id && x.Estado == "retirado");

        // Se puede volver a tildar. Si el administrador la termina, la casilla deja de figurar sola al refrescar.
        Assert.True((await c.MarcarTerminadaAsync(b.Id, true)).Ok);
        await adm.ActualizarSubtareaAsync(b.Id, terminada: true);
        await c.RefrescarAvisosAsync();
        Assert.False(c.SubtareaAvisada(b.Id));
        await c.CargarListasAsync(); // la lista pública se actualiza con el refresco periódico del panel
        Assert.DoesNotContain(c.SubtareasDe(obra), s => s.Id == b.Id); // ya no se ofrece
    }

    [Fact]
    public async Task El_panel_avisa_con_un_mensaje_claro_y_sin_conexion_no_pierde_nada()
    {
        var adm = await Admin("adm-av7");
        var (emp, obra, _) = _s.CrearDatos("AvPanel");
        var sub = (await adm.CrearSubtareaAsync(obra, "Montaje")).Valor!;
        var red = new RedIntermitente(new ApiClient(_s.CreateClient(), _s.Time));
        var c = new PanelController(red, new LocalStore(Path.Combine(Path.GetTempPath(), "play-cli-" + Guid.NewGuid().ToString("N"))), _s.Time, "PC-AV");
        Assert.True(await c.CargarListasAsync());
        Assert.Null(await c.LoginAsync(emp, "1234"));
        Assert.Contains(c.ObrasConSubtareas(), o => o.Id == obra);

        red.Caida = true;
        var sinRed = await c.AvisarSubtareaAsync(sub.Id);
        Assert.False(sinRed.Ok);
        Assert.Contains("conexión", sinRed.Mensaje);
        Assert.Empty((await adm.AvisosAsync()).Valor!.Where(x => x.SubtareaId == sub.Id));

        red.Caida = false;
        var ok = await c.AvisarSubtareaAsync(sub.Id);
        Assert.True(ok.Ok);
        Assert.Single((await adm.AvisosAsync()).Valor!.Where(x => x.SubtareaId == sub.Id));
    }
}
