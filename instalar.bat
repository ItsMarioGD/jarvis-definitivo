@echo off
:: ===========================================================================
::  instalar.bat - Instalador completo de JARVIS y ULTRON
::
::  Deja el equipo listo de una pasada: Python, dependencias, Ollama, el
::  modelo de IA, los accesos directos y (opcional) el arranque automatico.
::
::  Uso:
::    instalar.bat                         instalacion completa (pregunta)
::    instalar.bat --todo                  sin preguntas, con autoarranque
::    instalar.bat --sin-ollama            no toca Ollama ni el modelo
::    instalar.bat --sin-accesos           no crea accesos directos
::    instalar.bat --quitar-autoarranque   desactiva el arranque automatico
:: ===========================================================================
setlocal enabledelayedexpansion
chcp 65001 >nul 2>&1
cd /d "%~dp0"
set "RAIZ=%CD%"
set "FALLOS="
set "TODO="
set "SIN_OLLAMA="
set "SIN_ACCESOS="
set "MODELO="

for %%A in (%*) do (
    if /I "%%A"=="--todo" set "TODO=1"
    if /I "%%A"=="--sin-ollama" set "SIN_OLLAMA=1"
    if /I "%%A"=="--sin-accesos" set "SIN_ACCESOS=1"
    if /I "%%A"=="--quitar-autoarranque" set "QUITAR=1"
)
if defined QUITAR goto :quitar_auto

echo.
echo ===========================================================
echo   INSTALADOR DE JARVIS + ULTRON
echo   %RAIZ%
echo ===========================================================

:: ── 1. PYTHON ──────────────────────────────────────────────────────────────
echo.
echo [1/7] Python
set "PYTHON="
for %%P in ("C:\Python314\python.exe" "C:\Python313\python.exe" "C:\Python312\python.exe" "C:\Python311\python.exe") do (
    if exist %%P if not defined PYTHON set "PYTHON=%%~P"
)
if not defined PYTHON (
    for /f "delims=" %%P in ('where python 2^>nul') do (
        if not defined PYTHON set "PYTHON=%%P"
    )
)
if not defined PYTHON goto :sin_python
echo       %PYTHON%
"%PYTHON%" --version

:: ── 2. DEPENDENCIAS (JARVIS y ULTRON comparten requirements.txt) ───────────
echo.
echo [2/7] Dependencias de Python ^(varios minutos la primera vez^)
"%PYTHON%" -m pip install --upgrade pip --quiet 2>nul
"%PYTHON%" -m pip install -r requirements.txt --quiet
if errorlevel 1 (
    echo       [!] requirements.txt fallo. Instalo lo imprescindible...
    "%PYTHON%" -m pip install flask flask-socketio requests psutil openai python-dotenv --quiet
    set "FALLOS=!FALLOS! dependencias-parciales"
)
"%PYTHON%" -c "import google_auth_oauthlib" 2>nul
if errorlevel 1 (
    echo       Anado las librerias de Google Calendar...
    "%PYTHON%" -m pip install google-api-python-client google-auth-oauthlib google-auth-httplib2 --quiet
)
echo       Listo.

:: ── 3. OLLAMA ──────────────────────────────────────────────────────────────
echo.
if defined SIN_OLLAMA (
    echo [3/7] Ollama: omitido ^(--sin-ollama^)
    goto :tras_ollama
)
echo [3/7] Ollama ^(motor de IA local^)
where ollama >nul 2>nul
if not errorlevel 1 goto :ollama_ya
echo       No esta instalado. Instalando...
where winget >nul 2>nul
if not errorlevel 1 (
    winget install --id Ollama.Ollama --accept-source-agreements --accept-package-agreements --silent
) else (
    echo       Sin winget: descargo el instalador oficial...
    curl -L -o "%TEMP%\OllamaSetup.exe" https://ollama.com/download/OllamaSetup.exe
    if exist "%TEMP%\OllamaSetup.exe" "%TEMP%\OllamaSetup.exe" /SILENT
    timeout /t 10 /nobreak >nul 2>&1
)
if exist "%LOCALAPPDATA%\Programs\Ollama\ollama.exe" set "PATH=%LOCALAPPDATA%\Programs\Ollama;%PATH%"
where ollama >nul 2>nul
if errorlevel 1 (
    echo   [!] Ollama no quedo accesible en esta ventana.
    echo       Instalalo desde https://ollama.com/download, cierra esta ventana
    echo       y vuelve a ejecutar instalar.bat.
    set "FALLOS=!FALLOS! ollama"
    goto :tras_ollama
)
:ollama_ya
ollama --version 2>nul

:: ── 4. MODELO DE IA ────────────────────────────────────────────────────────
echo.
echo [4/7] Modelo de IA
curl -s -m 3 http://127.0.0.1:11434/api/tags >nul 2>&1
if not errorlevel 1 goto :servicio_ok
echo       Levantando el servicio de Ollama...
start "" /B ollama serve
call :esperar_ollama
curl -s -m 3 http://127.0.0.1:11434/api/tags >nul 2>&1
if errorlevel 1 (
    echo   [!] El servicio de Ollama no responde en el puerto 11434.
    set "FALLOS=!FALLOS! ollama-servicio"
    goto :tras_ollama
)
:servicio_ok
echo       Servicio en marcha. Descargando modelo ^(unos GB^)...
:: Se prueban en orden y se usa el primero que baje, para no depender de que
:: un tag concreto siga publicado en el registro de Ollama.
call :probar_modelo qwen3:4b-instruct
call :probar_modelo qwen3:4b
call :probar_modelo qwen2.5:3b
call :probar_modelo llama3.2:3b
if not defined MODELO (
    echo   [!] No pude descargar ningun modelo. Revisa tu conexion y ejecuta
    echo       luego:  ollama pull qwen3:4b
    set "FALLOS=!FALLOS! modelo"
)
:tras_ollama

:: ── 5. CONFIGURACION ───────────────────────────────────────────────────────
echo.
echo [5/7] Configuracion ^(.env^)
if exist ".env" (
    echo       Ya existe; conservo tu configuracion.
) else (
    if exist ".env.example" (
        copy ".env.example" ".env" >nul
        echo       Creado a partir de .env.example
    ) else (
        echo.> ".env"
    )
)
if defined MODELO (
    "%PYTHON%" -c "import io,os,re;p='.env';s=io.open(p,encoding='utf-8').read() if os.path.exists(p) else '';s=re.sub(r'(?m)^\s*#?\s*QWEN_MODEL=.*$','QWEN_MODEL=%MODELO%',s) if re.search(r'(?m)^\s*#?\s*QWEN_MODEL=',s) else s.rstrip()+'\nQWEN_MODEL=%MODELO%\n';io.open(p,'w',encoding='utf-8').write(s)"
    echo       QWEN_MODEL=%MODELO%
)
if not exist "Google" mkdir "Google"
if not exist "jarvis_log" mkdir "jarvis_log"

:: ── 6. ACCESOS DIRECTOS Y AUTOARRANQUE ─────────────────────────────────────
echo.
if defined SIN_ACCESOS (
    echo [6/7] Accesos directos: omitido ^(--sin-accesos^)
    goto :tras_accesos
)
echo [6/7] Accesos directos
set "AUTO="
if defined TODO (
    set "AUTO=-Autoarranque"
    goto :hacer_accesos
)
echo.
set /p "RESP=      Arrancar JARVIS solo al encender el PC? (s/N): "
if /I "!RESP!"=="s" set "AUTO=-Autoarranque"
:hacer_accesos
powershell -NoProfile -ExecutionPolicy Bypass -File "herramientas\accesos_directos.ps1" -Raiz "%RAIZ%" -Crear !AUTO!
if errorlevel 1 set "FALLOS=!FALLOS! accesos-directos"
:tras_accesos

:: ── 7. COMPROBACION ────────────────────────────────────────────────────────
echo.
echo [7/7] Comprobando la instalacion
echo.
"%PYTHON%" test_jarvis_responde.py
echo.
"%PYTHON%" diagnostico_bots.py

echo.
echo ===========================================================
if defined FALLOS (
    echo   TERMINADO CON AVISOS: !FALLOS!
) else (
    echo   INSTALACION COMPLETA
)
echo ===========================================================
echo   Abrir JARVIS:        icono "JARVIS" del Escritorio
echo   Abrir ULTRON:        icono "ULTRON" del Escritorio
echo   Conectar Calendar:   "%PYTHON%" autorizar_google.py
echo   Ver que falla:       "%PYTHON%" diagnostico_bots.py
echo   Quitar autoarranque: instalar.bat --quitar-autoarranque
echo ===========================================================
echo.
pause
exit /b 0

:: ═══ SUBRUTINAS ════════════════════════════════════════════════════════════

:probar_modelo
:: %1 = modelo a intentar. Si ya hay uno instalado, no hace nada.
if defined MODELO exit /b 0
echo       Probando %~1 ...
ollama pull %~1
if errorlevel 1 (
    echo       %~1 no disponible; pruebo el siguiente.
    exit /b 0
)
set "MODELO=%~1"
echo       [OK] Modelo instalado: %~1
exit /b 0

:esperar_ollama
:: Espera hasta 30 s a que el servicio responda.
for /L %%i in (1,1,15) do (
    timeout /t 2 /nobreak >nul 2>&1
    curl -s -m 3 http://127.0.0.1:11434/api/tags >nul 2>&1
    if not errorlevel 1 exit /b 0
)
exit /b 1

:sin_python
echo       No hay Python instalado.
where winget >nul 2>nul
if errorlevel 1 (
    echo   [MAL] Tampoco tienes winget.
    echo         Instala Python desde https://www.python.org/downloads/
    echo         MARCANDO la casilla "Add python.exe to PATH".
    pause
    exit /b 1
)
echo       Lo instalo con winget...
winget install --id Python.Python.3.12 --accept-source-agreements --accept-package-agreements --silent
echo.
echo   Python instalado. CIERRA esta ventana, abre otra y vuelve a ejecutar
echo   instalar.bat ^(hace falta para que Windows vea el nuevo PATH^).
pause
exit /b 1

:quitar_auto
echo.
powershell -NoProfile -ExecutionPolicy Bypass -File "herramientas\accesos_directos.ps1" -Raiz "%CD%" -Quitar
echo.
pause
exit /b 0
