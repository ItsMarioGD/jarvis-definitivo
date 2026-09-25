@echo off
setlocal
cd /d "%~dp0"

rem Trae los cambios nuevos de GitHub y actualiza JARVIS/ULTRON.
rem Hace copia del cerebro, git pull, instala dependencias si hicieron falta
rem y corre las pruebas; si algo se rompe, vuelve solo a la version anterior.
rem   actualizar.bat            actualizar de verdad
rem   actualizar.bat --probar   solo mirar si hay novedades, sin tocar nada
rem   actualizar.bat --volver   deshacer la ultima actualizacion

set "PYTHON=C:\Python314\python.exe"
if not exist "%PYTHON%" set "PYTHON=python"

"%PYTHON%" actualizar.py %*
pause
