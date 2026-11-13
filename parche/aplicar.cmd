@echo off
setlocal
if not "%~1"=="" goto argumentos
set /p cue=Ruta completa al CUE japones:
set "cue=%cue:"=%"
set /p destino=Ruta de carpeta NUEVA para el CHD:
set "destino=%destino:"=%"
"%~dp0python\python.exe" "%~dp0aplicar_parche_es.py" "%~dp0." "%cue%" "%destino%"
set "grandia_result=%errorlevel%"
goto fin
:argumentos
"%~dp0python\python.exe" "%~dp0aplicar_parche_es.py" "%~dp0." %*
set "grandia_result=%errorlevel%"
:fin
pause
exit /b %grandia_result%
