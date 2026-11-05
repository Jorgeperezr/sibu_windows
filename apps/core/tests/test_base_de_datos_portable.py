"""
La base de la portable, ajustada como el servidor donde importa.

**Una petición es una transacción.** `base.py` activa `ATOMIC_REQUESTS`, pero
`portable.py` redefine `DATABASES` entero y lo perdía. La portable era el único
entorno donde una pantalla que escribe dos registros y falla entre medias
dejaba la mitad guardada. Las pruebas corren contra PostgreSQL con los ajustes
de base, así que ninguna podía verlo.

Las pruebas de configuración FIJAN lo que afirman, no lo heredan: se carga el
módulo de ajustes de la portable con una carpeta de datos propia.
"""

import importlib
import sqlite3
import sys

import pytest


@pytest.fixture
def ajustes_portable(tmp_path, monkeypatch):
    monkeypatch.setenv("SIBU_DATOS", str(tmp_path / "datos"))
    monkeypatch.delenv("SECRET_KEY", raising=False)
    sys.modules.pop("config.settings.portable", None)
    modulo = importlib.import_module("config.settings.portable")
    yield modulo
    sys.modules.pop("config.settings.portable", None)


def test_la_portable_hace_de_cada_peticion_una_transaccion(ajustes_portable):
    assert ajustes_portable.DATABASES["default"].get("ATOMIC_REQUESTS") is True


def test_la_portable_pide_cache_y_temporales_en_memoria(ajustes_portable):
    """
    Se aplican de verdad: el `init_command` se ejecuta contra un SQLite real,
    sentencia a sentencia como hace Django, y se leen los PRAGMA.
    """
    opciones = ajustes_portable.DATABASES["default"]["OPTIONS"]
    conexion = sqlite3.connect(":memory:")
    for sentencia in opciones["init_command"].split(";"):
        if sentencia.strip():
            conexion.execute(sentencia)

    assert conexion.execute("PRAGMA cache_size").fetchone()[0] == -20000
    assert conexion.execute("PRAGMA temp_store").fetchone()[0] == 2  # 2 = MEMORY


def test_el_servidor_comprueba_la_conexion_antes_de_reutilizarla(monkeypatch):
    """
    Con conexiones reutilizadas, una muerta —PostgreSQL reiniciado, la red
    privada caída un momento— daba un 500 en la primera petición después.
    """
    monkeypatch.setenv("SECRET_KEY", "x" * 60)
    monkeypatch.setenv("ALLOWED_HOSTS", "sibu.unl.edu.ec")
    sys.modules.pop("config.settings.prod", None)
    prod = importlib.import_module("config.settings.prod")
    try:
        assert prod.DATABASES["default"]["CONN_HEALTH_CHECKS"] is True
        assert prod.DATABASES["default"]["ATOMIC_REQUESTS"] is True
    finally:
        sys.modules.pop("config.settings.prod", None)


def test_sin_transaccion_por_peticion_queda_la_mitad(tmp_path):
    """
    Lo que de verdad cambia, en un SQLite real: dos escrituras y un fallo entre
    medias. Dentro de una transacción no queda ninguna; fuera, la primera.
    """
    ruta = tmp_path / "prueba.sqlite3"
    conexion = sqlite3.connect(ruta, isolation_level=None)
    conexion.execute("CREATE TABLE t (x INTEGER)")

    # Sin transacción: cada sentencia se confirma sola.
    try:
        conexion.execute("INSERT INTO t VALUES (1)")
        raise RuntimeError("falla a mitad de la pantalla")
    except RuntimeError:
        pass
    assert conexion.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1

    # Con transacción: el fallo se lleva la primera escritura.
    conexion.execute("DELETE FROM t")
    conexion.execute("BEGIN")
    try:
        conexion.execute("INSERT INTO t VALUES (1)")
        raise RuntimeError("falla a mitad de la pantalla")
    except RuntimeError:
        conexion.execute("ROLLBACK")
    assert conexion.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 0


def test_el_arranque_optimiza_la_base(monkeypatch):
    """SQLite no recoge estadísticas solo; sin ellas elige índices a ciegas."""
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parents[3] / "portable"))
    import arrancar

    ejecutado = []

    class Cursor:
        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def execute(self, sql):
            ejecutado.append(sql)

    class Conexion:
        vendor = "sqlite"

        def cursor(self):
            return Cursor()

    monkeypatch.setattr("django.db.connection", Conexion())
    arrancar.optimizar_base()

    assert ejecutado == ["PRAGMA optimize"]
