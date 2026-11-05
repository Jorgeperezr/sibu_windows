"""
Una portable que atiende a los compañeros de la misma WiFi.

Hasta ahora cada portable escuchaba solo en `127.0.0.1`: compartir el zip con
la oficina daba un SIBU aislado por computador, cada uno con sus propios
pacientes. El modo servidor hace que uno de los equipos guarde los datos y
los demás entren desde los suyos.

Lo que se fija aquí:
- el servidor escucha en la red y en un puerto FIJO (los compañeros lo
  escriben una vez);
- acepta su nombre y sus IP como host y como origen de formularios;
- el modo queda guardado en la carpeta, para que el icono haga siempre lo
  mismo;
- la primera cuenta sigue sin poder crearse desde otro computador.
"""

import importlib
import socket
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(RAIZ / "portable"))

import arrancar  # noqa: E402


@pytest.fixture
def sin_entorno(monkeypatch):
    for var in ("SIBU_HOSTS", "SIBU_ORIGENES"):
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setenv("DJANGO_SETTINGS_MODULE", "config.settings.test")
    monkeypatch.setattr("django.setup", lambda: None)


def test_las_direcciones_de_red_llegan_a_los_ajustes(sin_entorno):
    arrancar.preparar_django(8000, ["RECEPCION", "192.168.1.23"])

    import os

    assert os.environ["SIBU_HOSTS"] == "RECEPCION,192.168.1.23"
    origenes = os.environ["SIBU_ORIGENES"].split(",")
    assert "http://RECEPCION:8000" in origenes
    assert "http://192.168.1.23:8000" in origenes, "sin esto, los formularios dan 403 desde la red"


def test_sin_modo_servidor_solo_el_propio_computador(sin_entorno):
    import os

    arrancar.preparar_django(51234)

    assert os.environ["SIBU_HOSTS"] == ""
    assert all("127.0.0.1" in o or "localhost" in o for o in os.environ["SIBU_ORIGENES"].split(","))


def test_los_ajustes_aceptan_esos_hosts(tmp_path, monkeypatch):
    """Lo FIJA la prueba, no lo hereda: se carga el módulo con un entorno propio."""
    monkeypatch.setenv("SIBU_DATOS", str(tmp_path / "datos"))
    monkeypatch.setenv("SIBU_HOSTS", "RECEPCION,192.168.1.23")
    monkeypatch.setenv("SIBU_ORIGENES", "http://RECEPCION:8000")
    sys.modules.pop("config.settings.portable", None)
    try:
        ajustes = importlib.import_module("config.settings.portable")
        assert {"RECEPCION", "192.168.1.23", "127.0.0.1"} <= set(ajustes.ALLOWED_HOSTS)
        assert "http://RECEPCION:8000" in ajustes.CSRF_TRUSTED_ORIGINS
    finally:
        sys.modules.pop("config.settings.portable", None)


def test_las_direcciones_empiezan_por_el_nombre_y_no_incluyen_el_bucle_local():
    """La IP la reparte el router y cambia; el nombre del equipo, no."""
    direcciones = arrancar.direcciones_de_red()

    assert direcciones[0] == socket.gethostname()
    assert not any(d.startswith("127.") for d in direcciones)


@pytest.fixture
def arranque_simulado(monkeypatch, tmp_path):
    """`main` hasta el `serve`, sin preparar una base ni abrir sockets."""
    llamado = {}
    monkeypatch.setattr(arrancar, "ARCHIVO_SERVIDOR", tmp_path / "servidor.txt")
    monkeypatch.setattr(arrancar, "ARCHIVO_MODO_SERVIDOR", tmp_path / "compartir_en_red.txt")
    monkeypatch.setattr(arrancar, "preparar_django", lambda p, d=None: llamado.update(dirs=d))
    monkeypatch.setattr(arrancar, "preparar_carpeta", lambda detallado: None)
    monkeypatch.setattr(arrancar, "hay_cuentas", lambda: True)
    monkeypatch.setattr(arrancar, "puerto_disponible", lambda p: True)
    monkeypatch.setattr(arrancar, "direcciones_de_red", lambda: ["RECEPCION", "192.168.1.23"])
    monkeypatch.setitem(sys.modules, "config.wsgi", type(sys)("config.wsgi"))
    sys.modules["config.wsgi"].application = object()
    import waitress

    monkeypatch.setattr(
        waitress, "serve", lambda app, host, port, threads: llamado.update(host=host, port=port)
    )
    return llamado, tmp_path


def test_en_modo_servidor_escucha_en_la_red_y_en_el_puerto_fijo(
    arranque_simulado, monkeypatch, capsys
):
    llamado, _ = arranque_simulado
    monkeypatch.setattr(sys, "argv", ["arrancar.py", "--modo-servidor", "--sin-navegador"])

    assert arrancar.main() == 0

    assert (llamado["host"], llamado["port"]) == ("0.0.0.0", 8000)
    salida = capsys.readouterr().out
    assert "http://RECEPCION:8000" in salida, "hay que decir qué escribir en los otros equipos"
    assert "sin cifrar" in salida, "y advertir de la WiFi compartida"


def test_el_modo_queda_guardado_para_el_icono(arranque_simulado, monkeypatch):
    """El icono arranca sin opciones: el modo tiene que leerse de la carpeta."""
    llamado, carpeta = arranque_simulado
    (carpeta / "compartir_en_red.txt").write_text("sí", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["arrancar.py", "--sin-navegador"])

    arrancar.main()

    assert llamado["host"] == "0.0.0.0"


def test_sin_compartir_sigue_siendo_solo_de_este_computador(arranque_simulado, monkeypatch):
    llamado, _ = arranque_simulado
    monkeypatch.setattr(sys, "argv", ["arrancar.py", "--sin-navegador"])

    arrancar.main()

    assert llamado["host"] == "127.0.0.1"
    assert llamado["dirs"] == []


def test_puerto_ocupado_se_dice(arranque_simulado, monkeypatch, capsys):
    monkeypatch.setattr(arrancar, "puerto_disponible", lambda p: False)
    monkeypatch.setattr(sys, "argv", ["arrancar.py", "--modo-servidor", "--sin-navegador"])

    assert arrancar.main() == 1
    assert "ya está en uso" in capsys.readouterr().out


@pytest.mark.django_db
def test_desde_otro_computador_se_entra_pero_no_se_reclama_la_primera_cuenta(settings, client):
    """
    Un compañero llega desde la WiFi: ve el ingreso normal. La pantalla de la
    primera cuenta sigue siendo solo del propio servidor, aunque no haya
    ninguna cuenta todavía.
    """
    settings.SIBU_PORTABLE = True
    settings.ALLOWED_HOSTS = ["127.0.0.1", "localhost", "RECEPCION"]

    respuesta = client.get("/cuentas/login/", HTTP_HOST="RECEPCION", REMOTE_ADDR="192.168.1.40")
    assert respuesta.status_code == 200

    respuesta = client.get("/cuentas/primera/", HTTP_HOST="RECEPCION", REMOTE_ADDR="192.168.1.40")
    assert respuesta.status_code == 404


def test_los_lanzadores_de_windows_existen_y_van_con_crlf():
    for nombre in (
        "Abrir SIBU.bat",
        "Compartir SIBU en la red.bat",
        "Conectar al SIBU de la oficina.bat",
    ):
        contenido = (RAIZ / nombre).read_bytes()
        assert b"\r\n" in contenido and b"\n" not in contenido.replace(b"\r\n", b""), nombre


def test_la_direccion_de_la_linea_de_ordenes_se_normaliza_igual(monkeypatch, capsys):
    """
    Se normalizaba solo la de `servidor.txt`: con `--servidor RECEPCION:8000`
    el arranque tomaba «RECEPCION» por esquema y daba el servidor por caído
    estando en pie. Comprobado contra un servidor real.
    """
    vistas = []
    monkeypatch.setattr(arrancar, "responde", lambda url, **k: vistas.append(url) or True)
    monkeypatch.setattr(
        sys, "argv", ["arrancar.py", "--servidor", "RECEPCION:8000", "--sin-navegador"]
    )

    assert arrancar.main() == 0
    assert vistas == ["http://RECEPCION:8000"]
