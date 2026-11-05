@echo off
REM ---------------------------------------------------------------------------
REM  SIBU portable - Windows
REM
REM  Lo que hay detras del icono. Usa el Python que viaja en la carpeta
REM  (python\python.exe), asi que no hace falta instalar nada.
REM
REM  Al arrancar deja en la carpeta un acceso directo "SIBU" con el escudo de
REM  la UNL. Se rehace en cada arranque porque un acceso directo guarda la ruta
REM  completa: si la carpeta se mueve a otro sitio o a otra memoria, el viejo
REM  apuntaria a donde ya no esta.
REM ---------------------------------------------------------------------------
setlocal
cd /d "%~dp0.."
set "RAIZ=%CD%"

REM Texto en UTF-8: la consola de Windows usa por omision una pagina de codigos
REM en la que las tildes y la raya de los mensajes de SIBU salen rotas o, si la
REM salida se redirige, revientan con UnicodeEncodeError.
set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"
chcp 65001 >nul 2>nul

if exist "python\python.exe" (
    set "PY=python\python.exe"
) else (
    where python >nul 2>nul
    if errorlevel 1 (
        echo.
        echo  Esta carpeta no trae su Python y este computador tampoco tiene uno.
        echo  Descargue la version para Windows ya armada: viene con todo dentro.
        echo.
        pause
        exit /b 1
    )
    set "PY=python"
)

REM El acceso directo con el icono, junto a esta carpeta. PowerShell viene con
REM Windows: no es instalar nada. Si falla, SIBU arranca igual.
powershell -NoProfile -ExecutionPolicy Bypass -Command ^
  "$s=(New-Object -ComObject WScript.Shell).CreateShortcut('%RAIZ%\SIBU.lnk');" ^
  "$s.TargetPath='%RAIZ%\portable\SIBU.bat';" ^
  "$s.WorkingDirectory='%RAIZ%';" ^
  "$s.IconLocation='%RAIZ%\portable\sibu.ico';" ^
  "$s.Description='SIBU - Bienestar Universitario UNL';" ^
  "$s.Save()" >nul 2>nul

title SIBU - Unidad de Bienestar Universitario
echo Arrancando SIBU... no cierre esta ventana mientras lo use.
"%PY%" portable\arrancar.py %*

REM Si algo revienta, que la ventana no se cierre antes de poder leerlo.
if errorlevel 1 pause
endlocal
