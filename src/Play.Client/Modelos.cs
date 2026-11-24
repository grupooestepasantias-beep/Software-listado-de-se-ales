using System.Net;
using System.Text.Json;

namespace Play.Client;

/// <param name="Area">Solo en la lista de empleados: «Oficina» o «Taller». Null si el servidor es anterior a las áreas.</param>
public record ItemLista(int Id, string Nombre, string? Area = null);

/// <summary>Las dos áreas de la empresa.</summary>
public static class AreasEmpresa
{
    public const string Oficina = "Oficina";
    public const string Taller = "Taller";
    public static readonly string[] Todas = [Oficina, Taller];

    /// <summary>Un empleado sin área (servidor viejo) cuenta como Oficina.</summary>
    public static string De(ItemLista empleado) => empleado.Area ?? Oficina;
}
public record ConfigServidor(int LatidoSegundos, int InactividadMinutos);

/// <summary>Obra tal como la devuelve <c>GET /api/obras</c>: con sus subtareas activas (si tiene alguna, hay que elegir una).</summary>
/// <summary>Una línea de horas de Taller (un día, una obra y una subtarea; sin obra = trabajo general de Taller). Origen: panel (la cargó el empleado) o admin (ya no la puede cambiar el empleado).</summary>
public record CargaDto(DateOnly Fecha, int Minutos, string Origen, int? ObraId = null, int? SubtareaId = null, string? Obra = null, string? Subtarea = null);
/// <param name="Hoy">Fecha de hoy según el servidor (el empleado solo puede cargar hoy y ayer).</param>
public record MisHorasDto(DateOnly Hoy, List<CargaDto> Cargas);

public record ObraPublica(int Id, string Nombre, List<ItemLista>? Subtareas = null);

public record RegistroDto(Guid Id, int EmpleadoId, int ObraId, DateTime InicioUtc, DateTime? FinUtc,
    DateTime UltimoLatidoUtc, string Estado, string Equipo, string Origen, bool RevisarAdmin, int? SubtareaId = null);

public record LoginResponse(string Token, int EmpleadoId, string Nombre, bool DebeCambiarPin, RegistroDto? RegistroActivo);

public record SincronizarItem(Guid Id, int ObraId, DateTime InicioUtc, DateTime? FinUtc, string? Equipo, int? SubtareaId = null);
public record SincronizarResultado(Guid Id, string Resultado);

public record ObraSegundos(int ObraId, string Obra, long Segundos);
public record PeriodoResumen(long TotalSegundos, List<ObraSegundos> PorObra);
public record ResumenDto(PeriodoResumen Hoy, PeriodoResumen Semana);

/// <summary>Cuerpo vacío (respuestas 204).</summary>
public record Vacio;

/// <summary>
/// Resultado de una llamada: o hubo respuesta del servidor (Status) o no hubo red (SinRed: sin conexión, tiempo agotado).
/// </summary>
public record ApiResult<T>(HttpStatusCode? Status, T? Valor, string? Codigo, bool SinRed, string? Texto = null)
{
    public bool Ok => !SinRed && Status is >= HttpStatusCode.OK and < HttpStatusCode.MultipleChoices;
    public static ApiResult<T> Red => new(null, default, null, true);

    /// <summary>Lee una propiedad del cuerpo JSON de la respuesta (p. ej. «equipo» en un 409).</summary>
    public JsonElement? Prop(string nombre)
    {
        if (string.IsNullOrEmpty(Texto)) return null;
        try
        {
            using var doc = JsonDocument.Parse(Texto);
            return doc.RootElement.TryGetProperty(nombre, out var p) ? p.Clone() : null;
        }
        catch (JsonException) { return null; }
    }
}
