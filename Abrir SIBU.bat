@echo off
REM La puerta de entrada para quien abre la carpeta por primera vez. Despues
REM aparece al lado el acceso directo "SIBU" con el escudo de la UNL, que hace
REM lo mismo.
call "%~dp0portable\SIBU.bat" %*
