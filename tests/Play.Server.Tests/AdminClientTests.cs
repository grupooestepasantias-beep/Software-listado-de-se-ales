using System.Net;
using Play.Client;
using Xunit;

namespace Play.Server.Tests;

/// <summary>Prueba el cliente de administración (el que usa el programa PlayAdmin) contra el servidor real.</summary>
public class AdminClientTests : IClassFixture<ServerFixture>
{
    private readonly ServerFixture _s;
    public AdminClientTests(ServerFixture s) => _s = s;

    private AdminApi Nuevo() => new(new ApiClient(_s.CreateClient(), _s.Time));

    private async Task<AdminApi> ConSesion(string usuario)
    {
        _s.CrearAdmin(usuario, "clave-segura-1");
        var api = Nuevo();
        var r = await api.LoginAsync(usuario, "clave-segura-1");
        Assert.True(r.Ok);
        api.Token = r.Valor!.Token;
        return api;
    }

    [Fact]
    public async Task Clave_temporal_obliga_a_cambiarla_antes_de_hacer_otra_cosa()
    {
        _s.CrearAdmin("adm-cli1", "temporal-123", debeCambiar: true);
        var api = Nuevo();
        var login = await api.LoginAsync("adm-cli1", "temporal-123");
        Assert.True(login.Valor!.DebeCambiarClave);
        api.Token = login.Valor.Token;

        var bloqueado = await api.EmpleadosAsync();
        Assert.Equal(HttpStatusCode.Forbidden, bloqueado.Status);
        Assert.Equal("debe_cambiar_clave", bloqueado.Codigo);

        Assert.False((await api.CambiarClaveAsync("temporal-123", "corta")).Ok);
        Assert.True((await api.CambiarClaveAsync("temporal-123", "nueva-clave-9")).Ok);
        Assert.True((await api.EmpleadosAsync()).Ok);
    }

    [Fact]
    public async Task Login_con_clave_incorrecta_falla()
    {
        _s.CrearAdmin("adm-cli2", "clave-segura-1");
        var r = await Nuevo().LoginAsync("adm-cli2", "otra");
        Assert.Equal(HttpStatusCode.Unauthorized, r.Status);
    }

    [Fact]
    public async Task Empleados_y_obras_se_crean_renombran_y_desactivan()
    {
        var api = await ConSesion("adm-cli3");

        var nuevo = await api.CrearEmpleadoAsync("Cli Empleado");
        Assert.Equal(4, nuevo.Valor!.PinInicial.Length);
        var id = nuevo.Valor.Empleado.Id;
        var dup = await api.CrearEmpleadoAsync("Cli Empleado");
        Assert.Equal("nombre_duplicado", dup.Codigo);

        Assert.Equal("Cli Empleado Renombrado", (await api.ActualizarEmpleadoAsync(id, nombre: "Cli Empleado Renombrado")).Valor!.Nombre);
        Assert.False((await api.ActualizarEmpleadoAsync(id, activo: false)).Valor!.Activo);
        Assert.Equal(4, (await api.ResetearPinAsync(id)).Valor!.PinInicial.Length);
        Assert.Contains((await api.EmpleadosAsync()).Valor!, e => e.Id == id && !e.Activo);

        var obra = (await api.CrearObraAsync("Cli Obra")).Valor!;
        Assert.False((await api.ActualizarObraAsync(obra.Id, activo: false)).Valor!.Activa);
        Assert.Contains((await api.ObrasAsync()).Valor!, o => o.Id == obra.Id && !o.Activa);
    }

    [Fact]
    public async Task Administradores_se_crean_y_se_resetean()
    {
        var api = await ConSesion("adm-cli4");
        var nuevo = (await api.CrearAdministradorAsync("segundo-admin", "Segundo Admin")).Valor!;
        Assert.False(string.IsNullOrEmpty(nuevo.ClaveTemporal));
        Assert.False((await api.ActivarAdministradorAsync(nuevo.Administrador.Id, false)).Valor!.Activo);
        Assert.False(string.IsNullOrEmpty((await api.ResetearClaveAdminAsync(nuevo.Administrador.Id)).Valor!.ClaveTemporal));
    }

    [Fact]
    public async Task Alta_manual_correccion_y_auditoria()
    {
        var api = await ConSesion("adm-cli5");
        var (emp, obra, obra2) = _s.CrearDatos("CliAdminReg");
        var ahora = _s.Time.GetUtcNow().UtcDateTime;

        var reg = (await api.CrearRegistroAsync(emp, obra, ahora.AddHours(-4), ahora.AddHours(-2), "Trabajó sin la PC")).Valor!;
        Assert.Equal(7200, reg.Segundos);

        var sinMotivo = await api.CorregirAsync(reg.Id, null, ahora.AddHours(-3), null, " ");
        Assert.Equal("motivo_requerido", sinMotivo.Codigo);
        var ok = (await api.CorregirAsync(reg.Id, null, ahora.AddHours(-3), obra2, "Salió antes")).Valor!;
        Assert.Equal(3600, ok.Segundos);
        Assert.Equal("corregido", ok.Estado);

        var aud = (await api.AuditoriaAsync(reg.Id)).Valor!;
        Assert.Equal(3, aud.Count); // creado + fin + obra
        Assert.All(aud, a => Assert.Equal("adm-cli5", a.Administrador));

        var lista = (await api.RegistrosAsync(new FiltroAdmin(EmpleadoId: emp, Desde: new DateOnly(2026, 11, 18), Hasta: new DateOnly(2026, 11, 18)))).Valor!;
        Assert.Single(lista);
    }

    [Fact]
    public async Task Excel_y_backup_funcionan_desde_el_cliente()
    {
        var api = await ConSesion("adm-cli6");
        var xlsx = await api.ReporteExcelAsync(new FiltroAdmin());
        Assert.True(xlsx.Ok);
        Assert.Equal((byte)'P', xlsx.Valor![0]); // los .xlsx son archivos zip («PK»)
        Assert.Equal((byte)'K', xlsx.Valor[1]);

        var backup = (await api.HacerBackupAsync()).Valor!;
        var lista = (await api.BackupsAsync()).Valor!;
        Assert.Contains(lista.Backups, b => b.Archivo == backup.Archivo);
    }

    [Fact]
    public async Task Sin_red_se_informa_sin_lanzar_excepciones()
    {
        var api = new AdminApi(new ApiClient(new HttpClient { BaseAddress = new Uri("http://127.0.0.1:1/"), Timeout = TimeSpan.FromSeconds(3) }, _s.Time, TimeSpan.FromSeconds(2)));
        Assert.True((await api.LoginAsync("x", "y")).SinRed);
    }
}
