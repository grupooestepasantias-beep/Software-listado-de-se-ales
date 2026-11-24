<#
.SYNOPSIS
  Genera PlayAdmin.exe, el programa de administración: un solo archivo para Windows 10/11 que no requiere instalar nada más.
  Se copia a mano a la(s) PC(s) de quienes administran (NO va a la carpeta de descargas de los empleados).
.EXAMPLE
  .\scripts\publicar-admin.ps1
#>
param([string]$Salida = (Join-Path $PSScriptRoot '..\dist\admin'))
$ErrorActionPreference = 'Stop'
$proyecto = Join-Path $PSScriptRoot '..\src\Play.Admin\Play.Admin.csproj'

dotnet publish $proyecto -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=false `
    -p:DebugType=None -p:DebugSymbols=false -o $Salida
if ($LASTEXITCODE -ne 0) { throw "dotnet publish falló (código $LASTEXITCODE)" }

$exe = Join-Path $Salida 'PlayAdmin.exe'
Write-Host ""
Write-Host ("Listo: {0} ({1:N0} MB)" -f (Resolve-Path $exe).Path, ((Get-Item $exe).Length / 1MB)) -ForegroundColor Green
Write-Host "Copiarlo a la PC del administrador. La primera vez pide la dirección del servidor."
