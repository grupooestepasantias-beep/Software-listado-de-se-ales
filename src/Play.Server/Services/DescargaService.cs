using System.Net;
using System.Text;

namespace Play.Server.Services;

/// <summary>Página de descarga: lista los instaladores que haya en datos/descargas (por ej. Play.exe) para que cada empleado los baje.</summary>
public static class DescargaService
{
    private static readonly string[] Extensiones = [".exe", ".msi", ".zip"];

    public static string Carpeta(PlayOptions o, string contentRoot) =>
        Path.Combine(Path.GetFullPath(o.DataDir, contentRoot), "descargas");

    public static List<FileInfo> Listar(string carpeta) =>
        !Directory.Exists(carpeta) ? [] :
        new DirectoryInfo(carpeta).GetFiles().Where(f => Extensiones.Contains(f.Extension, StringComparer.OrdinalIgnoreCase))
            .OrderBy(f => f.Name).ToList();

    /// <summary>Busca por nombre exacto dentro de la carpeta (evita rutas relativas o ..\).</summary>
    public static FileInfo? Buscar(string carpeta, string nombre) =>
        Listar(carpeta).FirstOrDefault(f => string.Equals(f.Name, nombre, StringComparison.OrdinalIgnoreCase));

    public static string Pagina(List<FileInfo> archivos, string direccion)
    {
        var sb = new StringBuilder();
        sb.Append("""
            <!DOCTYPE html><html lang="es"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
            <title>Play - Registro de horas</title>
            <style>
            body{font-family:Segoe UI,Arial,sans-serif;max-width:640px;margin:40px auto;padding:0 16px;color:#222}
            h1{font-size:26px;margin-bottom:4px}p.sub{color:#555;margin-top:0}
            .btn{display:block;background:#2e9e4f;color:#fff;text-decoration:none;padding:16px 20px;border-radius:8px;margin:12px 0;font-size:18px}
            .btn small{display:block;opacity:.85;font-size:13px;margin-top:2px}
            ol{line-height:1.7}.aviso{background:#fff7e0;border:1px solid #e6c65c;padding:10px 14px;border-radius:8px;font-size:14px}
            </style></head><body>
            <h1>Play: registro de horas</h1>
            <p class="sub">Programa para registrar las horas de trabajo en cada obra.</p>
            """);

        if (archivos.Count == 0)
        {
            sb.Append("<p class=\"aviso\">Todavía no hay ningún programa publicado en este servidor. Avisale al administrador.</p>");
        }
        else
        {
            foreach (var f in archivos)
            {
                var nombre = WebUtility.HtmlEncode(f.Name);
                var url = "/descargar/" + Uri.EscapeDataString(f.Name);
                sb.Append($"<a class=\"btn\" href=\"{url}\">Descargar {nombre}<small>{f.Length / 1024.0 / 1024.0:0.#} MB · actualizado {f.LastWriteTime:dd/MM/yyyy HH:mm}</small></a>");
            }
        }

        sb.Append($"""
            <h3>Cómo instalarlo</h3>
            <ol>
            <li>Descargá el programa con el botón verde.</li>
            <li>Abrilo (doble clic). Si Windows muestra «Windows protegió su PC», tocá <b>Más información</b> y luego <b>Ejecutar de todas formas</b>: el programa es de la empresa y no está firmado digitalmente.</li>
            <li>La primera vez te pide la <b>dirección del servidor</b>: escribí <b>{WebUtility.HtmlEncode(direccion.Replace("http://", ""))}</b> y tocá «Probar y guardar».</li>
            <li>Elegí tu nombre, ingresá tu PIN, elegí la obra y presioná Play.</li>
            </ol>
            <p class="aviso">Dirección del servidor: <b>{WebUtility.HtmlEncode(direccion)}</b></p>
            </body></html>
            """);
        return sb.ToString();
    }
}
