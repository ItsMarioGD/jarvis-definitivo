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
echo  JARVIS - Iniciando servidor web...
echo ==========================================
echo.

:: ── Cargar .env si existe (parseo minimo KEY=VAL) ──────────────────────────
if exist ".env" (
    for /f "usebackq tokens=1,2 delims==" %%A in (".env") do (
        if not "%%A"=="" if not "%%~A"=="" if not "%%B"=="" (
            set "%%A=%%B"
        )
    )
)

:: ── Defaults razonables (no pisan lo del .env) ─────────────────────────────
if "%JARVIS_PORT%"=="" set "JARVIS_PORT=5000"
if "%JARVIS_HOST%"=="" set "JARVIS_HOST=0.0.0.0"
if "%QWEN_MODEL%"=="" set "QWEN_MODEL=qwen3:4b-instruct"

:: ── Verificar Flask + requests ─────────────────────────────────────────────
"%PYTHON%" -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Instalando Flask...
    "%PYTHON%" -m pip install flask psutil requests --quiet
)

:: ── Lanzar servidor Flask en segundo plano ─────────────────────────────────
echo Iniciando servidor Flask en puerto %JARVIS_PORT%...
start /B "" "%PYTHON%" web_interface\app.py > flask_log.txt 2>&1

:: ── Esperar a que el servidor arranque ─────────────────────────────────────
echo Esperando servidor...
timeout /t 3 /nobreak >nul

:: ── Verificar que el servidor esta vivo ────────────────────────────────────
"%PYTHON%" -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:%JARVIS_PORT%/health')" >nul 2>&1
if errorlevel 1 (
    echo [!] El servidor no respondio. Revisando flask_log.txt...
    type flask_log.txt
    pause
    exit /b 1
)

:: ── Abrir navegador ────────────────────────────────────────────────────────
echo Abriendo interfaz web...
start "" "http://127.0.0.1:%JARVIS_PORT%"

echo.
echo ==========================================
echo  JARVIS HUD v2.0 - ACTIVO
echo ==========================================
echo  URL:      http://127.0.0.1:%JARVIS_PORT%
echo  Modelo:   %QWEN_MODEL%
echo  Host:     %JARVIS_HOST%
echo  Logs:     flask_log.txt
echo  Ctrl+C para detener
echo ==========================================
echo.

:: ── Mantener ventana abierta con titulo claro ──────────────────────────────
cmd /c "title JARVIS Server && :loop && timeout /t 10 /nobreak >nul && goto loop"

endlocal
