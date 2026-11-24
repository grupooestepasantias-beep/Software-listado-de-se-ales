namespace Play.Server.Data;

public enum EstadoRegistro
{
    Abierto = 0,
    Cerrado = 1,
    /// <summary>Cerrado por el servidor al dejar de recibir latidos (apagado, cierre accidental, corte de red).</summary>
    Cortado = 2,
    /// <summary>Modificado por un administrador (con constancia en Auditoria).</summary>
    Corregido = 3,
}

/// <summary>Las dos áreas de la empresa. Cada empleado pertenece a una; las obras son comunes a ambas.</summary>
public static class Areas
{
    public const string Oficina = "Oficina";
    public const string Taller = "Taller";
    public static readonly string[] Todas = [Oficina, Taller];

    /// <summary>«taller», «TALLER » → «Taller»; null si no es un área válida.</summary>
    public static string? Normalizar(string? area) =>
        Todas.FirstOrDefault(a => string.Equals(a, area?.Trim(), StringComparison.OrdinalIgnoreCase));
}

public class Empleado
{
    public int Id { get; set; }
    public string Nombre { get; set; } = "";
    /// <summary>Oficina o Taller (los empleados anteriores a la función de áreas quedaron en Oficina).</summary>
    public string Area { get; set; } = Areas.Oficina;
    public string PinHash { get; set; } = "";
    /// <summary>
    /// El PIN en texto legible, para que un administrador pueda verlo y exportarlo (decisión de la usuaria, 2026-11-19).
    /// Es null para PIN elegidos antes de esta función: hay que resetearlos para conocerlos. El login sigue usando <see cref="PinHash"/>.
    /// </summary>
    public string? PinVisible { get; set; }
    public bool DebeCambiarPin { get; set; } = true;
    public bool Activo { get; set; } = true;
    /// <summary>Día del alta (hora del servidor). Null en los empleados anteriores al control de asistencia: para ellos cuenta desde que empezó el control.</summary>
    public DateOnly? CreadoFecha { get; set; }
    public int IntentosFallidos { get; set; }
    public DateTime? BloqueadoHastaUtc { get; set; }
}

public class Obra
{
    public int Id { get; set; }
    public string Nombre { get; set; } = "";
    public bool Activa { get; set; } = true;
    public List<Subtarea> Subtareas { get; set; } = [];
}

/// <summary>
/// Subtarea propia de una obra (la definen los administradores). Si una obra tiene alguna subtarea ACTIVA, quien registra horas
/// en esa obra debe elegir una. Las desactivadas dejan de ofrecerse pero se conservan en los registros anteriores.
/// Las <b>terminadas</b> (las marca un administrador, a veces a partir de un aviso de un empleado) se ven tachadas en la
/// administración, ya no son tareas pendientes y dejan de ofrecerse igual que las desactivadas.
/// </summary>
public class Subtarea
{
    public int Id { get; set; }
    public int ObraId { get; set; }
    public Obra? Obra { get; set; }
    public string Nombre { get; set; } = "";
    public bool Activa { get; set; } = true;
    public bool Terminada { get; set; }
    public DateTime? TerminadaUtc { get; set; }
}

public enum EstadoAviso
{
    /// <summary>Un empleado avisó que terminó la subtarea y el administrador todavía no lo revisó.</summary>
    Nuevo = 0,
    /// <summary>El administrador lo aceptó: la subtarea quedó terminada (tachada).</summary>
    Aceptado = 1,
    Descartado = 2,
    /// <summary>El propio empleado destildó la casilla antes de que el administrador lo revisara.</summary>
    Retirado = 3,
}

/// <summary>Aviso de un empleado: «terminé esta subtarea». No cierra nada por sí solo; decide el administrador.</summary>
public class AvisoSubtarea
{
    public int Id { get; set; }
    public int SubtareaId { get; set; }
    public Subtarea? Subtarea { get; set; }
    public int EmpleadoId { get; set; }
    public Empleado? Empleado { get; set; }
    public DateTime CreadoUtc { get; set; }
    public EstadoAviso Estado { get; set; }
    public DateTime? ResueltoUtc { get; set; }
    public int? AdministradorId { get; set; }
}

/// <summary>
/// Horas que carga a mano un empleado de Taller (un registro individual por empleado, día, obra y subtarea; nunca un acumulado).
/// Las «eliminadas» por un administrador se marcan y no se borran.
/// </summary>
public class CargaHoras
{
    public int Id { get; set; }
    public int EmpleadoId { get; set; }
    public Empleado? Empleado { get; set; }
    public DateOnly Fecha { get; set; }
    public int Minutos { get; set; }
    /// <summary>Obra en la que trabajó (null = trabajo general de Taller, sin obra).</summary>
    public int? ObraId { get; set; }
    public Obra? Obra { get; set; }
    /// <summary>Subtarea de esa obra (null si la obra no tiene subtareas pendientes o no hay obra).</summary>
    public int? SubtareaId { get; set; }
    public Subtarea? Subtarea { get; set; }
    public DateTime CreadaUtc { get; set; }
    public DateTime ActualizadaUtc { get; set; }
    /// <summary>panel = la cargó el empleado; admin = la cargó o corrigió un administrador.</summary>
    public string Origen { get; set; } = "panel";
    public bool Anulado { get; set; }
}

public enum EstadoFalta
{
    /// <summary>La generó el sistema al cerrar el día y el administrador todavía no la revisó.</summary>
    Ausente = 0,
    Injustificada = 1,
    Justificada = 2,
}

/// <summary>Falta de un empleado en un día hábil (una sola por empleado y día). Guarda la decisión del administrador.</summary>
public class Falta
{
    public int Id { get; set; }
    public int EmpleadoId { get; set; }
    public Empleado? Empleado { get; set; }
    public DateOnly Fecha { get; set; }
    public EstadoFalta Estado { get; set; }
    public string? Motivo { get; set; }
    public DateTime CreadaUtc { get; set; }
    public DateTime? ResueltaUtc { get; set; }
    public int? AdministradorId { get; set; }
}

/// <summary>Ajuste interno clave/valor (p. ej. desde cuándo se controla la asistencia).</summary>
public class Ajuste
{
    public string Clave { get; set; } = "";
    public string Valor { get; set; } = "";
}

public class Administrador
{
    public int Id { get; set; }
    public string Usuario { get; set; } = "";
    public string NombreCompleto { get; set; } = "";
    public string PassHash { get; set; } = "";
    public bool DebeCambiarPass { get; set; } = true;
    public bool Activo { get; set; } = true;
    public int IntentosFallidos { get; set; }
    public DateTime? BloqueadoHastaUtc { get; set; }
}

public class RegistroTiempo
{
    /// <summary>GUID generado por el cliente: hace idempotentes los reenvíos.</summary>
    public Guid Id { get; set; }
    public int EmpleadoId { get; set; }
    public Empleado? Empleado { get; set; }
    public int ObraId { get; set; }
    public Obra? Obra { get; set; }
    /// <summary>Null si la obra no tiene subtareas (o el registro es anterior a que existieran).</summary>
    public int? SubtareaId { get; set; }
    public Subtarea? Subtarea { get; set; }
    public DateTime InicioUtc { get; set; }
    public DateTime? FinUtc { get; set; }
    public DateTime UltimoLatidoUtc { get; set; }
    public EstadoRegistro Estado { get; set; }
    public string Equipo { get; set; } = "";
    /// <summary>panel | offline | admin</summary>
    public string Origen { get; set; } = "panel";
    /// <summary>Marca registros dudosos (solapamientos, duración anormal, ajustes por sincronización) para el administrador.</summary>
    public bool RevisarAdmin { get; set; }
    /// <summary>
    /// «Eliminado» por un administrador (con motivo y constancia en Auditoria). No se borra de la base: deja de contar en
    /// totales, reportes y resúmenes, y se puede recuperar. Solo se pueden eliminar registros que no estén en curso.
    /// </summary>
    public bool Anulado { get; set; }
}

public class Auditoria
{
    public int Id { get; set; }
    public DateTime FechaUtc { get; set; }
    public int AdministradorId { get; set; }
    public Guid? RegistroId { get; set; }
    public string Campo { get; set; } = "";
    public string? ValorAnterior { get; set; }
    public string? ValorNuevo { get; set; }
    public string Motivo { get; set; } = "";
}

public class Sesion
{
    public string Token { get; set; } = "";
    /// <summary>empleado | admin</summary>
    public string Tipo { get; set; } = "empleado";
    public int UsuarioId { get; set; }
    public DateTime ExpiraUtc { get; set; }
}
