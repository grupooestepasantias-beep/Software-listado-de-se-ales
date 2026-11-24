# Instala Play en el servidor (NAS/Linux) desde esta PC. Se ejecuta con doble clic en «1-INSTALAR.bat».
# Pide la contraseña del servidor (la escribís vos; no queda guardada en ningún lado).
$ErrorActionPreference = 'Stop'
$Servidor = '__SERVIDOR__'
$Usuario  = Read-Host 'Escribi el USUARIO administrador del NAS y apreta Enter (la contrasena te la pide despues)'
if (-not $Usuario) { Write-Host 'No escribiste ningun usuario.' -ForegroundColor Red; exit 1 }
$Usuario = $Usuario.Trim()
$Puerto   = '__PUERTO__'
$Carpeta  = Split-Path -Parent $MyInvocation.MyCommand.Path
$ssh = "-o StrictHostKeyChecking=accept-new"

function Titulo($t) { Write-Host ""; Write-Host "=== $t ===" -ForegroundColor Cyan }
function Falla($t) { Write-Host ""; Write-Host "NO SE PUDO: $t" -ForegroundColor Red; Write-Host "Sacale una foto o copiá este mensaje y pasaselo a quien te ayuda."; exit 1 }

Titulo 'Play - instalación en el servidor'
Write-Host "Servidor: $Servidor    Usuario: $Usuario    Puerto de Play: $Puerto"
Write-Host "Cuando aparezca «password», escribí la contraseña y apretá Enter (no se ve lo que escribís; es normal)."

Titulo 'Paso 1: revisando que esta PC llegue al servidor'
if (-not (Get-Command ssh.exe -ErrorAction SilentlyContinue) -or -not (Get-Command tar.exe -ErrorAction SilentlyContinue)) {
    Falla 'Esta PC no tiene el «Cliente OpenSSH» de Windows (Configuración > Aplicaciones > Características opcionales > Agregar una característica > Cliente OpenSSH).'
}
$r = Test-NetConnection $Servidor -Port 22 -WarningAction SilentlyContinue
if (-not $r.TcpTestSucceeded) { Falla "No se puede conectar al puerto SSH (22) del servidor $Servidor. Revisá que el SSH esté activado en el NAS." }
Write-Host 'Perfecto, el servidor responde.' -ForegroundColor Green

Titulo 'Paso 2: enviando los archivos al servidor (puede tardar unos minutos)'
$destino = '~/play-instalacion'
# Se usa cmd.exe para que el archivo viaje tal cual (PowerShell rompe los archivos binarios en un «pipe»).
$cmd = "tar -czf - -C `"$Carpeta`" programa datos nombres.xlsx instalar-en-servidor.sh instalar-play.sh | ssh $ssh $Usuario@$Servidor `"rm -rf $destino && mkdir -p $destino && tar -xzf - -C $destino`""
cmd.exe /c $cmd
if ($LASTEXITCODE -ne 0) { Falla 'No se pudieron enviar los archivos (¿contraseña incorrecta, o este usuario no puede usar SSH?). Probá de nuevo.' }
Write-Host 'Archivos enviados.' -ForegroundColor Green

Titulo 'Paso 3: instalando y arrancando el servidor'
Write-Host 'Si te pide contraseña otra vez (para «sudo»), es la misma.'
& ssh.exe -t $ssh.Split(' ') "$Usuario@$Servidor" "bash $destino/instalar-en-servidor.sh"
if ($LASTEXITCODE -ne 0) { Falla 'La instalación en el servidor terminó con un error (mirá los mensajes de arriba).' }

Titulo 'Paso 4: comprobando que el servidor responde'
Start-Sleep -Seconds 10
try {
    Invoke-RestMethod "http://${Servidor}:${Puerto}/api/estado" -TimeoutSec 15 | Out-Null
    Write-Host "TODO LISTO: el servidor de Play está funcionando en http://${Servidor}:${Puerto}" -ForegroundColor Green
    Write-Host "En cada panel y en la Administración, la dirección del servidor es:  ${Servidor}:${Puerto}"
} catch {
    Write-Host "El servidor se instaló pero todavía no responde en http://${Servidor}:${Puerto}." -ForegroundColor Yellow
    Write-Host "Esperá un minuto y probá abrir esa dirección en el navegador. Si no abre, pasale este mensaje a quien te ayuda."
}
