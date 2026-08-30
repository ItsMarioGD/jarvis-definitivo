@echo off
setlocal

cd /d "%~dp0"

:: ── Detectar Python ────────────────────────────────────────────────────────
set "PYTHON=C:\Python314\python.exe"
if not exist "%PYTHON%" (
    set "PYTHON=python"
)

:: ── Banner ─────────────────────────────────────────────────────────────────
echo ==========================================
echo  ULTRON - Iniciando interfaz web...
echo ==========================================
echo.

:: ── Cargar .env si existe (parseo KEY=VAL) ──────────────────────────────────
if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%A in (".env") do (
        if not "%%A"=="" if not "%%~A"=="" if not "%%B"=="" (
            set "%%A=%%B"
        )
    )
)

:: ── Defaults Ultron (no pisan .env) ─────────────────────────────────────────
if "%ULTRON_PORT%"=="" set "ULTRON_PORT=8766"
if "%ULTRON_HOST%"=="" set "ULTRON_HOST=0.0.0.0"
if "%ULTRON_MODE%"==""  set "ULTRON_MODE=1"

set "ULTRON_MODE=%ULTRON_MODE%"
set "ULTRON_PORT=%ULTRON_PORT%"
set "ULTRON_HOST=%ULTRON_HOST%"
if not "%ULTRON_MODEL%"=="" set "QWEN_MODEL=%ULTRON_MODEL%"
if not "%ULTRON_VOICE_ID%"=="" set "ELEVENLABS_VOICE_ID=%ULTRON_VOICE_ID%"

:: ── Verificar Flask + requests ─────────────────────────────────────────────
"%PYTHON%" -c "import flask, flask_socketio" >nul 2>&1
if errorlevel 1 (
    echo Instalando Flask + Flask-SocketIO...
    "%PYTHON%" -m pip install flask flask-socketio psutil requests --quiet
)

:: ── Lanzar backend web de Ultron en segundo plano ──────────────────────────
echo Iniciando ULTRON web server en puerto %ULTRON_PORT%...
start /B "" "%PYTHON%" ultron_interface\app.py > ultron_web.log 2>&1

:: ── Esperar a que arranque ─────────────────────────────────────────────────
echo Esperando servidor...
timeout /t 4 /nobreak >nul

:: ── Verificar que responde ─────────────────────────────────────────────────
"%PYTHON%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:%ULTRON_PORT%/health')" >nul 2>&1
if errorlevel 1 (
    echo [!] El servidor ULTRON no respondio. Revisando ultron_web.log...
    type ultron_web.log
    pause
    exit /b 1
)

:: ── Abrir navegador en el panel principal ───────────────────────────────────
echo Abriendo panel ULTRON...
start "" "http://127.0.0.1:%ULTRON_PORT%/"

echo.
echo ==========================================
echo  ULTRON WEB - ACTIVO
echo ==========================================
echo  Panel:     http://127.0.0.1:%ULTRON_PORT%/
echo  Movil:     http://127.0.0.1:%ULTRON_PORT%/mobile
echo  Centro:    http://127.0.0.1:%ULTRON_PORT%/centro
echo  Dashboard: http://127.0.0.1:%ULTRON_PORT%/dashboard
echo  Pair/QR:   http://127.0.0.1:%ULTRON_PORT%/pair
echo  Modelo:    %QWEN_MODEL%
echo  Logs:      ultron_web.log
echo  Ctrl+C para detener
echo ==========================================
echo.

:: ── Mantener ventana abierta ───────────────────────────────────────────────
cmd /c "title ULTRON Web && :loop && timeout /t 10 /nobreak >nul && goto loop"

endlocal
