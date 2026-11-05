@echo off
REM ---------------------------------------------------------------------------
REM  Este computador se conecta al SIBU de otro computador de la oficina, por
REM  la misma red WiFi. Los datos NO se guardan aqui: estan en ese otro equipo.
REM
REM  La direccion queda guardada en portable\servidor.txt y a partir de ahora
REM  el icono "SIBU" de este equipo abre siempre el de la oficina.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
set "ACTUAL="
if exist "portable\servidor.txt" (
  for /f "usebackq eol=# delims=" %%L in ("portable\servidor.txt") do if not defined ACTUAL set "ACTUAL=%%L"
)
echo.
echo  Conectar al SIBU de la oficina
echo  ------------------------------
echo  Escriba la direccion que aparece en la ventana del computador que
echo  comparte SIBU. Por ejemplo:  http://RECEPCION:8000
echo.
if defined ACTUAL (
  echo  Guardada ahora: %ACTUAL%
  echo  Pulse Enter para usarla, o escriba NINGUNO para dejar de conectarse
  echo  y volver a usar SIBU solo en este computador.
  echo.
)
set "NUEVA="
set /p "NUEVA=Direccion: "
if /i "%NUEVA%"=="NINGUNO" (
  del "portable\servidor.txt" >nul 2>nul
  echo.
  echo  Listo: este computador vuelve a usar su propio SIBU.
  echo.
  pause
  exit /b 0
)
if not defined NUEVA set "NUEVA=%ACTUAL%"
if not defined NUEVA (
  echo  No escribio ninguna direccion.
  pause
  exit /b 1
)
> "portable\servidor.txt" echo %NUEVA%
call "%~dp0portable\SIBU.bat"
endlocal
