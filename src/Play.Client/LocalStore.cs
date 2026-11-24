using System.Text.Json;

namespace Play.Client;

/// <summary>Registro que el servidor puede no conocer o tener desactualizado (hecho sin conexión). Nunca se descarta sin confirmar.</summary>
public sealed class PendienteLocal
{
    public Guid Id { get; set; }
    public int EmpleadoId { get; set; }
    public int ObraId { get; set; }
    public int? SubtareaId { get; set; }
    public DateTime InicioUtc { get; set; }
    public DateTime? FinUtc { get; set; }
    public string Equipo { get; set; } = "";
}

public sealed class AjustesPanel
{
    public string? ServidorUrl { get; set; }
    public int? EmpleadoIdUltimo { get; set; }
    public int? ObraIdUltima { get; set; }
    /// <summary>Última subtarea elegida (se preselecciona si se vuelve a elegir la misma obra).</summary>
    public int? SubtareaIdUltima { get; set; }
    /// <summary>Última área elegida en el panel («Oficina» o «Taller»).</summary>
    public string? AreaUltima { get; set; }
    public double? X { get; set; }
    public double? Y { get; set; }
    public bool Contraida { get; set; }
    public bool PrimeraEjecucionHecha { get; set; }
    /// <summary>Última versión del panel que no arrancó bien al actualizar: no se vuelve a intentar con ella.</summary>
    public string? VersionRechazada { get; set; }
}

/// <summary>Archivos JSON en %AppData%\Play: ajustes de la ventana y cola de registros pendientes de enviar.</summary>
public sealed class LocalStore
{
    private static readonly JsonSerializerOptions Opciones = new(JsonSerializerDefaults.Web) { WriteIndented = true };
    private readonly string _dir;
    private readonly List<PendienteLocal> _pendientes;

    public AjustesPanel Ajustes { get; private set; }

    public string Carpeta => _dir;

    public LocalStore(string carpeta)
    {
        _dir = carpeta;
        Directory.CreateDirectory(_dir);
        Ajustes = Leer<AjustesPanel>("ajustes.json") ?? new AjustesPanel();
        _pendientes = Leer<List<PendienteLocal>>("pendientes.json") ?? [];
    }

    private T? Leer<T>(string archivo)
    {
        var ruta = Path.Combine(_dir, archivo);
        if (!File.Exists(ruta)) return default;
        try { return JsonSerializer.Deserialize<T>(File.ReadAllText(ruta), Opciones); }
        catch (Exception ex) when (ex is JsonException or IOException)
        {
            // Archivo dañado: se conserva una copia para no perder datos y se arranca limpio.
            try { File.Move(ruta, ruta + ".dañado-" + DateTime.Now.ToString("yyyyMMddHHmmss")); } catch (IOException) { }
            return default;
        }
    }

    private void Escribir<T>(string archivo, T valor)
    {
        var ruta = Path.Combine(_dir, archivo);
        var tmp = ruta + ".tmp";
        File.WriteAllText(tmp, JsonSerializer.Serialize(valor, Opciones));
        File.Move(tmp, ruta, overwrite: true);
    }

    public void GuardarAjustes() => Escribir("ajustes.json", Ajustes);

    // ---- Cola de pendientes ----
    public IReadOnlyList<PendienteLocal> Pendientes => _pendientes;
    public IEnumerable<PendienteLocal> PendientesDe(int empleadoId) => _pendientes.Where(p => p.EmpleadoId == empleadoId).ToList();
    public PendienteLocal? Pendiente(Guid id) => _pendientes.FirstOrDefault(p => p.Id == id);

    public void Guardar(PendienteLocal p)
    {
        var i = _pendientes.FindIndex(x => x.Id == p.Id);
        if (i >= 0) _pendientes[i] = p; else _pendientes.Add(p);
        Escribir("pendientes.json", _pendientes);
    }

    public void Persistir() => Escribir("pendientes.json", _pendientes);

    public void Quitar(Guid id)
    {
        _pendientes.RemoveAll(p => p.Id == id);
        Escribir("pendientes.json", _pendientes);
    }

    /// <summary>Registros que el servidor rechazó como inválidos: se archivan aquí para que alguien los revise.</summary>
    public void Rechazar(PendienteLocal p)
    {
        var rechazados = Leer<List<PendienteLocal>>("rechazados.json") ?? [];
        rechazados.Add(p);
        Escribir("rechazados.json", rechazados);
        Quitar(p.Id);
    }
}
