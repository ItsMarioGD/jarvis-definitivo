@echo off
chcp 65001 >nul
title JARVIS - Conexion del telefono (Tailscale)
cd /d "%~dp0"

REM Las reglas del Firewall necesitan administrador. Si no lo somos nos
REM relanzamos elevados, en vez de fallar a medias y dejar los puertos
REM cerrados (que es justo lo que impide que el movil reciba respuesta).
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Pidiendo permisos de administrador para abrir los puertos...
    powershell -NoProfile -Command "Start-Process -FilePath '%~f0' -Verb RunAs"
    exit /b
)

set "PY=python"
where python >nul 2>&1 || set "PY=py -3"

%PY% tailscale_setup.py %*

echo.
pause
