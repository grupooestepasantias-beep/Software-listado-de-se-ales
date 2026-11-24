namespace Play.Server.Services;

/// <summary>Zona horaria de la empresa (los datos se guardan en UTC; los días y reportes se calculan en hora local).</summary>
public static class Zona
{
    public static TimeZoneInfo De(PlayOptions o)
    {
        foreach (var id in new[] { o.TimeZone, "Argentina Standard Time" })
        {
            try { return TimeZoneInfo.FindSystemTimeZoneById(id); } catch (Exception ex) when (ex is TimeZoneNotFoundException or InvalidTimeZoneException) { }
        }
        // Equipos sin base de zonas horarias (por ejemplo algunos NAS): Argentina no usa horario de verano, así que alcanza con UTC-3 fijo.
        // Si no es Argentina, se usa la hora del equipo.
        return (o.TimeZone ?? "").Contains("Argentina", StringComparison.OrdinalIgnoreCase) || (o.TimeZone ?? "").Contains("Buenos_Aires", StringComparison.OrdinalIgnoreCase)
            ? TimeZoneInfo.CreateCustomTimeZone("ART", TimeSpan.FromHours(-3), "Argentina (UTC-3)", "Argentina (UTC-3)")
            : TimeZoneInfo.Local;
    }

    public static DateTime MedianocheLocalAUtc(TimeZoneInfo z, DateOnly dia) =>
        TimeZoneInfo.ConvertTimeToUtc(dia.ToDateTime(TimeOnly.MinValue, DateTimeKind.Unspecified), z);

    /// <summary>Rango UTC [desde, hasta) que cubre los días locales desde..hasta, ambos inclusive.</summary>
    public static (DateTime? DesdeUtc, DateTime? HastaUtc) RangoUtc(TimeZoneInfo z, DateOnly? desde, DateOnly? hasta) =>
        (desde is { } d ? MedianocheLocalAUtc(z, d) : null, hasta is { } h ? MedianocheLocalAUtc(z, h.AddDays(1)) : null);
}
