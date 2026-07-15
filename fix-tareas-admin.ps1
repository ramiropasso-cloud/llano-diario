# LLANO - Arreglar tareas para correr SIN sesion interactiva
# Ejecutar este script UNA VEZ como Administrador (click derecho → Ejecutar como administrador)

$RUTA = "C:\Users\Usuario\Desktop\LLANO-DIARIO-IA"
$SCRIPT = "$RUTA\llano-auto.ps1"
$CMD = "powershell.exe -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$SCRIPT`""
$USUARIO = "DESKTOP-QS5LQVE\Usuario"

Write-Host "=== LLANO - Configuracion de tareas automaticas ===" -ForegroundColor Cyan
Write-Host "Este script recrea las 4 tareas para correr AUNQUE la pantalla este bloqueada."
Write-Host ""

# Pedir contrasena del usuario (necesaria para correr sin sesion interactiva)
$cred = Get-Credential -UserName $USUARIO -Message "Ingresa tu contrasena de Windows para guardar las tareas:"
if (-not $cred) {
    Write-Host "Cancelado." -ForegroundColor Red
    exit 1
}

$pass = $cred.GetNetworkCredential().Password

function CrearTarea($nombre, $hora, $dias) {
    # Eliminar tarea anterior si existe
    schtasks /delete /tn $nombre /f 2>$null | Out-Null

    $result = schtasks /create /tn $nombre /tr $CMD /sc WEEKLY /d $dias /st $hora /ru $USUARIO /rp $pass /rl HIGHEST /f 2>&1
    if ($LASTEXITCODE -eq 0) {
        Write-Host "  [OK] $nombre ($hora)" -ForegroundColor Green
    } else {
        Write-Host "  [ERROR] $nombre : $result" -ForegroundColor Red
    }
}

Write-Host "Creando tareas semanales (Lun-Sab)..."
CrearTarea "\LLANO-auto-7am"  "07:00" "MON,TUE,WED,THU,FRI,SAT"
CrearTarea "\LLANO-auto-11am" "11:00" "MON,TUE,WED,THU,FRI,SAT"
CrearTarea "\LLANO-auto-17hs" "17:00" "MON,TUE,WED,THU,FRI,SAT"

Write-Host ""
Write-Host "Creando watchdog (cada 20 minutos)..."
# El watchdog usa trigger de repeticion — mas complejo, usar XML
$xmlWatchdog = @"
<?xml version="1.0" encoding="UTF-16"?>
<Task version="1.2" xmlns="http://schemas.microsoft.com/windows/2004/02/mit/task">
  <Triggers>
    <TimeTrigger>
      <Repetition>
        <Interval>PT20M</Interval>
        <StopAtDurationEnd>false</StopAtDurationEnd>
      </Repetition>
      <StartBoundary>2026-06-13T06:00:00</StartBoundary>
      <Enabled>true</Enabled>
    </TimeTrigger>
  </Triggers>
  <Principals>
    <Principal id="Author">
      <UserId>$USUARIO</UserId>
      <LogonType>Password</LogonType>
      <RunLevel>HighestAvailable</RunLevel>
    </Principal>
  </Principals>
  <Settings>
    <MultipleInstancesPolicy>IgnoreNew</MultipleInstancesPolicy>
    <DisallowStartIfOnBatteries>false</DisallowStartIfOnBatteries>
    <StopIfGoingOnBatteries>false</StopIfGoingOnBatteries>
    <ExecutionTimeLimit>PT1H</ExecutionTimeLimit>
    <Enabled>true</Enabled>
  </Settings>
  <Actions Context="Author">
    <Exec>
      <Command>powershell.exe</Command>
      <Arguments>-ExecutionPolicy Bypass -WindowStyle Hidden -File "$SCRIPT"</Arguments>
    </Exec>
  </Actions>
</Task>
"@

$tmpXml = "$env:TEMP\llano-watchdog.xml"
$xmlWatchdog | Out-File -FilePath $tmpXml -Encoding Unicode

schtasks /delete /tn "\LLANO-watchdog" /f 2>$null | Out-Null
$result2 = schtasks /create /tn "\LLANO-watchdog" /xml $tmpXml /ru $USUARIO /rp $pass /f 2>&1
if ($LASTEXITCODE -eq 0) {
    Write-Host "  [OK] LLANO-watchdog (cada 20 minutos)" -ForegroundColor Green
} else {
    Write-Host "  [ERROR] watchdog: $result2" -ForegroundColor Red
}

Remove-Item $tmpXml -Force -ErrorAction SilentlyContinue

Write-Host ""
Write-Host "=== Verificando tareas creadas ===" -ForegroundColor Cyan
schtasks /query /fo TABLE 2>&1 | Select-String "LLANO"

Write-Host ""
Write-Host "Listo. Las 3 corridas diarias ahora corren aunque la pantalla este bloqueada." -ForegroundColor Green
Write-Host "Podes cerrar esta ventana." -ForegroundColor Gray
Read-Host "Presiona Enter para salir"
