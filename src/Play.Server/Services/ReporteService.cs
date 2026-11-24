using ClosedXML.Excel;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Options;
using Play.Server.Data;

namespace Play.Server.Services;

public record FiltroReporte(int? EmpleadoId = null, int? ObraId = null, DateOnly? Desde = null, DateOnly? Hasta = null, string? Area = null);

/// <summary>Un tramo de trabajo dentro de un único día local (los registros que cruzan medianoche se reparten).</summary>
public record Tramo(DateOnly Fecha, string Empleado, string Area, string Obra, DateTime InicioLocal, DateTime FinLocal, long Segundos,
    string Estado, string Origen, string Equipo, bool Revisar, string Subtarea = "");

public class ReporteService(PlayDb db, TimeProvider time, IOptions<PlayOptions> options)
{
    private readonly PlayOptions _o = options.Value;

    public async Task<List<Tramo>> TramosAsync(FiltroReporte f)
    {
        var now = time.GetUtcNow().UtcDateTime;
        var zona = Zona.De(_o);
        var (desdeUtc, hastaUtc) = Zona.RangoUtc(zona, f.Desde, f.Hasta);

        var q = db.Registros.AsNoTracking().Where(r => !r.Anulado); // los eliminados no cuentan en ningún reporte
        if (f.EmpleadoId is { } e) q = q.Where(r => r.EmpleadoId == e);
        if (f.ObraId is { } o) q = q.Where(r => r.ObraId == o);
        if (Areas.Normalizar(f.Area) is { } area) q = q.Where(r => r.Empleado!.Area == area);
        if (desdeUtc is { } d) q = q.Where(r => r.FinUtc == null || r.FinUtc > d);
        if (hastaUtc is { } h) q = q.Where(r => r.InicioUtc < h);

        var regs = await q.Select(r => new
        {
            r.InicioUtc, r.FinUtc, r.Estado, r.Origen, r.Equipo, r.RevisarAdmin,
            Empleado = r.Empleado!.Nombre, Area = r.Empleado!.Area, Obra = r.Obra!.Nombre,
            Subtarea = r.Subtarea == null ? "" : r.Subtarea.Nombre,
        }).ToListAsync();

        var tramos = new List<Tramo>();
        foreach (var r in regs)
        {
            var ini = r.InicioUtc;
            var fin = r.FinUtc ?? now;
            if (desdeUtc is { } d0 && ini < d0) ini = d0;
            if (hastaUtc is { } h0 && fin > h0) fin = h0;
            if (fin <= ini) continue;

            var cursor = ini;
            while (cursor < fin)
            {
                var localCursor = TimeZoneInfo.ConvertTimeFromUtc(cursor, zona);
                var diaSiguienteUtc = Zona.MedianocheLocalAUtc(zona, DateOnly.FromDateTime(localCursor).AddDays(1));
                var corte = diaSiguienteUtc < fin ? diaSiguienteUtc : fin;
                tramos.Add(new Tramo(DateOnly.FromDateTime(localCursor), r.Empleado, r.Area, r.Obra, localCursor,
                    TimeZoneInfo.ConvertTimeFromUtc(corte, zona), (long)(corte - cursor).TotalSeconds,
                    r.Estado.ToString().ToLowerInvariant(), r.Origen, r.Equipo, r.RevisarAdmin, r.Subtarea));
                cursor = corte;
            }
        }
        // Horas cargadas a mano por el personal de Taller: también cuentan en el Excel general (con su obra y subtarea; sin obra: «(Carga de horas)»).
        {
            var qc = db.CargasHoras.AsNoTracking().Where(c => !c.Anulado);
            if (f.EmpleadoId is { } ec) qc = qc.Where(c => c.EmpleadoId == ec);
            if (f.ObraId is { } oc) qc = qc.Where(c => c.ObraId == oc);
            if (Areas.Normalizar(f.Area) is { } areaC) qc = qc.Where(c => c.Empleado!.Area == areaC);
            if (f.Desde is { } dc) qc = qc.Where(c => c.Fecha >= dc);
            if (f.Hasta is { } hc) qc = qc.Where(c => c.Fecha <= hc);
            foreach (var c in await qc.Select(c => new { c.Fecha, c.Minutos, Empleado = c.Empleado!.Nombre, Area = c.Empleado.Area, Obra = c.Obra == null ? null : c.Obra.Nombre, Subtarea = c.Subtarea == null ? "" : c.Subtarea.Nombre }).ToListAsync())
            {
                var dia = c.Fecha.ToDateTime(TimeOnly.MinValue);
                tramos.Add(new Tramo(c.Fecha, c.Empleado, c.Area, c.Obra ?? "(Carga de horas)", dia, dia, c.Minutos * 60L, "cargada", "carga de horas", "", false, c.Subtarea));
            }
        }
        return tramos.OrderBy(t => t.InicioLocal).ThenBy(t => t.Empleado).ToList();
    }

    public async Task<byte[]> GenerarExcelAsync(FiltroReporte f)
    {
        var tramos = await TramosAsync(f);
        using var wb = new XLWorkbook();

        // --- Detalle ---
        var det = wb.AddWorksheet("Detalle");
        string[] cab = ["Fecha", "Empleado", "Área", "Obra", "Subtarea", "Inicio", "Fin", "Horas (decimal)", "Horas (hh:mm)", "Estado", "Origen", "Equipo", "A revisar"];
        for (var i = 0; i < cab.Length; i++) det.Cell(1, i + 1).Value = cab[i];
        var fila = 2;
        foreach (var t in tramos)
        {
            det.Cell(fila, 1).Value = t.Fecha.ToDateTime(TimeOnly.MinValue);
            det.Cell(fila, 1).Style.DateFormat.Format = "dd/MM/yyyy";
            det.Cell(fila, 2).Value = t.Empleado;
            det.Cell(fila, 3).Value = t.Area;
            det.Cell(fila, 4).Value = t.Obra;
            det.Cell(fila, 5).Value = t.Subtarea;
            if (t.Origen != "carga de horas") // las horas cargadas a mano no tienen hora de inicio ni de fin
            {
                det.Cell(fila, 6).Value = t.InicioLocal.TimeOfDay;
                det.Cell(fila, 6).Style.DateFormat.Format = "hh:mm:ss";
                det.Cell(fila, 7).Value = t.FinLocal.Date > t.InicioLocal.Date ? TimeSpan.FromDays(1) : t.FinLocal.TimeOfDay;
                det.Cell(fila, 7).Style.DateFormat.Format = "hh:mm:ss";
            }
            EscribirHoras(det, fila, 8, t.Segundos);
            det.Cell(fila, 10).Value = t.Estado;
            det.Cell(fila, 11).Value = t.Origen;
            det.Cell(fila, 12).Value = t.Equipo;
            det.Cell(fila, 13).Value = t.Revisar ? "SÍ" : "";
            fila++;
        }
        Formato(det, cab.Length, fila - 1);

        // --- Por empleado / por área / por obra / por subtarea ---
        Resumen(wb.AddWorksheet("Por empleado"), "Empleado", tramos.GroupBy(t => t.Empleado));
        Resumen(wb.AddWorksheet("Por área"), "Área", tramos.GroupBy(t => t.Area));
        Resumen(wb.AddWorksheet("Por obra"), "Obra", tramos.GroupBy(t => t.Obra));
        PorSubtarea(wb.AddWorksheet("Por subtarea"), tramos);

        // --- Cruce empleado x obra (horas decimales) ---
        var cruce = wb.AddWorksheet("Empleado x Obra");
        var obras = tramos.Select(t => t.Obra).Distinct().Order().ToList();
        var empleados = tramos.Select(t => t.Empleado).Distinct().Order().ToList();
        cruce.Cell(1, 1).Value = "Empleado (horas decimales)";
        for (var c = 0; c < obras.Count; c++) cruce.Cell(1, c + 2).Value = obras[c];
        cruce.Cell(1, obras.Count + 2).Value = "Total";
        for (var r = 0; r < empleados.Count; r++)
        {
            cruce.Cell(r + 2, 1).Value = empleados[r];
            for (var c = 0; c < obras.Count; c++)
            {
                var seg = tramos.Where(t => t.Empleado == empleados[r] && t.Obra == obras[c]).Sum(t => t.Segundos);
                if (seg > 0) { cruce.Cell(r + 2, c + 2).Value = Math.Round(seg / 3600.0, 2); cruce.Cell(r + 2, c + 2).Style.NumberFormat.Format = "0.00"; }
            }
            cruce.Cell(r + 2, obras.Count + 2).Value = Math.Round(tramos.Where(t => t.Empleado == empleados[r]).Sum(t => t.Segundos) / 3600.0, 2);
            cruce.Cell(r + 2, obras.Count + 2).Style.NumberFormat.Format = "0.00";
        }
        Formato(cruce, obras.Count + 2, empleados.Count + 1);

        using var ms = new MemoryStream();
        wb.SaveAs(ms);
        return ms.ToArray();
    }

    /// <summary>
    /// Excel con los PIN de los empleados (confidencial). Los PIN que el empleado eligió antes de que se guardaran legibles
    /// figuran como «No disponible»: hay que resetearlos desde el administrador para conocerlos.
    /// </summary>
    public static byte[] GenerarExcelPines(IReadOnlyList<PinAdminDto> pines, string? area)
    {
        using var wb = new XLWorkbook();
        var ws = wb.AddWorksheet("PIN");
        string[] cab = ["Empleado", "Área", "Estado", "PIN", "Observación"];
        for (var i = 0; i < cab.Length; i++) ws.Cell(1, i + 1).Value = cab[i];
        var fila = 2;
        foreach (var p in pines)
        {
            ws.Cell(fila, 1).Value = p.Nombre;
            ws.Cell(fila, 2).Value = p.Area;
            ws.Cell(fila, 3).Value = p.Activo ? "Activo" : "Inactivo";
            // Como texto, para que Excel no elimine ceros a la izquierda («0042»).
            ws.Cell(fila, 4).SetValue(p.Pin ?? "No disponible");
            ws.Cell(fila, 4).Style.NumberFormat.Format = "@";
            ws.Cell(fila, 5).Value = p.Pin is null ? "Resetear el PIN para conocerlo"
                : p.DebeCambiarPin ? "PIN inicial: el empleado debe elegir uno propio al ingresar" : "";
            fila++;
        }
        Formato(ws, cab.Length, fila - 1);
        ws.Cell(fila + 1, 1).Value = $"CONFIDENCIAL: contiene los PIN de ingreso{(Areas.Normalizar(area) is { } a ? $" (área {a})" : "")}. No compartir.";
        ws.Cell(fila + 1, 1).Style.Font.Bold = true;
        ws.Cell(fila + 1, 1).Style.Font.FontColor = XLColor.Red;

        using var ms = new MemoryStream();
        wb.SaveAs(ms);
        return ms.ToArray();
    }

    /// <summary>Excel de asistencia del mes: libro (empleados x días), resumen por empleado y faltas.</summary>
    public static byte[] GenerarExcelAsistencia(AsistenciaMesDto mes, IReadOnlyList<FaltaDto> faltas)
    {
        using var wb = new XLWorkbook();
        var ws = wb.AddWorksheet("Asistencia");
        ws.Cell(1, 1).Value = "Empleado";
        ws.Cell(1, 2).Value = "Área";
        for (var i = 0; i < mes.Dias.Count; i++)
        {
            var d = mes.Dias[i].Fecha;
            ws.Cell(1, 3 + i).Value = $"{d.Day} {"DLMMJVS"[(int)d.DayOfWeek]}";
        }
        var c0 = 3 + mes.Dias.Count;
        ws.Cell(1, c0).Value = "Presentes"; ws.Cell(1, c0 + 1).Value = "Ausentes"; ws.Cell(1, c0 + 2).Value = "Justificados";
        var fila = 2;
        foreach (var e in mes.Filas)
        {
            ws.Cell(fila, 1).Value = e.Empleado;
            ws.Cell(fila, 2).Value = e.Area;
            for (var i = 0; i < e.Codigos.Count; i++)
            {
                var celda = ws.Cell(fila, 3 + i);
                var cod = e.Codigos[i];
                celda.Value = cod is "S" or "-" ? "" : cod;
                celda.Style.Alignment.Horizontal = XLAlignmentHorizontalValues.Center;
                celda.Style.Fill.BackgroundColor = cod switch
                {
                    "P" => XLColor.LightGreen, "A" => XLColor.LightSalmon, "J" => XLColor.LightGoldenrodYellow,
                    "S" => XLColor.LightGray, _ => XLColor.NoColor,
                };
            }
            ws.Cell(fila, c0).Value = e.Presentes; ws.Cell(fila, c0 + 1).Value = e.Ausentes; ws.Cell(fila, c0 + 2).Value = e.Justificados;
            fila++;
        }
        Formato(ws, c0 + 2, fila - 1);
        ws.Cell(fila + 1, 1).Value = "P presente · A ausente · J justificado · gris: sábado/domingo · … el día todavía no terminó";

        var res = wb.AddWorksheet("Resumen");
        string[] cab = ["Empleado", "Área", "Días controlados", "Presentes", "Ausentes", "Justificados", "% presente"];
        for (var i = 0; i < cab.Length; i++) res.Cell(1, i + 1).Value = cab[i];
        var f = 2;
        foreach (var e in mes.Filas)
        {
            var controlados = e.Presentes + e.Ausentes + e.Justificados;
            res.Cell(f, 1).Value = e.Empleado; res.Cell(f, 2).Value = e.Area; res.Cell(f, 3).Value = controlados;
            res.Cell(f, 4).Value = e.Presentes; res.Cell(f, 5).Value = e.Ausentes; res.Cell(f, 6).Value = e.Justificados;
            res.Cell(f, 7).Value = controlados == 0 ? 0 : Math.Round(100.0 * e.Presentes / controlados, 1);
            f++;
        }
        Formato(res, cab.Length, f - 1);

        var fa = wb.AddWorksheet("Faltas");
        string[] cabF = ["Fecha", "Empleado", "Área", "Estado", "Motivo", "Resuelta el", "Por"];
        for (var i = 0; i < cabF.Length; i++) fa.Cell(1, i + 1).Value = cabF[i];
        var g = 2;
        foreach (var x in faltas.OrderBy(x => x.Fecha).ThenBy(x => x.Empleado))
        {
            fa.Cell(g, 1).Value = x.Fecha.ToDateTime(TimeOnly.MinValue); fa.Cell(g, 1).Style.DateFormat.Format = "dd/MM/yyyy";
            fa.Cell(g, 2).Value = x.Empleado; fa.Cell(g, 3).Value = x.Area;
            fa.Cell(g, 4).Value = x.Estado switch { "justificada" => "Justificada", "injustificada" => "Injustificada", _ => "Sin revisar" };
            fa.Cell(g, 5).Value = x.Motivo ?? "";
            if (x.ResueltaUtc is { } r) { fa.Cell(g, 6).Value = r.ToLocalTime(); fa.Cell(g, 6).Style.DateFormat.Format = "dd/MM/yyyy HH:mm"; }
            fa.Cell(g, 7).Value = x.Administrador ?? "";
            g++;
        }
        Formato(fa, cabF.Length, g - 1);

        using var ms = new MemoryStream();
        wb.SaveAs(ms);
        return ms.ToArray();
    }

    /// <summary>Excel de las horas cargadas por los empleados de Taller: una fila por carga y un total por empleado.</summary>
    public static byte[] GenerarExcelHoras(IReadOnlyList<CargaAdminDto> cargas)
    {
        using var wb = new XLWorkbook();
        var det = wb.AddWorksheet("Detalle");
        string[] cab = ["Fecha", "Empleado", "Obra", "Subtarea", "Horas (decimal)", "Horas (hh:mm)", "Cargada el", "Origen"];
        for (var i = 0; i < cab.Length; i++) det.Cell(1, i + 1).Value = cab[i];
        var fila = 2;
        foreach (var c in cargas.OrderBy(c => c.Fecha).ThenBy(c => c.Empleado))
        {
            det.Cell(fila, 1).Value = c.Fecha.ToDateTime(TimeOnly.MinValue);
            det.Cell(fila, 1).Style.DateFormat.Format = "dd/MM/yyyy";
            det.Cell(fila, 2).Value = c.Empleado;
            det.Cell(fila, 3).Value = c.Obra ?? "(sin obra)";
            det.Cell(fila, 4).Value = c.Subtarea ?? "";
            EscribirHoras(det, fila, 5, c.Minutos * 60L);
            det.Cell(fila, 7).Value = c.CreadaUtc.ToLocalTime();
            det.Cell(fila, 7).Style.DateFormat.Format = "dd/MM/yyyy HH:mm";
            det.Cell(fila, 8).Value = c.Origen == "admin" ? "Administrador" : "Empleado";
            fila++;
        }
        Formato(det, cab.Length, fila - 1);

        var res = wb.AddWorksheet("Por empleado");
        res.Cell(1, 1).Value = "Empleado";
        res.Cell(1, 2).Value = "Días cargados";
        res.Cell(1, 3).Value = "Horas (decimal)";
        res.Cell(1, 4).Value = "Horas (hh:mm)";
        var f = 2;
        foreach (var g in cargas.GroupBy(c => c.Empleado).OrderBy(g => g.Key))
        {
            res.Cell(f, 1).Value = g.Key;
            res.Cell(f, 2).Value = g.Count();
            EscribirHoras(res, f, 3, g.Sum(c => (long)c.Minutos) * 60);
            f++;
        }
        res.Cell(f, 1).Value = "TOTAL";
        res.Cell(f, 2).Value = cargas.Count;
        EscribirHoras(res, f, 3, cargas.Sum(c => (long)c.Minutos) * 60);
        res.Row(f).Style.Font.Bold = true;
        Formato(res, 4, f);

        using var ms = new MemoryStream();
        wb.SaveAs(ms);
        return ms.ToArray();
    }

    /// <summary>Horas por obra y subtarea. Las horas de obras sin subtareas (o anteriores a ellas) figuran como «(sin subtarea)».</summary>
    private static void PorSubtarea(IXLWorksheet ws, List<Tramo> tramos)
    {
        ws.Cell(1, 1).Value = "Obra";
        ws.Cell(1, 2).Value = "Subtarea";
        ws.Cell(1, 3).Value = "Horas (decimal)";
        ws.Cell(1, 4).Value = "Horas (hh:mm)";
        var fila = 2;
        long total = 0;
        foreach (var g in tramos.GroupBy(t => (t.Obra, Subtarea: t.Subtarea.Length == 0 ? "(sin subtarea)" : t.Subtarea)).OrderBy(g => g.Key.Obra).ThenBy(g => g.Key.Subtarea))
        {
            var seg = g.Sum(t => t.Segundos);
            total += seg;
            ws.Cell(fila, 1).Value = g.Key.Obra;
            ws.Cell(fila, 2).Value = g.Key.Subtarea;
            EscribirHoras(ws, fila, 3, seg);
            fila++;
        }
        ws.Cell(fila, 1).Value = "TOTAL";
        EscribirHoras(ws, fila, 3, total);
        ws.Row(fila).Style.Font.Bold = true;
        Formato(ws, 4, fila);
    }

    private static void Resumen(IXLWorksheet ws, string titulo, IEnumerable<IGrouping<string, Tramo>> grupos)
    {
        ws.Cell(1, 1).Value = titulo;
        ws.Cell(1, 2).Value = "Horas (decimal)";
        ws.Cell(1, 3).Value = "Horas (hh:mm)";
        var fila = 2;
        long total = 0;
        foreach (var g in grupos.OrderBy(g => g.Key))
        {
            var seg = g.Sum(t => t.Segundos);
            total += seg;
            ws.Cell(fila, 1).Value = g.Key;
            EscribirHoras(ws, fila, 2, seg);
            fila++;
        }
        ws.Cell(fila, 1).Value = "TOTAL";
        EscribirHoras(ws, fila, 2, total);
        ws.Row(fila).Style.Font.Bold = true;
        Formato(ws, 3, fila);
    }

    /// <summary>Escribe horas decimales en la columna col y hh:mm en col+1, sin redondear los minutos.</summary>
    private static void EscribirHoras(IXLWorksheet ws, int fila, int col, long segundos)
    {
        ws.Cell(fila, col).Value = Math.Round(segundos / 3600.0, 2);
        ws.Cell(fila, col).Style.NumberFormat.Format = "0.00";
        ws.Cell(fila, col + 1).Value = segundos / 86400.0; // fracción de día; el formato [h]:mm suma más de 24 h
        ws.Cell(fila, col + 1).Style.NumberFormat.Format = "[h]:mm";
    }

    private static void Formato(IXLWorksheet ws, int columnas, int filas)
    {
        var cab = ws.Range(1, 1, 1, columnas);
        cab.Style.Font.Bold = true;
        cab.Style.Fill.BackgroundColor = XLColor.LightGray;
        ws.SheetView.FreezeRows(1);
        if (filas > 1) ws.Range(1, 1, filas, columnas).SetAutoFilter();
        ws.Columns(1, columnas).AdjustToContents();
    }
}
