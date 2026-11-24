# Prueba de punta a punta del programa de administración: abre PlayAdmin.exe REAL, ingresa con una clave temporal,
# cambia la clave (obligatorio), recorre las pestañas y guarda una captura de cada una. Servidor real temporal en el puerto 8093.
# Requiere haber compilado (dotnet build). No tocar el mouse/teclado mientras corre.
param(
    [string]$Salida = (Join-Path $env:TEMP 'play-e2e-admin'),
    [string]$Exe = ''   # por defecto el compilado en Debug; para probar el publicado: -Exe dist\admin\PlayAdmin.exe
)
$ErrorActionPreference = 'Stop'
$repo = Resolve-Path (Join-Path $PSScriptRoot '..')
if (-not $Exe) { $Exe = "$repo\src\Play.Admin\bin\Debug\net8.0-windows\PlayAdmin.exe" }
Remove-Item $Salida -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory "$Salida\srv", "$Salida\admin", "$Salida\capturas" | Out-Null
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes, System.Windows.Forms, System.Drawing
Add-Type @"
using System; using System.Runtime.InteropServices;
public static class Win { [DllImport("user32.dll")] public static extern bool SetForegroundWindow(IntPtr h); }
"@
$UIA = [System.Windows.Automation.AutomationElement]
function Paso($t) { Write-Output $t }
$script:fallos = 0
function Verificar($condicion, $texto) {
    if ($condicion) { Write-Output "  OK   $texto" } else { Write-Output "  FALLA $texto"; $script:fallos++ }
}

$env:Play__DataDir = "$Salida\srv"; $env:Urls = 'http://127.0.0.1:8093'
$srv = Start-Process dotnet -ArgumentList "$repo\src\Play.Server\bin\Debug\net8.0\Play.Server.dll" -PassThru -WindowStyle Hidden
Remove-Item Env:Play__DataDir, Env:Urls
foreach ($i in 1..30) { Start-Sleep -Milliseconds 500; try { Invoke-RestMethod http://127.0.0.1:8093/api/estado | Out-Null; break } catch { } }
$u = 'http://127.0.0.1:8093'
function Api($metodo, $ruta, $cuerpo, $h) {
    $p = @{ Uri = "$u$ruta"; Method = $metodo; ContentType = 'application/json; charset=utf-8' }
    if ($h) { $p.Headers = $h }
    # Windows PowerShell 5.1 no envía los acentos en UTF-8 por defecto: se mandan los bytes explícitamente.
    if ($null -ne $cuerpo) { $p.Body = [Text.Encoding]::UTF8.GetBytes(($cuerpo | ConvertTo-Json)) }
    try { Invoke-RestMethod @p }
    catch {
        $texto = ''
        if ($_.Exception.Response) { $texto = (New-Object IO.StreamReader($_.Exception.Response.GetResponseStream())).ReadToEnd() }
        throw "Falló $metodo $ruta -> $texto"
    }
}
function ApiLista($ruta) { $r = Api Get $ruta $null $h; foreach ($x in $r) { $x } }

try {
    # ---- datos de ejemplo por API
    $acc = Get-Content "$Salida\srv\accesos_iniciales.txt" -Raw
    $clave0 = [regex]::Match($acc, 'Clave temporal: (\S+)').Groups[1].Value
    $t = (Api Post '/api/admin/login' @{ usuario = 'Gabriel'; password = $clave0 }).token
    $h = @{ Authorization = "Bearer $t" }
    Api Post '/api/admin/clave' @{ claveActual = $clave0; claveNueva = 'ClaveNueva-123' } $h | Out-Null
    $emps = Api Get '/api/admin/empleados' $null $h
    $obras = Api Get '/api/admin/obras' $null $h
    $ahora = [DateTime]::UtcNow
    foreach ($e in $emps) {
        foreach ($d in 1..3) {
            $ini = $ahora.Date.AddDays(-$d).AddHours(11)
            Api Post '/api/admin/registros' @{ empleadoId = $e.id; obraId = $obras[$d % 2].id; inicioUtc = $ini.ToString('o'); finUtc = $ini.AddHours(4 + $d).ToString('o'); motivo = 'Datos de ejemplo' } $h | Out-Null
        }
    }
    $primero = (Api Get "/api/admin/registros?empleadoId=$($emps[0].id)" $null $h)[0]
    Api Put "/api/admin/registros/$($primero.id)" @{ finUtc = ([DateTime]$primero.finUtc).AddMinutes(-30).ToString('o'); motivo = 'Se olvidó de pausar' } $h | Out-Null
    Api Post '/api/admin/empleados' @{ nombre = 'Marcos Taller'; area = 'Taller' } $h | Out-Null
    Api Post '/api/admin/empleados' @{ nombre = 'Lucas Taller'; area = 'Taller' } $h | Out-Null
    $seg = Api Post '/api/admin/administradores' @{ usuario = 'Prueba'; nombreCompleto = 'Administrador de prueba' } $h
    Paso "Datos de ejemplo creados. Administrador 'Prueba' con clave temporal."

    # ---- abrir el programa real
    '{"servidorUrl":"http://127.0.0.1:8093"}' | Set-Content "$Salida\admin\ajustes.json" -Encoding UTF8
    $app = Start-Process $Exe -ArgumentList '--datos', "`"$Salida\admin`"" -PassThru

    function Ventanas() {
        $c = New-Object System.Windows.Automation.PropertyCondition($UIA::ProcessIdProperty, $app.Id)
        $UIA::RootElement.FindAll('Children', $c)
    }
    function EsperarVentana($titulo, $seg = 20) {
        foreach ($i in 1..($seg * 4)) {
            foreach ($w in (Ventanas)) {
                if ($w.Current.Name -eq $titulo) { return $w }
                # las ventanas de diálogo aparecen dentro de su ventana "dueña" en el árbol de UI Automation
                $hijas = New-Object System.Windows.Automation.AndCondition(
                    (New-Object System.Windows.Automation.PropertyCondition($UIA::ControlTypeProperty, [System.Windows.Automation.ControlType]::Window)),
                    (New-Object System.Windows.Automation.PropertyCondition($UIA::NameProperty, $titulo)))
                $d = $w.FindFirst('Descendants', $hijas)
                if ($d) { return $d }
            }
            Start-Sleep -Milliseconds 250
        }
        throw "No apareció la ventana '$titulo'"
    }
    function Foco($w) { [void][Win]::SetForegroundWindow([IntPtr]$w.Current.NativeWindowHandle); Start-Sleep -Milliseconds 300 }
    function Buscar($w, $tipo, $nombre) {
        $conds = @(New-Object System.Windows.Automation.PropertyCondition($UIA::ControlTypeProperty, $tipo))
        if ($nombre) { $conds += New-Object System.Windows.Automation.PropertyCondition($UIA::NameProperty, $nombre) }
        $cond = if ($conds.Count -gt 1) { New-Object System.Windows.Automation.AndCondition($conds) } else { $conds[0] }
        $w.FindFirst('Descendants', $cond)
    }
    function Clic($w, $nombre) { $b = Buscar $w ([System.Windows.Automation.ControlType]::Button) $nombre; if (-not $b) { throw "No hay botón '$nombre'" }; $b.GetCurrentPattern([System.Windows.Automation.InvokePattern]::Pattern).Invoke() }
    function Captura($w, $nombre) {
        Foco $w
        $r = $w.Current.BoundingRectangle
        if ($r.Width -lt 300 -or $r.Height -lt 200) { Paso "  AVISO: la captura '$nombre' tiene tamaño raro: $r" }
        $bmp = New-Object System.Drawing.Bitmap([int]$r.Width, [int]$r.Height)
        [System.Drawing.Graphics]::FromImage($bmp).CopyFromScreen([int]$r.X, [int]$r.Y, 0, 0, $bmp.Size)
        $bmp.Save("$Salida\capturas\$nombre.png")
    }

    $login = EsperarVentana 'Play · Administración'
    Paso 'Ventana de ingreso abierta.'
    Foco $login
    $edits = $login.FindAll('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)))
    # El usuario se pone con el patrón de valor de UI Automation (no depende del foco); la clave, al ser PasswordBox, se teclea.
    $edits[0].GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue('Prueba')
    $edits[1].SetFocus(); [System.Windows.Forms.SendKeys]::SendWait($seg.claveTemporal)
    Start-Sleep -Milliseconds 300
    Captura $login '01-ingreso'
    Clic $login 'Ingresar'
    Start-Sleep -Seconds 2
    Captura $login '01b-despues-de-ingresar'

    $cambio = EsperarVentana 'Elegí tu clave'
    Paso 'Pidió elegir una clave nueva (clave temporal obligatoria).'
    Foco $cambio
    $pw = $cambio.FindAll('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::ControlTypeProperty, [System.Windows.Automation.ControlType]::Edit)))
    $pw[0].SetFocus(); [System.Windows.Forms.SendKeys]::SendWait('MiClave-2026')
    $pw[1].SetFocus(); [System.Windows.Forms.SendKeys]::SendWait('MiClave-2026')
    Captura $cambio '02-clave-nueva'
    Clic $cambio 'Guardar clave'

    # el título de la ventana de ingreso y de la principal es el mismo: se espera a que aparezca el TabControl
    $principal = $null
    foreach ($i in 1..60) {
        Start-Sleep -Milliseconds 250
        foreach ($w in (Ventanas)) { if ($w.Current.Name -eq 'Play · Administración' -and (Buscar $w ([System.Windows.Automation.ControlType]::Tab) $null)) { $principal = $w } }
        if ($principal) { break }
    }
    if (-not $principal) { throw 'No se abrió la ventana principal.' }
    Paso 'Ventana principal abierta tras cambiar la clave.'
    Start-Sleep -Seconds 2

    foreach ($pestana in 'En vivo', 'Registros', 'Horas de Taller', 'Asistencia', 'Faltas', 'Empleados', 'Obras', 'Avisos', 'Administradores', 'Auditoría', 'Sistema') {
        $item = Buscar $principal ([System.Windows.Automation.ControlType]::TabItem) $pestana
        $item.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
        Start-Sleep -Milliseconds 1500
        if ($pestana -eq 'Registros') { Clic $principal 'Actualizar'; Start-Sleep -Milliseconds 1500 }
        Captura $principal ("03-" + $pestana.ToLower().Replace(' ', '-').Replace('í', 'i'))
        Paso "Pestaña '$pestana' capturada."
    }
    # ================= Subtareas (tachadas) y avisos «terminé esta subtarea» =================
    $TabT = [System.Windows.Automation.ControlType]::TabItem
    function Pestana($nombre) { (Buscar $principal $TabT $nombre).GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select(); Start-Sleep -Milliseconds 1500 }
    function Filas2($id) {
        $g = $principal.FindFirst('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::AutomationIdProperty, $id)))
        @($g.FindAll('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::ControlTypeProperty, [System.Windows.Automation.ControlType]::DataItem))))
    }
    $obraSen = @($obras | Where-Object { $_.nombre -eq 'Senillosa' })[0]
    $st = @{}
    foreach ($n in 'Fundación', 'Estructura', 'Terminaciones') { $st[$n] = Api Post "/api/admin/obras/$($obraSen.id)/subtareas" @{ nombre = $n } $h }
    Api Put "/api/admin/subtareas/$($st['Fundación'].id)" @{ terminada = $true } $h | Out-Null
    $pinS = (Api Post "/api/admin/empleados/$($emps[0].id)/reset-pin" $null $h).pinInicial
    $tokS = (Api Post '/api/login' @{ empleadoId = $emps[0].id; pin = $pinS }).token
    Api Post "/api/subtareas/$($st['Estructura'].id)/avisar" $null @{ Authorization = "Bearer $tokS" } | Out-Null

    Pestana 'Registros'; Pestana 'Obras'   # al entrar se recarga la lista
    $filasObras = Filas2 'GridObras'
    $filasObras[1].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()   # Ape, Senillosa (orden por nombre)
    Start-Sleep -Seconds 2
    Verificar ((Filas2 'GridSubtareas').Count -eq 3) 'Obras: al elegir Senillosa se ven sus 3 subtareas'
    Captura $principal '03b-obras-subtareas-tachada'

    Verificar ([bool](Buscar $principal $TabT 'Avisos (1)')) 'Avisos: la pestaña muestra el contador «Avisos (1)»'
    Pestana 'Avisos (1)'
    Verificar ((Filas2 'GridAvisos').Count -eq 1) 'Avisos: aparece el aviso del empleado'
    Captura $principal '03c-avisos'
    (Filas2 'GridAvisos')[0].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    Clic $principal 'Marcar subtarea terminada…'
    $dlgAv = EsperarVentana 'Confirmar'
    Clic $dlgAv 'Sí'
    Start-Sleep -Seconds 2
    $subsAhora = Api Get "/api/admin/obras/$($obraSen.id)/subtareas" $null $h
    Verificar (@($subsAhora | Where-Object { $_.terminada }).Count -eq 2) 'Avisos: al aceptar el aviso, «Estructura» queda terminada (2 tachadas)'
    Verificar (@(ApiLista '/api/admin/avisos').Count -eq 0) 'Avisos: ya no quedan avisos sin revisar'
    Verificar ([bool](Buscar $principal $TabT 'Avisos')) 'Avisos: el contador de la pestaña desaparece'
    Captura $principal '03d-avisos-resuelto'

    # ================= Horas de Taller (cargadas por empleados de Taller) =================
    $empsT = Api Get '/api/admin/empleados?area=Taller' $null $h
    $pinT = (Api Post "/api/admin/empleados/$($empsT[0].id)/reset-pin" $null $h).pinInicial
    $hT = @{ Authorization = "Bearer $((Api Post '/api/login' @{ empleadoId = $empsT[0].id; pin = $pinT }).token)" }
    $hoyT = (Api Get '/api/horas' $null $hT).hoy
    Api Post '/api/horas' @{ fecha = $hoyT; minutos = 480 } $hT | Out-Null
    Api Post '/api/horas' @{ fecha = ([DateTime]$hoyT).AddDays(-1).ToString('yyyy-MM-dd'); minutos = 450 } $hT | Out-Null
    Pestana 'Horas de Taller'
    Verificar ((Filas2 'GridHoras').Count -eq 2) 'Horas de Taller: la pestaña muestra las 2 cargas del empleado'
    Captura $principal '03e-horas-de-taller'
    (Filas2 'GridHoras')[0].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    Clic $principal 'Eliminar horas…'
    $dlgH = EsperarVentana 'Eliminar horas'
    Captura $dlgH '03f-eliminar-horas'
    Clic $dlgH 'Cancelar'
    Start-Sleep -Seconds 1
    Verificar ((Filas2 'GridHoras').Count -eq 2) 'Horas de Taller: al cancelar no se elimina nada'

    # ================= Asistencia (libro mensual) y Faltas =================
    Pestana 'Asistencia'
    $mesApi = Api Get "/api/admin/asistencia?anio=$((Get-Date).Year)&mes=$((Get-Date).Month)" $null $h
    $nFilas = @($mesApi.filas).Count
    Verificar ($nFilas -gt 0 -and (Filas2 'GridAsistencia').Count -eq $nFilas) "Asistencia: el libro del mes muestra a los $nFilas empleados"
    Captura $principal '03g-asistencia'
    Pestana 'Faltas'
    Verificar ([bool](Buscar $principal ([System.Windows.Automation.ControlType]::Button) 'Justificar…')) 'Faltas: está el botón «Justificar…»'
    Captura $principal '03h-faltas'

    # ================= Filtros automáticos + eliminar / recuperar (solo con patrones de UI Automation: no se teclea nada) =================
    $Tab = [System.Windows.Automation.ControlType]::TabItem
    ($principal | ForEach-Object { (Buscar $_ $Tab 'Registros').GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select() })
    Start-Sleep -Seconds 2
    function Elem($id) { $principal.FindFirst('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::AutomationIdProperty, $id))) }
    function Filas() {
        $g = Elem 'GridRegistros'
        if (-not $g) { return @() }
        @($g.FindAll('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::ControlTypeProperty, [System.Windows.Automation.ControlType]::DataItem))))
    }
    function EsperarFilas($esperadas, $seg = 8) {
        foreach ($i in 1..($seg * 4)) { if ((Filas).Count -eq $esperadas) { return $true }; Start-Sleep -Milliseconds 250 }
        return $false
    }
    function ElegirEn($id, $texto) {
        $cb = Elem $id
        $cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Expand()
        Start-Sleep -Milliseconds 600
        $it = $cb.FindAll('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::ControlTypeProperty, [System.Windows.Automation.ControlType]::ListItem))) | Where-Object { $_.Current.Name -like "*$texto*" } | Select-Object -First 1
        if (-not $it) { throw "No encontré '$texto' en $id" }
        $it.GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
        Start-Sleep -Milliseconds 300
        try { $cb.GetCurrentPattern([System.Windows.Automation.ExpandCollapsePattern]::Pattern).Collapse() } catch { }
    }
    $hoy = (Get-Date).ToString('yyyy-MM-dd'); $desde = (Get-Date).AddDays(-7).ToString('yyyy-MM-dd')
    $esperaTotal = @(ApiLista "/api/admin/registros?desde=$desde&hasta=$hoy").Count
    if (-not (EsperarFilas $esperaTotal)) { throw "Sin filtros se esperaban $esperaTotal filas y hay $((Filas).Count)." }
    Paso "Filtros: sin filtrar hay $esperaTotal registros (coincide con el servidor)."

    $idEzequiel = ($emps | Where-Object { $_.nombre -eq 'Ezequiel' }).id
    ElegirEn 'CmbFEmpleado' 'Ezequiel'                      # sin apretar Buscar
    $esperaEmp = @(ApiLista "/api/admin/registros?empleadoId=$idEzequiel&desde=$desde&hasta=$hoy").Count
    if (-not (EsperarFilas $esperaEmp)) { throw "Al elegir empleado se esperaban $esperaEmp filas y hay $((Filas).Count)." }
    Paso "Filtros: al elegir el empleado (sin apretar Buscar) quedan $esperaEmp registros: solo los de Ezequiel."

    $idApe = ($obras | Where-Object { $_.nombre -eq 'Ape' }).id
    ElegirEn 'CmbFObra' 'Ape'
    $esperaObra = @(ApiLista "/api/admin/registros?empleadoId=$idEzequiel&obraId=$idApe&desde=$desde&hasta=$hoy").Count
    if (-not (EsperarFilas $esperaObra)) { throw "Al elegir obra se esperaban $esperaObra filas y hay $((Filas).Count)." }
    Paso "Filtros: empleado + obra dan $esperaObra registro(s), igual que el servidor."
    Captura $principal '04-filtros-empleado-y-obra'

    Clic $principal 'Limpiar filtros'
    if (-not (EsperarFilas $esperaTotal)) { throw "Tras limpiar filtros se esperaban $esperaTotal filas y hay $((Filas).Count)." }
    Paso "Filtros: 'Limpiar filtros' vuelve a mostrar los $esperaTotal registros."

    # --- eliminar con motivo (se elige la fila más vieja: las primeras pueden ser horas de Taller, que se eliminan en su propia pestaña)
    (Filas)[-1].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    Clic $principal 'Eliminar…'
    $dlg = EsperarVentana 'Eliminar registro'
    $motivo = $dlg.FindFirst('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::AutomationIdProperty, 'TxtMotivo')))
    Clic $dlg 'Eliminar'                                      # sin motivo: no debe dejar
    Start-Sleep -Milliseconds 600
    if ((Filas).Count -ne $esperaTotal) { throw 'Eliminó un registro sin pedir el motivo.' }
    $motivo.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue('Prueba automatica de eliminacion')
    Captura $dlg '05-eliminar-registro'
    Clic $dlg 'Eliminar'
    if (-not (EsperarFilas ($esperaTotal - 1))) { throw "Tras eliminar se esperaban $($esperaTotal - 1) filas y hay $((Filas).Count)." }
    Paso "Eliminar: sin motivo no deja; con motivo el registro desaparece de la lista ($($esperaTotal - 1) restantes)."
    $enServidor = @(ApiLista "/api/admin/registros?eliminados=true&desde=$desde&hasta=$hoy")
    Paso "Eliminar: el servidor lo conserva marcado como eliminado ($($enServidor.Count) en la lista de eliminados; no se borró)."
    if ($enServidor.Count -ne 1) { throw 'El registro eliminado no figura en la lista de eliminados del servidor.' }

    # --- ver eliminados y recuperar
    $chk = Elem 'ChkEliminados'
    $chk.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Toggle()
    if (-not (EsperarFilas 1)) { throw "Con 'Ver eliminados' se esperaba 1 fila y hay $((Filas).Count)." }
    Captura $principal '06-ver-eliminados'
    (Filas)[0].GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select()
    Clic $principal 'Recuperar…'
    $dlg2 = EsperarVentana 'Recuperar registro'
    $dlg2.FindFirst('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::AutomationIdProperty, 'TxtMotivo'))).GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern).SetValue('Estaba bien')
    Clic $dlg2 'Recuperar'
    if (-not (EsperarFilas 0)) { throw 'Tras recuperar, la lista de eliminados debería quedar vacía.' }
    $chk.GetCurrentPattern([System.Windows.Automation.TogglePattern]::Pattern).Toggle()
    if (-not (EsperarFilas $esperaTotal)) { throw "Tras recuperar se esperaban $esperaTotal filas y hay $((Filas).Count)." }
    Paso "Recuperar: el registro vuelve a la lista normal ($esperaTotal registros)."
    $aud = @(ApiLista '/api/admin/auditoria' | Where-Object { $_.campo -in 'anulado', 'restaurado' })
    Paso "Historial: quedaron $($aud.Count) constancias ($(($aud | ForEach-Object { $_.campo + ' - ' + $_.motivo }) -join '; '))."

    # ================= Áreas y PIN visibles (Empleados) =================
    ($principal | ForEach-Object { (Buscar $_ $Tab 'Empleados').GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select() })
    function FilasDe($id) {
        $g = Elem $id
        @($g.FindAll('Descendants', (New-Object System.Windows.Automation.PropertyCondition($UIA::ControlTypeProperty, [System.Windows.Automation.ControlType]::DataItem))))
    }
    function EsperarFilasDe($id, $esperadas, $seg = 8) {
        foreach ($i in 1..($seg * 4)) { if ((FilasDe $id).Count -eq $esperadas) { return $true }; Start-Sleep -Milliseconds 250 }
        return $false
    }
    $totalEmp = @(ApiLista '/api/admin/empleados').Count
    $tallerEmp = @(ApiLista '/api/admin/empleados?area=Taller').Count
    Verificar (EsperarFilasDe 'GridEmpleados' $totalEmp) "Empleados: sin filtro se ven los $totalEmp"
    ElegirEn 'CmbEmpArea' 'Taller'
    Verificar (EsperarFilasDe 'GridEmpleados' $tallerEmp) "Empleados: al elegir el área Taller (sin apretar nada) se ven solo los $tallerEmp del taller"
    Captura $principal '07-empleados-taller'
    ElegirEn 'CmbEmpArea' 'Todas'
    Verificar (EsperarFilasDe 'GridEmpleados' $totalEmp) 'Empleados: volver a (Todas) muestra todos'

    $antes = @(ApiLista '/api/admin/auditoria' | Where-Object { $_.campo -eq 'pines_consultados' }).Count
    Clic $principal 'Mostrar PIN'
    $dlgPin = EsperarVentana 'Mostrar PIN'
    Clic $dlgPin 'Sí'
    Start-Sleep -Seconds 2
    $despues = @(ApiLista '/api/admin/auditoria' | Where-Object { $_.campo -eq 'pines_consultados' }).Count
    Verificar ($despues -eq $antes + 1) 'PIN: al tocar «Mostrar PIN» queda UNA constancia en el historial'
    Captura $principal '08-pin-visibles'
    $btnOcultar = Buscar $principal ([System.Windows.Automation.ControlType]::Button) 'Ocultar PIN'
    Verificar ([bool]$btnOcultar) 'PIN: el botón pasa a «Ocultar PIN»'
    if ($btnOcultar) { Clic $principal 'Ocultar PIN' }
    Verificar ([bool](Buscar $principal ([System.Windows.Automation.ControlType]::Button) 'Mostrar PIN')) 'PIN: al ocultar vuelve a «Mostrar PIN»'

    # el filtro de área también existe en Registros y En vivo
    ($principal | ForEach-Object { (Buscar $_ $Tab 'Registros').GetCurrentPattern([System.Windows.Automation.SelectionItemPattern]::Pattern).Select() })
    Start-Sleep -Seconds 1
    ElegirEn 'CmbFArea' 'Taller'
    Verificar (EsperarFilas 2) 'Registros: el área Taller muestra solo sus 2 cargas de horas (los registros de ejemplo son de Oficina)'
    ElegirEn 'CmbFArea' 'Oficina'
    Verificar (EsperarFilas ($esperaTotal - 2)) "Registros: el área Oficina muestra los $($esperaTotal - 2) registros del cronómetro (sin las cargas de Taller)"
    Captura $principal '09-registros-area'

    if ($script:fallos -gt 0) { Paso "HUBO $($script:fallos) FALLA(S) en las comprobaciones." } else { Paso 'Todas las comprobaciones de la ventana dieron OK.' }
    Paso "Capturas en $Salida\capturas"
}
finally {
    if ($app -and -not $app.HasExited) { Stop-Process -Id $app.Id -Force }
    if ($srv -and -not $srv.HasExited) { Stop-Process $srv.Id -Force }
    if (Test-Path "$Salida\admin\errores.log") { Write-Output '--- errores.log ---'; Get-Content "$Salida\admin\errores.log" | Select-Object -First 25 }
}
