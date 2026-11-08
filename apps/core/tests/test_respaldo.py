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


def test_los_documentos_van_con_la_copia(base_wal, tmp_path, settings):
    """
    Viven en disco, no en la base: una copia sin ellos se restauraba con la
    lista de documentos y ninguno de los archivos.
    """
    import zipfile

    conexion, _ruta = base_wal
    docs = tmp_path / "documentos" / "7"
    docs.mkdir(parents=True)
    (docs / "abc.pdf").write_bytes(b"%PDF-1.4 informe")
    settings.SIBU_DOCUMENTOS_ROOT = str(tmp_path / "documentos")

    archivo = modulo.respaldar(tmp_path / "respaldos", conexion=conexion)

    zip_docs = Path(str(archivo).replace(".sqlite3", "-documentos.zip"))
    with zipfile.ZipFile(zip_docs) as zf:
        assert zf.read("7/abc.pdf") == b"%PDF-1.4 informe"


def test_al_rotar_se_va_tambien_su_zip(base_wal, tmp_path, settings):
    conexion, _ruta = base_wal
    (tmp_path / "documentos").mkdir()
    (tmp_path / "documentos" / "a.pdf").write_bytes(b"%PDF-1.4")
    settings.SIBU_DOCUMENTOS_ROOT = str(tmp_path / "documentos")
    destino = tmp_path / "respaldos"
    for dia in range(1, 4):
        modulo.respaldar(destino, conservar=1, ahora=datetime(2026, 11, dia, 8), conexion=conexion)

    assert sorted(p.name for p in destino.iterdir()) == [
        "sibu-20261103-080000-documentos.zip",
        "sibu-20261103-080000.sqlite3",
    ]


# ------------------------------------------------- antes de actualizar y fuera


def test_las_de_antes_de_actualizar_no_las_empujan_las_diarias(base_wal, tmp_path):
    """Tras una actualización que salió mal se tarda días en notarlo: las
    catorce diarias siguientes no pueden llevarse la copia de antes."""
    conexion, _ruta = base_wal
    destino = tmp_path / "respaldos"
    previa = modulo.respaldar(
        destino,
        conservar=5,
        ahora=datetime(2026, 11, 1, 7),
        conexion=conexion,
        prefijo=modulo.PREFIJO_ACTUALIZACION,
    )
    for dia in range(2, 8):
        modulo.respaldar(destino, conservar=2, ahora=datetime(2026, 11, dia, 8), conexion=conexion)

    assert previa.exists()
    assert len(modulo.respaldos_en(destino)) == 2


def test_la_copia_externa_llega_entera_y_rota(base_wal, tmp_path, settings):
    conexion, _ruta = base_wal
    (tmp_path / "documentos").mkdir()
    (tmp_path / "documentos" / "a.pdf").write_bytes(b"%PDF-1.4")
    settings.SIBU_DOCUMENTOS_ROOT = str(tmp_path / "documentos")
    externa = tmp_path / "disco_externo"
    externa.mkdir()
    for dia in range(1, 4):
        copia = modulo.respaldar(
            tmp_path / "respaldos", ahora=datetime(2026, 11, dia, 8), conexion=conexion
        )
        modulo.copiar_a(copia, externa, conservar=2)

    nombres = sorted(p.name for p in externa.iterdir())
    assert nombres == [
        "sibu-20261102-080000-documentos.zip",
        "sibu-20261102-080000.sqlite3",
        "sibu-20261103-080000-documentos.zip",
        "sibu-20261103-080000.sqlite3",
    ], "sin .parcial y con la rotación propia"
    assert _filas(externa / "sibu-20261103-080000.sqlite3") == 50


def test_sin_el_disco_externo_se_dice(base_wal, tmp_path):
    conexion, _ruta = base_wal
    copia = modulo.respaldar(tmp_path / "respaldos", conexion=conexion)
    with pytest.raises(CommandError, match="conectado el disco"):
        modulo.copiar_a(copia, tmp_path / "no_esta")


def test_una_copia_externa_distinta_se_descarta(base_wal, tmp_path, monkeypatch):
    conexion, _ruta = base_wal
    copia = modulo.respaldar(tmp_path / "respaldos", conexion=conexion)
    externa = tmp_path / "externa"
    externa.mkdir()
    huellas = iter(["mala", "buena"])
    monkeypatch.setattr(modulo, "_huella", lambda archivo: next(huellas))

    with pytest.raises(CommandError, match="no salió igual"):
        modulo.copiar_a(copia, externa)
    assert list(externa.iterdir()) == [], "ni el archivo ni su .parcial"


@pytest.mark.django_db
def test_con_la_base_al_dia_no_hay_migraciones_pendientes():
    assert modulo.hay_migraciones_pendientes() is False
