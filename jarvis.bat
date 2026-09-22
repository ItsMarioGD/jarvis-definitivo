@echo off
setlocal
cd /d "%~dp0"

rem Lanzador unico de JARVIS/ULTRON. Todo pasa por jarvis.py:
rem   jarvis.bat            HUD de escritorio de JARVIS
rem   jarvis.bat web        interfaz web (y movil)
rem   jarvis.bat ultron     ULTRON
rem   jarvis.bat estado     diagnostico del entorno

set "PYTHON=C:\Python314\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" jarvis.py %*
if errorlevel 1 pause
