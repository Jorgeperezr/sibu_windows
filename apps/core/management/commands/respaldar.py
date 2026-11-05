"""
Copia de seguridad de la base de una portable.

No existía ninguna. Y copiar `datos/sibu.sqlite3` a mano mientras SIBU está
abierto puede dar una copia ROTA: la base va en modo WAL, y lo último que se
escribió todavía vive en `sibu.sqlite3-wal`, no en el archivo principal. Quien
copia solo el principal se lleva una base de hace un rato, o una a medias.

`VACUUM INTO` es la forma que SQLite da para esto: escribe una instantánea
coherente de la base entera en otro archivo, con lo que haya en el WAL
incluido, mientras la base sigue en uso. Después se abre la copia y se pasa
`PRAGMA integrity_check`: una copia que no se ha comprobado no es una copia.

Se guardan las últimas `--conservar` (14 por omisión) en `datos/respaldos/`.

    python manage.py respaldar
    python manage.py respaldar --si-no-hay-de-hoy     # lo que hace el arranque
    python manage.py respaldar --destino E:/respaldos-sibu

IMPORTANTE: la copia contiene la base ENTERA, contenido de Psicología
incluido. Va a donde vaya la carpeta, y debe ir solo a un disco cifrado bajo
control de la Unidad. En un servidor con PostgreSQL esto no aplica: ahí se usa
`pg_dump` (docs/ORACLE_CLOUD.md).
"""

import sqlite3
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

PREFIJO = "sibu-"
SUFIJO = ".sqlite3"


def carpeta_por_omision() -> Path:
    return Path(settings.DATABASES["default"]["NAME"]).parent / "respaldos"


def respaldos_en(carpeta: Path) -> list[Path]:
    """Los respaldos de la carpeta, del más antiguo al más reciente."""
    if not carpeta.exists():
        return []
    return sorted(carpeta.glob(f"{PREFIJO}*{SUFIJO}"))


def hay_de_hoy(carpeta: Path, hoy=None) -> bool:
    hoy = hoy or datetime.now()
    marca = f"{PREFIJO}{hoy:%Y%m%d}"
    return any(r.name.startswith(marca) for r in respaldos_en(carpeta))


def respaldar(destino: Path, conservar: int = 14, ahora=None, conexion=None) -> Path:
    """Escribe una copia coherente y comprobada. Devuelve su ruta."""
    conexion = conexion or connection
    if conexion.vendor != "sqlite":
        raise CommandError(
            "Este comando respalda la base SQLite de una portable. En un servidor con "
            "PostgreSQL use pg_dump (ver docs/ORACLE_CLOUD.md)."
        )
    ahora = ahora or datetime.now()
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / f"{PREFIJO}{ahora:%Y%m%d-%H%M%S}{SUFIJO}"
    if archivo.exists():
        raise CommandError(f"Ya existe {archivo.name}.")

    conexion.ensure_connection()
    with conexion.cursor() as cursor:
        # El nombre va como parámetro, no pegado en el SQL: una ruta con una
        # comilla no puede convertirse en otra sentencia.
        cursor.execute("VACUUM INTO %s", [str(archivo)])

    comprobacion = sqlite3.connect(archivo)
    try:
        estado = comprobacion.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        comprobacion.close()
    if estado != "ok":
        archivo.unlink(missing_ok=True)
        raise CommandError(f"La copia salió dañada ({estado}) y se descartó.")

    for viejo in respaldos_en(destino)[:-conservar] if conservar > 0 else []:
        viejo.unlink(missing_ok=True)
    return archivo


class Command(BaseCommand):
    help = "Copia de seguridad coherente y comprobada de la base de la portable."

    def add_arguments(self, parser):
        parser.add_argument("--destino", default=None, help="Carpeta de destino.")
        parser.add_argument(
            "--conservar", type=int, default=14, help="Cuántos respaldos guardar (14)."
        )
        parser.add_argument(
            "--si-no-hay-de-hoy",
            action="store_true",
            help="No hacer nada si ya hay uno de hoy (lo usa el arranque).",
        )

    def handle(self, *args, **opciones):
        destino = Path(opciones["destino"]) if opciones["destino"] else carpeta_por_omision()
        if opciones["si_no_hay_de_hoy"] and hay_de_hoy(destino):
            return
        archivo = respaldar(destino, opciones["conservar"])
        tamano = archivo.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(f"Respaldo comprobado: {archivo} ({tamano:.1f} MB)."))
