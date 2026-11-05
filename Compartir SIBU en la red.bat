@echo off
REM ---------------------------------------------------------------------------
REM  Este computador pasa a ser el SIBU de la oficina: guarda los datos y los
REM  companeros de la misma red WiFi entran desde los suyos.
REM
REM  Queda guardado en la carpeta: a partir de ahora el icono "SIBU" de este
REM  equipo arranca siempre asi. Para volver a usarlo solo en este equipo,
REM  borre el archivo portable\compartir_en_red.txt
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0"
(
  echo Este computador comparte SIBU con la oficina por la red WiFi.
  echo Los datos de todos viven en esta carpeta. Borre este archivo para
  echo volver a usar SIBU solo en este equipo.
) > "portable\compartir_en_red.txt"
echo.
echo  Este computador sera el SIBU de la oficina.
echo.
echo  La primera vez, Windows preguntara si deja a Python usar la red:
echo  marque "Redes privadas" y pulse "Permitir acceso". Si su WiFi esta
echo  marcada como "Publica", cambiela a "Privada" en Configuracion ^> Red.
echo.
call "%~dp0portable\SIBU.bat" %*
endlocal
