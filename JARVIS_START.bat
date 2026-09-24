@echo off
setlocal enabledelayedexpansion
cd /d "%~dp0"
title J.A.R.V.I.S. UNIFIED v5

:: ============================================================
::  J.A.R.V.I.S. UNIFIED LAUNCHER — v5
::  Levanta los tres servicios del sistema definitivo:
::    1. Python core   (Flask/SocketIO)   → puerto 5000
::    2. Node BFF      (Express/WS hub)   → puerto 3000
::    3. Vite HUD      (React + Three.js) → puerto 5173
::
::  Uso:  JARVIS_START.bat          — arranque normal
::        JARVIS_START.bat --clean  — mata puertos y arranca limpio
:: ============================================================

echo.
echo  =====================================================
echo   J . A . R . V . I . S .    U N I F I E D   v 5
echo  =====================================================
echo.

:: ── Python ──────────────────────────────────────────────────
set "PYTHON=C:\Python314\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instala Python 3.10+ y reinicia.
    pause & exit /b 1
)

:: ── Node / npm ───────────────────────────────────────────────
where node >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Node.js no encontrado. Instala Node 18+ y reinicia.
    pause & exit /b 1
)

:: ── Modo --clean: liberar puertos antes de arrancar ──────────
if /i "%1"=="--clean" (
    echo [LIMPIEZA] Liberando puertos 5000, 3000, 5173...
    for %%p in (5000 3000 5173) do (
        for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr ":%%p "') do (
            taskkill /F /PID %%a >nul 2>nul
        )
    )
    timeout /t 2 /nobreak >nul
    echo [OK] Puertos liberados.
    echo.
)

:: ── Cargar .env si existe ────────────────────────────────────
if exist ".env" (
    for /f "usebackq tokens=1,* delims==" %%a in (".env") do (
        if not "%%a"=="" if not "%%a:~0,1%"=="#" set "%%a=%%b"
    )
)

:: ── Dependencias Python (solo si falta alguna) ───────────────
"%PYTHON%" -c "import flask, flask_socketio" >nul 2>nul
if errorlevel 1 (
    echo [DEPS] Instalando dependencias Python...
    "%PYTHON%" -m pip install -r requirements.txt --quiet
)

:: ── Dependencias Node (solo si falta node_modules) ──────────
if not exist "web-hud\node_modules" (
    echo [DEPS] Instalando dependencias Node...
    cd web-hud
    npm install --silent
    cd ..
)

echo.
echo [INICIO] Arrancando servicios...
echo.

:: ── 1. MCPs opcionales (en background silencioso) ────────────
if exist "mcp_servers\ha_server.py" (
    start "HA MCP" /min "%PYTHON%" mcp_servers\ha_server.py
)
if exist "mcp_servers\calendar_server.py" (
    start "Calendar MCP" /min "%PYTHON%" mcp_servers\calendar_server.py
)
if exist "mcp_servers\android_server.py" (
    start "Android MCP" /min "%PYTHON%" mcp_servers\android_server.py
)

:: ── 2. Python core (Flask/SocketIO) ─────────────────────────
start "JARVIS Python Core :5000" cmd /k "cd /d "%~dp0" && "%PYTHON%" web_interface\app.py"
echo [1/3] Python core iniciando en http://localhost:5000

timeout /t 3 /nobreak >nul

:: ── 3. Node BFF + Vite HUD (npm start los lanza juntos) ──────
start "JARVIS HUD :3000+5173" cmd /k "cd /d "%~dp0web-hud" && npm start"
echo [2/3] Node BFF arrancando en http://localhost:3000
echo [3/3] Vite HUD arrancando en http://localhost:5173

timeout /t 5 /nobreak >nul

:: ── Obtener IP local ─────────────────────────────────────────
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /i "IPv4" ^| findstr /v "127\." ^| head -1 2^>nul') do set LOCAL_IP=%%a
set LOCAL_IP=%LOCAL_IP: =%
if "%LOCAL_IP%"=="" (
    for /f "tokens=3" %%a in ('route print 0.0.0.0 ^| findstr "0.0.0.0" 2^>nul') do (
        if not defined LOCAL_IP set "LOCAL_IP=%%a"
    )
)
if "%LOCAL_IP%"=="" set "LOCAL_IP=TU_IP_LOCAL"

:: ── Abrir HUD en el navegador ────────────────────────────────
timeout /t 3 /nobreak >nul
start "" http://localhost:5173

echo.
echo  =====================================================
echo   JARVIS UNIFIED v5 - TODOS LOS SERVICIOS ACTIVOS
echo  =====================================================
echo.
echo   HUD (navegador):   http://localhost:5173
echo   Node BFF/WS:       http://localhost:3000
echo   Python core:       http://localhost:5000
echo   Red local (movil): http://%LOCAL_IP%:5173
echo.
echo   Nuevas capacidades:
echo     - Web demos: "crea una demo para [empresa]"
echo     - Email:     "lee mis correos" / "resume correos"
echo     - Llamada:   "llamame" / "llama al celular"
echo     - Consejo:   "consejo: [dilema]"
echo.
echo   Cierra las ventanas de consola para detener todo.
echo  =====================================================
echo.
pause
