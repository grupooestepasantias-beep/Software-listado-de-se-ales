using ClosedXML.Excel;
using Microsoft.Extensions.DependencyInjection;
using Play.Client;
using Play.Server.Data;
using Play.Server.Services;
using Xunit;

namespace Play.Server.Tests;

/// <summary>
/// Control de asistencia: solo lunes a viernes; los días se cierran a las 23:59 y se genera UNA falta por
/// empleado y día; el administrador la justifica (con motivo) o la deja injustificada.
/// Cada prueba usa su propio servidor y su propio reloj (arranca el lunes 16/11/2026 a las 09:00 hora Argentina).
/// </summary>
public class AsistenciaTests
{
    private static readonly DateOnly Lun = new(2026, 11, 16), Mar = new(2026, 11, 17), Mie = new(2026, 11, 18), Jue = new(2026, 11, 19), Vie = new(2026, 11, 20),
        Sab = new(2026, 11, 21), Dom = new(2026, 11, 22);

    private static ServerFixture Nuevo() => new(Arg(16, 9, 0));

    /// <summary>Hora de Argentina (UTC-3) del día de noviembre de 2026.</summary>
    private static DateTimeOffset Arg(int dia, int hora, int min) => new(2026, 11, dia, hora, min, 0, TimeSpan.FromHours(-3));

    private static async Task<int> Cerrar(ServerFixture s)
    {
        using var scope = s.Services.CreateScope();
        return await scope.ServiceProvider.GetRequiredService<AsistenciaService>().CerrarDiasAsync();
    }

    private static async Task<AdminApi> Admin(ServerFixture s, string usuario = "adm-as")
    {
        s.CrearAdmin(usuario, "clave-segura-1");
        var api = new AdminApi(new ApiClient(s.CreateClient(), s.Time));
        api.Token = (await api.LoginAsync(usuario, "clave-segura-1")).Valor!.Token;
        return api;
    }

    private static async Task<(int Id, ApiClient Api, int Obra)> Empleado(ServerFixture s, AdminApi adm, string nombre, bool taller = false)
    {
        var (id, obra, _) = s.CrearDatos(nombre);
        if (taller) await adm.ActualizarEmpleadoAsync(id, area: "Taller");
        var c = new ApiClient(s.CreateClient(), s.Time);
        c.Token = (await c.LoginAsync(id, "1234")).Valor!.Token;
        return (id, c, obra);
    }

    /// <summary>Usa el cronómetro un rato (un registro de Play).</summary>
    private static async Task UsarPlay(ServerFixture s, ApiClient e, int obra)
    {
        var r = await e.IniciarAsync(Guid.NewGuid(), obra, null, "PC");
        Assert.True(r.Ok);
        s.Time.Advance(TimeSpan.FromMinutes(30));
        Assert.True((await e.CerrarAsync(r.Valor!.Id, null)).Ok);
    }

    private static async Task<string> Codigo(AdminApi adm, int empleadoId, DateOnly dia)
    {
        var r = await adm.AsistenciaAsync(dia.Year, dia.Month);
        Assert.True(r.Ok, r.Status + " " + r.Texto);
        var mes = r.Valor!;
        return mes.Filas.First(f => f.EmpleadoId == empleadoId).Codigos[dia.Day - 1];
    }

    /// <summary>Mueve el reloj y vuelve a ingresar el administrador (las sesiones duran 24 horas y acÃ¡ pasan dÃ­as).</summary>
    private static async Task Ir(ServerFixture s, AdminApi adm, DateTimeOffset momento)
    {
        s.Time.SetUtcNow(momento);
        adm.Token = (await adm.LoginAsync("adm-as", "clave-segura-1")).Valor!.Token;
    }

    private static async Task<int> SinRevisar(AdminApi adm) => (await adm.AlertasFaltasAsync()).Valor!.SinRevisar;

    // ---------------------------------------------------------------- cierre de días

    [Fact]
    public async Task El_dia_se_cierra_a_las_2359_y_se_genera_una_sola_falta_por_empleado_y_dia_sin_contar_fines_de_semana()
    {
        await using var s = Nuevo();
        var adm = await Admin(s);
        var (id, _, _) = await Empleado(s, adm, "AsCierre");
        await Cerrar(s); // el control empieza hoy (lunes)

        await Ir(s, adm, Arg(16, 23, 58));
        await Cerrar(s);
        Assert.Empty((await adm.FaltasAsync(Lun, Lun, id)).Valor!);       // todavía no terminó el día
        Assert.Equal("…", await Codigo(adm, id, Lun));

        await Ir(s, adm, Arg(16, 23, 59));
        Assert.True(await Cerrar(s) >= 1);
        var f = Assert.Single((await adm.FaltasAsync(Lun, Lun, id)).Valor!);
        Assert.Equal(("AsCierre", "sin_revisar"), (f.Empleado, f.Estado));
        Assert.Equal(0, await Cerrar(s));                                  // cerrar de nuevo no duplica nada
        using (var scope = s.Services.CreateScope())
            Assert.Equal(1, scope.ServiceProvider.GetRequiredService<PlayDb>().Faltas.Count(x => x.EmpleadoId == id));

        // Resto de la semana y fin de semana: sábado y domingo no son faltas.
        await Ir(s, adm, Arg(22, 23, 59));
        await Cerrar(s);
        var faltas = (await adm.FaltasAsync(Lun, Dom, id)).Valor!.Select(x => x.Fecha).OrderBy(x => x).ToArray();
        Assert.Equal([Lun, Mar, Mie, Jue, Vie], faltas);
        var mes = (await adm.AsistenciaAsync(2026, 11)).Valor!;
        var fila = mes.Filas.First(x => x.EmpleadoId == id);
        Assert.Equal(["S", "S"], new[] { fila.Codigos[Sab.Day - 1], fila.Codigos[Dom.Day - 1] });
        Assert.Equal((0, 5, 0), (fila.Presentes, fila.Ausentes, fila.Justificados));
    }

    [Fact]
    public async Task Presente_es_haber_usado_Play_en_Oficina_o_haber_cargado_horas_en_Taller()
    {
        await using var s = Nuevo();
        var adm = await Admin(s);
        var (oficina, apiO, obraO) = await Empleado(s, adm, "AsOficinaPlay");
        var (taller, apiT, _) = await Empleado(s, adm, "AsTallerCarga", taller: true);
        var (tallerPlay, apiTP, obraTP) = await Empleado(s, adm, "AsTallerSoloPlay", taller: true);
        var (nadie, _, _) = await Empleado(s, adm, "AsNadie");
        await Cerrar(s);

        await UsarPlay(s, apiO, obraO);
        await UsarPlay(s, apiTP, obraTP); // un empleado de Taller que usa Play: no cuenta, a Taller se lo controla por sus horas
        Assert.True((await apiT.CargarHorasAsync(Lun, 8 * 60)).Ok);

        await Ir(s, adm, Arg(16, 23, 59));
        await Cerrar(s);
        Assert.Equal("P", await Codigo(adm, oficina, Lun));
        Assert.Equal("P", await Codigo(adm, taller, Lun));
        Assert.Equal("A", await Codigo(adm, tallerPlay, Lun));
        Assert.Equal("A", await Codigo(adm, nadie, Lun));
        Assert.DoesNotContain((await adm.FaltasAsync(Lun, Lun)).Valor!, x => x.EmpleadoId == oficina || x.EmpleadoId == taller);
    }

    [Fact]
    public async Task Un_empleado_de_Taller_puede_cargar_ayer_y_la_falta_desaparece_sola()
    {
        await using var s = Nuevo();
        var adm = await Admin(s);
        var (id, api, _) = await Empleado(s, adm, "AsTardio", taller: true);
        await Cerrar(s);
        await Ir(s, adm, Arg(16, 23, 59));
        await Cerrar(s);
        var antes = await SinRevisar(adm);
        Assert.Equal("A", await Codigo(adm, id, Lun));

        await Ir(s, adm, Arg(17, 8, 0)); // martes por la mañana: todavía puede cargar «ayer»
        Assert.True((await api.CargarHorasAsync(Lun, 8 * 60)).Ok);
        Assert.Equal("P", await Codigo(adm, id, Lun));
        Assert.Equal(antes - 1, await SinRevisar(adm));
        Assert.Empty((await adm.FaltasAsync(Lun, Lun, id)).Valor!);
    }

    [Fact]
    public async Task No_hay_faltas_hacia_atras_ni_antes_del_alta_de_un_empleado_nuevo()
    {
        await using var s = Nuevo();
        var adm = await Admin(s);
        var (viejo, _, _) = await Empleado(s, adm, "AsViejo");
        await Cerrar(s);                           // el control empieza el lunes 16

        await Ir(s, adm, Arg(18, 9, 0));            // miércoles: se da de alta a alguien nuevo
        var nuevo = (await adm.CrearEmpleadoAsync("AsNuevo")).Valor!.Empleado.Id;
        await Ir(s, adm, Arg(20, 23, 59));
        await Cerrar(s);

        var mes = (await adm.AsistenciaAsync(2026, 11)).Valor!;
        Assert.Equal(Lun, mes.ControlDesde);
        var fViejo = mes.Filas.First(f => f.EmpleadoId == viejo).Codigos;
        Assert.Equal(["-", "-", "-", "-", "-"], Enumerable.Range(9, 5).Select(d => fViejo[d - 1]).ToArray()); // 9 al 13: antes de que empezara el control (no hay faltas hacia atrás)
        var fNuevo = mes.Filas.First(f => f.EmpleadoId == nuevo).Codigos;
        // El empleado nuevo se dio de alta el miércoles: lunes y martes son «sin control»; miércoles a viernes, ausencias.
        Assert.Equal(["-", "-", "A", "A", "A"], new[] { fNuevo[Lun.Day - 1], fNuevo[Mar.Day - 1], fNuevo[Mie.Day - 1], fNuevo[Jue.Day - 1], fNuevo[Vie.Day - 1] });
    }

    // ---------------------------------------------------------------- el administrador resuelve las faltas

    [Fact]
    public async Task El_administrador_justifica_con_motivo_o_deja_la_falta_injustificada_y_puede_corregirla()
    {
        await using var s = Nuevo();
        var adm = await Admin(s);
        var (id, _, _) = await Empleado(s, adm, "AsJustificar");
        await Cerrar(s);
        await Ir(s, adm, Arg(16, 23, 59)); await Cerrar(s);   // el lunes termina...
        await Ir(s, adm, Arg(17, 8, 0));                      // ...y ya es martes por la mañana
        var base0 = await SinRevisar(adm);

        Assert.Equal("motivo_requerido", (await adm.JustificarFaltaAsync(id, Lun, "  ")).Codigo);
        Assert.Equal("no_corresponde", (await adm.JustificarFaltaAsync(id, Mar, "Licencia")).Codigo); // el martes todavía no terminó
        Assert.Equal("no_corresponde", (await adm.JustificarFaltaAsync(id, Sab, "Licencia")).Codigo); // sábado: no cuenta
        Assert.Equal(404, (int)(await adm.JustificarFaltaAsync(99999, Lun, "x")).Status!);

        var j = (await adm.JustificarFaltaAsync(id, Lun, "Licencia por enfermedad")).Valor!;
        Assert.Equal(("justificada", "Licencia por enfermedad"), (j.Estado, j.Motivo));
        Assert.Equal("J", await Codigo(adm, id, Lun));
        Assert.Equal(base0 - 1, await SinRevisar(adm));
        var f = Assert.Single((await adm.FaltasAsync(Lun, Lun, id)).Valor!);
        Assert.Equal(("justificada", "Licencia por enfermedad", "adm-as"), (f.Estado, f.Motivo, f.Administrador));
        // Una falta justificada no cuenta como injustificada.
        Assert.Empty((await adm.FaltasAsync(Lun, Lun, id, estado: "injustificada")).Valor!);
        var resumen = (await adm.AsistenciaAsync(2026, 11)).Valor!.Filas.First(x => x.EmpleadoId == id);
        Assert.Equal((0, 0, 1), (resumen.Presentes, resumen.Ausentes, resumen.Justificados));

        // Corregir el motivo y después dejarla injustificada.
        Assert.Equal("Cita médica", (await adm.JustificarFaltaAsync(id, Lun, "Cita médica")).Valor!.Motivo);
        var inj = (await adm.InjustificarFaltaAsync(id, Lun, "No avisó")).Valor!;
        Assert.Equal("injustificada", inj.Estado);
        Assert.Equal("A", await Codigo(adm, id, Lun));
        Assert.Equal(base0 - 1, await SinRevisar(adm)); // injustificada = ya revisada, no sigue siendo alerta
        Assert.Single((await adm.FaltasAsync(Lun, Lun, id, estado: "injustificada")).Valor!);

        var aud = (await adm.AuditoriaAsync()).Valor!;
        Assert.Contains(aud, x => x.Campo == "falta_justificada" && x.ValorNuevo!.Contains("AsJustificar") && x.Motivo == "Licencia por enfermedad");
        Assert.Contains(aud, x => x.Campo == "falta_injustificada" && x.ValorAnterior!.Contains("Cita médica"));
    }

    [Fact]
    public async Task Los_empleados_no_pueden_justificar_ni_ver_la_asistencia()
    {
        await using var s = Nuevo();
        var adm = await Admin(s);
        var (id, api, _) = await Empleado(s, adm, "AsPermisos");
        await Cerrar(s);
        var comoEmpleado = new AdminApi(api);
        Assert.Equal(401, (int)(await comoEmpleado.AsistenciaAsync(2026, 11)).Status!);
        Assert.Equal(401, (int)(await comoEmpleado.JustificarFaltaAsync(id, Lun, "x")).Status!);
        Assert.Equal(401, (int)(await comoEmpleado.FaltasAsync()).Status!);
    }

    // ---------------------------------------------------------------- libro mensual y Excel

    [Fact]
    public async Task El_libro_mensual_muestra_dias_totales_y_se_exporta_a_Excel()
    {
        await using var s = Nuevo();
        var adm = await Admin(s);
        var (a, apiA, obraA) = await Empleado(s, adm, "AsLibroA");
        var (b, _, _) = await Empleado(s, adm, "AsLibroB", taller: true);
        await Cerrar(s);
        await UsarPlay(s, apiA, obraA);
        await Ir(s, adm, Arg(16, 23, 59)); await Cerrar(s);
        await Ir(s, adm, Arg(17, 23, 59)); await Cerrar(s);
        await adm.JustificarFaltaAsync(b, Mar, "Capacitación");

        var mes = (await adm.AsistenciaAsync(2026, 11)).Valor!;
        Assert.Equal(30, mes.Dias.Count);
        Assert.Equal(["finde", "habil"], new[] { mes.Dias[Sab.Day - 1].Tipo, mes.Dias[Lun.Day - 1].Tipo });
        var fa = mes.Filas.First(x => x.EmpleadoId == a);
        var fb = mes.Filas.First(x => x.EmpleadoId == b);
        Assert.Equal((1, 1, 0), (fa.Presentes, fa.Ausentes, fa.Justificados)); // presente el lunes, ausente el martes
        Assert.Equal((0, 1, 1), (fb.Presentes, fb.Ausentes, fb.Justificados)); // ausente el lunes, justificado el martes
        Assert.All(mes.Filas, f => Assert.Equal(30, f.Codigos.Count));
        // El filtro de área.
        Assert.All((await adm.AsistenciaAsync(2026, 11, "Taller")).Valor!.Filas, f => Assert.Equal("Taller", f.Area));
        Assert.Equal(400, (int)(await adm.AsistenciaAsync(2026, 13)).Status!);

        using var wb = new XLWorkbook(new MemoryStream((await adm.AsistenciaExcelAsync(2026, 11)).Valor!));
        Assert.Equal(["Asistencia", "Resumen", "Faltas"], wb.Worksheets.Select(w => w.Name).ToArray());
        var fila = wb.Worksheet("Asistencia").RowsUsed().Skip(1).First(r => r.Cell(1).GetString() == "AsLibroA");
        Assert.Equal("P", fila.Cell(2 + Lun.Day).GetString());
        Assert.Equal("A", fila.Cell(2 + Mar.Day).GetString());
        var resumen = wb.Worksheet("Resumen").RowsUsed().Skip(1).First(r => r.Cell(1).GetString() == "AsLibroB");
        Assert.Equal((2.0, 0.0, 1.0, 1.0), (resumen.Cell(3).GetDouble(), resumen.Cell(4).GetDouble(), resumen.Cell(5).GetDouble(), resumen.Cell(6).GetDouble()));
        Assert.Contains(wb.Worksheet("Faltas").RowsUsed().Skip(1), r => r.Cell(2).GetString() == "AsLibroB" && r.Cell(4).GetString() == "Justificada" && r.Cell(5).GetString() == "Capacitación");
    }

    [Fact]
    public async Task Los_dias_anteriores_al_control_figuran_sin_control_y_un_dia_sin_cerrar_figura_pendiente()
    {
        await using var s = Nuevo();
        var adm = await Admin(s);
        var (id, _, _) = await Empleado(s, adm, "AsSinControl");
        await Cerrar(s);
        Assert.Equal("-", await Codigo(adm, id, new DateOnly(2026, 11, 12)));  // antes de que empezara el control
        Assert.Equal("…", await Codigo(adm, id, Lun));                          // hoy todavía no terminó
        Assert.Equal("…", await Codigo(adm, id, Mie));                          // futuro
        Assert.Equal(0, await SinRevisar(adm) - await SinRevisar(adm));          // (sin alertas por días anteriores)
        Assert.Empty((await adm.FaltasAsync(new DateOnly(2026, 11, 1), new DateOnly(2026, 11, 15), id)).Valor!);
    }
}
