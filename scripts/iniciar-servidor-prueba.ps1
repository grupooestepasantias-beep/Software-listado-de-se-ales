<#
.SYNOPSIS
  Inicia (si no está corriendo) el servidor de PRUEBA de esta PC y muestra a qué dirección tienen que conectarse los paneles.
  Sirve cada vez que cambiás de red (por ejemplo, el wifi de una casa): la dirección IP de esta PC cambia con la red.
.DESCRIPTION
  - Usa los datos de prueba de C:\PlayPrueba\datos (no toca nada más).
  - Si el servidor ya estaba corriendo, no lo duplica.
  - Revisa que Windows deje pasar las conexiones y avisa si puede preguntar por el firewall.
.EXAMPLE
  powershell -ExecutionPolicy Bypass -File scripts\iniciar-servidor-prueba.ps1
#>
param(
    [string]$Servidor = (Join-Path $PSScriptRoot '..\dist\servidor\Play.Server.exe'),
    [string]$Datos = 'C:\PlayPrueba\datos',
    [int]$Puerto = 8080,
    # Excel de empleados (la base de datos de empleados). Vacío = los empleados se manejan desde la app.
    [string]$Excel = 'C:\Users\ecb_2\OneDrive\Documents\nombres.xlsx'
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path $Servidor)) { throw "No se encontró el servidor en '$Servidor'. Ejecutá primero scripts\publicar-servidor.ps1." }
$Servidor = (Resolve-Path $Servidor).Path
New-Item -ItemType Directory -Force $Datos | Out-Null

# 1) Iniciar el servidor si hace falta
$corriendo = Get-Process Play.Server -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $Servidor }
if ($corriendo) {
    Write-Host "El servidor de prueba ya estaba corriendo (PID $($corriendo.Id))." -ForegroundColor Green
}
else {
    Write-Host "Iniciando el servidor de prueba..."
    $env:Play__DataDir = $Datos
    $env:Play__EmpleadosExcel = $Excel
    $env:Urls = "http://0.0.0.0:$Puerto"
    Start-Process $Servidor -WorkingDirectory (Split-Path $Datos) -WindowStyle Minimized | Out-Null
    Remove-Item Env:Play__DataDir, Env:Urls, Env:Play__EmpleadosExcel -ErrorAction SilentlyContinue
}

$ok = $false
foreach ($i in 1..120) {
    try { Invoke-RestMethod "http://localhost:$Puerto/api/estado" -TimeoutSec 2 | Out-Null; $ok = $true; break } catch { Start-Sleep -Milliseconds 500 }
}
if (-not $ok) { throw "El servidor no responde en el puerto $Puerto." }
Write-Host "El servidor responde." -ForegroundColor Green

# 2) Direcciones para los paneles
Write-Host ""
Write-Host "Esta PC está conectada a:"
$perfiles = Get-NetConnectionProfile
foreach ($p in $perfiles) { Write-Host ("   {0} ({1}), red {2}" -f $p.Name, $p.InterfaceAlias, $p.NetworkCategory) }
Write-Host ""
Write-Host "En los paneles / el administrador (clic derecho > Servidor...), escribí una de estas direcciones:" -ForegroundColor Cyan
Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' -and $_.InterfaceAlias -notlike '*Radmin*' } |
    ForEach-Object { Write-Host ("   {0}:{1}    (adaptador {2})" -f $_.IPAddress, $Puerto, $_.InterfaceAlias) -ForegroundColor Cyan }
Write-Host "Para bajar el programa desde otra PC: abrí en el navegador  http://<esa dirección>"

# 3) ¿Windows va a dejar pasar las conexiones?
$reglas = Get-NetFirewallApplicationFilter -ErrorAction SilentlyContinue | Where-Object { $_.Program -eq $Servidor } |
    ForEach-Object { $_ | Get-NetFirewallRule } | Where-Object { $_.Enabled -eq 'True' -and $_.Direction -eq 'Inbound' -and $_.Action -eq 'Allow' }
$reglaPuerto = Get-NetFirewallRule -DisplayName "Play servidor (TCP $Puerto)" -ErrorAction SilentlyContinue
$problema = @()
foreach ($p in $perfiles | Where-Object { $_.NetworkCategory -ne 'DomainAuthenticated' }) {
    $cubierto = ($reglas + $reglaPuerto) | Where-Object { $_ -and ($_.Profile -match 'Any' -or $_.Profile -match $p.NetworkCategory) }
    if (-not $cubierto) { $problema += "$($p.Name) ($($p.NetworkCategory))" }
}
Write-Host ""
if ($problema.Count -gt 0) {
    Write-Host "OJO: no hay una regla del firewall que deje entrar conexiones en: $($problema -join ', ')." -ForegroundColor Yellow
    Write-Host "Si Windows muestra un cartel «Permitir acceso» para Play.Server, elegí PERMITIR (marcá también las redes privadas)." -ForegroundColor Yellow
    Write-Host "Si no aparece, desde otra PC no va a poder entrar: avisame y lo resolvemos."
}
else {
    Write-Host "Firewall: hay una regla que deja pasar las conexiones en esta red." -ForegroundColor Green
}
Write-Host ""
Write-Host "Recordá: esta PC no tiene que dormirse ni apagarse mientras probás, y el servidor se cierra si la reiniciás (volvé a ejecutar este script)."
