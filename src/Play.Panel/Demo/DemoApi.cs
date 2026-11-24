using System.Net;
using Play.Client;

namespace Play.Panel.Demo;

/// <summary>Reloj que solo avanza cuando se le indica (para las capturas de ejemplo).</summary>
internal sealed class RelojManual(DateTimeOffset inicio) : TimeProvider
{
    private DateTimeOffset _ahora = inicio;
    public override DateTimeOffset GetUtcNow() => _ahora;
    public void Avanzar(TimeSpan t) => _ahora += t;
}

/// <summary>API de mentira con datos de ejemplo: sirve para ver la interfaz sin servidor.</summary>
internal sealed class DemoApi(RelojManual reloj) : IPlayApi
{
    public string? Token { get; set; }
    public TimeSpan Desfase => TimeSpan.Zero;
    public bool Caida { get; set; }

    private static readonly List<ItemLista> Empleados =
    [
        new(1, "pepe", "Oficina"), new(2, "Ramiro Bianchini", "Oficina"), new(3, "Ezequiel", "Oficina"),
        new(4, "Marcos Díaz", "Taller"), new(5, "Lucas Pérez", "Taller"),
    ];
    // Senillosa tiene subtareas (hay que elegir una); Ape no.
    private static readonly List<ObraPublica> Obras =
    [
        new(1, "Senillosa", [new(10, "Fundación"), new(11, "Estructura"), new(12, "Terminaciones")]),
        new(2, "Ape"),
    ];

    private static ApiResult<T> Ok<T>(T valor) => new(HttpStatusCode.OK, valor, null, false);
    private ApiResult<T> R<T>(Func<ApiResult<T>> f) => Caida ? ApiResult<T>.Red : f();
    private RegistroDto Reg(Guid id, int obra) => new(id, 1, obra, reloj.GetUtcNow().UtcDateTime, null, reloj.GetUtcNow().UtcDateTime, "abierto", "PC-DEMO", "panel", false);

    public Task<ApiResult<ConfigServidor>> ConfigAsync() => Task.FromResult(R(() => Ok(new ConfigServidor(30, 120))));
    public Task<ApiResult<List<ItemLista>>> EmpleadosAsync() => Task.FromResult(R(() => Ok(Empleados)));
    public Task<ApiResult<List<ObraPublica>>> ObrasAsync() => Task.FromResult(R(() => Ok(Obras)));
    public Task<ApiResult<LoginResponse>> LoginAsync(int empleadoId, string pin) => Task.FromResult(R(() =>
        pin == "1234"
            ? Ok(new LoginResponse("demo", empleadoId, Empleados.First(e => e.Id == empleadoId).Nombre, DebeCambiarPin: empleadoId == 3, null))
            : new ApiResult<LoginResponse>(HttpStatusCode.Unauthorized, null, "invalido", false)));
    public Task<ApiResult<Vacio>> CambiarPinAsync(string a, string n) => Task.FromResult(R(() => Ok(new Vacio())));
    public Task<ApiResult<RegistroDto>> IniciarAsync(Guid id, int obraId, int? subtareaId, string equipo) => Task.FromResult(R(() => Ok(Reg(id, obraId) with { SubtareaId = subtareaId })));
    public Task<ApiResult<RegistroDto>> CambiarObraAsync(Guid id, int obraId, int? subtareaId, string equipo) => Task.FromResult(R(() => Ok(Reg(id, obraId) with { SubtareaId = subtareaId })));
    public Task<ApiResult<RegistroDto>> LatidoAsync(Guid id) => Task.FromResult(R(() => Ok(Reg(id, 1))));
    public Task<ApiResult<RegistroDto>> CerrarAsync(Guid id, DateTime? f) => Task.FromResult(R(() => Ok(Reg(id, 1) with { Estado = "cerrado", FinUtc = f })));
    public Task<ApiResult<List<SincronizarResultado>>> SincronizarAsync(List<SincronizarItem> i) =>
        Task.FromResult(R(() => Ok(i.Select(x => new SincronizarResultado(x.Id, "insertado")).ToList())));
    public Task<ApiResult<ResumenDto>> ResumenAsync() => Task.FromResult(R(() => Ok(new ResumenDto(
        new PeriodoResumen(3 * 3600 + 20 * 60, [new(1, "Senillosa", 2 * 3600), new(2, "Ape", 1 * 3600 + 20 * 60)]),
        new PeriodoResumen(14 * 3600 + 5 * 60, [new(1, "Senillosa", 9 * 3600), new(2, "Ape", 5 * 3600 + 5 * 60)])))));
    public Task<ApiResult<Vacio>> AvisarSubtareaAsync(int subtareaId) => Task.FromResult(R(() => Ok(new Vacio())));
    public Task<ApiResult<Vacio>> RetirarAvisoAsync(int subtareaId) => Task.FromResult(R(() => Ok(new Vacio())));
    public Task<ApiResult<List<int>>> MisAvisosAsync() => Task.FromResult(R(() => Ok(new List<int>())));
    private readonly List<CargaDto> _cargas = [new(new DateOnly(2026, 11, 18), 8 * 60, "panel"), new(new DateOnly(2026, 11, 17), 7 * 60 + 30, "panel"), new(new DateOnly(2026, 11, 16), 8 * 60, "admin")];
    public Task<ApiResult<MisHorasDto>> MisHorasAsync() => Task.FromResult(R(() => Ok(new MisHorasDto(new DateOnly(2026, 11, 18), _cargas.ToList()))));
    public Task<ApiResult<CargaDto>> CargarHorasAsync(DateOnly fecha, int minutos, int? obraId = null, int? subtareaId = null)
    {
        _cargas.RemoveAll(c => c.Fecha == fecha && c.ObraId == obraId && c.SubtareaId == subtareaId);
        var obra = Obras.FirstOrDefault(o => o.Id == obraId)?.Nombre;
        var sub = Obras.FirstOrDefault(o => o.Id == obraId)?.Subtareas?.FirstOrDefault(s => s.Id == subtareaId)?.Nombre;
        _cargas.Insert(0, new CargaDto(fecha, minutos, "panel", obraId, subtareaId, obra, sub));
        return Task.FromResult(R(() => Ok(_cargas[0])));
    }
    public Task<ApiResult<Vacio>> RetirarHorasAsync(DateOnly fecha, int? obraId = null, int? subtareaId = null)
    {
        _cargas.RemoveAll(c => c.Fecha == fecha && c.ObraId == obraId && c.SubtareaId == subtareaId);
        return Task.FromResult(R(() => Ok(new Vacio())));
    }
}
