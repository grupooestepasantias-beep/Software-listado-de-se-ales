using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage.ValueConversion;

namespace Play.Server.Data;

public class PlayDb(DbContextOptions<PlayDb> options) : DbContext(options)
{
    public DbSet<Empleado> Empleados => Set<Empleado>();
    public DbSet<Obra> Obras => Set<Obra>();
    public DbSet<Subtarea> Subtareas => Set<Subtarea>();
    public DbSet<AvisoSubtarea> AvisosSubtarea => Set<AvisoSubtarea>();
    public DbSet<CargaHoras> CargasHoras => Set<CargaHoras>();
    public DbSet<Falta> Faltas => Set<Falta>();
    public DbSet<Ajuste> Ajustes => Set<Ajuste>();
    public DbSet<Administrador> Administradores => Set<Administrador>();
    public DbSet<RegistroTiempo> Registros => Set<RegistroTiempo>();
    public DbSet<Auditoria> Auditorias => Set<Auditoria>();
    public DbSet<Sesion> Sesiones => Set<Sesion>();

    protected override void ConfigureConventions(ModelConfigurationBuilder b)
    {
        // Todas las fechas se guardan y leen como UTC.
        b.Properties<DateTime>().HaveConversion<UtcConverter>();
        b.Properties<DateTime?>().HaveConversion<NullableUtcConverter>();
    }

    protected override void OnModelCreating(ModelBuilder m)
    {
        m.Entity<Empleado>().HasIndex(e => e.Nombre).IsUnique();
        m.Entity<Obra>().HasIndex(o => o.Nombre).IsUnique();
        m.Entity<Subtarea>().HasIndex(s => new { s.ObraId, s.Nombre }).IsUnique();
        m.Entity<Falta>().HasOne(f => f.Empleado).WithMany().HasForeignKey(f => f.EmpleadoId).OnDelete(DeleteBehavior.Restrict);
        m.Entity<Falta>().HasIndex(f => new { f.EmpleadoId, f.Fecha }).IsUnique(); // una sola falta por empleado y día: no hay alertas duplicadas
        m.Entity<Ajuste>().HasKey(a => a.Clave);
        m.Entity<CargaHoras>().HasOne(c => c.Empleado).WithMany().HasForeignKey(c => c.EmpleadoId).OnDelete(DeleteBehavior.Restrict);
        m.Entity<CargaHoras>().HasIndex(c => c.Fecha);
        // Un día puede tener varias líneas (una por obra y subtarea); que no se repita la misma línea lo controla HorasService.
        m.Entity<CargaHoras>().HasIndex(c => new { c.EmpleadoId, c.Fecha }).HasDatabaseName("IX_CargasHoras_EmpleadoId_Fecha");
        m.Entity<CargaHoras>().HasOne(c => c.Obra).WithMany().HasForeignKey(c => c.ObraId).OnDelete(DeleteBehavior.Restrict);
        m.Entity<CargaHoras>().HasOne(c => c.Subtarea).WithMany().HasForeignKey(c => c.SubtareaId).OnDelete(DeleteBehavior.Restrict);
        m.Entity<AvisoSubtarea>().HasIndex(a => new { a.Estado, a.CreadoUtc });
        m.Entity<AvisoSubtarea>().HasOne(a => a.Subtarea).WithMany().HasForeignKey(a => a.SubtareaId).OnDelete(DeleteBehavior.Cascade);
        m.Entity<AvisoSubtarea>().HasOne(a => a.Empleado).WithMany().HasForeignKey(a => a.EmpleadoId).OnDelete(DeleteBehavior.Restrict);
        m.Entity<RegistroTiempo>().HasOne(r => r.Subtarea).WithMany().HasForeignKey(r => r.SubtareaId).OnDelete(DeleteBehavior.Restrict);
        m.Entity<Administrador>().HasIndex(a => a.Usuario).IsUnique();
        m.Entity<Sesion>().HasKey(s => s.Token);

        var r = m.Entity<RegistroTiempo>();
        r.HasIndex(x => new { x.EmpleadoId, x.InicioUtc });
        // Regla central: un solo registro abierto (Estado = 0) por empleado.
        r.HasIndex(x => x.EmpleadoId).IsUnique().HasFilter("\"Estado\" = 0").HasDatabaseName("UX_Registro_UnAbiertoPorEmpleado");
    }

    private sealed class UtcConverter() : ValueConverter<DateTime, DateTime>(
        v => v.ToUniversalTime(), v => DateTime.SpecifyKind(v, DateTimeKind.Utc));

    private sealed class NullableUtcConverter() : ValueConverter<DateTime?, DateTime?>(
        v => v.HasValue ? v.Value.ToUniversalTime() : v,
        v => v.HasValue ? DateTime.SpecifyKind(v.Value, DateTimeKind.Utc) : v);
}
