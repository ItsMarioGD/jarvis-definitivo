@echo off
REM ============================================================
REM  JARVIS/ULTRON - LAUNCHER SIMPLE (batch)
REM  Ejecuta: start_jarvis.bat
REM ============================================================

set PROJECT_ROOT=%~dp0
cd /d "%PROJECT_ROOT%"

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║  JARVIS/ULTRON - INICIO RAPIDO                              ║
echo ╚══════════════════════════════════════════════════════════════╝
echo.

REM Verificar Python
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python no encontrado en PATH
    pause
    exit /b 1
)

REM Verificar Ollama
echo [INFO] Verificando Ollama...
curl -s http://localhost:11434/api/tags >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Ollama no responde en localhost:11434
    echo        Ejecuta: ollama serve
    pause
    exit /b 1
)
echo [OK] Ollama activo

REM Matar procesos previos en puertos conocidos
for %%p in (5000 8001 8002 8003 8766) do (
    for /f "tokens=5" %%a in ('netstat -ano ^| findstr ":%%p "') do (
        taskkill /F /PID %%a >nul 2>nul
    )
)

echo.
echo [INICIO] Levantando servicios...
echo.

REM 1. HA MCP (puerto 8001)
start "HA MCP" /B python mcp_servers\ha_server.py
timeout /t 2 /nobreak >nul

REM 2. Calendar MCP (puerto 8002)
start "Calendar MCP" /B python mcp_servers\calendar_server.py
timeout /t 2 /nobreak >nul

REM 3. Android MCP (puerto 8003)
start "Android MCP" /B python mcp_servers\android_server.py
timeout /t 2 /nobreak >nul

REM 4. Jarvis Web (puerto 5000)
start "Jarvis Web" /B python web_interface\app.py
timeout /t 3 /nobreak >nul

REM 5. Ultron Web (puerto 8766)
start "Ultron Web" /B python ultron_interface\app.py
timeout /t 2 /nobreak >nul

echo.
echo ╔══════════════════════════════════════════════════════════════╗
echo ║  SERVICIOS INICIADOS                                        ║
echo ╠══════════════════════════════════════════════════════════════╣
echo ║  Jarvis Web:      http://localhost:5000                     ║
echo ║  HA MCP:          http://localhost:8001                     ║
echo ║  Calendar MCP:    http://localhost:8002                     ║
echo ║  Android MCP:     http://localhost:8003                     ║
echo ║  Ultron Web:      http://localhost:8766                     ║
echo ╠═════════════════════════════════════════════════════════════╣

REM Obtener IP local para móvil
for /f "tokens=2 delims=[]" %%a in ('ping -n 1 -4 "%COMPUTERNAME%" ^| findstr "Respuesta"') do set LOCAL_IP=%%a
if "%LOCAL_IP%"=="" set LOCAL_IP=TU_IP_LOCAL

echo ║  MOVIL: http://%LOCAL_IP%:5000/mobile?token=XXXXXX          ║
echo ║  (token aparece en consola de Jarvis Web)                   ║
echo ╚═════════════════════════════════════════════════════════════╝
echo.
echo Presiona Ctrl+C en CUALQUIER ventana para detener todo.
echo.

REM Mantener vivo
pause