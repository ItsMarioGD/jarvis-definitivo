@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"

echo ==========================================================
echo  INSTALADOR DE JARVIS
echo ==========================================================
echo.

:: ── 1. Python ─────────────────────────────────────────────────────────────
set "PYTHON="
for %%P in ("C:\Python314\python.exe" "C:\Python313\python.exe" "C:\Python312\python.exe") do (
    if exist %%P set "PYTHON=%%~P"
)
if not defined PYTHON (
    where python >nul 2>nul && set "PYTHON=python"
)
if not defined PYTHON (
    echo  [MAL] No encuentro Python.
    echo        Instalalo desde https://www.python.org/downloads/
    echo        MARCA la casilla "Add Python to PATH" al instalar.
    pause
    exit /b 1
)
echo  [1/5] Python: %PYTHON%
"%PYTHON%" --version

:: ── 2. Dependencias ───────────────────────────────────────────────────────
echo.
echo  [2/5] Instalando dependencias (tarda unos minutos)...
"%PYTHON%" -m pip install --upgrade pip --quiet
"%PYTHON%" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo  [!] Algo fallo instalando requirements.txt. Reintento lo imprescindible...
    "%PYTHON%" -m pip install flask flask-socketio requests psutil openai python-dotenv --quiet
    "%PYTHON%" -m pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 --quiet
)
echo       Dependencias listas.

:: ── 3. Fichero .env ───────────────────────────────────────────────────────
echo.
if exist ".env" (
    echo  [3/5] Ya tienes un .env; no lo toco.
) else (
    copy ".env.example" ".env" >nul 2>&1
    echo  [3/5] Creado .env a partir de .env.example.
    echo       Editalo si quieres voz de ElevenLabs o bot de Telegram.
)

:: ── 4. Carpeta de credenciales de Google ──────────────────────────────────
echo.
if not exist "Google" mkdir "Google"
dir /b "Google\*.json" >nul 2>nul
if errorlevel 1 (
    echo  [4/5] Falta el JSON de Google Calendar.
    echo       Descargalo de Google Cloud Console ^(tu ID de cliente OAuth,
    echo       boton DESCARGAR JSON^) y dejalo en la carpeta Google\
    echo       Despues ejecuta:  "%PYTHON%" autorizar_google.py
) else (
    echo  [4/5] Credenciales de Google encontradas.
)

:: ── 5. Comprobacion ───────────────────────────────────────────────────────
echo.
echo  [5/5] Comprobando la instalacion...
echo.
"%PYTHON%" test_jarvis_responde.py
echo.
"%PYTHON%" diagnostico_bots.py

echo.
echo ==========================================================
echo  INSTALACION TERMINADA
echo ==========================================================
echo   Arrancar JARVIS:     start_jarvis.bat
echo   Conectar Calendar:   "%PYTHON%" autorizar_google.py
echo   Ver que falla:       "%PYTHON%" diagnostico_bots.py
echo ==========================================================
pause
