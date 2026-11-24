<#
.SYNOPSIS
  Genera Play.exe, el panel de los empleados: un solo archivo para Windows 10/11 que no requiere instalar nada más.
.PARAMETER Publicar
  Opcional: carpeta del servidor donde dejar el .exe para que los empleados lo bajen
  (por ejemplo C:\PlayServidor\datos\descargas, o la carpeta "datos\descargas" de dist\servidor).
.EXAMPLE
  .\scripts\publicar-panel.ps1
  .\scripts\publicar-panel.ps1 -Publicar C:\PlayServidor\datos\descargas
#>
param(
    [string]$Salida = (Join-Path $PSScriptRoot '..\dist\panel'),
    [string]$Publicar = '',
    # Versión que se graba en el .exe y que los paneles comparan para actualizarse solos. Debe SUBIR en cada publicación.
    # Por defecto: 1.AAMM.DDHH.mm (cada parte entra en 16 bits), p. ej. 1.2611.1812.35 = 18/11/2026 12:35.
    [string]$Version = (Get-Date -Format '1.yyMM.ddHH.mm')
)
$ErrorActionPreference = 'Stop'
$proyecto = Join-Path $PSScriptRoot '..\src\Play.Panel\Play.Panel.csproj'

# Sin compresión: el archivo pesa más (~140 MB) pero el panel, que queda abierto todo el día, usa ~60 MB menos de RAM.
dotnet publish $proyecto -c Release -r win-x64 --self-contained true `
    -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:EnableCompressionInSingleFile=false `
    -p:DebugType=None -p:DebugSymbols=false `
    -p:Version=$Version -p:AssemblyVersion=$Version -p:FileVersion=$Version -p:InformationalVersion=$Version -o $Salida
if ($LASTEXITCODE -ne 0) { throw "dotnet publish falló (código $LASTEXITCODE)" }

$exe = Join-Path $Salida 'Play.exe'
Write-Host ""
Write-Host ("Listo: {0} ({1:N0} MB), versión {2}" -f (Resolve-Path $exe).Path, ((Get-Item $exe).Length / 1MB), (Get-Item $exe).VersionInfo.FileVersion) -ForegroundColor Green

if ($Publicar) {
    New-Item -ItemType Directory -Force $Publicar | Out-Null
    Copy-Item $exe $Publicar -Force
    Write-Host "Publicado en ${Publicar}: los empleados ya pueden bajarlo desde http://IP-del-servidor:8080" -ForegroundColor Green
}
else {
    Write-Host "Para publicarlo: copiar Play.exe a la carpeta 'datos\descargas' del servidor (o usar -Publicar)."
}
