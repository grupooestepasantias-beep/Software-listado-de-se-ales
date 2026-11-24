using Play.Client;

namespace Play.Admin;

/// <summary>Filas de las tablas (texto ya formateado para mostrar).</summary>
internal static class Fmt
{
    public static string Hm(long segundos) { var t = TimeSpan.FromSeconds(segundos); return $"{(int)t.TotalHours}:{t.Minutes:00}"; }
    public static string Hms(long segundos) { var t = TimeSpan.FromSeconds(segundos); return $"{(int)t.TotalHours}:{t.Minutes:00}:{t.Seconds:00}"; }
    public static string Fecha(DateTime utc) => utc.ToLocalTime().ToString("dd/MM/yyyy HH:mm");

    public static string Mensaje(string? codigo) => codigo switch
    {
        "nombre_duplicado" => "Ya existe uno con ese nombre.",
        "area_invalida" => "El área tiene que ser Oficina o Taller.",
        "subtarea_requerida" => "Esa obra tiene subtareas: hay que elegir una.",
        "aviso_resuelto" => "Ese aviso ya fue revisado.",
        "solo_taller" => "Esa persona no es del área Taller.",
        "gestionado_por_excel" => "Los empleados se manejan desde el Excel de empleados: cambialo ahí y la app se actualiza sola.",
        "no_corresponde" => "Ese día no se puede justificar: el empleado estuvo presente, es fin de semana, o el día todavía no terminó.",
        "motivo_largo" => "El motivo es demasiado largo (máximo 500 caracteres).",
        "periodo_invalido" => "El mes o el año no son válidos.",
        "ya_cargado" => "Ese día ya tiene horas cargadas: corregilas en lugar de agregar otras.",
        "horas_invalidas" => "Las horas tienen que estar entre 1 minuto y 24 horas.",
        "subtarea_invalida" => "Esa subtarea no corresponde a la obra elegida.",
        "nombre_largo" => "El nombre es demasiado largo (máximo 80 caracteres).",
        "usuario_duplicado" => "Ya existe un administrador con ese usuario.",
        "nombre_requerido" or "usuario_requerido" => "Falta el nombre.",
        "motivo_requerido" => "Hay que escribir el motivo del cambio.",
        "registro_abierto" => "Ese registro todavía está en curso: esperá a que se pause para corregirlo o eliminarlo.",
        "registro_eliminado" => "Ese registro está eliminado. Recuperalo primero si querés corregirlo.",
        "rango_invalido" => "La hora de fin tiene que ser posterior a la de inicio.",
        "fecha_futura" => "No se pueden cargar horas en el futuro.",
        "sin_cambios" => "No cambiaste nada.",
        "obra_invalida" or "datos_invalidos" => "La obra o el empleado elegido no es válido.",
        "no_podes_desactivarte" => "No podés desactivar tu propio usuario.",
        "no_encontrado" => "El elemento ya no existe (¿lo borró otra persona?). Actualizá la lista.",
        "debe_cambiar_clave" => "Primero hay que cambiar la clave temporal.",
        null or "" => "El servidor rechazó la operación.",
        _ => $"El servidor rechazó la operación ({codigo}).",
    };
}

internal record FilaVivo(EnVivoDto D)
{
    public string Empleado => D.Empleado;
    public string Area => D.Area;
    public string Obra => D.Obra;
    public string Equipo => D.Equipo;
    public string Desde => D.InicioUtc.ToLocalTime().ToString("dd/MM HH:mm");
    public string Tiempo => Fmt.Hms(D.Segundos);
}

internal record FilaRegistro(RegistroAdminDto D)
{
    public string Fecha => D.InicioUtc.ToLocalTime().ToString("dd/MM/yyyy");
    public string Empleado => D.Empleado;
    public string Area => D.Area;
    public string Obra => D.Obra;
    public string Subtarea => D.Subtarea ?? "";
    /// <summary>Horas cargadas a mano por el personal de Taller (no son registros del cronómetro).</summary>
    public bool EsCarga => D.Origen == "carga";
    public string Inicio => EsCarga ? "—" : D.InicioUtc.ToLocalTime().ToString("HH:mm");
    public string Fin => EsCarga ? "—" : D.FinUtc is { } f ? f.ToLocalTime().ToString("HH:mm") : "en curso";
    public string Horas => Fmt.Hm(D.Segundos);
    public string Estado => D.Estado switch { "abierto" => "En curso", "cargada" => "Cargada", "cerrado" => "Cerrado", "cortado" => "Cortado", "corregido" => "Corregido", var e => e };
    public string Origen => D.Origen switch { "panel" => "Panel", "offline" => "Sin conexión", "admin" => "Administrador", "carga" => "Carga de horas", var o => o };
    public string Equipo => D.Equipo;
    public string Revisar => D.RevisarAdmin ? "⚠ Revisar" : "";
    public bool ARevisar => D.RevisarAdmin;
    public bool Eliminado => D.Anulado;
}

/// <param name="PinLegible">El PIN en texto, si ya se pidió verlo (si no, es null).</param>
internal record FilaEmpleado(EmpleadoAdminDto D, string? PinLegible = null, bool MostrarPin = false)
{
    public string Nombre => D.Nombre;
    public string Area => D.Area;
    public string Estado => D.Activo ? "Activo" : "Inactivo";
    /// <summary>Oculto («••••») hasta que el administrador toca «Mostrar PIN».</summary>
    public string Pin => !D.PinConocido ? "(no disponible)" : MostrarPin ? (PinLegible ?? "(actualizar)") : "••••";
    public string ObsPin => !D.PinConocido ? "Elegido antes: resetear para conocerlo"
        : D.DebeCambiarPin ? "Inicial: debe elegir el suyo" : "Elegido por el empleado";
}

internal record FilaObra(ObraAdminDto D)
{
    public string Nombre => D.Nombre;
    public string Estado => D.Activa ? "Activa" : "Inactiva";
    public string Subtareas => D.SubtareasActivas == 0 ? "—" : $"{D.SubtareasActivas} pendiente(s)";
}

internal record FilaSubtarea(SubtareaAdminDto D)
{
    public string Nombre => D.Nombre;
    /// <summary>Terminada = tachada, como en una lista del súper: ya no es una tarea pendiente.</summary>
    public bool Terminada => D.Terminada;
    public string Estado => D.Terminada ? "Terminada" : D.Activa ? "Pendiente" : "Inactiva";
}

/// <summary>Una celda del libro de asistencia: el código del día con su color.</summary>
internal sealed class CeldaAsistencia
{
    private static System.Windows.Media.Brush Fijo(string color) { var b = (System.Windows.Media.SolidColorBrush)new System.Windows.Media.BrushConverter().ConvertFromString(color)!; b.Freeze(); return b; }
    private static readonly System.Windows.Media.Brush Verde = Fijo("#C8E6C9"), Rojo = Fijo("#FFCDD2"), Amarillo = Fijo("#FFF59D"), GrisClaro = Fijo("#ECEFF1");

    public string Codigo { get; }
    public string Texto { get; }
    public System.Windows.Media.Brush Fondo { get; }
    public string Detalle { get; }

    public CeldaAsistencia(string codigo, DateOnly dia)
    {
        Codigo = codigo;
        Texto = codigo switch { "S" => "", "-" => "·", var c => c };
        Fondo = codigo switch { "P" => Verde, "A" => Rojo, "J" => Amarillo, "S" => GrisClaro, _ => System.Windows.Media.Brushes.Transparent };
        var fecha = dia.ToString("dddd dd/MM/yyyy");
        Detalle = codigo switch
        {
            "P" => $"{fecha}: presente", "A" => $"{fecha}: ausente", "J" => $"{fecha}: ausencia justificada",
            "S" => $"{fecha}: fin de semana (no se controla)", "…" => $"{fecha}: el día todavía no terminó", _ => $"{fecha}: sin control (el control empezó después)",
        };
    }
}

internal sealed record FilaAsistencia(FilaAsistenciaDto D, List<CeldaAsistencia> Celdas)
{
    public string Empleado => D.Activo ? D.Empleado : D.Empleado + " (inactivo)";
    public string Area => D.Area;
    public int Presentes => D.Presentes;
    public int Ausentes => D.Ausentes;
    public int Justificados => D.Justificados;
}

internal record FilaFalta(FaltaDto D)
{
    public string Fecha => D.Fecha.ToString("ddd dd/MM/yyyy");
    public string Empleado => D.Empleado;
    public string Area => D.Area;
    public string Estado => D.Estado switch { "justificada" => "Justificada", "injustificada" => "Injustificada", _ => "Sin revisar" };
    public bool SinRevisar => D.Estado == "sin_revisar";
    public string Motivo => D.Motivo ?? "";
    public string Resuelta => D.ResueltaUtc is { } r ? Fmt.Fecha(r) : "";
    public string Por => D.Administrador ?? "";
}

internal record FilaCarga(CargaAdminDto D)
{
    public string Fecha => D.Fecha.ToString("ddd dd/MM/yyyy", System.Globalization.CultureInfo.CurrentCulture);
    public string Empleado => D.Empleado;
    public string Obra => D.Obra ?? "(sin obra)";
    public string Subtarea => D.Subtarea ?? "";
    public string Horas => Fmt.Hm(D.Minutos * 60L);
    public string Cargada => Fmt.Fecha(D.CreadaUtc);
    public string Quien => D.Origen == "admin" ? "Administrador" : "Empleado";
    public bool Eliminada => D.Anulado;
}

internal record FilaAviso(AvisoAdminDto D)
{
    public string Fecha => Fmt.Fecha(D.CreadoUtc);
    public string Empleado => D.Empleado;
    public string Area => D.Area;
    public string Obra => D.Obra;
    public string Subtarea => D.Subtarea;
    public string Estado => D.Estado switch
    {
        "nuevo" => "Sin revisar",
        "aceptado" => "Aceptado (terminada)",
        "descartado" => "Descartado",
        "retirado" => "Retirado por el empleado",
        var e => e,
    };
}

internal record FilaAdmin(AdminDto D)
{
    public string Usuario => D.Usuario;
    public string Nombre => D.NombreCompleto;
    public string Estado => D.Activo ? "Activo" : "Inactivo";
}

internal record FilaAuditoria(AuditoriaDto D)
{
    public string Fecha => Fmt.Fecha(D.FechaUtc);
    public string Administrador => D.Administrador;
    public string Campo => D.Campo switch
    {
        "inicio" => "Hora de inicio", "fin" => "Hora de fin", "obra" => "Obra", "creado" => "Registro creado a mano",
        "anulado" => "Registro ELIMINADO", "restaurado" => "Registro recuperado",
        "empleados_excel" => "Sincronización con el Excel de empleados", "falta_justificada" => "Falta justificada", "falta_injustificada" => "Falta injustificada", "horas_taller" => "Horas de Taller (corrección)", "horas_taller_creadas" => "Horas de Taller agregadas", "horas_taller_eliminadas" => "Horas de Taller ELIMINADAS", "horas_taller_recuperadas" => "Horas de Taller recuperadas", "subtarea" => "Subtarea", "subtarea_terminada" => "Subtarea terminada", "subtarea_reabierta" => "Subtarea reabierta", "aviso_descartado" => "Aviso de subtarea descartado", "area" => "Área del empleado", "pines_consultados" => "PIN consultados", "pines_exportados" => "PIN exportados a Excel",
        "pin_reseteado" => "PIN reseteado", "clave_admin_reseteada" => "Clave de administrador reseteada", var c => c,
    };
    public string Anterior => Formatear(D.ValorAnterior);
    public string Nuevo => Formatear(D.ValorNuevo);
    public string Motivo => D.Motivo;

    // Las fechas se guardan en UTC («2026-11-18 15:00:00Z», también dentro de textos más largos): se muestran en hora local.
    private static string Formatear(string? v) =>
        v is null ? "" : System.Text.RegularExpressions.Regex.Replace(v, @"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}Z", m =>
            DateTime.TryParse(m.Value, null, System.Globalization.DateTimeStyles.AdjustToUniversal | System.Globalization.DateTimeStyles.AssumeUniversal, out var d)
                ? d.ToLocalTime().ToString("dd/MM/yyyy HH:mm") : m.Value);
}

internal record FilaBackup(BackupInfo D)
{
    public string Archivo => D.Archivo;
    public string Fecha => Fmt.Fecha(D.FechaUtc);
    public string Tamano => $"{D.Bytes / 1024.0:N0} KB";
}

/// <summary>Elemento de un menú de filtro («(Todos)» tiene Id 0).</summary>
internal record Opcion(int Id, string Nombre);
