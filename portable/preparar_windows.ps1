# ---------------------------------------------------------------------------
#  Arma la carpeta portable de SIBU para Windows.
#
#  Deja DENTRO de la carpeta un Python propio (la distribución "embeddable" de
#  python.org) con todas las dependencias. Después la carpeta se copia a
#  cualquier Windows —o a una memoria— y funciona sin instalar nada.
#
#  Normalmente NO hace falta ejecutarlo: la carpeta ya armada la construye y la
#  prueba GitHub Actions en un Windows real (.github/workflows/portable-windows.yml)
#  y se descarga como zip. Esto es para armarla a mano:
#
#      powershell -ExecutionPolicy Bypass -File portable\preparar_windows.ps1
# ---------------------------------------------------------------------------

$ErrorActionPreference = "Stop"
# La barra de progreso de Invoke-WebRequest en Windows PowerShell 5 hace que una
# descarga de 10 MB tarde minutos.
$ProgressPreference = "SilentlyContinue"

$VersionPython = "3.11.9"
$Raiz    = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$Destino = Join-Path $Raiz "python"
$Temp    = Join-Path $env:TEMP "sibu-portable"
$Py      = Join-Path $Destino "python.exe"

# Los comandos externos (python, pip) no lanzan aunque fallen: hay que mirar
# su código de salida. Sin esto, un pip que no pudo instalar Django dejaba una
# carpeta "lista" que no arrancaba.
function Exigir($que) {
    if ($LASTEXITCODE -ne 0) { throw "Falló: $que (código $LASTEXITCODE)" }
}

Write-Host ""
Write-Host "SIBU portable - armando la carpeta para Windows" -ForegroundColor Green
Write-Host "Carpeta: $Raiz"
Write-Host ""

if (Test-Path $Destino) {
    Write-Host "Ya existe '$Destino'. Bórrelo si quiere rehacerlo desde cero." -ForegroundColor Yellow
    exit 1
}
New-Item -ItemType Directory -Force -Path $Temp | Out-Null

# 1) Python embebido -------------------------------------------------------
$Zip = Join-Path $Temp "python-embed.zip"
$Url = "https://www.python.org/ftp/python/$VersionPython/python-$VersionPython-embed-amd64.zip"
Write-Host "[1/4] Bajando Python $VersionPython embebido..."
Invoke-WebRequest -Uri $Url -OutFile $Zip
Expand-Archive -Path $Zip -DestinationPath $Destino -Force

# La distribución embebida trae un archivo ._pth que deja fuera site-packages y
# la carpeta de SIBU. Sin tocarlo, `import django` falla aunque Django esté
# instalado al lado.
$Pth = Get-ChildItem -Path $Destino -Filter "python*._pth" | Select-Object -First 1
if (-not $Pth) { throw "La distribución embebida no trae su archivo ._pth" }
$contenido = Get-Content $Pth.FullName
$contenido = $contenido -replace '^#\s*import site', 'import site'
if ($contenido -notcontains "import site") { $contenido += "import site" }
if ($contenido -notcontains "..")          { $contenido += ".." }
Set-Content -Path $Pth.FullName -Value $contenido -Encoding ascii

# 2) pip -------------------------------------------------------------------
Write-Host "[2/4] Instalando pip..."
$GetPip = Join-Path $Temp "get-pip.py"
Invoke-WebRequest -Uri "https://bootstrap.pypa.io/get-pip.py" -OutFile $GetPip
& $Py $GetPip --no-warn-script-location
Exigir "instalar pip"

# 3) Dependencias ----------------------------------------------------------
Write-Host "[3/4] Instalando las dependencias de SIBU..."
& $Py -m pip install --no-warn-script-location --no-cache-dir `
    -r (Join-Path $Raiz "requirements\portable.txt")
Exigir "instalar las dependencias"

# 4) Estáticos -------------------------------------------------------------
# Se recolectan ahora para que el primer arranque sea más corto. La base NO se
# crea aquí: cada computador la crea al abrir SIBU por primera vez.
Write-Host "[4/4] Recolectando los estáticos..."
Push-Location $Raiz
$env:PYTHONUTF8 = "1"
& $Py manage.py collectstatic --noinput --settings=config.settings.portable -v 0
Exigir "recolectar los estáticos"
Pop-Location

# Cualquier comando de Django con los ajustes de la portable crea datos\ y su
# clave.txt. Si se quedaran, todas las copias de esta carpeta compartirían la
# misma clave secreta, que es la que firma las sesiones. Se borra: cada
# computador genera la suya al primer arranque.
$Datos = Join-Path $Raiz "datos"
if (Test-Path $Datos) { Remove-Item -Recurse -Force $Datos }

Write-Host ""
Write-Host "Listo." -ForegroundColor Green
Write-Host ""
Write-Host "  Doble clic en 'Abrir SIBU'. La primera vez el navegador pedirá"
Write-Host "  crear la cuenta de Administración General, y en la carpeta"
Write-Host "  aparecerá el acceso directo 'SIBU' con el escudo de la UNL."
Write-Host ""
Write-Host "  La carpeta completa ya es portable: cópiela a otro Windows o a una"
Write-Host "  memoria y funcionará igual." -ForegroundColor Green
Write-Host ""
