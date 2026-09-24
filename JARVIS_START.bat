@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title J.A.R.V.I.S.

:: ============================================================
::  J.A.R.V.I.S. - lanzador
::  Arranca el nucleo (Flask/SocketIO, puerto 5000) y abre ORIGEN,
::  la unica interfaz: http://localhost:5000
::  El telefono se empareja desde ORIGEN (boton del movil).
::
::  Antes de arrancar libera el puerto 5000: si quedaba un JARVIS
::  viejo escuchando, el nuevo se cerraba solo y el navegador seguia
::  mostrando la version antigua.
:: ============================================================

echo.
echo  =====================================================
echo   J . A . R . V . I . S .
echo  =====================================================
echo.

:: -- Python ---------------------------------------------------
set "PYTHON=C:\Python314\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" --version >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python no encontrado. Instala Python 3.10+ y reinicia.
    pause & exit /b 1
)

:: -- Liberar el puerto del JARVIS anterior --------------------
for %%p in (5000 5001) do (
    for /f "tokens=5" %%a in ('netstat -ano 2^>nul ^| findstr /r /c:":%%p .*LISTENING"') do (
        taskkill /F /PID %%a >nul 2>nul
    )
)

:: -- Cargar .env si existe ------------------------------------
if exist ".env" (
    for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env") do (
        if not "%%a"=="" set "%%a=%%b"
    )
)

:: -- Dependencias Python (solo si falta alguna) ---------------
"%PYTHON%" -c "import flask, flask_socketio" >nul 2>nul
if errorlevel 1 (
    echo [DEPS] Instalando dependencias Python...
    "%PYTHON%" -m pip install -r requirements.txt --quiet
)

:: -- MCPs opcionales (en segundo plano) -----------------------
if exist "mcp_servers\ha_server.py" (
    start "HA MCP" /min "%PYTHON%" mcp_servers\ha_server.py
)
if exist "mcp_servers\calendar_server.py" (
    start "Calendar MCP" /min "%PYTHON%" mcp_servers\calendar_server.py
)
if exist "mcp_servers\android_server.py" (
    start "Android MCP" /min "%PYTHON%" mcp_servers\android_server.py
)

:: -- Nucleo de JARVIS -----------------------------------------
start "JARVIS :5000" cmd /k "cd /d "%~dp0" && "%PYTHON%" web_interface\app.py"
echo [OK] JARVIS arrancando en http://localhost:5000

:: -- Abrir ORIGEN (con marca de tiempo: nada de paginas viejas) -
timeout /t 5 /nobreak >nul
start "" "http://localhost:5000/?v=%RANDOM%%RANDOM%"

echo.
echo  =====================================================
echo   JARVIS:   http://localhost:5000
echo   Movil:    en JARVIS, boton del movil ^> escanea el QR
echo  =====================================================
echo.
echo   Cierra la ventana "JARVIS :5000" para detenerlo.
echo.
pause
