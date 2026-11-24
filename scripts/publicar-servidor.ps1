<#
.SYNOPSIS
  Compila el servidor de Play y lo deja listo para copiar/instalar en la PC servidor (no requiere instalar .NET allí).
.EXAMPLE
  .\scripts\publicar-servidor.ps1
  Genera dist\servidor. Para otro sistema (p. ej. Linux) usar -Runtime linux-x64.
#>
param(
    [string]$Salida = (Join-Path $PSScriptRoot '..\dist\servidor'),
    [string]$Runtime = 'win-x64'
)
$ErrorActionPreference = 'Stop'
$proyecto = Join-Path $PSScriptRoot '..\src\Play.Server\Play.Server.csproj'

dotnet publish $proyecto -c Release -r $Runtime --self-contained true -o $Salida
if ($LASTEXITCODE -ne 0) { throw "dotnet publish falló (código $LASTEXITCODE)" }

# No se publica la configuración de desarrollo.
Remove-Item (Join-Path $Salida 'appsettings.Development.json') -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "Listo: $((Resolve-Path $Salida).Path)" -ForegroundColor Green
Write-Host "Siguiente paso: en la PC servidor, ejecutar scripts\instalar-servicio.ps1 como administrador."
