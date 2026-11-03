"""Usa Microsoft Word (si está instalado) para actualizar índices y campos y exportar a PDF.

Se hace con un script de PowerShell para no depender de librerías extra dentro del .exe.
Si Word no está disponible, los documentos igualmente se generan: el índice queda marcado para
actualizarse al abrirlos y se informa al usuario.
"""
import base64
import json
import os
import subprocess
import sys

SCRIPT = r"""
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
$items = [System.Text.Encoding]::UTF8.GetString([Convert]::FromBase64String($env:SAT_JOBS)) | ConvertFrom-Json
$w = $null
try {
  $w = New-Object -ComObject Word.Application
  $w.Visible = $false
  $w.DisplayAlerts = 0
  foreach ($it in $items) {
    $res = @{ id = $it.id; ok = $false; paginas = 0; error = '' }
    try {
      $d = $w.Documents.Open($it.path, $false, $false)
      $d.Repaginate()
      foreach ($t in $d.TablesOfContents) { $t.Update() }
      $d.Fields.Update() | Out-Null
      foreach ($s in $d.Sections) {
        foreach ($k in 1,2,3) {
          try { $s.Headers.Item($k).Range.Fields.Update() | Out-Null } catch {}
          try { $s.Footers.Item($k).Range.Fields.Update() | Out-Null } catch {}
        }
      }
      foreach ($t in $d.TablesOfContents) { $t.UpdatePageNumbers() }
      $d.Repaginate()
      $res.paginas = $d.ComputeStatistics(2)
      $d.Save()
      if ($it.pdf) { $d.ExportAsFixedFormat($it.pdf, 17) }
      $d.Close($false)
      $res.ok = $true
    } catch {
      $res.error = $_.Exception.Message
      try { $d.Close($false) } catch {}
    }
    $res | ConvertTo-Json -Compress
  }
} catch {
  @{ id = -1; ok = $false; paginas = 0; error = 'Word no disponible: ' + $_.Exception.Message } | ConvertTo-Json -Compress
} finally {
  if ($w) { try { $w.Quit() } catch {} }
}
"""


def word_disponible():
    """True si Word está registrado en esta PC (no lo abre)."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        winreg.CloseKey(winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, r"Word.Application\CLSID"))
        return True
    except OSError:
        return False


def actualizar(rutas, pdf=False, timeout=600):
    """Actualiza índice, numeración y totales de página de cada .docx; opcionalmente exporta a PDF.

    Devuelve [{path, ok, paginas, error, pdf}]. No lanza excepciones: los fallos van en 'error'.
    """
    rutas = [os.path.abspath(r) for r in rutas]
    if not rutas:
        return []
    if not word_disponible():
        return [{"path": r, "ok": False, "paginas": 0, "pdf": "",
                 "error": "Microsoft Word no está instalado: el índice se actualizará al abrir el documento."}
                for r in rutas]
    trabajos = [{"id": i, "path": r, "pdf": os.path.splitext(r)[0] + ".pdf" if pdf else ""}
                for i, r in enumerate(rutas)]
    # Base64 de UTF-8: las rutas con tildes ("Estación") viajan intactas por la variable de entorno
    entorno = dict(os.environ, SAT_JOBS=base64.b64encode(json.dumps(trabajos).encode("utf-8")).decode())
    codificado = base64.b64encode(SCRIPT.encode("utf-16-le")).decode()
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-EncodedCommand", codificado],
            capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=timeout, env=entorno,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        return [{"path": p, "ok": False, "paginas": 0, "pdf": "", "error": f"No se pudo usar Word: {e}"}
                for p in rutas]
    resultados = {}
    for linea in r.stdout.splitlines():
        try:
            d = json.loads(linea)
        except ValueError:
            continue
        resultados[d.get("id", -1)] = d
    salida = []
    for t in trabajos:
        d = resultados.get(t["id"]) or {"ok": False, "paginas": 0,
                                         "error": next((x["error"] for x in resultados.values() if x.get("error")),
                                                       r.stderr.strip()[:300] or "Word no respondió")}
        salida.append({"path": t["path"], "ok": bool(d.get("ok")), "paginas": d.get("paginas", 0),
                       "error": d.get("error", ""), "pdf": t["pdf"] if d.get("ok") and t["pdf"] else ""})
    return salida
