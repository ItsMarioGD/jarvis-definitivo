@echo off
:: ===========================================================================
::  autoarranque.bat - Arranca JARVIS al encender el PC.
::
::  Lo lanza el acceso directo que instalar.bat pone en la carpeta Inicio.
::  No abre ventanas: espera a que el sistema termine de arrancar, levanta
::  Ollama si hace falta y luego JARVIS.
::
::  Para desactivarlo:  instalar.bat --quitar-autoarranque
::  o borra "JARVIS (autoarranque)" de  shell:startup
:: ===========================================================================
setlocal
cd /d "%~dp0"

:: Margen para que Windows acabe de arrancar (red, audio, servicios).
set "ESPERA=%JARVIS_AUTOARRANQUE_ESPERA%"
if "%ESPERA%"=="" set "ESPERA=25"
timeout /t %ESPERA% /nobreak >nul 2>&1

:: ── Ollama: sin el, JARVIS arranca pero no razona ──────────────────────────
where ollama >nul 2>nul
if not errorlevel 1 (
    curl -s -m 3 http://127.0.0.1:11434/api/tags >nul 2>&1
    if errorlevel 1 (
        start "" /B ollama serve
        :: Esperamos a que responda, hasta 60 s
        for /L %%i in (1,1,20) do (
            timeout /t 3 /nobreak >nul 2>&1
            curl -s -m 3 http://127.0.0.1:11434/api/tags >nul 2>&1
            if not errorlevel 1 goto :ollama_ok
        )
    )
)
:ollama_ok

:: ── Si ya hay un JARVIS escuchando, no arrancamos otro ─────────────────────
if "%JARVIS_PORT%"=="" set "JARVIS_PORT=5000"
curl -s -m 3 http://127.0.0.1:%JARVIS_PORT%/health >nul 2>&1
if not errorlevel 1 (
    echo JARVIS ya estaba en marcha. >> "jarvis_log\autoarranque.log"
    exit /b 0
)

echo [%DATE% %TIME%] Arrancando JARVIS. >> "jarvis_log\autoarranque.log"
start "" /MIN "start_jarvis.bat"
endlocal
