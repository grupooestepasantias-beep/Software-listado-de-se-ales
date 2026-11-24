# Prueba de punta a punta: abre el panel REAL y lo maneja con UI Automation contra un servidor real (puerto 8096, datos temporales).
# Verifica que se pueda escribir el PIN, Play, latidos y Pause. Requiere haber compilado (dotnet build) y no tocar el mouse/teclado mientras corre.
$ErrorActionPreference = 'Stop'
$base = Join-Path $env:TEMP 'play-e2e'
Remove-Item $base -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory "$base\srv", "$base\panel" | Out-Null
$repo = Resolve-Path (Join-Path $PSScriptRoot '..')
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms, System.Drawing
$log = @()
function Paso($t) { $script:log += $t; Write-Output $t }

# ---- servidor real en puerto 8096 con datos temporales
$env:Play__DataDir = "$base\srv"; $env:Urls = 'http://127.0.0.1:8096'
$srv = Start-Process dotnet -ArgumentList "$repo\src\Play.Server\bin\Debug\net8.0\Play.Server.dll" -PassThru -WindowStyle Hidden
Remove-Item Env:Play__DataDir, Env:Urls
foreach ($i in 1..30) { Start-Sleep -Milliseconds 500; try { Invoke-RestMethod http://127.0.0.1:8096/api/estado | Out-Null; break } catch { } }
$u = 'http://127.0.0.1:8096'

try {
    # ---- preparar un empleado con PIN ya elegido (4321)
    $acc = Get-Content "$base\srv\accesos_iniciales.txt" -Raw
    $clave = [regex]::Match($acc, 'Clave temporal: (\S+)').Groups[1].Value
    $adm = Invoke-RestMethod "$u/api/admin/login" -Method Post -ContentType 'application/json' -Body (@{ usuario = 'Gabriel'; password = $clave } | ConvertTo-Json)
    $h = @{ Authorization = "Bearer $($adm.token)" }
    Invoke-RestMethod "$u/api/admin/clave" -Method Post -Headers $h -ContentType 'application/json' -Body (@{ claveActual = $clave; claveNueva = 'ClaveNueva-123' } | ConvertTo-Json) | Out-Null
    $nuevo = Invoke-RestMethod "$u/api/admin/empleados" -Method Post -Headers $h -ContentType 'application/json' -Body (@{ nombre = 'Probador Uno' } | ConvertTo-Json)
    $login = Invoke-RestMethod "$u/api/login" -Method Post -ContentType 'application/json' -Body (@{ empleadoId = $nuevo.empleado.id; pin = $nuevo.pinInicial } | ConvertTo-Json)
    Invoke-RestMethod "$u/api/pin" -Method Post -Headers @{ Authorization = "Bearer $($login.token)" } -ContentType 'application/json' -Body (@{ pinActual = $nuevo.pinInicial; pinNuevo = '4321' } | ConvertTo-Json) | Out-Null
    Paso "Empleado de prueba creado (id $($nuevo.empleado.id)) con PIN definitivo."

    # ---- panel real, con carpeta de datos aislada (no toca %AppData% ni el registro de Windows)
    '{"servidorUrl":"http://127.0.0.1:8096","primeraEjecucionHecha":true}' | Set-Content "$base\panel\ajustes.json" -Encoding UTF8
    $panel = Start-Process "$repo\src\Play.Panel\bin\Debug\net8.0-windows\Play.exe" -ArgumentList '--datos', "`"$base\panel`"" -PassThru
    $win = $null
    foreach ($i in 1..30) {
        Start-Sleep -Milliseconds 500
        $c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ProcessIdProperty, $panel.Id)
        $win = [System.Windows.Automation.AutomationElement]::RootElement.FindFirst('Children', $c)
        if ($win) { break }
    }
    if (-not $win) { throw 'No apareciÃ³ la ventana del panel.' }
    Paso 'Panel abierto.'
    Start-Sleep -Seconds 2

    function Elem($id) {
        $c = New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::AutomationIdProperty, $id)
        $win.FindFirst('Descendants', $c)
    }
    function ElegirItem($comboId, $texto) {
        $cb = Elem $comboId
        $cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
        $hit = $null; $items = @()
        foreach ($intento in 1..40) {   # si el servidor tarda en responder, el panel reintenta cada 10 s: se espera hasta ~20 s
            Start-Sleep -Milliseconds 500
            if ($cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Current.ExpandCollapseState -ne 'Expanded') {
                $cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
            }
            $items = $cb.FindAll('Descendants', (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::ListItem)))
            foreach ($it in $items) { if ($it.Current.Name -like "*$texto*") { $hit = $it; break } }
            if ($hit) { break }
        }
        if (-not $hit) {
            $r = $win.Current.BoundingRectangle
            $bmp = New-Object System.Drawing.Bitmap([int]$r.Width, [int]$r.Height)
            [System.Drawing.Graphics]::FromImage($bmp).CopyFromScreen([int]$r.X, [int]$r.Y, 0, 0, $bmp.Size)
            $bmp.Save("$base\fallo-$comboId.png")
            $enServidor = (Invoke-RestMethod "$u/api/obras" | ForEach-Object { $_.nombre }) -join ', '
            throw "No encontré '$texto' en $comboId (items: $($items.Count), habilitado: $($cb.Current.IsEnabled), estado: $($cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Current.ExpandCollapseState); obras en el servidor: $enServidor). Captura en $base\fallo-$comboId.png"
        }
        $hit.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
        Start-Sleep -Milliseconds 400
        try { $cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Collapse() } catch { }
    }

    ElegirItem 'CmbUsuario' 'Probador Uno'
    Paso 'Usuario elegido; aparece el campo PIN.'
    # SendKeys a veces pierde la primera tecla justo después de cambiar el foco: se reintenta (si entró, el campo PIN desaparece)
    foreach ($intento in 1..3) {
        $tp = Elem 'TxtPin'
        if (-not $tp -or $tp.Current.IsOffscreen) { break }
        $tp.SetFocus()
        Start-Sleep -Milliseconds 500
        [System.Windows.Forms.SendKeys]::SendWait('^a{BACKSPACE}')
        [System.Windows.Forms.SendKeys]::SendWait('4321')
        Start-Sleep -Seconds 3
    }
    $obra = Elem 'CmbObra'
    Paso "Tras el PIN, el selector de obra estÃ¡ disponible: $([bool]$obra -and -not $obra.Current.IsOffscreen)"

    ElegirItem 'CmbObra' 'Senillosa'
    ([System.Windows.Automation.InvokePattern]$((Elem 'BtnPlay').GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern))).Invoke()
    Paso 'Play presionado.'
    Start-Sleep -Seconds 4

    $b = $win.Current.BoundingRectangle
    $bmp = New-Object System.Drawing.Bitmap([int]$b.Width, [int]$b.Height)
    [System.Drawing.Graphics]::FromImage($bmp).CopyFromScreen([int]$b.X, [int]$b.Y, 0, 0, $bmp.Size)
    $bmp.Save("$base\pantalla-registrando.png")

    $vivo = Invoke-RestMethod "$u/api/admin/en-vivo" -Headers $h
    Paso "En vivo en el servidor: $(($vivo | ForEach-Object { "$($_.empleado) en $($_.obra) desde $($_.equipo)" }) -join '; ')"

    Start-Sleep -Seconds 33   # al menos un latido
    ([System.Windows.Automation.InvokePattern]$((Elem 'BtnPlay').GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern))).Invoke()
    Paso 'Pause presionado.'
    Start-Sleep -Seconds 2
    $regs = Invoke-RestMethod "$u/api/admin/registros?empleadoId=$($nuevo.empleado.id)" -Headers $h
    foreach ($r in $regs) { Paso "Registro: $($r.estado), $($r.segundos) s, obra $($r.obra), equipo $($r.equipo)" }

    # ---- un empleado creado por el administrador aparece SIN reiniciar el panel (al desplegar el menú de usuarios)
    $otro = Invoke-RestMethod "$u/api/admin/empleados" -Method Post -Headers $h -ContentType 'application/json' -Body (@{ nombre = 'Recien Creado' } | ConvertTo-Json)
    # el panel refresca las listas solo (cada 30 s): se espera hasta 50 s a que aparezca en el menú
    $aparecio = $false
    $reloj = [Diagnostics.Stopwatch]::StartNew()
    while (-not $aparecio -and $reloj.Elapsed.TotalSeconds -lt 50) {
        Start-Sleep -Seconds 4
        $cb = Elem 'CmbUsuario'
        $cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
        Start-Sleep -Milliseconds 1200
        $items = $cb.FindAll('Descendants', (New-Object System.Windows.Automation.PropertyCondition([System.Windows.Automation.AutomationElement]::ControlTypeProperty, [System.Windows.Automation.ControlType]::ListItem)))
        foreach ($it in $items) { if ($it.Current.Name -like '*Recien Creado*') { $aparecio = $true } }
        try { $cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Collapse() } catch { }
    }
    Paso "Empleado creado con el panel abierto aparece en el menú ($([int]$reloj.Elapsed.TotalSeconds) s): $aparecio"
    if (-not $aparecio) { throw 'El empleado nuevo no apareció en el panel sin reiniciarlo.' }

    # ---- volver a abrir Play.exe con el panel ya abierto: no abre otro, avisa al que está corriendo
    $segunda = Start-Process "$repo\src\Play.Panel\bin\Debug\net8.0-windows\Play.exe" -ArgumentList '--datos', "`"$base\panel`"" -PassThru
    [void]$segunda.WaitForExit(15000)
    Paso "Segunda copia terminó sola: $($segunda.HasExited); el panel original sigue abierto: $(-not $panel.HasExited)"

    # ---- cierre: el panel debe seguir vivo hasta que lo cerremos nosotros
    Paso "Panel sigue abierto: $(-not $panel.HasExited)"
}
finally {
    if ($panel -and -not $panel.HasExited) { Stop-Process $panel.Id -Force }
    if ($srv -and -not $srv.HasExited) { Stop-Process $srv.Id -Force }
    if (Test-Path "$base\panel\errores.log") { Write-Output '--- errores.log del panel ---'; Get-Content "$base\panel\errores.log" | Select-Object -First 20 }
}
