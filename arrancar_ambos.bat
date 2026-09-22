@echo off
setlocal
cd /d "%~dp0"

rem Arranca JARVIS y ULTRON a la vez y abre sus dos interfaces web.
rem   arrancar_ambos.bat                doble clic: todo
rem   arrancar_ambos.bat --reiniciar    cierra lo anterior y arranca limpio

title JARVIS + ULTRON

set "PYTHON=C:\Python314\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" arrancar_ambos.py %*
if errorlevel 1 pause
