using System.Data;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Play.Server.Data;

namespace Play.Server.Services;

/// <summary>
/// Actualiza una base ya existente cuando el programa agrega columnas (EnsureCreated no modifica bases existentes).
/// Cada cambio es idempotente: solo se aplica si falta. Antes de tocar nada se hace una copia de seguridad.
/// Cuando haya cambios más complejos conviene pasar a migraciones de EF Core.
/// </summary>
public static class Esquema
{
    /// <summary>Tablas que se crean si faltan (van primero: las columnas nuevas pueden referenciarlas).</summary>
    private static readonly (string Tabla, string[] Sql)[] TablasNuevas =
    [
        ("Subtareas",
        [
            "CREATE TABLE Subtareas (Id INTEGER NOT NULL CONSTRAINT PK_Subtareas PRIMARY KEY AUTOINCREMENT, ObraId INTEGER NOT NULL, " +
            "Nombre TEXT NOT NULL, Activa INTEGER NOT NULL, CONSTRAINT FK_Subtareas_Obras_ObraId FOREIGN KEY (ObraId) REFERENCES Obras (Id) ON DELETE CASCADE)",
            "CREATE UNIQUE INDEX IX_Subtareas_ObraId_Nombre ON Subtareas (ObraId, Nombre)",
        ]),
        ("Faltas",
        [
            "CREATE TABLE Faltas (Id INTEGER NOT NULL CONSTRAINT PK_Faltas PRIMARY KEY AUTOINCREMENT, EmpleadoId INTEGER NOT NULL, Fecha TEXT NOT NULL, " +
            "Estado INTEGER NOT NULL, Motivo TEXT NULL, CreadaUtc TEXT NOT NULL, ResueltaUtc TEXT NULL, AdministradorId INTEGER NULL, " +
            "CONSTRAINT FK_Faltas_Empleados_EmpleadoId FOREIGN KEY (EmpleadoId) REFERENCES Empleados (Id))",
            "CREATE UNIQUE INDEX IX_Faltas_EmpleadoId_Fecha ON Faltas (EmpleadoId, Fecha)",
        ]),
        ("Ajustes",
        [
            "CREATE TABLE Ajustes (Clave TEXT NOT NULL CONSTRAINT PK_Ajustes PRIMARY KEY, Valor TEXT NOT NULL)",
        ]),
        ("CargasHoras",
        [
            "CREATE TABLE CargasHoras (Id INTEGER NOT NULL CONSTRAINT PK_CargasHoras PRIMARY KEY AUTOINCREMENT, EmpleadoId INTEGER NOT NULL, " +
            "Fecha TEXT NOT NULL, Minutos INTEGER NOT NULL, CreadaUtc TEXT NOT NULL, ActualizadaUtc TEXT NOT NULL, Origen TEXT NOT NULL, Anulado INTEGER NOT NULL, " +
            "CONSTRAINT FK_CargasHoras_Empleados_EmpleadoId FOREIGN KEY (EmpleadoId) REFERENCES Empleados (Id))",
            "CREATE INDEX IX_CargasHoras_Fecha ON CargasHoras (Fecha)",
        ]),
        ("AvisosSubtarea",
        [
            "CREATE TABLE AvisosSubtarea (Id INTEGER NOT NULL CONSTRAINT PK_AvisosSubtarea PRIMARY KEY AUTOINCREMENT, SubtareaId INTEGER NOT NULL, " +
            "EmpleadoId INTEGER NOT NULL, CreadoUtc TEXT NOT NULL, Estado INTEGER NOT NULL, ResueltoUtc TEXT NULL, AdministradorId INTEGER NULL, " +
            "CONSTRAINT FK_AvisosSubtarea_Subtareas_SubtareaId FOREIGN KEY (SubtareaId) REFERENCES Subtareas (Id) ON DELETE CASCADE, " +
            "CONSTRAINT FK_AvisosSubtarea_Empleados_EmpleadoId FOREIGN KEY (EmpleadoId) REFERENCES Empleados (Id))",
            "CREATE INDEX IX_AvisosSubtarea_Estado_CreadoUtc ON AvisosSubtarea (Estado, CreadoUtc)",
        ]),
    ];

    private static readonly (string Tabla, string Columna, string Sql)[] Cambios =
    [
        ("Registros", "Anulado", "ALTER TABLE Registros ADD COLUMN Anulado INTEGER NOT NULL DEFAULT 0"),
        ("Empleados", "Area", "ALTER TABLE Empleados ADD COLUMN Area TEXT NOT NULL DEFAULT 'Oficina'"),
        ("Empleados", "PinVisible", "ALTER TABLE Empleados ADD COLUMN PinVisible TEXT NULL"),
        ("Registros", "SubtareaId", "ALTER TABLE Registros ADD COLUMN SubtareaId INTEGER NULL REFERENCES Subtareas (Id)"),
        ("CargasHoras", "ObraId", "ALTER TABLE CargasHoras ADD COLUMN ObraId INTEGER NULL REFERENCES Obras (Id)"),
        ("CargasHoras", "SubtareaId", "ALTER TABLE CargasHoras ADD COLUMN SubtareaId INTEGER NULL REFERENCES Subtareas (Id)"),
        ("Empleados", "CreadoFecha", "ALTER TABLE Empleados ADD COLUMN CreadoFecha TEXT NULL"),
        ("Subtareas", "Terminada", "ALTER TABLE Subtareas ADD COLUMN Terminada INTEGER NOT NULL DEFAULT 0"),
        ("Subtareas", "TerminadaUtc", "ALTER TABLE Subtareas ADD COLUMN TerminadaUtc TEXT NULL"),
    ];

    /// <summary>Índices que acompañan a los cambios de arriba (idempotentes).</summary>
    private static readonly string[] Indices =
    [
        "CREATE INDEX IF NOT EXISTS IX_Registros_SubtareaId ON Registros (SubtareaId)",
        // Las horas de Taller ya no son una sola por día (hay una línea por obra y subtarea): se quita el índice único anterior.
        "DROP INDEX IF EXISTS UX_CargasHoras_EmpleadoId_Fecha",
        "CREATE INDEX IF NOT EXISTS IX_CargasHoras_EmpleadoId_Fecha ON CargasHoras (EmpleadoId, Fecha)",
        "CREATE INDEX IF NOT EXISTS IX_CargasHoras_ObraId ON CargasHoras (ObraId)",
    ];

    /// <summary>Devuelve la cantidad de cambios aplicados (tablas + columnas).</summary>
    public static async Task<int> ActualizarAsync(PlayDb db, string dataDir)
    {
        var conexion = (SqliteConnection)db.Database.GetDbConnection();
        if (conexion.State != ConnectionState.Open) await conexion.OpenAsync();

        var pendientes = new List<string>();
        var cantidadTablas = 0;
        foreach (var (tabla, sql) in TablasNuevas)
            if (!await ExisteTablaAsync(conexion, tabla)) { pendientes.AddRange(sql); cantidadTablas++; }
        foreach (var (tabla, columna, sql) in Cambios)
            if (!await ExisteColumnaAsync(conexion, tabla, columna)) pendientes.Add(sql);
        if (pendientes.Count == 0) return 0;

        var carpeta = Path.Combine(dataDir, "backups");
        Directory.CreateDirectory(carpeta);
        var copia = Path.Combine(carpeta, $"play-antes-de-actualizar-{DateTime.Now:yyyyMMdd-HHmmss}.db");
        await using (var cmd = conexion.CreateCommand())
        {
            cmd.CommandText = $"VACUUM INTO '{copia.Replace("'", "''")}'";
            await cmd.ExecuteNonQueryAsync();
        }

        foreach (var sql in pendientes.Concat(Indices))
        {
            await using var cmd = conexion.CreateCommand();
            cmd.CommandText = sql;
            await cmd.ExecuteNonQueryAsync();
        }
        return cantidadTablas + pendientes.Count(s => s.StartsWith("ALTER TABLE", StringComparison.Ordinal));
    }

    private static async Task<bool> ExisteTablaAsync(SqliteConnection conexion, string tabla)
    {
        await using var cmd = conexion.CreateCommand();
        cmd.CommandText = "SELECT COUNT(*) FROM sqlite_master WHERE type = 'table' AND name = $tabla";
        cmd.Parameters.AddWithValue("$tabla", tabla);
        return Convert.ToInt64(await cmd.ExecuteScalarAsync()) > 0;
    }

    private static async Task<bool> ExisteColumnaAsync(SqliteConnection conexion, string tabla, string columna)
    {
        await using var cmd = conexion.CreateCommand();
        cmd.CommandText = "SELECT COUNT(*) FROM pragma_table_info($tabla) WHERE name = $columna";
        cmd.Parameters.AddWithValue("$tabla", tabla);
        cmd.Parameters.AddWithValue("$columna", columna);
        return Convert.ToInt64(await cmd.ExecuteScalarAsync()) > 0;
    }
}
