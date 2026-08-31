@echo off
:: ===========================================================================
::  INICIAR_TODO.bat  -  Arranca JARVIS y ULTRON de una vez
::  -------------------------------------------------------------------------
::  Levanta los dos servidores web con el HUD AETHER y abre una pestana para
::  cada uno:
::      JARVIS  ->  web_interface\app.py       (por defecto :5000)
::      ULTRON  ->  ultron_interface\app.py    (por defecto :8766)
::
::  Arranca *esos dos* y nada mas. Ni ultron_web_backend.py, que ocupa el
::  mismo 8766 pero no sirve el HUD nuevo, ni ultron_core.py, que duplicaria
::  el nucleo y daria voz y TTS por partida doble.
::
::  Si un puerto ya responde, no relanza: solo abre el navegador.
:: ===========================================================================
setlocal enabledelayedexpansion

cd /d "%~dp0"
title JARVIS + ULTRON

echo.
echo  ===========================================
echo    JARVIS + ULTRON  -  arranque conjunto
echo  ===========================================
echo.

:: -- Detectar Python --------------------------------------------------------
set "PYTHON=C:\Python314\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" -c "import sys" >nul 2>&1
if errorlevel 1 (
    echo  [X] No encuentro Python. Instalalo, o edita la variable PYTHON
    echo      unas lineas mas arriba en este mismo archivo.
    echo.
    pause
    exit /b 1
)

:: -- Cargar .env si existe (parseo minimo CLAVE=VALOR, saltando comentarios) -
::    ULTRON_MODE no se toca aqui a proposito: si quedara en la sesion, el
::    proceso de JARVIS tambien lo heredaria.
if exist ".env" (
    for /f "usebackq eol=# tokens=1* delims==" %%A in (".env") do (
        if not "%%A"=="" if not "%%B"=="" set "%%A=%%B"
    )
)

if "%JARVIS_PORT%"=="" set "JARVIS_PORT=5000"
if "%ULTRON_PORT%"=="" set "ULTRON_PORT=8766"

:: Los puertos se interpolan en lineas de comandos, asi que solo digitos.
:: El truco: con todos los digitos como delimitadores, un valor puramente
:: numerico no produce ningun token y el bucle no llega a ejecutarse.
set "_chk=%JARVIS_PORT%"
for /f "delims=0123456789" %%X in ("%JARVIS_PORT%") do set "_chk="
if not defined _chk (
    echo  [!] JARVIS_PORT no es un numero; uso 5000.
    set "JARVIS_PORT=5000"
)
set "_chk=%ULTRON_PORT%"
for /f "delims=0123456789" %%X in ("%ULTRON_PORT%") do set "_chk="
if not defined _chk (
    echo  [!] ULTRON_PORT no es un numero; uso 8766.
    set "ULTRON_PORT=8766"
)
set "_chk="

:: -- Dependencias minimas ---------------------------------------------------
"%PYTHON%" -c "import flask, flask_socketio, psutil, requests" >nul 2>&1
if errorlevel 1 (
    echo  [..] Faltan dependencias. Instalando...
    "%PYTHON%" -m pip install flask flask-socketio psutil requests --quiet
    echo.
)

:: ===========================================================================
::  1. JARVIS
:: ===========================================================================
echo  [1/4] JARVIS en el puerto %JARVIS_PORT%
call :vivo %JARVIS_PORT%
if "!VIVO!"=="1" (
    echo        ya estaba activo, no lo relanzo.
) else (
    if exist "flask_log.txt" del /q "flask_log.txt" >nul 2>&1
    start "" /B "%PYTHON%" "web_interface\app.py" > flask_log.txt 2>&1
    echo        arrancando...
)

:: ===========================================================================
::  2. ULTRON
::  ULTRON_MODE se pone justo antes y se borra justo despues, de modo que
::  solo lo vea este proceso. JARVIS ya se lanzo arriba, asi que no lo hereda.
:: ===========================================================================
echo  [2/4] ULTRON en el puerto %ULTRON_PORT%
call :vivo %ULTRON_PORT%
if "!VIVO!"=="1" (
    echo        ya estaba activo, no lo relanzo.
) else (
    if exist "ultron_log.txt" del /q "ultron_log.txt" >nul 2>&1
    set "ULTRON_MODE=1"
    start "" /B "%PYTHON%" "ultron_interface\app.py" > ultron_log.txt 2>&1
    set "ULTRON_MODE="
    echo        arrancando...
)

:: ===========================================================================
::  3. Esperar a que respondan
:: ===========================================================================
echo.
echo  [3/4] Esperando respuesta (hasta 40s)...

set "JOK=0"
set "UOK=0"
for /l %%i in (1,1,20) do (
    if "!JOK!"=="0" (
        call :vivo %JARVIS_PORT%
        if "!VIVO!"=="1" (
            set "JOK=1"
            echo        [OK] JARVIS responde en :%JARVIS_PORT%
        )
    )
    if "!UOK!"=="0" (
        call :vivo %ULTRON_PORT%
        if "!VIVO!"=="1" (
            set "UOK=1"
            echo        [OK] ULTRON responde en :%ULTRON_PORT%
        )
    )
    if "!JOK!!UOK!"=="11" goto :listos
    timeout /t 2 /nobreak >nul 2>&1
)

:listos
echo.
if "!JOK!"=="0" (
    echo  [X] JARVIS no respondio. Contenido de flask_log.txt:
    echo  ---------------------------------------------------------
    if exist "flask_log.txt" type "flask_log.txt"
    echo  ---------------------------------------------------------
    echo.
)
if "!UOK!"=="0" (
    echo  [X] ULTRON no respondio. Contenido de ultron_log.txt:
    echo  ---------------------------------------------------------
    if exist "ultron_log.txt" type "ultron_log.txt"
    echo  ---------------------------------------------------------
    echo.
)

:: ===========================================================================
::  4. Abrir navegador
:: ===========================================================================
echo  [4/4] Abriendo interfaces...
if "!JOK!"=="1" start "" "http://127.0.0.1:%JARVIS_PORT%"
if "!UOK!"=="1" (
    timeout /t 1 /nobreak >nul 2>&1
    start "" "http://127.0.0.1:%ULTRON_PORT%"
)

:: -- IP de la red local, para entrar desde el movil -------------------------
::    Se escribe a un temporal en vez de canalizarla: asi no hay que escapar
::    nada raro en la linea de comandos de batch.
set "LANIP=127.0.0.1"
"%PYTHON%" -c "import jarvis_config;print(jarvis_config.LOCAL_IP)" > "%TEMP%\_aether_ip.txt" 2>nul
if exist "%TEMP%\_aether_ip.txt" (
    for /f "usebackq delims=" %%I in ("%TEMP%\_aether_ip.txt") do (
        if not "%%I"=="" set "LANIP=%%I"
    )
    del /q "%TEMP%\_aether_ip.txt" >nul 2>&1
)

echo.
echo  ===========================================
echo    ESTADO
echo  ===========================================
if "!JOK!"=="1" (
    echo    JARVIS   http://127.0.0.1:%JARVIS_PORT%
) else (
    echo    JARVIS   CAIDO  -  revisa flask_log.txt
)
if "!UOK!"=="1" (
    echo    ULTRON   http://127.0.0.1:%ULTRON_PORT%
) else (
    echo    ULTRON   CAIDO  -  revisa ultron_log.txt
)
echo.
echo    Desde el movil, en la misma wifi:
echo      JARVIS   http://%LANIP%:%JARVIS_PORT%
echo      ULTRON   http://%LANIP%:%ULTRON_PORT%
echo      PIN      http://%LANIP%:%JARVIS_PORT%/pair
echo.
echo    Interfaz anterior:  anade  /classic  a cualquiera de las dos
echo.
echo    Para detenerlos:    taskkill /F /IM python.exe
echo                        (cierra todos los Python, no solo estos dos)
echo  ===========================================
echo.
echo  Puedes cerrar esta ventana: los servidores siguen en segundo plano.
echo.
pause
exit /b 0


:: ---------------------------------------------------------------------------
::  :vivo ^<puerto^>   ->   deja VIVO=1 si /health contesta
:: ---------------------------------------------------------------------------
:vivo
set "VIVO=0"
"%PYTHON%" -c "import urllib.request;urllib.request.urlopen('http://127.0.0.1:%~1/health',timeout=2)" >nul 2>&1
if not errorlevel 1 set "VIVO=1"
goto :eof
