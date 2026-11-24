<#
.SYNOPSIS
  Arma la carpeta «Play-para-NAS» (en dist\) para instalar el servidor en un equipo Linux/NAS desde esta PC con doble clic
  en 1-INSTALAR.bat. Incluye el servidor Linux x64 y ARM64, el Excel de empleados, el Play.exe de los empleados y (opcional)
  los datos actuales. La CONTRASEÑA nunca se guarda: la escribe la persona al instalar.
.EXAMPLE
  .\scripts\armar-paquete-servidor.ps1 -ConDatos
#>
param(
    [switch]$ConDatos,
    [string]$Servidor = '192.168.4.11',
    [string]$Usuario = 'Pasante',
    [int]$Puerto = 8090,
    [string]$Excel = 'C:\Users\ecb_2\OneDrive\Documents\nombres.xlsx'
)
$ErrorActionPreference = 'Stop'
$repo = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$raiz = Join-Path $repo 'dist\Play-para-NAS'
if (Test-Path $raiz) { Remove-Item $raiz -Recurse -Force }
New-Item -ItemType Directory -Force "$raiz\programa", "$raiz\datos\descargas" | Out-Null

foreach ($rt in 'linux-x64', 'linux-arm64') {
    $origen = Join-Path $repo "dist\servidor-$rt"
    if (-not (Test-Path "$origen\Play.Server")) { throw "Falta $origen. Compilá antes con: scripts\publicar-servidor.ps1 -Salida dist\servidor-$rt -Runtime $rt" }
    Copy-Item $origen "$raiz\programa\$rt" -Recurse
}
Copy-Item "$repo\scripts\linux\paquete\*" $raiz
Copy-Item "$repo\scripts\linux\instalar-play.sh" $raiz
if (-not (Test-Path $Excel)) { throw "No encuentro el Excel de empleados: $Excel" }
Copy-Item $Excel "$raiz\nombres.xlsx"
if (Test-Path "$repo\dist\panel\Play.exe") { Copy-Item "$repo\dist\panel\Play.exe" "$raiz\datos\descargas\Play.exe" }

# Se escriben en los scripts el equipo, el usuario y el puerto.
foreach ($f in Get-ChildItem $raiz -File | Where-Object { $_.Extension -in '.ps1', '.sh', '.txt', '.bat' }) {
    $t = [IO.File]::ReadAllText($f.FullName, [Text.Encoding]::UTF8)
    $t = $t.Replace('__SERVIDOR__', $Servidor).Replace('__USUARIO__', $Usuario).Replace('__PUERTO__', "$Puerto")
    $bom = $f.Extension -eq '.ps1' -or $f.Extension -eq '.txt'
    if ($f.Extension -eq '.sh') { $t = $t -replace "`r`n", "`n" }
    [IO.File]::WriteAllText($f.FullName, $t, (New-Object Text.UTF8Encoding($bom)))
}

if ($ConDatos) {
    $datos = 'C:\PlayPrueba\datos'
    $srv = Join-Path $repo 'dist\servidor\Play.Server.exe'
    $corria = Get-CimInstance Win32_Process | Where-Object { $_.ExecutablePath -eq $srv }
    foreach ($p in $corria) { Stop-Process -Id $p.ProcessId -Force }
    Start-Sleep -Seconds 3
    Copy-Item "$datos\play.db*" "$raiz\datos\"
    if ($corria) { Write-Host 'AVISO: el servidor local quedó detenido; volvelo a iniciar (scripts\iniciar-servidor-prueba.ps1).' -ForegroundColor Yellow }
}
$tam = Get-ChildItem $raiz -Recurse -File | Measure-Object Length -Sum
"{0}  ({1} archivos, {2:N0} MB)" -f $raiz, $tam.Count, ($tam.Sum / 1MB)
