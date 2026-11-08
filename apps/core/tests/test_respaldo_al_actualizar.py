"""
El arranque de la portable copia la base ANTES de migrar una versión nueva.

La copia diaria iba después de `migrate`: si una actualización dejaba la base
a medias, no había copia de cómo estaba antes. Y si la copia previa no se puede
hacer, no se migra.
"""

import importlib.util
from pathlib import Path

import pytest
from django.conf import settings


@pytest.fixture
def arrancar():
    ruta = Path(settings.BASE_DIR) / "portable" / "arrancar.py"
    spec = importlib.util.spec_from_file_location("arrancar_respaldo", ruta)
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _registrar(monkeypatch, arrancar, falla_en=None):
    import django.core.management as gestion

    orden = []

    def llamar(nombre, *args, **kwargs):
        orden.append((nombre, args))
        if nombre == falla_en and "--antes-de-actualizar" in args:
            raise RuntimeError("disco lleno")

    monkeypatch.setattr(gestion, "call_command", llamar)
    monkeypatch.setattr(arrancar, "optimizar_base", lambda: None)
    return orden


def test_la_copia_previa_va_antes_de_migrar(monkeypatch, arrancar):
    orden = _registrar(monkeypatch, arrancar)
    arrancar.preparar_carpeta(detallado=False)
    nombres = [n for n, _ in orden]
    assert nombres.index("respaldar") < nombres.index("migrate")
    assert "--antes-de-actualizar" in orden[0][1]


def test_si_la_copia_previa_falla_no_se_migra(monkeypatch, arrancar):
    orden = _registrar(monkeypatch, arrancar, falla_en="respaldar")
    with pytest.raises(SystemExit, match="no se actualizó"):
        arrancar.preparar_carpeta(detallado=False)
    assert "migrate" not in [n for n, _ in orden]


def test_la_copia_externa_se_lee_del_archivo(monkeypatch, arrancar, tmp_path):
    archivo = tmp_path / "copia_externa.txt"
    archivo.write_text('# un comentario\n"E:\\SIBU respaldos"\n', encoding="utf-8")
    monkeypatch.setattr(arrancar, "ARCHIVO_COPIA_EXTERNA", archivo)
    orden = _registrar(monkeypatch, arrancar)

    arrancar.preparar_carpeta(detallado=False)

    for nombre, args in orden:
        if nombre == "respaldar":
            assert args[-2:] == ("--copia-en", "E:\\SIBU respaldos")


def test_el_servidor_abierto_dias_sigue_respaldando(monkeypatch, arrancar):
    """La copia solo se hacía al arrancar, y el servidor de la oficina se
    deja abierto: una semana sin cerrar era una semana sin copias."""
    import threading

    hechas = threading.Event()
    monkeypatch.setattr(arrancar, "respaldo_del_dia", lambda *a: hechas.set())
    parar = arrancar.vigilar_respaldo_diario(intervalo=0.01)
    try:
        assert hechas.wait(2)
    finally:
        parar.set()
