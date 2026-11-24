<#
.SYNOPSIS
  Instala (o actualiza) el servidor de Play como servicio de Windows en esta PC.
  Ejecutar en la PC servidor, en una consola de PowerShell abierta como administrador.
.DESCRIPTION
  - Copia el programa a C:\PlayServidor (la carpeta "datos" con la base, backups y Excel NO se toca al actualizar).
  - Si ya existe appsettings.json en el destino, lo conserva.
  - Crea el servicio "PlayServidor" (inicio automático, se reinicia solo si falla).
  - Abre el puerto en el Firewall de Windows.
.EXAMPLE
  .\scripts\instalar-servicio.ps1
  .\scripts\instalar-servicio.ps1 -Origen D:\entrega\servidor -Puerto 8080
#>
#Requires -RunAsAdministrator
param(
    [string]$Origen = (Join-Path $PSScriptRoot '..\dist\servidor'),
    [string]$Destino = 'C:\PlayServidor',
    [int]$Puerto = 8080
)
$ErrorActionPreference = 'Stop'
$servicio = 'PlayServidor'
$exe = Join-Path $Destino 'Play.Server.exe'

if (-not (Test-Path (Join-Path $Origen 'Play.Server.exe'))) {
    throw "No se encontró Play.Server.exe en '$Origen'. Ejecutá primero scripts\publicar-servidor.ps1 o indicá -Origen."
}

# 1) Detener el servicio si ya existe (actualización).
if (Get-Service $servicio -ErrorAction SilentlyContinue) {
    Write-Host "Deteniendo el servicio existente..."
    Stop-Service $servicio -Force
    (Get-Service $servicio).WaitForStatus('Stopped', [TimeSpan]::FromSeconds(30))
}

# 2) Copiar archivos sin pisar datos ni la configuración existente.
New-Item -ItemType Directory -Force $Destino | Out-Null
$exclArchivos = @()
if (Test-Path (Join-Path $Destino 'appsettings.json')) { $exclArchivos = @('/XF', 'appsettings.json') }
robocopy $Origen $Destino /E /XD datos @exclArchivos /NFL /NDL /NJH /NJS /NP | Out-Null
if ($LASTEXITCODE -ge 8) { throw "No se pudieron copiar los archivos (robocopy código $LASTEXITCODE)." }

# 3) Cambiar el puerto solo si se pidió uno distinto del que ya tiene la configuración.
if ($PSBoundParameters.ContainsKey('Puerto')) {
    $cfgPath = Join-Path $Destino 'appsettings.json'
    $cfg = Get-Content $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
    $cfg.Urls = "http://0.0.0.0:$Puerto"
    $cfg | ConvertTo-Json -Depth 10 | Set-Content $cfgPath -Encoding UTF8
}

# 4) Crear el servicio si no existe.
if (-not (Get-Service $servicio -ErrorAction SilentlyContinue)) {
    New-Service -Name $servicio -BinaryPathName "`"$exe`"" -DisplayName 'Play - Registro de horas' `
        -Description 'Servidor central del registro de horas por empleado y obra.' -StartupType Automatic | Out-Null
    sc.exe failure $servicio reset= 86400 actions= restart/5000/restart/5000/restart/5000 | Out-Null
}

# 5) Firewall: la red wifi suele estar marcada como "Pública", por eso se abre en todos los perfiles.
$regla = "Play servidor (TCP $Puerto)"
Get-NetFirewallRule -DisplayName $regla -ErrorAction SilentlyContinue | Remove-NetFirewallRule
New-NetFirewallRule -DisplayName $regla -Direction Inbound -Protocol TCP -LocalPort $Puerto -Action Allow -Profile Any | Out-Null

# 6) Iniciar y comprobar.
Start-Service $servicio
$ok = $false
foreach ($i in 1..20) {
    Start-Sleep -Milliseconds 500
    try { Invoke-RestMethod "http://localhost:$Puerto/api/estado" | Out-Null; $ok = $true; break } catch { }
}
if (-not $ok) { throw "El servicio se inició pero no responde en el puerto $Puerto. Revisá el Visor de eventos (Aplicación)." }

Write-Host ""
Write-Host "Servidor instalado y funcionando." -ForegroundColor Green
Write-Host "Direcciones para los empleados (probá cuál abre desde otra PC):"
Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' -and $_.IPAddress -notlike '169.254.*' } |
    ForEach-Object { Write-Host "   http://$($_.IPAddress):$Puerto" }
Write-Host ""
Write-Host "Recomendado: reservar la IP de esta PC en el router (reserva DHCP) para que no cambie."
$accesos = Join-Path $Destino 'datos\accesos_iniciales.txt'
if (Test-Path $accesos) { Write-Host "PIN iniciales y clave del administrador: $accesos (entregarlos y borrar el archivo)." -ForegroundColor Yellow }
Write-Host "Para publicar el programa de los empleados, copiar el .exe a: $(Join-Path $Destino 'datos\descargas')"
