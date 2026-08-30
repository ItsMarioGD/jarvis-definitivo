@echo off
REM jarvis_web_start.bat — one-shot launcher for the new HUD.
REM Starts the Python backend, the Node BFF and Vite dev server.

start "Jarvis Python Backend" cmd /k "cd /d %~dp0 && python jarvis_web_backend.py"
timeout /t 2 /nobreak >nul
start "Jarvis Node BFF + Vite" cmd /k "cd /d %~dp0\web-hud && npm start"
echo.
echo Jarvis HUD arrancando. Abra http://localhost:5173 cuando Vite lo indique.
