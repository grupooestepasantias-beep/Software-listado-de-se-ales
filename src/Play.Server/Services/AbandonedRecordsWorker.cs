using Microsoft.Extensions.Options;

namespace Play.Server.Services;

/// <summary>Cada pocos segundos cierra como «cortado» los registros que dejaron de enviar latidos.</summary>
public class AbandonedRecordsWorker(IServiceScopeFactory scopes, IOptions<PlayOptions> options, ILogger<AbandonedRecordsWorker> log) : BackgroundService
{
    protected override async Task ExecuteAsync(CancellationToken ct)
    {
        var intervalo = TimeSpan.FromSeconds(Math.Max(5, options.Value.HeartbeatSeconds));
        using var timer = new PeriodicTimer(intervalo);
        do
        {
            try
            {
                using var scope = scopes.CreateScope();
                var n = await scope.ServiceProvider.GetRequiredService<RegistroService>().CerrarAbandonadosAsync();
                if (n > 0) log.LogInformation("{N} registro(s) cortado(s) por falta de latidos.", n);
            }
            catch (Exception ex) when (ex is not OperationCanceledException)
            {
                log.LogError(ex, "Error al cerrar registros abandonados.");
            }
        } while (await timer.WaitForNextTickAsync(ct));
    }
}
