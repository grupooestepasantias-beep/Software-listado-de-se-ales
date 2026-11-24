using ClosedXML.Excel;
using Play.Client;
using Play.Server.Data;
using Play.Server.Services;
using Microsoft.EntityFrameworkCore;
using Xunit;
using FiltroAdmin = Play.Client.FiltroAdmin;
using CargaDto = Play.Client.CargaDto;
using MisHorasDto = Play.Client.MisHorasDto;
using CargaAdminDto = Play.Client.CargaAdminDto;

namespace Play.Server.Tests;

/// <summary>
/// Horas de Taller: los empleados de Taller cargan a mano las horas de hoy o de ayer (registros individuales, uno por día);
/// el administrador las consulta, las corrige (con motivo y auditoría), las elimina y las recupera.
/// </summary>
public class HorasTallerTests : IClassFixture<ServerFixture>
{
    private readonly ServerFixture _s;
    public HorasTallerTests(ServerFixture s) => _s = s;

    private async Task<AdminApi> Admin(string usuario)
    {
        _s.CrearAdmin(usuario, "clave-segura-1");
        var api = new AdminApi(new ApiClient(_s.CreateClient(), _s.Time));
        api.Token = (await api.LoginAsync(usuario, "clave-segura-1")).Valor!.Token;
        return api;
    }

    /// <summary>Un empleado de Taller (o de Oficina) ya logueado, con su cliente de API.</summary>
    private async Task<(int Id, ApiClient Api)> Empleado(AdminApi adm, string nombre, bool taller = true)
    {
        var (id, _, _) = _s.CrearDatos(nombre);
        if (taller) await adm.ActualizarEmpleadoAsync(id, area: "Taller");
        var c = new ApiClient(_s.CreateClient(), _s.Time);
        c.Token = (await c.LoginAsync(id, "1234")).Valor!.Token;
        return (id, c);
    }

    private static DateOnly Hoy(MisHorasDto h) => h.Hoy;

    // ---------------------------------------------------------------- empleado

    [Fact]
    public async Task Un_empleado_de_Taller_carga_las_horas_de_hoy_y_de_ayer_como_registros_individuales()
    {
        var adm = await Admin("adm-ht1");
        var (id, e) = await Empleado(adm, "HtBasico");
        var hoy = Hoy((await e.MisHorasAsync()).Valor!);

        Assert.True((await e.CargarHorasAsync(hoy, 8 * 60)).Ok);
        Assert.True((await e.CargarHorasAsync(hoy.AddDays(-1), 7 * 60 + 30)).Ok);

        var mias = (await e.MisHorasAsync()).Valor!;
        Assert.Equal(hoy, mias.Hoy);
        Assert.Equal([(hoy, 480), (hoy.AddDays(-1), 450)], mias.Cargas.Select(c => (c.Fecha, c.Minutos)).ToArray());

        // El administrador ve dos registros separados (quién, qué día, cuántas horas), no un acumulado.
        var lista = (await adm.HorasAsync(id)).Valor!;
        Assert.Equal(2, lista.Count);
        Assert.All(lista, c => Assert.Equal("HtBasico", c.Empleado));
        Assert.Equal("panel", lista[0].Origen);
    }

    [Fact]
    public async Task Volver_a_cargar_el_mismo_dia_reemplaza_la_carga_y_no_la_duplica()
    {
        var adm = await Admin("adm-ht2");
        var (id, e) = await Empleado(adm, "HtReemplazo");
        var hoy = Hoy((await e.MisHorasAsync()).Valor!);

        await e.CargarHorasAsync(hoy, 4 * 60);
        await e.CargarHorasAsync(hoy, 9 * 60 + 15);

        var lista = (await adm.HorasAsync(id)).Valor!;
        Assert.Equal(555, Assert.Single(lista).Minutos);
    }

    [Fact]
    public async Task Solo_se_puede_cargar_hoy_o_ayer_con_horas_validas()
    {
        var adm = await Admin("adm-ht3");
        var (id, e) = await Empleado(adm, "HtLimites");
        var hoy = Hoy((await e.MisHorasAsync()).Valor!);

        Assert.Equal("fecha_no_permitida", (await e.CargarHorasAsync(hoy.AddDays(-2), 480)).Codigo);
        Assert.Equal("fecha_no_permitida", (await e.CargarHorasAsync(hoy.AddDays(1), 480)).Codigo);
        Assert.Equal("horas_invalidas", (await e.CargarHorasAsync(hoy, 0)).Codigo);
        Assert.Equal("horas_invalidas", (await e.CargarHorasAsync(hoy, -30)).Codigo);
        Assert.Equal("horas_invalidas", (await e.CargarHorasAsync(hoy, 24 * 60 + 1)).Codigo);
        Assert.True((await e.CargarHorasAsync(hoy, 24 * 60)).Ok);
        Assert.Single((await adm.HorasAsync(id)).Valor!); // lo inválido no dejó nada
    }

    [Fact]
    public async Task La_carga_de_horas_es_solo_para_Taller_y_hay_que_estar_identificado()
    {
        var adm = await Admin("adm-ht4");
        var (_, oficina) = await Empleado(adm, "HtOficina", taller: false);
        var hoy = DateOnly.FromDateTime(_s.Time.GetLocalNow().DateTime);

        Assert.Equal(403, (int)(await oficina.MisHorasAsync()).Status!);
        var r = await oficina.CargarHorasAsync(hoy, 480);
        Assert.Equal(403, (int)r.Status!);
        Assert.Equal("solo_taller", r.Codigo);

        Assert.Equal(401, (int)(await new ApiClient(_s.CreateClient(), _s.Time).CargarHorasAsync(hoy, 480)).Status!);
        // Y un empleado con su token no entra a las rutas del administrador.
        Assert.Equal(401, (int)(await new AdminApi(oficina).HorasAsync()).Status!);
    }

    // ---------------------------------------------------------------- administración

    [Fact]
    public async Task El_administrador_consulta_por_empleado_y_fechas_y_ve_los_totales_en_el_Excel()
    {
        var adm = await Admin("adm-ht5");
        var (idA, a) = await Empleado(adm, "HtListaA");
        var (idB, b) = await Empleado(adm, "HtListaB");
        var hoy = Hoy((await a.MisHorasAsync()).Valor!);
        await a.CargarHorasAsync(hoy, 8 * 60);
        await a.CargarHorasAsync(hoy.AddDays(-1), 6 * 60);
        await b.CargarHorasAsync(hoy, 7 * 60 + 30);

        Assert.Equal(2, (await adm.HorasAsync(idA)).Valor!.Count);
        Assert.Single((await adm.HorasAsync(idB)).Valor!);
        Assert.Single((await adm.HorasAsync(idA, desde: hoy, hasta: hoy)).Valor!);
        Assert.Empty((await adm.HorasAsync(idA, desde: hoy.AddDays(1))).Valor!);

        var bytes = (await adm.HorasExcelAsync(desde: hoy.AddDays(-1), hasta: hoy)).Valor!;
        using var wb = new XLWorkbook(new MemoryStream(bytes));
        var porEmpleado = wb.Worksheet("Por empleado").RowsUsed().Skip(1).ToList();
        var filaA = porEmpleado.First(f => f.Cell(1).GetString() == "HtListaA");
        Assert.Equal(2, filaA.Cell(2).GetDouble());
        Assert.Equal(14.0, filaA.Cell(3).GetDouble(), 2);
        Assert.Contains(wb.Worksheet("Detalle").RowsUsed().Skip(1), f => f.Cell(2).GetString() == "HtListaB");
    }

    [Fact]
    public async Task Corregir_exige_motivo_deja_constancia_y_el_empleado_ya_no_puede_cambiarla()
    {
        var adm = await Admin("adm-ht6");
        var (id, e) = await Empleado(adm, "HtCorreccion");
        var hoy = Hoy((await e.MisHorasAsync()).Valor!);
        await e.CargarHorasAsync(hoy, 8 * 60);
        var carga = (await adm.HorasAsync(id)).Valor!.Single();

        Assert.Equal("motivo_requerido", (await adm.CorregirHorasAsync(carga.Id, 9 * 60, "  ")).Codigo);
        Assert.Equal("sin_cambios", (await adm.CorregirHorasAsync(carga.Id, 8 * 60, "igual")).Codigo);
        Assert.Equal("horas_invalidas", (await adm.CorregirHorasAsync(carga.Id, 0, "mal")).Codigo);
        var c = (await adm.CorregirHorasAsync(carga.Id, 9 * 60, "Trabajó una hora más")).Valor!;
        Assert.Equal((540, "admin"), (c.Minutos, c.Origen));

        var aud = (await adm.AuditoriaAsync()).Valor!.First(x => x.Campo == "horas_taller" && x.Motivo == "Trabajó una hora más");
        Assert.Contains("8:00", aud.ValorAnterior);
        Assert.Contains("9:00", aud.ValorNuevo);

        Assert.Equal("cargada_por_admin", (await e.CargarHorasAsync(hoy, 7 * 60)).Codigo); // ya la tocó un administrador
        Assert.Equal(540, (await adm.HorasAsync(id)).Valor!.Single().Minutos);
    }

    [Fact]
    public async Task El_administrador_agrega_horas_de_cualquier_dia_pasado_solo_de_Taller_y_sin_duplicar()
    {
        var adm = await Admin("adm-ht7");
        var (id, e) = await Empleado(adm, "HtAlta");
        var (idOf, _) = await Empleado(adm, "HtAltaOficina", taller: false);
        var hoy = Hoy((await e.MisHorasAsync()).Valor!);
        var viejo = hoy.AddDays(-20);

        Assert.Equal("motivo_requerido", (await adm.CrearHorasAsync(id, viejo, 480, "")).Codigo);
        Assert.Equal("fecha_futura", (await adm.CrearHorasAsync(id, hoy.AddDays(1), 480, "x")).Codigo);
        Assert.Equal("solo_taller", (await adm.CrearHorasAsync(idOf, viejo, 480, "x")).Codigo);
        Assert.Equal("horas_invalidas", (await adm.CrearHorasAsync(id, viejo, 0, "x")).Codigo);

        var c = (await adm.CrearHorasAsync(id, viejo, 480, "No pudo cargarlas")).Valor!;
        Assert.Equal(("admin", viejo), (c.Origen, c.Fecha));
        Assert.Equal("ya_cargado", (await adm.CrearHorasAsync(id, viejo, 300, "otra vez")).Codigo);
        Assert.Contains((await adm.AuditoriaAsync()).Valor!, x => x.Campo == "horas_taller_creadas" && x.Motivo == "No pudo cargarlas");
    }

    [Fact]
    public async Task Eliminar_no_borra_se_puede_recuperar_y_el_empleado_puede_volver_a_cargar_ese_dia()
    {
        var adm = await Admin("adm-ht8");
        var (id, e) = await Empleado(adm, "HtEliminar");
        var hoy = Hoy((await e.MisHorasAsync()).Valor!);
        await e.CargarHorasAsync(hoy, 5 * 60);
        var carga = (await adm.HorasAsync(id)).Valor!.Single();

        Assert.Equal("motivo_requerido", (await adm.EliminarHorasAsync(carga.Id, "")).Codigo);
        Assert.True((await adm.EliminarHorasAsync(carga.Id, "Se cargó por error")).Ok);
        Assert.Empty((await adm.HorasAsync(id)).Valor!);                       // ya no cuenta
        Assert.Single((await adm.HorasAsync(id, eliminados: true)).Valor!);     // pero no se borró
        Assert.Empty((await e.MisHorasAsync()).Valor!.Cargas);                  // ni el empleado la ve

        // El empleado vuelve a cargar ese día; recuperar la anterior ya no corresponde (no puede haber dos).
        Assert.True((await e.CargarHorasAsync(hoy, 6 * 60)).Ok);
        Assert.Equal("ya_cargado", (await adm.RecuperarHorasAsync(carga.Id, "Estaba bien")).Codigo);

        // Si se elimina la nueva, la vieja se puede recuperar.
        var nueva = (await adm.HorasAsync(id)).Valor!.Single();
        await adm.EliminarHorasAsync(nueva.Id, "Era la otra");
        Assert.True((await adm.RecuperarHorasAsync(carga.Id, "Estaba bien")).Ok);
        Assert.Equal(300, (await adm.HorasAsync(id)).Valor!.Single().Minutos);
        Assert.Contains((await adm.AuditoriaAsync()).Valor!, x => x.Campo == "horas_taller_eliminadas" && x.Motivo == "Se cargó por error");
    }

    [Fact]
    public async Task Las_horas_de_Taller_tambien_figuran_entre_los_registros_y_en_el_Excel_general()
    {
        var adm = await Admin("adm-ht10");
        var (idT, t) = await Empleado(adm, "HtRegTaller");
        var (idO, _) = await Empleado(adm, "HtRegOficina", taller: false);
        var obra = _s.CrearDatos("HtRegObra").ObraId;
        var hoy = Hoy((await t.MisHorasAsync()).Valor!);
        await t.CargarHorasAsync(hoy, 8 * 60);
        await t.CargarHorasAsync(hoy.AddDays(-1), 6 * 60 + 30);
        // Un registro común de Oficina el mismo día, para comprobar que conviven.
        var ahora = _s.Time.GetUtcNow().UtcDateTime;
        await adm.CrearRegistroAsync(idO, obra, ahora.AddHours(-3), ahora.AddHours(-1), "Prueba");

        var f = new FiltroAdmin(Desde: hoy.AddDays(-1), Hasta: hoy);
        var todos = (await adm.RegistrosAsync(f with { EmpleadoId = idT })).Valor!;
        Assert.Equal(2, todos.Count);
        Assert.All(todos, r => Assert.Equal(("carga", "Taller", "HtRegTaller", "(Carga de horas)"), (r.Origen, r.Area, r.Empleado, r.Obra)));
        Assert.Equal([8 * 3600L, 6 * 3600L + 1800], todos.Select(r => r.Segundos).ToArray()); // la de hoy primero
        Assert.Equal(todos.Select(r => r.Id).Distinct().Count(), todos.Count);                // ids distintos

        // Con el resto de los registros, y filtrando por área.
        Assert.Contains((await adm.RegistrosAsync(f)).Valor!, r => r.Origen == "carga" && r.Empleado == "HtRegTaller");
        Assert.DoesNotContain((await adm.RegistrosAsync(f with { Area = "Oficina" })).Valor!, r => r.Origen == "carga");
        Assert.All((await adm.RegistrosAsync(f with { Area = "Taller" })).Valor!, r => Assert.Equal("Taller", r.Area));
        // Sin obra ni «a revisar»: con esos filtros no aparecen.
        Assert.DoesNotContain((await adm.RegistrosAsync(f with { ObraId = obra })).Valor!, r => r.Origen == "carga");
        Assert.DoesNotContain((await adm.RegistrosAsync(f with { Revisar = true })).Valor!, r => r.Origen == "carga");

        // Las eliminadas figuran en «eliminados» y no en la lista normal.
        var primera = (await adm.HorasAsync(idT, hoy, hoy)).Valor!.Single();
        await adm.EliminarHorasAsync(primera.Id, "Error");
        Assert.Single((await adm.RegistrosAsync(f with { EmpleadoId = idT })).Valor!);
        Assert.Single((await adm.RegistrosAsync(f with { EmpleadoId = idT, Eliminados = true })).Valor!, r => r.Origen == "carga");
        await adm.RecuperarHorasAsync(primera.Id, "Estaba bien");

        // Excel general: la carga cuenta como horas del empleado, sin hora de inicio ni de fin.
        using var wb = new XLWorkbook(new MemoryStream((await adm.ReporteExcelAsync(f with { EmpleadoId = idT })).Valor!));
        var det = wb.Worksheet("Detalle").RowsUsed().Skip(1).ToList();
        Assert.Equal(2, det.Count);
        Assert.All(det, fila => Assert.Equal("carga de horas", fila.Cell(11).GetString()));
        Assert.All(det, fila => Assert.True(fila.Cell(6).IsEmpty() && fila.Cell(7).IsEmpty()));
        var porEmp = wb.Worksheet("Por empleado").RowsUsed().Skip(1).First(r => r.Cell(1).GetString() == "HtRegTaller");
        Assert.Equal(14.5, porEmp.Cell(2).GetDouble(), 2);
    }

    // ---------------------------------------------------------------- obras y subtareas

    private async Task<(int Id, ApiClient Api, int Obra, int Obra2, int Estructura, int Pintura)> TallerConObras(AdminApi adm, string nombre)
    {
        var (id, api) = await Empleado(adm, nombre);
        var (_, obra, obra2) = _s.CrearDatos("Obras " + nombre);
        var estructura = (await adm.CrearSubtareaAsync(obra, "Estructura")).Valor!.Id;
        var pintura = (await adm.CrearSubtareaAsync(obra, "Pintura")).Valor!.Id;
        return (id, api, obra, obra2, estructura, pintura);
    }

    [Fact]
    public async Task Un_empleado_de_Taller_reparte_las_horas_del_dia_entre_obras_y_subtareas_y_el_administrador_las_ve_una_por_una()
    {
        var adm = await Admin("adm-ht11");
        var (id, e, obra, obra2, estructura, pintura) = await TallerConObras(adm, "HtObras");
        var hoy = Hoy((await e.MisHorasAsync()).Valor!);

        Assert.True((await e.CargarHorasAsync(hoy, 5 * 60, obra, estructura)).Ok);
        Assert.True((await e.CargarHorasAsync(hoy, 2 * 60, obra, pintura)).Ok);   // otra subtarea de la misma obra = otra línea
        Assert.True((await e.CargarHorasAsync(hoy, 60, obra2)).Ok);               // obra sin subtareas
        Assert.True((await e.CargarHorasAsync(hoy, 30)).Ok);                      // trabajo general, sin obra
        Assert.True((await e.CargarHorasAsync(hoy, 4 * 60, obra, estructura)).Ok); // la misma línea: se reemplaza, no se suma

        var mias = (await e.MisHorasAsync()).Valor!.Cargas;
        Assert.Equal(4, mias.Count);
        Assert.Equal(4 * 60 + 2 * 60 + 60 + 30, mias.Sum(c => c.Minutos));
        Assert.Equal(240, mias.Single(c => c.SubtareaId == estructura).Minutos);

        var lista = (await adm.HorasAsync(id)).Valor!;
        Assert.Equal(4, lista.Count);
        var est = lista.Single(c => c.Subtarea == "Estructura");
        Assert.Equal(("Obra A Obras HtObras", 240), (est.Obra, est.Minutos));
        Assert.Contains(lista, c => c.Obra is null && c.Minutos == 30);

        // Filtro de obra del administrador.
        Assert.Equal(2, (await adm.HorasAsync(id, obraId: obra)).Valor!.Count);
    }

    [Fact]
    public async Task La_obra_y_la_subtarea_de_las_horas_siguen_las_mismas_reglas_que_Play()
    {
        var adm = await Admin("adm-ht12");
        var (id, e, obra, obra2, estructura, pintura) = await TallerConObras(adm, "HtReglasObra");
        var hoy = Hoy((await e.MisHorasAsync()).Valor!);

        Assert.Equal("subtarea_requerida", (await e.CargarHorasAsync(hoy, 60, obra)).Codigo);            // la obra tiene subtareas
        Assert.Equal("subtarea_invalida", (await e.CargarHorasAsync(hoy, 60, obra2, estructura)).Codigo); // subtarea de otra obra
        Assert.Equal("subtarea_invalida", (await e.CargarHorasAsync(hoy, 60, null, estructura)).Codigo);  // subtarea sin obra
        Assert.Equal("obra_invalida", (await e.CargarHorasAsync(hoy, 60, 99999)).Codigo);
        await adm.ActualizarObraAsync(obra2, activo: false);
        Assert.Equal("obra_invalida", (await e.CargarHorasAsync(hoy, 60, obra2)).Codigo);                // obra desactivada
        await adm.ActualizarSubtareaAsync(pintura, terminada: true);
        Assert.Equal("subtarea_invalida", (await e.CargarHorasAsync(hoy, 60, obra, pintura)).Codigo);    // subtarea terminada: ya no se ofrece
        Assert.Empty((await adm.HorasAsync(id)).Valor!);                                                  // nada de eso dejó registros

        // Si se terminan todas las subtareas, la obra vuelve a cargarse sin subtarea.
        await adm.ActualizarSubtareaAsync(estructura, terminada: true);
        Assert.True((await e.CargarHorasAsync(hoy, 60, obra)).Ok);

        // El total del día no puede pasar de 24 horas.
        Assert.True((await e.CargarHorasAsync(hoy, 22 * 60)).Ok);
        Assert.Equal("horas_invalidas", (await e.CargarHorasAsync(hoy.AddDays(-1), 24 * 60 + 1)).Codigo);
        Assert.Equal("horas_invalidas", (await e.CargarHorasAsync(hoy, 3 * 60, obra)).Codigo);            // 22 h + 3 h > 24 h
    }

    [Fact]
    public async Task El_empleado_puede_quitar_una_linea_pero_no_una_que_toco_el_administrador()
    {
        var adm = await Admin("adm-ht13");
        var (id, e, obra, _, estructura, _) = await TallerConObras(adm, "HtQuitar");
        var hoy = Hoy((await e.MisHorasAsync()).Valor!);
        await e.CargarHorasAsync(hoy, 3 * 60, obra, estructura);
        await e.CargarHorasAsync(hoy, 60);

        Assert.True((await e.RetirarHorasAsync(hoy, obra, estructura)).Ok);
        Assert.Equal([(null, 60)], (await e.MisHorasAsync()).Valor!.Cargas.Select(c => (c.ObraId, c.Minutos)).ToArray());
        Assert.Equal(404, (int)(await e.RetirarHorasAsync(hoy, obra, estructura)).Status!); // ya no existe
        Assert.Equal(1, (await adm.HorasAsync(id, eliminados: true)).Valor!.Count);          // no se borró: queda como eliminada
        Assert.Equal("fecha_no_permitida", (await e.RetirarHorasAsync(hoy.AddDays(-3))).Codigo);

        // Una línea que corrigió el administrador ya no se puede quitar.
        var linea = (await adm.HorasAsync(id)).Valor!.Single();
        await adm.CorregirHorasAsync(linea.Id, 2 * 60, "Corrección");
        Assert.Equal("cargada_por_admin", (await e.RetirarHorasAsync(hoy)).Codigo);

        // Volver a cargar la línea quitada es posible.
        Assert.True((await e.CargarHorasAsync(hoy, 90, obra, estructura)).Ok);
    }

    [Fact]
    public async Task El_administrador_agrega_horas_con_obra_y_subtarea_sin_duplicar_la_misma_linea()
    {
        var adm = await Admin("adm-ht14");
        var (id, _, obra, obra2, estructura, pintura) = await TallerConObras(adm, "HtAltaObra");
        var dia = new DateOnly(2026, 11, 2);
        await adm.ActualizarSubtareaAsync(pintura, terminada: true); // el administrador puede cargar sobre una subtarea ya terminada

        Assert.Equal("subtarea_requerida", (await adm.CrearHorasAsync(id, dia, 60, "Alta", obra)).Codigo);
        Assert.Equal("subtarea_invalida", (await adm.CrearHorasAsync(id, dia, 60, "Alta", obra2, estructura)).Codigo);
        var a = (await adm.CrearHorasAsync(id, dia, 5 * 60, "Alta", obra, estructura)).Valor!;
        Assert.Equal(("Obra A Obras HtAltaObra", "Estructura", "admin"), (a.Obra, a.Subtarea, a.Origen));
        Assert.True((await adm.CrearHorasAsync(id, dia, 60, "Alta", obra, pintura)).Ok);
        Assert.True((await adm.CrearHorasAsync(id, dia, 60, "Alta", obra2)).Ok);
        Assert.Equal("ya_cargado", (await adm.CrearHorasAsync(id, dia, 30, "Otra vez", obra, estructura)).Codigo);
        Assert.Equal(3, (await adm.HorasAsync(id, dia, dia)).Valor!.Count);
        Assert.Contains((await adm.AuditoriaAsync()).Valor!, x => x.Campo == "horas_taller_creadas" && x.ValorNuevo!.Contains("Obra A Obras HtAltaObra › Estructura"));
    }

    [Fact]
    public async Task Las_horas_por_obra_figuran_en_Registros_y_en_los_reportes_por_obra_y_subtarea_y_cuentan_para_la_asistencia()
    {
        var adm = await Admin("adm-ht15");
        var (id, e, obra, _, estructura, _) = await TallerConObras(adm, "HtReportes");
        var hoy = Hoy((await e.MisHorasAsync()).Valor!);
        await e.CargarHorasAsync(hoy, 6 * 60, obra, estructura);
        await e.CargarHorasAsync(hoy, 90);

        var f = new FiltroAdmin(Desde: hoy, Hasta: hoy, EmpleadoId: id);
        var regs = (await adm.RegistrosAsync(f)).Valor!;
        var conObra = regs.Single(r => r.ObraId == obra);
        Assert.Equal(("Obra A Obras HtReportes", "Estructura", "carga", 6 * 3600L), (conObra.Obra, conObra.Subtarea, conObra.Origen, conObra.Segundos));
        Assert.Equal("(Carga de horas)", regs.Single(r => r.ObraId == 0).Obra);
        Assert.Single((await adm.RegistrosAsync(f with { ObraId = obra })).Valor!); // el filtro de obra encuentra la carga de esa obra

        using var wb = new XLWorkbook(new MemoryStream((await adm.ReporteExcelAsync(f)).Valor!));
        var porObra = wb.Worksheet("Por obra").RowsUsed().Skip(1).First(r => r.Cell(1).GetString() == "Obra A Obras HtReportes");
        Assert.Equal(6.0, porObra.Cell(2).GetDouble(), 2);
        var porSub = wb.Worksheet("Por subtarea").RowsUsed().Skip(1).First(r => r.Cell(2).GetString() == "Estructura");
        Assert.Equal(6.0, porSub.Cell(3).GetDouble(), 2);
        var excelHoras = new XLWorkbook(new MemoryStream((await adm.HorasExcelAsync(id, hoy, hoy)).Valor!)).Worksheet("Detalle").RowsUsed().Skip(1).ToList();
        Assert.Contains(excelHoras, r => r.Cell(3).GetString() == "Obra A Obras HtReportes" && r.Cell(4).GetString() == "Estructura");
        Assert.Contains(excelHoras, r => r.Cell(3).GetString() == "(sin obra)");
    }

    [Fact]
    public async Task Una_base_con_horas_de_Taller_de_la_version_anterior_se_actualiza_y_ya_admite_varias_lineas_por_dia()
    {
        var dir = Path.Combine(Path.GetTempPath(), "play-esquema-ht-" + Guid.NewGuid().ToString("N"));
        Directory.CreateDirectory(dir);
        var cs = $"Data Source={Path.Combine(dir, "antigua.db")};Pooling=False";

        // La base de «antes»: CargasHoras con su índice único (una sola carga por empleado y día) y sin obra ni subtarea.
        await using (var cn = new Microsoft.Data.Sqlite.SqliteConnection(cs))
        {
            await cn.OpenAsync();
            foreach (var sql in new[]
            {
                "CREATE TABLE Empleados (Id INTEGER PRIMARY KEY AUTOINCREMENT, Nombre TEXT NOT NULL, Area TEXT NOT NULL DEFAULT 'Oficina', PinVisible TEXT NULL)",
                "CREATE TABLE Obras (Id INTEGER PRIMARY KEY AUTOINCREMENT, Nombre TEXT NOT NULL, Activa INTEGER NOT NULL)",
                "CREATE TABLE Registros (Id TEXT PRIMARY KEY, EmpleadoId INTEGER NOT NULL, ObraId INTEGER NOT NULL, Anulado INTEGER NOT NULL DEFAULT 0)",
                "CREATE TABLE CargasHoras (Id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT, EmpleadoId INTEGER NOT NULL, Fecha TEXT NOT NULL, Minutos INTEGER NOT NULL, CreadaUtc TEXT NOT NULL, ActualizadaUtc TEXT NOT NULL, Origen TEXT NOT NULL, Anulado INTEGER NOT NULL)",
                "CREATE UNIQUE INDEX UX_CargasHoras_EmpleadoId_Fecha ON CargasHoras (EmpleadoId, Fecha) WHERE \"Anulado\" = 0",
                "INSERT INTO Empleados (Nombre, Area) VALUES ('Taller Viejo', 'Taller')",
                "INSERT INTO Obras (Nombre, Activa) VALUES ('Obra', 1)",
                "INSERT INTO CargasHoras (EmpleadoId, Fecha, Minutos, CreadaUtc, ActualizadaUtc, Origen, Anulado) VALUES (1, '2026-11-18', 480, '2026-11-18 15:00:00', '2026-11-18 15:00:00', 'panel', 0)",
            })
            {
                await using var cmd = cn.CreateCommand();
                cmd.CommandText = sql;
                await cmd.ExecuteNonQueryAsync();
            }
        }

        var opciones = new Microsoft.EntityFrameworkCore.DbContextOptionsBuilder<PlayDb>().UseSqlite(cs).Options;
        await using (var db = new PlayDb(opciones))
        {
            Assert.True(await Esquema.ActualizarAsync(db, dir) > 0);
            Assert.Equal(0, await Esquema.ActualizarAsync(db, dir)); // idempotente
        }

        await using (var cn = new Microsoft.Data.Sqlite.SqliteConnection(cs))
        {
            await cn.OpenAsync();
            async Task<long> Contar(string sql) { await using var c = cn.CreateCommand(); c.CommandText = sql; return Convert.ToInt64(await c.ExecuteScalarAsync()); }
            Assert.Equal(0, await Contar("SELECT COUNT(*) FROM sqlite_master WHERE name = 'UX_CargasHoras_EmpleadoId_Fecha'")); // se quitó el índice único
            Assert.Equal(2, await Contar("SELECT COUNT(*) FROM pragma_table_info('CargasHoras') WHERE name IN ('ObraId', 'SubtareaId')"));
            Assert.Equal(1, await Contar("SELECT COUNT(*) FROM CargasHoras WHERE ObraId IS NULL AND Minutos = 480")); // la carga de antes sigue ahí, sin obra
            // Ahora el mismo día admite más de una línea.
            await using var ins = cn.CreateCommand();
            ins.CommandText = "INSERT INTO CargasHoras (EmpleadoId, Fecha, Minutos, ObraId, CreadaUtc, ActualizadaUtc, Origen, Anulado) VALUES (1, '2026-11-18', 120, 1, '2026-11-18 16:00:00', '2026-11-18 16:00:00', 'panel', 0)";
            await ins.ExecuteNonQueryAsync();
            Assert.Equal(2, await Contar("SELECT COUNT(*) FROM CargasHoras WHERE EmpleadoId = 1 AND Fecha = '2026-11-18'"));
        }
        Microsoft.Data.Sqlite.SqliteConnection.ClearAllPools();
    }

    // ---------------------------------------------------------------- panel

    [Theory]
    [InlineData("8", 480)]
    [InlineData("7,5", 450)]
    [InlineData("7.5", 450)]
    [InlineData("7:30", 450)]
    [InlineData("8 h", 480)]
    [InlineData("8hs", 480)]
    [InlineData(" 0:45 ", 45)]
    [InlineData("24", 1440)]
    public void El_panel_entiende_las_horas_escritas_de_distintas_formas(string texto, int minutos)
    {
        Assert.True(PanelController.TryParseHoras(texto, out var m));
        Assert.Equal(minutos, m);
    }

    [Theory]
    [InlineData("")]
    [InlineData("  ")]
    [InlineData("abc")]
    [InlineData("0")]
    [InlineData("-3")]
    [InlineData("25")]
    [InlineData("7:75")]
    [InlineData("1:2:3")]
    [InlineData("NaN")]
    public void El_panel_rechaza_horas_que_no_se_entienden_o_estan_fuera_de_rango(string texto) =>
        Assert.False(PanelController.TryParseHoras(texto, out _));

    [Fact]
    public async Task El_panel_de_Taller_sabe_que_es_de_Taller_carga_las_horas_y_sin_conexion_no_pierde_nada_en_silencio()
    {
        var adm = await Admin("adm-ht9");
        var (id, _) = await Empleado(adm, "HtPanel");
        var (idOf, _) = await Empleado(adm, "HtPanelOficina", taller: false);
        var red = new RedIntermitente(new ApiClient(_s.CreateClient(), _s.Time));
        var c = new PanelController(red, new LocalStore(Path.Combine(Path.GetTempPath(), "play-cli-" + Guid.NewGuid().ToString("N"))), _s.Time, "PC-TALLER");
        Assert.True(await c.CargarListasAsync());

        Assert.Null(await c.LoginAsync(idOf, "1234"));
        Assert.False(c.EsTaller);
        Assert.Null(c.Horas);
        c.CerrarSesion();

        Assert.Null(await c.LoginAsync(id, "1234"));
        Assert.True(c.EsTaller);
        Assert.NotNull(c.Horas);
        var hoy = c.Horas!.Hoy;

        red.Caida = true;
        var sinRed = await c.CargarHorasAsync(hoy, 480);
        Assert.False(sinRed.Ok);
        Assert.Contains("no se guardaron", sinRed.Mensaje);
        Assert.Empty((await adm.HorasAsync(id)).Valor!);

        red.Caida = false;
        var ok = await c.CargarHorasAsync(hoy, 8 * 60);
        Assert.True(ok.Ok);
        Assert.Equal([(hoy, 480)], c.Horas!.Cargas.Select(x => (x.Fecha, x.Minutos)).ToArray());
        Assert.Equal(480, (await adm.HorasAsync(id)).Valor!.Single().Minutos);

        var fuera = await c.CargarHorasAsync(hoy.AddDays(-5), 480);
        Assert.False(fuera.Ok);
        Assert.Contains("hoy o ayer", fuera.Mensaje);
    }

    [Fact]
    public async Task El_panel_de_Taller_elige_obra_y_tarea_carga_quita_y_marca_la_tarea_como_terminada()
    {
        var adm = await Admin("adm-ht16");
        var (id, _, obra, obra2, estructura, _) = await TallerConObras(adm, "HtPanelObras");
        var c = new PanelController(new ApiClient(_s.CreateClient(), _s.Time), new LocalStore(Path.Combine(Path.GetTempPath(), "play-cli-" + Guid.NewGuid().ToString("N"))), _s.Time, "PC-T2");
        Assert.True(await c.CargarListasAsync());
        Assert.Null(await c.LoginAsync(id, "1234"));
        var hoy = c.Horas!.Hoy;

        Assert.Equal((0, "(Sin obra: trabajo general)"), (c.ObrasParaCarga[0].Id, c.ObrasParaCarga[0].Nombre)); // el menú de Taller empieza con «(Sin obra)»
        Assert.Contains(c.ObrasParaCarga, o => o.Id == obra);

        var sinTarea = await c.CargarHorasAsync(hoy, 60, obra);       // la obra tiene subtareas: ni siquiera llega al servidor
        Assert.False(sinTarea.Ok);
        Assert.Contains("subtareas", sinTarea.Mensaje);
        Assert.Empty((await adm.HorasAsync(id)).Valor!);

        Assert.True((await c.CargarHorasAsync(hoy, 5 * 60, obra, estructura)).Ok);
        Assert.True((await c.CargarHorasAsync(hoy, 2 * 60, obra2)).Ok);
        Assert.True((await c.CargarHorasAsync(hoy, 30, 0)).Ok);          // 0 = «(Sin obra)»
        Assert.Equal(3, c.Horas!.Cargas.Count(x => x.Fecha == hoy));
        Assert.Contains(c.Horas.Cargas, x => x.Obra == "Obra A Obras HtPanelObras" && x.Subtarea == "Estructura");

        // La casilla «Tarea terminada» funciona igual que para un empleado de Oficina.
        Assert.True((await c.MarcarTerminadaAsync(estructura, true)).Ok);
        Assert.Single((await adm.AvisosAsync()).Valor!, a => a.SubtareaId == estructura && a.Empleado == "HtPanelObras");

        Assert.True((await c.QuitarHorasAsync(hoy, obra2, null)).Ok);
        Assert.Equal(2, c.Horas.Cargas.Count(x => x.Fecha == hoy));
    }
}
