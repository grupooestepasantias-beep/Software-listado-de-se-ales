# Prueba de punta a punta de la ACTUALIZACIÓN AUTOMÁTICA con .exe publicados REALES (no toca tu instalación ni tu servidor).
#
#   1) Actualización normal:  un panel con la versión A (1.0.0.1) se actualiza solo a la B (1.0.0.2) publicada en el servidor.
#   2) Vuelta atrás:          el servidor publica un .exe "roto" (dotnet.exe con versión mayor): el panel debe volver a la versión anterior.
#   3) Con registro en curso: el panel NO se reinicia mientras hay un cronómetro andando; al volver a abrirlo se actualiza.
#
# Requisitos: dos .exe publicados con versiones distintas (scripts\publicar-panel.ps1 -Salida <carpeta> -Version 1.0.0.1 / 1.0.0.2).
# El escenario 3 teclea un PIN con SendKeys: no tocar el mouse/teclado mientras corre.
param(
    [string]$A = (Join-Path $env:TEMP 'play-upd-bin\A\Play.exe'),
    [string]$B = (Join-Path $env:TEMP 'play-upd-bin\B\Play.exe'),
    [string]$Salida = (Join-Path $env:TEMP 'play-e2e-upd'),
    [int[]]$Escenarios = @(1, 2, 3)
)
$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..')
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class WinUpd { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); }
"@
$UIA = [System.Windows.Automation.AutomationElement]
$script:fallos = 0
function Paso($t) { Write-Output $t }
function Verificar($condicion, $texto) {
    if ($condicion) { Write-Output "  OK   $texto" } else { Write-Output "  FALLA $texto"; $script:fallos++ }
}
function Hash($ruta) { (Get-FileHash $ruta -Algorithm SHA256).Hash }
function Version($ruta) { (Get-Item $ruta).VersionInfo.FileVersion }

Remove-Item $Salida -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory $Salida | Out-Null
$hashA = Hash $A; $hashB = Hash $B; $verB = Version $B
Paso "Versión A: $(Version $A)   Versión B (publicada): $verB"

function NuevoServidor($puerto, $nombre, $exeParaDescargas) {
    $datos = "$Salida\$nombre-srv"
    New-Item -ItemType Directory "$datos\descargas" | Out-Null
    Copy-Item $exeParaDescargas "$datos\descargas\Play.exe"
    $env:Play__DataDir = $datos; $env:Urls = "http://127.0.0.1:$puerto"
    $p = Start-Process dotnet -ArgumentList "$repo\src\Play.Server\bin\Debug\net8.0\Play.Server.dll" -PassThru -WindowStyle Hidden
    Remove-Item Env:Play__DataDir, Env:Urls
    foreach ($i in 1..40) { Start-Sleep -Milliseconds 500; try { Invoke-RestMethod "http://127.0.0.1:$puerto/api/estado" | Out-Null; break } catch { } }
    [pscustomobject]@{ Proceso = $p; Datos = $datos; Url = "http://127.0.0.1:$puerto" }
}
function NuevoPanel($nombre, $url) {
    $app = "$Salida\$nombre-app"
    New-Item -ItemType Directory "$app\datos" | Out-Null
    Copy-Item $A "$app\Play.exe"
    "{`"servidorUrl`":`"$url`",`"primeraEjecucionHecha`":true}" | Set-Content "$app\datos\ajustes.json" -Encoding UTF8
    $p = Start-Process "$app\Play.exe" -ArgumentList '--datos', "`"$app\datos`"", '--permitir-actualizacion' -PassThru
    [pscustomobject]@{ App = $app; Exe = "$app\Play.exe"; Datos = "$app\datos"; Proceso = $p }
}
function PanelActual($panel) { Get-Process Play -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $panel.Exe } | Select-Object -First 1 }
function Ventana($proc) {
    $c = New-Object System.Windows.Automation.PropertyCondition($UIA::ProcessIdProperty, $proc.Id)
    $UIA::RootElement.FindFirst('Children', $c)
}
function Esperar($segundos, [scriptblock]$condicion) {
    $t = [Diagnostics.Stopwatch]::StartNew()
    while ($t.Elapsed.TotalSeconds -lt $segundos) { if (& $condicion) { return $true }; Start-Sleep -Milliseconds 500 }
    return $false
}
function Log($panel) { $r = "$($panel.Datos)\actualizaciones.log"; if (Test-Path $r) { Get-Content $r -Raw -Encoding UTF8 } else { '' } }
function Limpiar() {
    Get-Process Play -ErrorAction SilentlyContinue | Where-Object { $_.Path -like "$Salida*" } | Stop-Process -Force
    Get-CimInstance Win32_Process -Filter "Name='dotnet.exe'" | Where-Object { $_.CommandLine -like "*$Salida*" -or $_.CommandLine -like '*src\Play.Server\bin\Debug*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -Force }
}

try {
    Limpiar

    # ============================================================ 1) actualización normal
    if (1 -in $Escenarios) {
        Paso "`n[1] Actualización normal (A -> B)"
        $srv = NuevoServidor 8085 'e1' $B
        $panel = NuevoPanel 'e1' $srv.Url
        $pidViejo = $panel.Proceso.Id
        $listo = Esperar 150 { $p = PanelActual $panel; $p -and $p.Id -ne $pidViejo -and $p.MainModule.FileVersionInfo.FileVersion -eq $verB }
        Verificar $listo "El panel se reinició solo con la versión nueva ($verB)"
        $nuevo = PanelActual $panel
        Verificar ($null -eq (Get-Process -Id $pidViejo -ErrorAction SilentlyContinue)) 'El proceso anterior terminó'
        Verificar ((Hash $panel.Exe) -eq $hashB) 'El Play.exe del disco es exactamente la versión publicada (misma huella)'
        Verificar (Esperar 40 { -not (Test-Path "$($panel.Exe).viejo") }) 'Se borró el .exe anterior (.viejo) cuando terminó de cerrarse'
        Verificar (-not (Test-Path "$($panel.Exe).nuevo")) 'No quedaron archivos a medias'
        Verificar ((Log $panel) -match "Actualizado a $([regex]::Escape($verB))") 'Quedó anotado en actualizaciones.log'
        Verificar ((Get-Content "$($panel.Datos)\ajustes.json" -Raw) -match [regex]::Escape($srv.Url)) 'Se conservaron los ajustes (dirección del servidor)'
        $w = if ($nuevo) { Ventana $nuevo } else { $null }
        Verificar ([bool]$w) 'La versión nueva muestra su ventana'
        if ($w) {
            $combo = $w.FindFirst('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::AutomationIdProperty, 'CmbUsuario')))
            Verificar ([bool]$combo) 'La versión nueva funciona (aparece el menú de usuarios)'
        }
        Limpiar
    }

    # ============================================================ 2) vuelta atrás si lo nuevo no arranca
    if (2 -in $Escenarios) {
        Paso "`n[2] Vuelta atrás: el servidor publica un .exe que no arranca"
        # «Play.exe» roto con versión válida (9.9.9.9): un ejecutable de .NET suelto, sin sus archivos, no puede arrancar.
        $src = "$Salida\roto-src"
        dotnet new console -n Roto -o $src --framework net8.0 --no-restore 2>&1 | Out-Null
        dotnet publish "$src\Roto.csproj" -c Release -o "$Salida\roto-out" -p:AssemblyName=Play -p:Version=9.9.9.9 -p:FileVersion=9.9.9.9 -p:AssemblyVersion=9.9.9.9 2>&1 | Out-Null
        $roto = "$Salida\roto.exe"; Copy-Item "$Salida\roto-out\Play.exe" $roto
        $verRota = Version $roto
        Paso "  (programa roto de prueba: versión $verRota, $((Get-Item $roto).Length) bytes)"
        $srv = NuevoServidor 8086 'e2' $roto
        $panel = NuevoPanel 'e2' $srv.Url
        $pidA = $panel.Proceso.Id
        $fallo = Esperar 120 { (Log $panel) -match 'FALLÓ' }
        Verificar $fallo 'El panel detectó que la versión nueva no arrancó bien'
        Start-Sleep -Seconds 3
        Verificar ($null -ne (Get-Process -Id $pidA -ErrorAction SilentlyContinue)) 'El panel original sigue funcionando (mismo proceso)'
        Verificar ((Hash $panel.Exe) -eq $hashA) 'El Play.exe del disco volvió a ser el original (misma huella)'
        Verificar (-not (Test-Path "$($panel.Exe).viejo") -and -not (Test-Path "$($panel.Exe).nuevo")) 'No quedaron restos de la actualización fallida'
        Verificar ((Get-Content "$($panel.Datos)\ajustes.json" -Raw) -match [regex]::Escape($verRota)) 'Anotó esa versión como rechazada para no insistir'
        $w = Ventana (Get-Process -Id $pidA -ErrorAction SilentlyContinue)
        $combo = if ($w) { $w.FindFirst('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::AutomationIdProperty, 'CmbUsuario'))) }
        Verificar ([bool]$combo) 'El panel sigue usable (menú de usuarios visible)'
        Limpiar
    }

    # ============================================================ 3) no interrumpe un registro en curso
    if (3 -in $Escenarios) {
        Paso "`n[3] Con un registro en curso no se reinicia; al volver a abrirlo se actualiza"
        $srv = NuevoServidor 8087 'e3' $B
        $u = $srv.Url
        # empleado de prueba con PIN conocido
        $acc = Get-Content "$($srv.Datos)\accesos_iniciales.txt" -Raw
        $clave0 = [regex]::Match($acc, 'Clave temporal: (\S+)').Groups[1].Value
        $json = @{ ContentType = 'application/json; charset=utf-8' }
        $t = (Invoke-RestMethod "$u/api/admin/login" -Method Post @json -Body ([Text.Encoding]::UTF8.GetBytes((@{ usuario = 'Gabriel'; password = $clave0 } | ConvertTo-Json)))).token
        $h = @{ Authorization = "Bearer $t" }
        Invoke-RestMethod "$u/api/admin/clave" -Method Post -Headers $h @json -Body ([Text.Encoding]::UTF8.GetBytes((@{ claveActual = $clave0; claveNueva = 'ClaveNueva-123' } | ConvertTo-Json))) | Out-Null
        $emp = Invoke-RestMethod "$u/api/admin/empleados" -Method Post -Headers $h @json -Body ([Text.Encoding]::UTF8.GetBytes((@{ nombre = 'Probador Act' } | ConvertTo-Json)))
        $lg = Invoke-RestMethod "$u/api/login" -Method Post @json -Body ([Text.Encoding]::UTF8.GetBytes((@{ empleadoId = $emp.empleado.id; pin = $emp.pinInicial } | ConvertTo-Json)))
        Invoke-RestMethod "$u/api/pin" -Method Post -Headers @{ Authorization = "Bearer $($lg.token)" } @json -Body ([Text.Encoding]::UTF8.GetBytes((@{ pinActual = $emp.pinInicial; pinNuevo = '4321' } | ConvertTo-Json))) | Out-Null

        $panel = NuevoPanel 'e3' $srv.Url
        $pidA = $panel.Proceso.Id
        $w = $null
        Esperar 30 { $script:w = Ventana $panel.Proceso; [bool]$script:w } | Out-Null
        $w = Ventana $panel.Proceso
        function Elem($id) { $w.FindFirst('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::AutomationIdProperty, $id))) }
        function Elegir($comboId, $texto) {
            $cb = Elem $comboId
            $cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
            $hit = $null
            foreach ($i in 1..30) {
                Start-Sleep -Milliseconds 500
                if ($cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Current.ExpandCollapseState -ne 'Expanded') { $cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand() }
                $hit = $cb.FindAll('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::ControlTypeProperty, [System.Windows.Automation.ControlType]::ListItem))) | Where-Object { $_.Current.Name -like "*$texto*" } | Select-Object -First 1
                if ($hit) { break }
            }
            if (-not $hit) { throw "No encontré '$texto' en $comboId" }
            $hit.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
            Start-Sleep -Milliseconds 300
            try { $cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Collapse() } catch { }
        }
        Elegir 'CmbUsuario' 'Probador Act'
        foreach ($intento in 1..3) {
            $tp = Elem 'TxtPin'
            if (-not $tp -or $tp.Current.IsOffscreen) { break }
            [void][WinUpd]::SetForegroundWindow([IntPtr]$w.Current.NativeWindowHandle)
            $tp.SetFocus(); Start-Sleep -Milliseconds 500
            [System.Windows.Forms.SendKeys]::SendWait('^a{BACKSPACE}'); [System.Windows.Forms.SendKeys]::SendWait('4321')
            Start-Sleep -Seconds 3
        }
        Elegir 'CmbObra' 'Senillosa'
        (Elem 'BtnPlay').GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke()
        Start-Sleep -Seconds 3
        $vivo = Invoke-RestMethod "$u/api/admin/en-vivo" -Headers $h
        Verificar (@($vivo).Count -eq 1) 'Hay un registro en curso en el servidor'

        Verificar (Esperar 60 { Test-Path "$($panel.Exe).nuevo" }) 'Mientras registra, descarga la versión nueva en segundo plano'
        Start-Sleep -Seconds 40
        Verificar ($null -ne (Get-Process -Id $pidA -ErrorAction SilentlyContinue)) 'NO se reinició con el cronómetro andando (mismo proceso)'
        Verificar ((Hash $panel.Exe) -eq $hashA) 'El Play.exe en uso sigue siendo el original'
        Verificar (@(Invoke-RestMethod "$u/api/admin/en-vivo" -Headers $h).Count -eq 1) 'El registro sigue corriendo sin interrupciones'

        # el empleado cierra el programa y lo vuelve a abrir: se instala la versión ya descargada al arrancar
        Stop-Process -Id $pidA -Force; Start-Sleep -Seconds 2
        $panel.Proceso = Start-Process $panel.Exe -ArgumentList '--datos', "`"$($panel.Datos)`"", '--permitir-actualizacion' -PassThru
        $pid2 = $panel.Proceso.Id
        $listo = Esperar 90 { $p = PanelActual $panel; $p -and $p.Id -ne $pid2 -and $p.MainModule.FileVersionInfo.FileVersion -eq $verB }
        Verificar $listo 'Al reabrir, instala la versión ya descargada y arranca con la nueva'
        Verificar ((Hash $panel.Exe) -eq $hashB) 'El Play.exe del disco es la versión publicada'
        Limpiar
    }

    Paso ""
    if ($script:fallos -eq 0) { Paso 'TODO CORRECTO' } else { Paso "HUBO $($script:fallos) FALLA(S)" }
}
finally {
    Limpiar
}
if ($script:fallos -gt 0) { exit 1 }
