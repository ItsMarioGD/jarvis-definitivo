@echo off
setlocal enabledelayedexpansion
chcp 65001 >nul
cd /d "%~dp0"
title J.A.R.V.I.S.

:: ============================================================
::  J.A.R.V.I.S. - lanzador
::  Arranca el nucleo (Flask/SocketIO, puerto 5000) sin consolas y abre
::  ORIGEN, la unica interfaz, en su propia ventana (escritorio.py).
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

:: -- Arrancar todo oculto y abrir la ventana de JARVIS --------
:: reiniciar_todo arranca los servidores sin consolas (solo los MCP que tengan
:: algo que hacer) y abre ORIGEN como aplicacion, en su propia ventana.
"%PYTHON%" reiniciar_todo.py

:: -- Acceso directo «JARVIS» en el escritorio y en Inicio ---------
"%PYTHON%" escritorio.py --acceso

echo.
echo  =====================================================
echo   JARVIS esta en su ventana. A partir de ahora basta
echo   con el icono «JARVIS» del escritorio.
echo  =====================================================
echo.
timeout /t 8 >nul
