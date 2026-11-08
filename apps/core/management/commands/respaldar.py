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

Los documentos del expediente van en un zip al lado, con la misma fecha.

Dos resguardos más, porque una copia en el mismo disco muere con el disco y
una actualización es el momento en que más fácil se rompe la base:

    python manage.py respaldar --antes-de-actualizar   # el arranque, si hay migraciones
    python manage.py respaldar --copia-en E:/SIBU-respaldos  # además, a otro disco

Las de antes de actualizar llevan otro nombre (`antes-de-actualizar-…`) y su
propia rotación: las diarias no las empujan fuera, porque tras una
actualización que salió mal hacen falta días en darse cuenta.

IMPORTANTE: la copia contiene la base ENTERA y todos los documentos,
contenido de Psicología incluido. Va a donde vaya la carpeta, y debe ir solo a un disco cifrado bajo
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
PREFIJO_ACTUALIZACION = "antes-de-actualizar-"
SUFIJO = ".sqlite3"
CONSERVAR_ACTUALIZACIONES = 5


def carpeta_por_omision() -> Path:
    return Path(settings.DATABASES["default"]["NAME"]).parent / "respaldos"


def respaldos_en(carpeta: Path, prefijo: str = PREFIJO) -> list[Path]:
    """Los respaldos de la carpeta, del más antiguo al más reciente."""
    if not carpeta.exists():
        return []
    return sorted(carpeta.glob(f"{prefijo}*{SUFIJO}"))


def hay_de_hoy(carpeta: Path, hoy=None) -> bool:
    hoy = hoy or datetime.now()
    marca = f"{PREFIJO}{hoy:%Y%m%d}"
    return any(r.name.startswith(marca) for r in respaldos_en(carpeta))


def zip_de(copia: Path) -> Path:
    return Path(str(copia)[: -len(SUFIJO)] + "-documentos.zip")


def respaldar(
    destino: Path, conservar: int = 14, ahora=None, conexion=None, prefijo: str = PREFIJO
) -> Path:
    """Escribe una copia coherente y comprobada. Devuelve su ruta."""
    conexion = conexion or connection
    if conexion.vendor != "sqlite":
        raise CommandError(
            "Este comando respalda la base SQLite de una portable. En un servidor con "
            "PostgreSQL use pg_dump (ver docs/ORACLE_CLOUD.md)."
        )
    ahora = ahora or datetime.now()
    destino.mkdir(parents=True, exist_ok=True)
    archivo = destino / f"{prefijo}{ahora:%Y%m%d-%H%M%S}{SUFIJO}"
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

    respaldar_documentos(archivo)
    rotar(destino, conservar, prefijo)
    return archivo


def rotar(carpeta: Path, conservar: int, prefijo: str = PREFIJO) -> None:
    for viejo in respaldos_en(carpeta, prefijo)[:-conservar] if conservar > 0 else []:
        viejo.unlink(missing_ok=True)
        zip_de(viejo).unlink(missing_ok=True)


def _huella(archivo: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(archivo, "rb") as f:
        for bloque in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloque)
    return h.hexdigest()


def copiar_a(copia: Path, carpeta: Path, conservar: int = 14, prefijo: str = PREFIJO) -> Path:
    """
    Lleva una copia ya comprobada a otra carpeta (un disco externo, una
    memoria, otra unidad) y comprueba que llegó entera.

    Se copia primero con un nombre provisional y se renombra al final: un
    disco que se desconecta a mitad deja un `.parcial`, nunca un archivo con
    nombre de respaldo bueno que no lo es.
    """
    import shutil

    if not carpeta.is_dir():
        raise CommandError(
            f"La carpeta de la copia externa no está disponible: {carpeta}. "
            "¿Está conectado el disco?"
        )
    destinos = []
    for origen in (copia, zip_de(copia)):
        if not origen.exists():
            continue
        final = carpeta / origen.name
        parcial = carpeta / (origen.name + ".parcial")
        shutil.copyfile(origen, parcial)
        if _huella(parcial) != _huella(origen):
            parcial.unlink(missing_ok=True)
            raise CommandError(f"La copia en {carpeta} no salió igual a la original; se descartó.")
        parcial.replace(final)
        destinos.append(final)
    rotar(carpeta, conservar, prefijo)
    return destinos[0]


def hay_migraciones_pendientes(conexion=None) -> bool:
    """
    ¿El código que arranca trae cambios de esquema que esta base no tiene?
    Es la señal de que se está estrenando una versión nueva.
    """
    from django.db.migrations.executor import MigrationExecutor

    conexion = conexion or connection
    if "django_migrations" not in conexion.introspection.table_names():
        return False  # base nueva: no hay nada que proteger
    ejecutor = MigrationExecutor(conexion)
    return bool(ejecutor.migration_plan(ejecutor.loader.graph.leaf_nodes()))


def respaldar_documentos(copia_base: Path) -> Path | None:
    """
    Los documentos del expediente, junto a la copia de la base.

    Viven en disco, no en la base: sin esto, una copia restaurada traía la
    lista de documentos y ninguno de los archivos. Van en un zip con el mismo
    sello de fecha, y se comprueba antes de darlo por bueno.
    """
    import zipfile

    origen = Path(getattr(settings, "SIBU_DOCUMENTOS_ROOT", ""))
    if not origen.is_dir() or not any(origen.rglob("*")):
        return None
    zip_destino = zip_de(copia_base)
    with zipfile.ZipFile(zip_destino, "w", zipfile.ZIP_DEFLATED) as zf:
        for archivo in sorted(origen.rglob("*")):
            if archivo.is_file():
                zf.write(archivo, archivo.relative_to(origen))
    with zipfile.ZipFile(zip_destino) as zf:
        if zf.testzip() is not None:
            zip_destino.unlink(missing_ok=True)
            raise CommandError("La copia de los documentos salió dañada y se descartó.")
    return zip_destino


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
        parser.add_argument(
            "--antes-de-actualizar",
            action="store_true",
            help="Copia previa a migrar una versión nueva; solo si hay migraciones pendientes.",
        )
        parser.add_argument(
            "--copia-en", default=None, help="Llevar también la copia a esta carpeta (otro disco)."
        )

    def handle(self, *args, **opciones):
        destino = Path(opciones["destino"]) if opciones["destino"] else carpeta_por_omision()
        prefijo, conservar = PREFIJO, opciones["conservar"]
        if opciones["antes_de_actualizar"]:
            if not hay_migraciones_pendientes():
                return
            prefijo, conservar = PREFIJO_ACTUALIZACION, CONSERVAR_ACTUALIZACIONES
        elif opciones["si_no_hay_de_hoy"] and hay_de_hoy(destino):
            # La de hoy ya está; pero si el disco externo no estaba conectado
            # cuando se hizo, se lleva ahora en lugar de esperar a mañana.
            externa = Path(opciones["copia_en"]) if opciones["copia_en"] else None
            if externa and externa.is_dir() and not hay_de_hoy(externa):
                copiar_a(respaldos_en(destino)[-1], externa, conservar)
                self.stdout.write(self.style.SUCCESS(f"Copia de hoy llevada a: {externa}"))
            return
        archivo = respaldar(destino, conservar, prefijo=prefijo)
        tamano = archivo.stat().st_size / (1024 * 1024)
        self.stdout.write(self.style.SUCCESS(f"Respaldo comprobado: {archivo} ({tamano:.1f} MB)."))
        if opciones["copia_en"]:
            externa = copiar_a(archivo, Path(opciones["copia_en"]), conservar, prefijo)
            self.stdout.write(self.style.SUCCESS(f"Copia también en: {externa}"))
