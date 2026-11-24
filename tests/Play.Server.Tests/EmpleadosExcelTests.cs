using ClosedXML.Excel;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.DependencyInjection;
using Play.Client;
using Play.Server.Data;
using Play.Server.Services;
using Xunit;
using EmpleadosExcelEstadoDto = Play.Server.Services.EmpleadosExcelEstadoDto;

namespace Play.Server.Tests;

/// <summary>
/// El Excel de empleados (Empleado, Contraseña, Área) es la base de datos de empleados: la primera vez reemplaza a los
/// empleados anteriores; después, cada cambio del Excel (alta, baja, PIN, área) se refleja en la app.
/// </summary>
public class EmpleadosExcelTests
{
    private static readonly DateTimeOffset Inicio = new(2026, 11, 18, 12, 0, 0, TimeSpan.FromHours(-3));

    private static string RutaNueva() => Path.Combine(Path.GetTempPath(), "play-xl-" + Guid.NewGuid().ToString("N") + ".xlsx");

    /// <summary>Arma un Excel como el de la usuaria: Empleado | Contraseña | Área, y a la derecha las referencias de color.</summary>
    private static void CrearExcel(string ruta, params (string Nombre, string Secreto, string Area)[] filas)
    {
        using var wb = new XLWorkbook();
        var ws = wb.AddWorksheet("Hoja1");
        ws.Cell(1, 1).Value = "Empleado"; ws.Cell(1, 2).Value = "Contraseña"; ws.Cell(1, 3).Value = "Área"; ws.Cell(1, 5).Value = "Codigo de color";
        ws.Cell(2, 4).Value = "Oficina = "; ws.Cell(3, 4).Value = "Taller = "; ws.Cell(4, 4).Value = "Admin = "; // referencias que la app tiene que ignorar
        for (var i = 0; i < filas.Length; i++)
        {
            ws.Cell(i + 2, 1).Value = filas[i].Nombre;
            // Como en el Excel real: un PIN con ceros se escribe como texto; los demás pueden ser números.
            if (int.TryParse(filas[i].Secreto, out var n) && !filas[i].Secreto.StartsWith('0') && filas[i].Secreto.Length == 4) ws.Cell(i + 2, 2).Value = n;
            else ws.Cell(i + 2, 2).Value = filas[i].Secreto;
            ws.Cell(i + 2, 3).Value = filas[i].Area;
        }
        wb.SaveAs(ruta);
    }

    private static async Task<EmpleadosExcelEstadoDto> Sincronizar(ServerFixture s, bool forzar = false)
    {
        using var scope = s.Services.CreateScope();
        return await scope.ServiceProvider.GetRequiredService<EmpleadosExcelService>().SincronizarAsync(forzar);
    }

    private static PlayDb Db(IServiceScope scope) => scope.ServiceProvider.GetRequiredService<PlayDb>();

    private static async Task<ApiClient?> Entrar(ServerFixture s, string nombre, string pin)
    {
        using var scope = s.Services.CreateScope();
        var id = await Db(scope).Empleados.Where(e => e.Nombre == nombre).Select(e => (int?)e.Id).FirstOrDefaultAsync();
        if (id is null) return null;
        var c = new ApiClient(s.CreateClient(), s.Time);
        var r = await c.LoginAsync(id.Value, pin);
        if (!r.Ok) return null;
        c.Token = r.Valor!.Token;
        return c;
    }

    private static readonly (string, string, string)[] Base =
    [
        ("Ahuad Juan Pablo", "2914", "Oficina"),
        ("Rodriguez Pardo Ezequiel Agustin", "0187'", "Oficina"),   // PIN con cero inicial y apóstrofe, como en el Excel real
        ("Acosta Marcelo", "5439", "Taller"),
        ("Garcia Gabriel Gines  ", "3703", "Oficina"),               // espacios de más
        ("Garcia Gabriel Gines", "12345678", "Administrador"),
    ];

    // ---------------------------------------------------------------- primera vez

    [Fact]
    public async Task La_primera_vez_elimina_a_los_empleados_anteriores_con_todo_su_rastro_y_carga_los_del_Excel()
    {
        var ruta = RutaNueva();
        CrearExcel(ruta, Base);
        await using var s = new ServerFixture(Inicio, ruta);

        // Antes: empleados de prueba con registros, horas de Taller, faltas, avisos y constancias.
        var (viejo, obra, _) = s.CrearDatos("Viejo de Prueba");
        int subtarea;
        using (var scope = s.Services.CreateScope())
        {
            var db = Db(scope);
            var st = new Subtarea { ObraId = obra, Nombre = "Tarea vieja" };
            db.Subtareas.Add(st);
            await db.SaveChangesAsync();
            subtarea = st.Id;
            var reg = new RegistroTiempo { Id = Guid.NewGuid(), EmpleadoId = viejo, ObraId = obra, InicioUtc = s.Time.GetUtcNow().UtcDateTime.AddHours(-3), FinUtc = s.Time.GetUtcNow().UtcDateTime.AddHours(-1), UltimoLatidoUtc = s.Time.GetUtcNow().UtcDateTime, Estado = EstadoRegistro.Cerrado, Equipo = "PC" };
            db.Registros.Add(reg);
            db.CargasHoras.Add(new CargaHoras { EmpleadoId = viejo, Fecha = new DateOnly(2026, 11, 17), Minutos = 480, CreadaUtc = DateTime.UtcNow, ActualizadaUtc = DateTime.UtcNow, Origen = "panel" });
            db.Faltas.Add(new Falta { EmpleadoId = viejo, Fecha = new DateOnly(2026, 11, 16), CreadaUtc = DateTime.UtcNow });
            db.AvisosSubtarea.Add(new AvisoSubtarea { SubtareaId = st.Id, EmpleadoId = viejo, CreadoUtc = DateTime.UtcNow });
            db.Auditorias.Add(new Auditoria { FechaUtc = DateTime.UtcNow, AdministradorId = 1, RegistroId = reg.Id, Campo = "inicio", Motivo = "corrección vieja" });
            db.Auditorias.Add(new Auditoria { FechaUtc = DateTime.UtcNow, AdministradorId = 1, Campo = "area", ValorNuevo = "Viejo de Prueba → Taller", Motivo = "cambio de área" });
            db.Auditorias.Add(new Auditoria { FechaUtc = DateTime.UtcNow, AdministradorId = 1, Campo = "otra_cosa", ValorNuevo = "no menciona a nadie", Motivo = "esta constancia se conserva" });
            await db.SaveChangesAsync();
        }

        var r = await Sincronizar(s);
        Assert.True(r.Ok, r.Mensaje);

        using (var scope = s.Services.CreateScope())
        {
            var db = Db(scope);
            Assert.DoesNotContain(db.Empleados, e => e.Nombre == "Viejo de Prueba" || e.Nombre == "Semilla Uno"); // ni el de prueba ni el de la semilla
            Assert.Equal(0, db.Registros.Count());
            Assert.Equal(0, db.CargasHoras.Count());
            Assert.Equal(0, db.Faltas.Count());
            Assert.Equal(0, db.AvisosSubtarea.Count());
            Assert.DoesNotContain(db.Auditorias.ToList(), a => a.Campo == "inicio" || a.ValorNuevo == "Viejo de Prueba → Taller"); // sin rastro de ellos
            Assert.Contains(db.Auditorias.ToList(), a => a.Campo == "otra_cosa"); // lo que no tiene que ver con empleados se conserva
            Assert.Equal(obra, db.Obras.Single(o => o.Id == obra).Id);             // las obras y subtareas siguen ahí
            Assert.True(db.Subtareas.Any(x => x.Id == subtarea));
            Assert.Equal(4, db.Empleados.Count());                                  // 4 empleados (los 5 con la fila de administrador, que no es empleada)
        }
        Assert.NotEmpty(Directory.GetFiles(Path.Combine(s.DataDir, "backups"), "play-antes-de-importar-excel-*.db")); // copia previa

        // Los PIN del Excel funcionan tal cual (sin el apóstrofe, con su cero y venga como número o como texto).
        Assert.NotNull(await Entrar(s, "Ahuad Juan Pablo", "2914"));
        Assert.NotNull(await Entrar(s, "Rodriguez Pardo Ezequiel Agustin", "0187"));
        Assert.NotNull(await Entrar(s, "Garcia Gabriel Gines", "3703"));  // el nombre se guarda sin espacios sobrantes
        Assert.Null(await Entrar(s, "Ahuad Juan Pablo", "0000"));

        using (var scope = s.Services.CreateScope())
        {
            var db = Db(scope);
            Assert.Equal("Taller", db.Empleados.Single(e => e.Nombre == "Acosta Marcelo").Area);
            Assert.All(db.Empleados.ToList(), e => { Assert.False(e.DebeCambiarPin); Assert.True(e.Activo); }); // el PIN sale del Excel: no se pide cambiarlo
            Assert.Equal("0187", db.Empleados.Single(e => e.Nombre.StartsWith("Rodriguez")).PinVisible);
            var aud = db.Auditorias.AsEnumerable().Single(a => a.Campo == "empleados_excel");
            Assert.Equal(0, aud.AdministradorId);
            Assert.DoesNotContain("2914", aud.ValorNuevo!);   // la constancia nunca lleva PIN
        }
        Assert.True((await new AdminApi(new ApiClient(s.CreateClient(), s.Time)).LoginAsync("x", "y")).Status is not null); // el servidor sigue de pie
    }

    [Fact]
    public async Task Las_filas_Administrador_crean_administradores_con_clave_temporal_y_no_pisan_a_los_que_ya_existen()
    {
        var ruta = RutaNueva();
        CrearExcel(ruta,
            ("Garcia Gabriel Gines", "3703", "Oficina"), ("Garcia Gabriel Gines", "12345678", "Administrador"),
            ("Ruggeri Gonzalo Mauro", "0442'", "Oficina"), ("Ruggeri Gonzalo Mauro", "12345678", "Administrador"),
            ("Vera Diego Ricardo", "0909'", "Oficina"), ("Vera Diego Ricardo", "12345678", "Administrador"));
        await using var s = new ServerFixture(Inicio, ruta);
        // La administradora que ya existía (el servidor de prueba trae a «Gabriel» de su configuración) con su propia clave ya elegida.
        using (var scope = s.Services.CreateScope())
        {
            var db = Db(scope);
            var g = db.Administradores.Single(a => a.Usuario == "Gabriel");
            g.PassHash = PinHasher.Hash("mi-clave-propia");
            g.DebeCambiarPass = false;
            await db.SaveChangesAsync();
        }

        var r = await Sincronizar(s);
        Assert.True(r.Ok, r.Mensaje);

        using (var scope = s.Services.CreateScope())
        {
            var admins = Db(scope).Administradores.AsNoTracking().OrderBy(a => a.Usuario).ToList();
            Assert.Equal(["Diego", "Gabriel", "Gonzalo"], admins.Select(a => a.Usuario).ToArray()); // Gabriel no se duplicó
            Assert.Equal("Garcia Gabriel Gines", admins.Single(a => a.Usuario == "Gabriel").NombreCompleto); // se le puso su nombre
            Assert.False(admins.Single(a => a.Usuario == "Gabriel").DebeCambiarPass);                          // su clave no se tocó
            Assert.All(admins.Where(a => a.Usuario != "Gabriel"), a => Assert.True(a.DebeCambiarPass));       // los nuevos: clave temporal
        }

        var api = new AdminApi(new ApiClient(s.CreateClient(), s.Time));
        Assert.True((await api.LoginAsync("Gabriel", "mi-clave-propia")).Ok);            // la suya sigue funcionando
        Assert.False((await api.LoginAsync("Gabriel", "12345678")).Ok);                   // y la del Excel no la pisó
        var nuevo = (await api.LoginAsync("gonzalo", "12345678")).Valor!;                 // el usuario no distingue mayúsculas
        Assert.True(nuevo.DebeCambiarClave);                                              // tiene que cambiarla al entrar
        // Cada uno también figura como empleado (son personas que son empleadas y administradoras).
        using (var scope = s.Services.CreateScope())
            Assert.Equal(3, Db(scope).Empleados.Count(e => e.Nombre.StartsWith("Garcia") || e.Nombre.StartsWith("Ruggeri") || e.Nombre.StartsWith("Vera")));
        // Si más adelante cambia la clave del Excel, la app no la pisa.
        CrearExcel(ruta, ("Garcia Gabriel Gines", "3703", "Oficina"), ("Ruggeri Gonzalo Mauro", "0442", "Oficina"), ("Ruggeri Gonzalo Mauro", "otra-clave-nueva", "Administrador"), ("Vera Diego Ricardo", "0909", "Oficina"));
        await Sincronizar(s);
        Assert.True((await api.LoginAsync("gonzalo", "12345678")).Ok);
    }

    // ---------------------------------------------------------------- cambios del Excel

    [Fact]
    public async Task Los_cambios_del_Excel_se_reflejan_PIN_area_altas_y_bajas_sin_borrar_a_nadie()
    {
        var ruta = RutaNueva();
        CrearExcel(ruta, ("Ahuad Juan Pablo", "2914", "Oficina"), ("Acosta Marcelo", "5439", "Taller"), ("Canno Francisco", "2243", "Oficina"));
        await using var s = new ServerFixture(Inicio, ruta);
        Assert.True((await Sincronizar(s)).Ok);

        // Un registro de Acosta, para comprobar que su historial sobrevive a la baja.
        var sesionAhuad = await Entrar(s, "Ahuad Juan Pablo", "2914");
        Assert.NotNull(sesionAhuad);
        using (var scope = s.Services.CreateScope())
        {
            var db = Db(scope);
            var acosta = db.Empleados.Single(e => e.Nombre == "Acosta Marcelo");
            db.CargasHoras.Add(new CargaHoras { EmpleadoId = acosta.Id, Fecha = new DateOnly(2026, 11, 17), Minutos = 300, CreadaUtc = DateTime.UtcNow, ActualizadaUtc = DateTime.UtcNow, Origen = "panel" });
            await db.SaveChangesAsync();
        }

        // Sin cambios: no hace nada y no deja constancias de más.
        int constancias;
        using (var scope = s.Services.CreateScope()) constancias = Db(scope).Auditorias.Count(a => a.Campo == "empleados_excel");
        var igual = await Sincronizar(s);
        Assert.Contains("al día", igual.Mensaje);
        using (var scope = s.Services.CreateScope()) Assert.Equal(constancias, Db(scope).Auditorias.Count(a => a.Campo == "empleados_excel"));

        // El Excel cambia: PIN de Ahuad, Acosta pasa a Oficina, Canno ya no está y entra uno nuevo.
        CrearExcel(ruta, ("Ahuad Juan Pablo", "1111", "Oficina"), ("Acosta Marcelo", "5439", "Oficina"), ("Quiroga Jose Omar", "9964", "Taller"));
        var r = await Sincronizar(s);
        Assert.True(r.Ok, r.Mensaje);
        Assert.Equal((1, 2, 1), (r.Creados, r.Actualizados, r.Desactivados));

        Assert.Null(await Entrar(s, "Ahuad Juan Pablo", "2914"));                       // el PIN viejo ya no sirve
        Assert.NotNull(await Entrar(s, "Ahuad Juan Pablo", "1111"));                    // el nuevo sí
        Assert.Equal(401, (int)(await sesionAhuad!.LatidoAsync(Guid.NewGuid())).Status!); // y la sesión abierta con el PIN viejo se cerró
        Assert.NotNull(await Entrar(s, "Quiroga Jose Omar", "9964"));                   // alta
        Assert.Null(await Entrar(s, "Canno Francisco", "2243"));                        // baja: ya no entra...
        using (var scope = s.Services.CreateScope())
        {
            var db = Db(scope);
            Assert.False(db.Empleados.Single(e => e.Nombre == "Canno Francisco").Activo);  // ...pero no se borró
            Assert.Equal("Oficina", db.Empleados.Single(e => e.Nombre == "Acosta Marcelo").Area);
            Assert.Equal(300, db.CargasHoras.Single().Minutos);                               // su historial sigue ahí
            var emp = new ApiClient(s.CreateClient(), s.Time);
            Assert.DoesNotContain((await emp.EmpleadosAsync()).Valor!, e => e.Nombre == "Canno Francisco");   // el panel ya no lo ofrece
            Assert.Contains((await emp.EmpleadosAsync()).Valor!, e => e.Nombre == "Quiroga Jose Omar" && e.Area == "Taller");
            var texto = db.Auditorias.AsEnumerable().Last(a => a.Campo == "empleados_excel").ValorNuevo!;
            Assert.Contains("Altas: Quiroga Jose Omar", texto);
            Assert.Contains("Bajas (desactivados): Canno Francisco", texto);
            Assert.DoesNotContain("1111", texto);
        }

        // Vuelve a figurar en el Excel: se reactiva.
        CrearExcel(ruta, ("Ahuad Juan Pablo", "1111", "Oficina"), ("Acosta Marcelo", "5439", "Oficina"), ("Quiroga Jose Omar", "9964", "Taller"), ("Canno Francisco", "2243", "Oficina"));
        await Sincronizar(s);
        Assert.NotNull(await Entrar(s, "Canno Francisco", "2243"));
    }

    // ---------------------------------------------------------------- protecciones

    [Fact]
    public async Task Si_el_Excel_no_esta_o_esta_vacio_o_esta_en_uso_no_se_pierde_nada()
    {
        var ruta = RutaNueva();
        CrearExcel(ruta, ("Ahuad Juan Pablo", "2914", "Oficina"), ("Acosta Marcelo", "5439", "Taller"));
        await using var s = new ServerFixture(Inicio, ruta);
        Assert.True((await Sincronizar(s)).Ok);

        // Un Excel sin empleados válidos (vacío o con otra estructura) no borra a nadie.
        CrearExcel(ruta);
        var vacio = await Sincronizar(s);
        Assert.False(vacio.Ok);
        Assert.Contains("ningún empleado", vacio.Mensaje);
        Assert.NotNull(await Entrar(s, "Ahuad Juan Pablo", "2914"));

        using (var wb = new XLWorkbook()) { wb.AddWorksheet("X").Cell(1, 1).Value = "otra cosa"; wb.SaveAs(ruta); }
        var sinColumnas = await Sincronizar(s);
        Assert.False(sinColumnas.Ok);
        Assert.Contains("columnas", sinColumnas.Mensaje);

        // Un archivo que no es Excel.
        await File.WriteAllTextAsync(ruta, "esto no es un xlsx");
        var roto = await Sincronizar(s);
        Assert.False(roto.Ok);
        Assert.Contains("válido", roto.Mensaje);

        // El archivo no existe.
        File.Delete(ruta);
        var falta = await Sincronizar(s);
        Assert.False(falta.Ok);
        Assert.Contains("No se encontró", falta.Mensaje);
        Assert.NotNull(await Entrar(s, "Acosta Marcelo", "5439")); // todo sigue funcionando

        // El archivo está abierto/guardándose (bloqueado): se reintenta y después sincroniza.
        CrearExcel(ruta, ("Ahuad Juan Pablo", "2914", "Oficina"), ("Acosta Marcelo", "5439", "Taller"), ("Canno Francisco", "2243", "Oficina"));
        using (new FileStream(ruta, FileMode.Open, FileAccess.ReadWrite, FileShare.None))
        {
            var bloqueado = await Sincronizar(s);
            Assert.False(bloqueado.Ok);
            Assert.Contains("guardado", bloqueado.Mensaje);
        }
        var listo = await Sincronizar(s);
        Assert.True(listo.Ok, listo.Mensaje);
        Assert.NotNull(await Entrar(s, "Canno Francisco", "2243"));
    }

    [Fact]
    public async Task Una_fila_con_errores_se_avisa_y_se_saltea_sin_dar_de_baja_a_esa_persona()
    {
        var ruta = RutaNueva();
        CrearExcel(ruta, ("Ahuad Juan Pablo", "2914", "Oficina"), ("Acosta Marcelo", "5439", "Taller"));
        await using var s = new ServerFixture(Inicio, ruta);
        Assert.True((await Sincronizar(s)).Ok);

        CrearExcel(ruta,
            ("Ahuad Juan Pablo", "29", "Oficina"),                  // PIN de 2 números: se conserva el anterior
            ("Acosta Marcelo", "5439", "Cocina"),                   // área inválida
            ("Canno Francisco", "abcd", "Oficina"),                 // PIN inválido y es nuevo: no se crea
            ("Quiroga Jose Omar", "9964", "Taller"),                // esta fila está bien
            ("Quiroga Jose Omar", "1234", "Taller"));               // repetido
        var r = await Sincronizar(s);
        Assert.True(r.Ok);
        Assert.Equal(4, r.Errores.Count);
        Assert.All(r.Errores, e => Assert.True(e.Fila >= 2));
        Assert.Contains(r.Errores, e => e.Mensaje.Contains("Cocina"));
        Assert.Contains(r.Errores, e => e.Mensaje.Contains("más de una vez"));

        Assert.NotNull(await Entrar(s, "Ahuad Juan Pablo", "2914"));     // conserva su PIN y sigue activo
        Assert.NotNull(await Entrar(s, "Acosta Marcelo", "5439"));       // el área inválida no lo dio de baja
        Assert.Null(await Entrar(s, "Canno Francisco", "abcd"));
        Assert.NotNull(await Entrar(s, "Quiroga Jose Omar", "9964"));    // la fila válida entró (la repetida se ignoró)
    }

    // ---------------------------------------------------------------- la app no edita empleados cuando manda el Excel

    [Fact]
    public async Task Cuando_manda_el_Excel_la_app_no_deja_editar_empleados_ni_cambiar_el_PIN_y_muestra_el_estado()
    {
        var ruta = RutaNueva();
        CrearExcel(ruta, ("Ahuad Juan Pablo", "2914", "Oficina"), ("Garcia Gabriel Gines", "12345678", "Administrador"));
        await using var s = new ServerFixture(Inicio, ruta);
        s.CrearAdmin("adm-xl", "clave-segura-1");
        var api = new AdminApi(new ApiClient(s.CreateClient(), s.Time));
        api.Token = (await api.LoginAsync("adm-xl", "clave-segura-1")).Valor!.Token;

        var antes = (await api.EmpleadosExcelAsync()).Valor!;
        Assert.True(antes.Configurado);
        Assert.Equal(ruta, antes.Archivo);

        var ahora = (await api.SincronizarEmpleadosExcelAsync()).Valor!;   // «Sincronizar ahora»
        Assert.True(ahora.Ok, ahora.Mensaje);
        Assert.Equal(1, ahora.Empleados);

        var id = (await api.EmpleadosAsync()).Valor!.Single().Id;
        Assert.Equal("gestionado_por_excel", (await api.CrearEmpleadoAsync("Nuevo", "Oficina")).Codigo);
        Assert.Equal("gestionado_por_excel", (await api.ActualizarEmpleadoAsync(id, nombre: "Otro nombre")).Codigo);
        Assert.Equal("gestionado_por_excel", (await api.ActualizarEmpleadoAsync(id, activo: false)).Codigo);
        Assert.Equal("gestionado_por_excel", (await api.ResetearPinAsync(id)).Codigo);
        Assert.Equal(409, (int)(await (await Entrar(s, "Ahuad Juan Pablo", "2914"))!.CambiarPinAsync("2914", "4321")).Status!);
        Assert.NotNull(await Entrar(s, "Ahuad Juan Pablo", "2914"));         // sigue con el del Excel

        // Ver y exportar los PIN sigue funcionando.
        Assert.Equal("2914", (await api.PinesAsync()).Valor!.Single().Pin);
        // La constancia del sistema figura con el nombre «Sistema».
        Assert.Contains((await api.AuditoriaAsync()).Valor!, a => a.Campo == "empleados_excel" && a.Administrador == "Sistema");
    }

    [Fact]
    public async Task Sin_Excel_configurado_todo_funciona_como_antes()
    {
        await using var s = new ServerFixture(Inicio);
        s.CrearAdmin("adm-sx", "clave-segura-1");
        var api = new AdminApi(new ApiClient(s.CreateClient(), s.Time));
        api.Token = (await api.LoginAsync("adm-sx", "clave-segura-1")).Valor!.Token;
        Assert.False((await api.EmpleadosExcelAsync()).Valor!.Configurado);
        Assert.True((await api.CrearEmpleadoAsync("Sin Excel", "Oficina")).Ok);
        Assert.False((await api.SincronizarEmpleadosExcelAsync()).Valor!.Configurado);
    }

    [Theory]
    [InlineData("Garcia Gabriel Gines", "Gabriel")]
    [InlineData("Ruggeri Gonzalo Mauro", "Gonzalo")]
    [InlineData("Vera Diego Ricardo", "Diego")]
    [InlineData("  vera   diego ", "Diego")]
    [InlineData("Soledad", "Soledad")]
    public void El_usuario_del_administrador_es_su_nombre_de_pila(string nombre, string usuario) =>
        Assert.Equal(usuario, EmpleadosExcelService.UsuarioDe(nombre));
}
