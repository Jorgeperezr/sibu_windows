"""
La copia de seguridad de la portable.

No existía ninguna: perder el disco era perder todas las historias clínicas.
Y la salida obvia —copiar `sibu.sqlite3` a mano— puede dar una copia rota: la
base va en modo WAL, y lo último escrito vive en `sibu.sqlite3-wal`, no en el
archivo principal. `VACUUM INTO` hace una instantánea coherente con el WAL
incluido.

Las pruebas usan una conexión de Django real contra un SQLite real en modo WAL,
sin migrar una base entera.
"""

from datetime import datetime
from pathlib import Path

import pytest
from django.core.management.base import CommandError
from django.db.backends.sqlite3.base import DatabaseWrapper

from apps.core.management.commands import respaldar as modulo


@pytest.fixture
def base_wal(tmp_path, db):
    """Una base SQLite en WAL con filas que todavía NO pasaron al archivo principal."""
    ruta = tmp_path / "datos" / "sibu.sqlite3"
    ruta.parent.mkdir()
    conexion = DatabaseWrapper(
        {
            "NAME": str(ruta),
            "OPTIONS": {},
            "TIME_ZONE": None,
            "CONN_MAX_AGE": 0,
            "CONN_HEALTH_CHECKS": False,
            "AUTOCOMMIT": True,
            "ATOMIC_REQUESTS": False,
            "USER": "",
            "PASSWORD": "",
            "HOST": "",
            "PORT": "",
        },
        alias="respaldo",
    )
    with conexion.cursor() as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.execute("PRAGMA wal_autocheckpoint=0")  # que nada pase solo al principal
        c.execute("CREATE TABLE historia (texto TEXT)")
        for i in range(50):
            c.execute("INSERT INTO historia VALUES (%s)", [f"consulta {i}"])
    yield conexion, ruta
    conexion.close()


def _filas(archivo: Path) -> int:
    import sqlite3

    con = sqlite3.connect(archivo)
    try:
        return con.execute("SELECT COUNT(*) FROM historia").fetchone()[0]
    finally:
        con.close()


def test_copiar_el_archivo_a_mano_pierde_lo_que_esta_en_el_wal(base_wal, tmp_path):
    """
    La premisa del defecto, comprobada: lo escrito sigue en el `-wal`, así que
    copiar solo el archivo principal no se lo lleva.
    """
    import shutil

    _conexion, ruta = base_wal
    assert Path(str(ruta) + "-wal").stat().st_size > 0, "las filas tienen que estar en el WAL"
    copia = tmp_path / "a_mano.sqlite3"
    shutil.copy(ruta, copia)

    import sqlite3

    con = sqlite3.connect(copia)
    tablas = con.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    con.close()
    assert ("historia",) not in tablas or _filas(copia) < 50


def test_el_respaldo_se_lleva_todo_incluido_el_wal(base_wal, tmp_path):
    conexion, _ruta = base_wal

    archivo = modulo.respaldar(tmp_path / "respaldos", conexion=conexion)

    assert _filas(archivo) == 50


def test_se_conservan_solo_los_ultimos(base_wal, tmp_path):
    conexion, _ruta = base_wal
    destino = tmp_path / "respaldos"
    for dia in range(1, 6):
        modulo.respaldar(destino, conservar=3, ahora=datetime(2026, 11, dia, 8), conexion=conexion)

    nombres = [r.name for r in modulo.respaldos_en(destino)]
    assert nombres == [
        "sibu-20261103-080000.sqlite3",
        "sibu-20261104-080000.sqlite3",
        "sibu-20261105-080000.sqlite3",
    ]


def test_el_arranque_no_repite_el_respaldo_del_dia(base_wal, tmp_path):
    conexion, _ruta = base_wal
    destino = tmp_path / "respaldos"
    assert not modulo.hay_de_hoy(destino, datetime(2026, 11, 5, 9))

    modulo.respaldar(destino, ahora=datetime(2026, 11, 5, 8), conexion=conexion)

    assert modulo.hay_de_hoy(destino, datetime(2026, 11, 5, 17))
    assert not modulo.hay_de_hoy(destino, datetime(2026, 11, 6, 8))


def test_una_ruta_con_comilla_no_rompe_ni_inyecta(base_wal, tmp_path):
    """El nombre viaja como parámetro, no pegado en el SQL."""
    conexion, _ruta = base_wal
    destino = tmp_path / "res'paldos"

    archivo = modulo.respaldar(destino, conexion=conexion)

    assert _filas(archivo) == 50


def test_en_postgresql_se_niega_y_dice_que_usar(db):
    """En el servidor el respaldo es `pg_dump`; este comando no finge hacerlo."""
    with pytest.raises(CommandError, match="pg_dump"):
        modulo.respaldar(Path("/tmp/no-se-usa"))
