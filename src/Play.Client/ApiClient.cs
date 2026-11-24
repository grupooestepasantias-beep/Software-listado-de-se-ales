using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text.Json;

namespace Play.Client;

/// <summary>Contrato de la API del servidor (permite probar el panel con una API simulada).</summary>
public interface IPlayApi
{
    string? Token { get; set; }
    /// <summary>Diferencia estimada servidor − reloj local (para estampar registros hechos sin conexión).</summary>
    TimeSpan Desfase { get; }
    Task<ApiResult<ConfigServidor>> ConfigAsync();
    Task<ApiResult<List<ItemLista>>> EmpleadosAsync();
    Task<ApiResult<List<ObraPublica>>> ObrasAsync();
    Task<ApiResult<LoginResponse>> LoginAsync(int empleadoId, string pin);
    Task<ApiResult<Vacio>> CambiarPinAsync(string pinActual, string pinNuevo);
    Task<ApiResult<RegistroDto>> IniciarAsync(Guid id, int obraId, int? subtareaId, string equipo);
    Task<ApiResult<RegistroDto>> CambiarObraAsync(Guid id, int obraId, int? subtareaId, string equipo);
    Task<ApiResult<RegistroDto>> LatidoAsync(Guid id);
    Task<ApiResult<RegistroDto>> CerrarAsync(Guid id, DateTime? finUtc);
    Task<ApiResult<List<SincronizarResultado>>> SincronizarAsync(List<SincronizarItem> items);
    Task<ApiResult<ResumenDto>> ResumenAsync();
    /// <summary>Avisa al administrador que el empleado terminó una subtarea (no la cierra: decide el administrador).</summary>
    Task<ApiResult<Vacio>> AvisarSubtareaAsync(int subtareaId);
    /// <summary>El empleado destilda la casilla: retira su aviso sin revisar.</summary>
    Task<ApiResult<Vacio>> RetirarAvisoAsync(int subtareaId);
    /// <summary>Ids de las subtareas que el empleado marcó como terminadas y esperan al administrador.</summary>
    Task<ApiResult<List<int>>> MisAvisosAsync();
    /// <summary>Horas de Taller: las cargas de los últimos días y la fecha de hoy del servidor (solo empleados de Taller).</summary>
    Task<ApiResult<MisHorasDto>> MisHorasAsync();
    /// <summary>Carga (o corrige) las horas de hoy o de ayer.</summary>
    Task<ApiResult<CargaDto>> CargarHorasAsync(DateOnly fecha, int minutos, int? obraId = null, int? subtareaId = null);
    /// <summary>Quita una línea de horas de hoy o de ayer (la de esa obra y subtarea).</summary>
    Task<ApiResult<Vacio>> RetirarHorasAsync(DateOnly fecha, int? obraId = null, int? subtareaId = null);
}

public sealed class ApiClient(HttpClient http, TimeProvider? time = null, TimeSpan? timeout = null) : IPlayApi
{
    private static readonly JsonSerializerOptions Json = new(JsonSerializerDefaults.Web);
    private readonly TimeSpan _timeout = timeout ?? TimeSpan.FromSeconds(8);

    public string? Token { get; set; }
    public TimeSpan Desfase { get; private set; }

    private Task<ApiResult<T>> EnviarAsync<T>(HttpMethod metodo, string url, object? cuerpo = null) => LlamarAsync<T>(metodo, url, cuerpo);

    /// <summary>Descarga un archivo binario (p. ej. el Excel de reportes) con un tiempo de espera más largo.</summary>
    public async Task<ApiResult<byte[]>> DescargarAsync(string url)
    {
        using var cts = new CancellationTokenSource(TimeSpan.FromSeconds(120));
        try
        {
            using var req = new HttpRequestMessage(HttpMethod.Get, url);
            if (Token is not null) req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", Token);
            using var resp = await http.SendAsync(req, cts.Token);
            var bytes = await resp.Content.ReadAsByteArrayAsync(cts.Token);
            if (resp.IsSuccessStatusCode) return new ApiResult<byte[]>(resp.StatusCode, bytes, null, false);
            string? codigo = null;
            try
            {
                using var doc = JsonDocument.Parse(bytes);
                if (doc.RootElement.TryGetProperty("codigo", out var c)) codigo = c.GetString();
            }
            catch (JsonException) { }
            return new ApiResult<byte[]>(resp.StatusCode, null, codigo, false);
        }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException)
        {
            return ApiResult<byte[]>.Red;
        }
    }

    /// <summary>Llamada genérica al servidor (la usan las demás clases cliente, como la de administración).</summary>
    public async Task<ApiResult<T>> LlamarAsync<T>(HttpMethod metodo, string url, object? cuerpo = null)
    {
        using var cts = new CancellationTokenSource(_timeout);
        try
        {
            using var req = new HttpRequestMessage(metodo, url);
            if (cuerpo is not null) req.Content = JsonContent.Create(cuerpo, options: Json);
            if (Token is not null) req.Headers.Authorization = new AuthenticationHeaderValue("Bearer", Token);

            using var resp = await http.SendAsync(req, cts.Token);
            if (resp.Headers.Date is { } fecha)
                Desfase = fecha.UtcDateTime - (time?.GetUtcNow() ?? DateTimeOffset.UtcNow).UtcDateTime;

            var texto = await resp.Content.ReadAsStringAsync(cts.Token);
            if (resp.IsSuccessStatusCode)
            {
                T? valor = default;
                if (typeof(T) == typeof(Vacio)) valor = (T)(object)new Vacio();
                else if (!string.IsNullOrWhiteSpace(texto)) valor = JsonSerializer.Deserialize<T>(texto, Json);
                return new ApiResult<T>(resp.StatusCode, valor, null, false, texto);
            }

            string? codigo = null;
            try
            {
                using var doc = JsonDocument.Parse(texto);
                if (doc.RootElement.TryGetProperty("codigo", out var c)) codigo = c.GetString();
            }
            catch (JsonException) { }
            return new ApiResult<T>(resp.StatusCode, default, codigo, false, texto);
        }
        catch (Exception ex) when (ex is HttpRequestException or OperationCanceledException or JsonException)
        {
            return ApiResult<T>.Red;
        }
    }

    public Task<ApiResult<ConfigServidor>> ConfigAsync() => EnviarAsync<ConfigServidor>(HttpMethod.Get, "api/config");
    public Task<ApiResult<List<ItemLista>>> EmpleadosAsync() => EnviarAsync<List<ItemLista>>(HttpMethod.Get, "api/empleados");
    public Task<ApiResult<List<ObraPublica>>> ObrasAsync() => EnviarAsync<List<ObraPublica>>(HttpMethod.Get, "api/obras");
    public Task<ApiResult<LoginResponse>> LoginAsync(int empleadoId, string pin) => EnviarAsync<LoginResponse>(HttpMethod.Post, "api/login", new { empleadoId, pin });
    public Task<ApiResult<Vacio>> CambiarPinAsync(string pinActual, string pinNuevo) => EnviarAsync<Vacio>(HttpMethod.Post, "api/pin", new { pinActual, pinNuevo });
    public Task<ApiResult<RegistroDto>> IniciarAsync(Guid id, int obraId, int? subtareaId, string equipo) => EnviarAsync<RegistroDto>(HttpMethod.Post, "api/registros", new { id, obraId, subtareaId, equipo });
    public Task<ApiResult<RegistroDto>> CambiarObraAsync(Guid id, int obraId, int? subtareaId, string equipo) => EnviarAsync<RegistroDto>(HttpMethod.Post, "api/registros/cambiar-obra", new { id, obraId, subtareaId, equipo });
    public Task<ApiResult<RegistroDto>> LatidoAsync(Guid id) => EnviarAsync<RegistroDto>(HttpMethod.Post, $"api/registros/{id}/latido");
    public Task<ApiResult<RegistroDto>> CerrarAsync(Guid id, DateTime? finUtc) => EnviarAsync<RegistroDto>(HttpMethod.Post, $"api/registros/{id}/cerrar", new { finUtc });
    public Task<ApiResult<List<SincronizarResultado>>> SincronizarAsync(List<SincronizarItem> items) => EnviarAsync<List<SincronizarResultado>>(HttpMethod.Post, "api/registros/sincronizar", new { registros = items });
    public Task<ApiResult<ResumenDto>> ResumenAsync() => EnviarAsync<ResumenDto>(HttpMethod.Get, "api/resumen");
    public Task<ApiResult<Vacio>> AvisarSubtareaAsync(int subtareaId) => EnviarAsync<Vacio>(HttpMethod.Post, $"api/subtareas/{subtareaId}/avisar");
    public Task<ApiResult<Vacio>> RetirarAvisoAsync(int subtareaId) => EnviarAsync<Vacio>(HttpMethod.Delete, $"api/subtareas/{subtareaId}/avisar");
    public Task<ApiResult<List<int>>> MisAvisosAsync() => EnviarAsync<List<int>>(HttpMethod.Get, "api/mis-avisos");
    public Task<ApiResult<MisHorasDto>> MisHorasAsync() => EnviarAsync<MisHorasDto>(HttpMethod.Get, "api/horas");
    public Task<ApiResult<CargaDto>> CargarHorasAsync(DateOnly fecha, int minutos, int? obraId = null, int? subtareaId = null) =>
        EnviarAsync<CargaDto>(HttpMethod.Post, "api/horas", new { fecha, minutos, obraId, subtareaId });
    public Task<ApiResult<Vacio>> RetirarHorasAsync(DateOnly fecha, int? obraId = null, int? subtareaId = null) =>
        EnviarAsync<Vacio>(HttpMethod.Delete, $"api/horas?fecha={fecha:yyyy-MM-dd}" + (obraId is { } o ? $"&obraId={o}" : "") + (subtareaId is { } s ? $"&subtareaId={s}" : ""));
}
