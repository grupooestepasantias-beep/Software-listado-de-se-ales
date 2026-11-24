using System.Security.Cryptography;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Play.Server.Data;

namespace Play.Server.Services;

public record LoginResult(string Token, int EmpleadoId, string Nombre, bool DebeCambiarPin);

public class AuthService(PlayDb db, TimeProvider time, IOptions<PlayOptions> options)
{
    private readonly PlayOptions _o = options.Value;

    public static bool PinValido(string? pin) =>
        pin is { Length: 4 } && pin.All(char.IsAsciiDigit);

    /// <summary>Devuelve el resultado o el motivo del rechazo: invalido | bloqueado.</summary>
    public async Task<(LoginResult? Ok, string? Error, DateTime? BloqueadoHasta)> LoginEmpleadoAsync(int empleadoId, string pin)
    {
        var now = time.GetUtcNow().UtcDateTime;
        var emp = await db.Empleados.FindAsync(empleadoId);
        if (emp is null || !emp.Activo) return (null, "invalido", null);

        if (emp.BloqueadoHastaUtc is { } hasta && hasta > now)
            return (null, "bloqueado", hasta);

        if (!PinHasher.Verify(pin, emp.PinHash))
        {
            emp.IntentosFallidos++;
            if (emp.IntentosFallidos >= _o.MaxPinAttempts)
            {
                emp.BloqueadoHastaUtc = now.AddMinutes(_o.LockoutMinutes);
                emp.IntentosFallidos = 0;
            }
            await db.SaveChangesAsync();
            return (null, emp.BloqueadoHastaUtc > now ? "bloqueado" : "invalido", emp.BloqueadoHastaUtc);
        }

        emp.IntentosFallidos = 0;
        emp.BloqueadoHastaUtc = null;
        var token = Convert.ToBase64String(RandomNumberGenerator.GetBytes(32)).Replace('+', '-').Replace('/', '_').TrimEnd('=');
        db.Sesiones.Add(new Sesion { Token = token, Tipo = "empleado", UsuarioId = emp.Id, ExpiraUtc = now.AddHours(_o.SessionHours) });
        // Limpieza de sesiones vencidas.
        await db.Sesiones.Where(s => s.ExpiraUtc < now).ExecuteDeleteAsync();
        await db.SaveChangesAsync();
        return (new LoginResult(token, emp.Id, emp.Nombre, emp.DebeCambiarPin), null, null);
    }

    /// <summary>Id del empleado autenticado por el encabezado Authorization: Bearer, o null.</summary>
    public async Task<int?> EmpleadoDeSolicitudAsync(HttpRequest req)
    {
        var header = req.Headers.Authorization.ToString();
        if (!header.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase)) return null;
        var token = header[7..].Trim();
        var now = time.GetUtcNow().UtcDateTime;
        var s = await db.Sesiones.FindAsync(token);
        if (s is null || s.Tipo != "empleado" || s.ExpiraUtc < now) return null;

        var activo = await db.Empleados.AnyAsync(e => e.Id == s.UsuarioId && e.Activo);
        if (!activo) return null;

        // Renueva la sesión cuando queda menos de la mitad del tiempo (evita escribir en cada llamada).
        if (s.ExpiraUtc - now < TimeSpan.FromHours(_o.SessionHours / 2.0))
        {
            s.ExpiraUtc = now.AddHours(_o.SessionHours);
            await db.SaveChangesAsync();
        }
        return s.UsuarioId;
    }

    private string NuevoToken() =>
        Convert.ToBase64String(RandomNumberGenerator.GetBytes(32)).Replace('+', '-').Replace('/', '_').TrimEnd('=');

    public async Task<(string? Token, string? Error, bool DebeCambiar, DateTime? BloqueadoHasta)> LoginAdminAsync(string usuario, string password)
    {
        var now = time.GetUtcNow().UtcDateTime;
        var a = await db.Administradores.FirstOrDefaultAsync(x => x.Usuario.ToLower() == usuario.ToLower() && x.Activo);
        if (a is null) return (null, "invalido", false, null);
        if (a.BloqueadoHastaUtc is { } hasta && hasta > now) return (null, "bloqueado", false, hasta);

        if (!PinHasher.Verify(password, a.PassHash))
        {
            a.IntentosFallidos++;
            if (a.IntentosFallidos >= _o.MaxPinAttempts)
            {
                a.BloqueadoHastaUtc = now.AddMinutes(_o.LockoutMinutes);
                a.IntentosFallidos = 0;
            }
            await db.SaveChangesAsync();
            return (null, a.BloqueadoHastaUtc > now ? "bloqueado" : "invalido", false, a.BloqueadoHastaUtc);
        }

        a.IntentosFallidos = 0;
        a.BloqueadoHastaUtc = null;
        var token = NuevoToken();
        db.Sesiones.Add(new Sesion { Token = token, Tipo = "admin", UsuarioId = a.Id, ExpiraUtc = now.AddHours(_o.SessionHours) });
        await db.SaveChangesAsync();
        return (token, null, a.DebeCambiarPass, null);
    }

    /// <summary>Administrador autenticado por Bearer: su Id y si todavía debe cambiar la clave temporal.</summary>
    public async Task<(int Id, bool DebeCambiar)?> AdminDeSolicitudAsync(HttpRequest req)
    {
        var header = req.Headers.Authorization.ToString();
        if (!header.StartsWith("Bearer ", StringComparison.OrdinalIgnoreCase)) return null;
        var now = time.GetUtcNow().UtcDateTime;
        var s = await db.Sesiones.FindAsync(header[7..].Trim());
        if (s is null || s.Tipo != "admin" || s.ExpiraUtc < now) return null;
        var a = await db.Administradores.AsNoTracking().FirstOrDefaultAsync(x => x.Id == s.UsuarioId && x.Activo);
        return a is null ? null : (a.Id, a.DebeCambiarPass);
    }

    public async Task<bool> CambiarPassAdminAsync(int adminId, string actual, string nueva)
    {
        var a = await db.Administradores.FindAsync(adminId);
        if (a is null || nueva.Length < 8 || !PinHasher.Verify(actual, a.PassHash)) return false;
        a.PassHash = PinHasher.Hash(nueva);
        a.DebeCambiarPass = false;
        await db.SaveChangesAsync();
        return true;
    }

    public async Task<bool> CambiarPinAsync(int empleadoId, string pinActual, string pinNuevo)
    {
        var emp = await db.Empleados.FindAsync(empleadoId);
        if (emp is null || !PinHasher.Verify(pinActual, emp.PinHash) || !PinValido(pinNuevo)) return false;
        emp.PinHash = PinHasher.Hash(pinNuevo);
        emp.PinVisible = pinNuevo; // el administrador puede verlo
        emp.DebeCambiarPin = false;
        await db.SaveChangesAsync();
        return true;
    }
}
