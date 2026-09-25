@echo off
setlocal
cd /d "%~dp0"

rem Baja y prueba un Pull Request de GitHub SIN mergearlo a master.
rem Para volver a la version estable despues: git checkout master
rem   probar_pr.bat        pregunta el numero de PR
rem   probar_pr.bat 5      prueba el PR #5 directamente

set "PR=%~1"
if "%PR%"=="" set /p PR="Numero de PR de GitHub a probar: "

powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0probar_pr.ps1" -PR %PR%
pause
