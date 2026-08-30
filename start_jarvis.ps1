<# 
.SYNOPSIS
    Inicia todos los servicios de JARVIS/ULTRON en orden correcto.
.DESCRIPTION
    Levanta: Home Assistant MCP (8001), Calendar MCP (8002), Android MCP (8003),
    Web Interface (5000), Ultron Web (8766).
    Verifica dependencias y Ollama antes de arrancar.
#>

param(
    [switch]$SoloJarvis,      # Solo servicios base (sin Ultron)
    [switch]$SinMCP,          # No levantar MCP servers
    [switch]$ModoDesarrollo,  # Ventanas visibles para debug
    [string]$OllamaModel = "qwen3:4b-instruct"
)

$ErrorActionPreference = "Stop"
$PROJECT_ROOT = "C:\Users\ItsMarioGD\Downloads\jarvis definitivo"
$PYTHON = "python"
$VENV_PYTHON = "$PROJECT_ROOT\.venv\Scripts\python.exe"

# Colores para output
$GREEN = [ConsoleColor]::Green
$YELLOW = [ConsoleColor]::Yellow
$RED = [ConsoleColor]::Red
$CYAN = [ConsoleColor]::Cyan

function Write-Log($msg, $color = $CYAN) {
    $ts = Get-Date -Format "HH:mm:ss"
    Write-Host "[$ts] $msg" -ForegroundColor $color
}

function Test-Port($port) {
    $listener = New-Object System.Net.Sockets.TcpListener([System.Net.IPAddress]::IPv6Loopback, $port)
    try { $listener.Start(); $listener.Stop(); return $true } catch { return $false }
}

function Wait-Port($port, $timeoutSec = 10) {
    $sw = [Diagnostics.Stopwatch]::StartNew()
    while ($sw.Elapsed.TotalSeconds -lt $timeoutSec) {
        if (-not (Test-Port $port)) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

function Start-Service {
    param($name, $script, $port, $args = @(), $cwd = $PROJECT_ROOT)
    
    if (Test-Port $port) {
        Write-Log "$name ya corriendo en puerto $port" $YELLOW
        return $true
    }
    
    Write-Log "Iniciando $name en puerto $port..." $GREEN
    
    $pythonExe = if (Test-Path $VENV_PYTHON) { $VENV_PYTHON } else { $PYTHON }
    $scriptPath = Join-Path $cwd $script
    
    if (-not (Test-Path $scriptPath)) {
        Write-Log "No encontrado: $scriptPath" $RED
        return $false
    }
    
    $windowStyle = if ($ModoDesarrollo) { "Normal" } else { "Hidden" }
    $proc = Start-Process $pythonExe -ArgumentList @($scriptPath) + $args -WorkingDirectory $cwd -WindowStyle $windowStyle -PassThru
    
    if (Wait-Port $port 15) {
        Write-Log "$name LISTO (PID: $($proc.Id))" $GREEN
        return $true
    } else {
        Write-Log "$name NO respondió en puerto $port" $RED
        return $false
    }
}

# ─── MAIN ───
Write-Host "`n╔══════════════════════════════════════════════════════════════╗" -ForegroundColor $CYAN
Write-Host "║  JARVIS/ULTRON - LAUNCHER UNIFICADO                          ║" -ForegroundColor $CYAN
Write-Host "╚══════════════════════════════════════════════════════════════╝" -ForegroundColor $CYAN

# Verificar Python
if (-not (Get-Command $PYTHON -ErrorAction SilentlyContinue)) {
    Write-Log "Python no encontrado en PATH" $RED
    exit 1
}

# Verificar Ollama
Write-Log "Verificando Ollama..." $CYAN
try {
    $ollama = Invoke-RestMethod -Uri "http://localhost:11434/api/tags" -Method GET -TimeoutSec 3
    $modelos = $ollama.models.name -join ", "
    Write-Log "Ollama OK - Modelos: $modelos" $GREEN
    
    if ($ollama.models.name -notcontains $OllamaModel) {
        Write-Log "Modelo $OllamaModel no encontrado. Disponibles: $modelos" $YELLOW
    }
} catch {
    Write-Log "Ollama NO responde en localhost:11434" $RED
    Write-Log "Inicia Ollama: `ollama serve`" $YELLOW
    exit 1
}

# Verificar dependencias críticas
Write-Log "Verificando dependencias Python..." $CYAN
$deps = @("librosa", "piper_tts", "aiohttp", "mem0ai", "google.auth", "google_auth_oauthlib")
foreach ($dep in $deps) {
    $ok = & $PYTHON -c "import $dep" 2>$null
    if ($LASTEXITCODE -eq 0) { Write-Log "  $dep: OK" $GREEN } else { Write-Log "  $dep: FALTA (pip install $dep)" $YELLOW }
}

# Matar procesos previos en puertos nuestros
$puertos = @(5000, 8001, 8002, 8003, 8766)
foreach ($p in $puertos) {
    if (-not (Test-Port $p)) {
        $proc = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess
        if ($proc) { Stop-Process -Id $proc -Force -ErrorAction SilentlyContinue; Write-Log "Matado proceso en puerto $p" $YELLOW }
    }
}

$ok = $true

# 1. Home Assistant MCP
if (-not $SinMCP) {
    $ok = Start-Service "HA MCP" "mcp_servers\ha_server.py" 8001
}

# 2. Calendar MCP
if ($ok -and -not $SinMCP) {
    $ok = Start-Service "Calendar MCP" "mcp_servers\calendar_server.py" 8002
}

# 3. Android MCP
if ($ok -and -not $SinMCP) {
    $ok = Start-Service "Android MCP" "mcp_servers\android_server.py" 8003
}

# 4. Jarvis Web Interface
if ($ok) {
    $ok = Start-Service "Jarvis Web" "web_interface\app.py" 5000
}

# 5. Ultron Web Interface
if ($ok -and -not $SoloJarvis) {
    $ok = Start-Service "Ultron Web" "ultron_interface\app.py" 8766
}

# ─── RESUMEN ───
Write-Host "`n╔══════════════════════════════════════════════════════════════╗" -ForegroundColor $CYAN
Write-Host "║  SERVICIOS ACTIVOS                                            ║" -ForegroundColor $CYAN
Write-Host "╠══════════════════════════════════════════════════════════════╣" -ForegroundColor $CYAN

$servicios = @(
    @{Name="Jarvis Web"; Port=5000; URL="http://localhost:5000"},
    @{Name="HA MCP"; Port=8001; URL="http://localhost:8001"},
    @{Name="Calendar MCP"; Port=8002; URL="http://localhost:8002"},
    @{Name="Android MCP"; Port=8003; URL="http://localhost:8003"},
    @{Name="Ultron Web"; Port=8766; URL="http://localhost:8766"}
)

foreach ($s in $servicios) {
    $estado = if (Test-Port $s.Port) { "✗ DETENIDO" } else { "✓ ACTIVO" }
    $color = if (Test-Port $s.Port) { $RED } else { $GREEN }
    Write-Host "  $($s.Name).PadRight(15) $estado  $($s.URL)" -ForegroundColor $color
}

# IP local para móvil
$ip = (Test-Connection -ComputerName "8.8.8.8" -Count 1 -ErrorAction SilentlyContinue).IPV4Address.IPAddressToString
if (-not $ip) { $ip = "TU_IP_LOCAL" }
Write-Host "`n  MÓVIL: http://$ip:5000/mobile?token=XXXXXX" -ForegroundColor $YELLOW
Write-Host "  (el token sale en la consola de Jarvis Web)" -ForegroundColor $YELLOW

Write-Host "`n╚══════════════════════════════════════════════════════════════╝" -ForegroundColor $CYAN

if ($ok) {
    Write-Log "`n¡TODO LISTO! Presiona Ctrl+C para detener todos los servicios." $GREEN
    Write-Log "Logs aparecen en las ventanas ocultas. Usa -ModoDesarrollo para verlos." $CYAN
    
    # Mantener script vivo
    try {
        while ($true) { Start-Sleep 10 }
    } catch {
        Write-Log "`nDeteniendo servicios..." $YELLOW
        foreach ($p in $puertos) {
            $proc = Get-NetTCPConnection -LocalPort $p -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty OwningProcess
            if ($proc) { Stop-Process -Id $proc -Force -ErrorAction SilentlyContinue }
        }
        Write-Log "Servicios detenidos." $GREEN
    }
} else {
    Write-Log "Algunos servicios fallaron. Revisa logs arriba." $RED
    exit 1
}