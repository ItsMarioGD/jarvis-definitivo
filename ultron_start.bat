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
echo  ULTRON - Protocolo de activacion
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

:: ── Valores por defecto de Ultron (no pisan lo del .env) ──────────────────
if "%ULTRON_MODE%"=="" set "ULTRON_MODE=1"
if "%ULTRON_PORT%"=="" set "ULTRON_PORT=8766"
if "%ULTRON_SALUDAR%"=="" set "ULTRON_SALUDAR=1"

:: Exportar al entorno del proceso Python
set "ULTRON_MODE=%ULTRON_MODE%"
set "ULTRON_PORT=%ULTRON_PORT%"
set "ULTRON_SALUDAR=%ULTRON_SALUDAR%"
if not "%ULTRON_MODEL%"=="" set "QWEN_MODEL=%ULTRON_MODEL%"
if not "%ULTRON_VOICE_ID%"=="" set "ELEVENLABS_VOICE_ID=%ULTRON_VOICE_ID%"

:: ── Verificar Flask + requests ─────────────────────────────────────────────
"%PYTHON%" -c "import flask" >nul 2>&1
if errorlevel 1 (
    echo Instalando Flask...
    "%PYTHON%" -m pip install flask psutil requests --quiet
)

:: ── Lanzar backend web de Ultron en segundo plano ──────────────────────────
echo Iniciando ULTRON web backend en puerto %ULTRON_PORT%...
start /B "" "%PYTHON%" ultron_web_backend.py

:: ── Lanzar HUD brutalista en su propia ventana ─────────────────────────────
echo Iniciando HUD brutalista de terminal...
start "ULTRON HUD" "%PYTHON%" -m ultron.ultron_hud

:: ── Lanzar nucleo cognitivo Ultron (foreground) ────────────────────────────
echo.
echo ==========================================
echo  ULTRON NUCLEO - MODO OFENSIVA
echo  Modelo: %QWEN_MODEL%
echo  Puerto backend: %ULTRON_PORT%
echo  HUD: ventana separada
echo  Ctrl+C para abortar el nucleo
echo ==========================================
echo.

"%PYTHON%" ultron_core.py

endlocal
