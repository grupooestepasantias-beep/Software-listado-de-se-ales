using System.Security.Cryptography;
using System.Text;
using Microsoft.EntityFrameworkCore;
using Play.Server.Data;

namespace Play.Server.Services;

/// <summary>Crea la base y la carga inicial (solo si está vacía). Los PIN y la clave temporal se escriben una vez en un archivo.</summary>
public static class Seeder
{
    public static async Task InicializarAsync(PlayDb db, PlayOptions o, string dataDir)
    {
        await db.Database.EnsureCreatedAsync();
        await Esquema.ActualizarAsync(db, dataDir); // bases creadas por versiones anteriores
        await db.Database.ExecuteSqlRawAsync("PRAGMA journal_mode=WAL;");

        if (await db.Empleados.AnyAsync() || await db.Obras.AnyAsync() || await db.Administradores.AnyAsync()) return;

        var sb = new StringBuilder();
        sb.AppendLine("DATOS INICIALES DE ACCESO - entregar a cada persona y borrar este archivo.");
        sb.AppendLine("Cada empleado debe cambiar su PIN en el primer uso.");
        sb.AppendLine();

        foreach (var nombre in o.Seed.Empleados.Select(n => n.Trim()).Where(n => n.Length > 0).Distinct(StringComparer.OrdinalIgnoreCase))
        {
            var pin = PinHasher.NuevoPin();
            db.Empleados.Add(new Empleado { Nombre = nombre, PinHash = PinHasher.Hash(pin), PinVisible = pin, DebeCambiarPin = true });
            sb.AppendLine($"Empleado: {nombre} | PIN inicial: {pin}");
        }

        foreach (var obra in o.Seed.Obras.Select(n => n.Trim()).Where(n => n.Length > 0).Distinct(StringComparer.OrdinalIgnoreCase))
            db.Obras.Add(new Obra { Nombre = obra });

        if (!string.IsNullOrWhiteSpace(o.Seed.AdminUsuario))
        {
            var pass = PinHasher.NuevaClaveTemporal();
            db.Administradores.Add(new Administrador
            {
                Usuario = o.Seed.AdminUsuario.Trim(), NombreCompleto = o.Seed.AdminUsuario.Trim(),
                PassHash = PinHasher.Hash(pass), DebeCambiarPass = true,
            });
            sb.AppendLine();
            sb.AppendLine($"Administrador: {o.Seed.AdminUsuario.Trim()} | Clave temporal: {pass} (debe cambiarla al ingresar)");
        }

        await db.SaveChangesAsync();
        await File.WriteAllTextAsync(Path.Combine(dataDir, "accesos_iniciales.txt"), sb.ToString());
    }
}
