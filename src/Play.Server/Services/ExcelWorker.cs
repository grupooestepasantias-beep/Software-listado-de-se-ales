using Microsoft.Extensions.Options;

namespace Play.Server.Services;

/// <summary>
/// Mantiene actualizado el archivo data/excel/horas.xlsx con todo el historial. Se escribe a un archivo temporal
/// y se reemplaza al terminar; si el Excel está abierto en el servidor (bloqueado), reintenta en el próximo ciclo.
/// </summary>
public class ExcelWorker(IServiceScopeFactory scopes, IOptions<PlayOptions> options, IWebHostEnvironment env, ILogger<ExcelWorker> log) : BackgroundService
{
    public static string RutaExcel(PlayOptions o, string contentRoot) =>
        Path.Combine(Path.GetFullPath(o.DataDir, contentRoot), "excel", "horas.xlsx");

    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        var o = options.Value;
        if (o.ExcelMinutes <= 0) return;
        var ruta = RutaExcel(o, env.ContentRootPath);
        Directory.CreateDirectory(Path.GetDirectoryName(ruta)!);

        using var timer = new PeriodicTimer(TimeSpan.FromMinutes(o.ExcelMinutes));
        do
        {
            try
            {
                using var scope = scopes.CreateScope();
                var bytes = await scope.ServiceProvider.GetRequiredService<ReporteService>().GenerarExcelAsync(new FiltroReporte());
                var tmp = ruta + ".tmp";
                await File.WriteAllBytesAsync(tmp, bytes, ct);
                File.Move(tmp, ruta, overwrite: true);
            }
            catch (IOException ex)
            {
                log.LogWarning("No se pudo actualizar {Ruta} (¿está abierto en Excel?): {Mensaje}", ruta, ex.Message);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                log.LogError(ex, "Error al generar el Excel automático.");
            }
        } while (await timer.WaitForNextTickAsync(ct));
    }
}
