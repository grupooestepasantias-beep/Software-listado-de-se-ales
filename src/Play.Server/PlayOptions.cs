namespace Play.Server;

public class PlayOptions
{
    /// <summary>Carpeta de datos (base, Excel, accesos iniciales). No debe llamarse «data»: en Windows chocaría con la carpeta de código «Data».</summary>
    public string DataDir { get; set; } = "datos";
    /// <summary>Cada cuántos segundos el panel avisa que sigue vivo.</summary>
    public int HeartbeatSeconds { get; set; } = 30;
    /// <summary>Sin latidos durante este tiempo, el servidor cierra el registro como «cortado».</summary>
    public int CutoffSeconds { get; set; } = 180;
    /// <summary>Minutos sin mouse/teclado para que el panel avise «¿seguís ahí?» (2 horas, definido el 2026-11-19).</summary>
    public int InactivityMinutes { get; set; } = 120;
    /// <summary>Cada cuántos minutos el servidor regenera el Excel automático.</summary>
    public int ExcelMinutes { get; set; } = 5;
    /// <summary>Un registro abierto por más horas que esto se marca para revisión.</summary>
    public int MaxRecordHours { get; set; } = 12;
    public int MaxPinAttempts { get; set; } = 5;
    public int LockoutMinutes { get; set; } = 5;
    public int SessionHours { get; set; } = 24;
    /// <summary>Antigüedad máxima aceptada para registros sincronizados desde el modo sin conexión.</summary>
    public int MaxOfflineDays { get; set; } = 14;
    /// <summary>Hora local (0-23) a partir de la cual se hace el backup diario. Si el servidor estaba apagado, se hace al encenderse.</summary>
    public int BackupHour { get; set; } = 2;
    /// <summary>Días que se conservan los backups.</summary>
    public int BackupRetentionDays { get; set; } = 30;
    /// <summary>Carpeta de backups. Vacío = «backups» dentro de la carpeta de datos. Conviene otro disco o una carpeta de red.</summary>
    public string BackupDir { get; set; } = "";
    public string TimeZone { get; set; } = "America/Argentina/Buenos_Aires";
    /// <summary>
    /// Ruta del Excel de empleados (columnas Empleado, Contraseña y Área). Si está definida, ese Excel es la base de datos de
    /// empleados: la app se sincroniza sola cuando cambia y los empleados ya no se editan desde la app. Vacío = como antes.
    /// </summary>
    public string EmpleadosExcel { get; set; } = "";
    /// <summary>Cada cuántos segundos el servidor mira si el Excel de empleados cambió.</summary>
    public int EmpleadosExcelSegundos { get; set; } = 10;
    public SeedOptions Seed { get; set; } = new();
}

public class SeedOptions
{
    public List<string> Empleados { get; set; } = [];
    public List<string> Obras { get; set; } = [];
    public string AdminUsuario { get; set; } = "";
}
