@echo off
echo Compilando Jarvis Hotkey Listener...
g++ jarvis_hotkey.cpp -o jarvis_hotkey.exe -lws2_32 -mwindows
if %ERRORLEVEL% EQU 0 (
    echo [EXITO] Compilacion terminada: jarvis_hotkey.exe
    echo Para ejecutar en segundo plano, abre jarvis_hotkey.exe
) else (
    echo [ERROR] No se pudo compilar. Asegurate de tener MinGW/g++ instalado.
)
pause
