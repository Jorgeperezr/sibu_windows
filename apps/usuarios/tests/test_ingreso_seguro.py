"""
El ingreso: correo o usuario, clave breve, y el bloqueo que la hace aceptable.

La Unidad pidió claves breves —un PIN de 4 dígitos—. Con 10 000 combinaciones
lo que protege la cuenta son dos cosas, y las dos se prueban aquí: que no se
acepten los PIN que se prueban primero, y que tras 10 fallos la cuenta quede
cerrada hasta que Administración General la abra.
"""

import pytest
from django.conf import settings
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.auditoria.models import LogAuditoria
from apps.usuarios.ingreso import desbloquear
from apps.usuarios.models import Rol, Usuario

PIN = "4826"


@pytest.fixture
def cuenta(db):
    return Usuario.objects.create_user(
        username="1100000007",
        cedula="1100000007",
        email="Ana.Perez@unl.edu.ec",
        password=PIN,
        first_name="Ana",
        last_name="Pérez",
        rol_principal=Rol.PROFESIONAL,
    )


def _intentar(clave, quien="ana.perez@unl.edu.ec", ip="192.168.1.40"):
    cliente = Client(REMOTE_ADDR=ip)
    respuesta = cliente.post(reverse("login"), {"username": quien, "password": clave})
    return cliente, respuesta


# ------------------------------------------------------------------ la clave


def test_un_pin_de_cuatro_digitos_vale(cuenta):
    validate_password("4826", user=cuenta)


@pytest.mark.parametrize("clave", ["123", "1234", "0000", "7777", "9876", "2580", "0007"])
def test_los_pin_que_se_prueban_primero_no_valen(cuenta, clave):
    """«2580» está en la lista de Django; «0007» sale de la cédula 1100000007."""
    with pytest.raises(ValidationError):
        validate_password(clave, user=cuenta)


# ------------------------------------------------------------------ el correo


def test_se_entra_con_el_correo_sin_distinguir_mayusculas(cuenta):
    cliente, respuesta = _intentar(PIN, quien="  ANA.PEREZ@unl.edu.ec ")
    assert respuesta.status_code == 302
    assert cliente.session["_auth_user_id"] == str(cuenta.pk)


def test_se_sigue_entrando_con_la_cedula(cuenta):
    _cliente, respuesta = _intentar(PIN, quien="1100000007")
    assert respuesta.status_code == 302


def test_un_correo_compartido_no_abre_ninguna_de_las_dos(cuenta):
    """Adivinar cuál de las dos es la buena sería abrir la ajena."""
    Usuario.objects.create_user(
        username="1700000001", email="ana.perez@unl.edu.ec", password="otra-9182"
    )
    _cliente, respuesta = _intentar(PIN)
    assert respuesta.status_code == 200
    assert "_auth_user_id" not in _cliente.session


# ------------------------------------------------------------------ el bloqueo


def test_tras_diez_fallos_la_cuenta_queda_cerrada_aunque_luego_acierte(cuenta):
    for intento in range(settings.SIBU_BLOQUEO_CUENTA):
        _intentar(f"{9000 + intento}")
    cuenta.refresh_from_db()
    assert cuenta.bloqueada_desde is not None

    cliente, respuesta = _intentar(PIN, ip="10.0.0.99")  # desde OTRO equipo
    assert "_auth_user_id" not in cliente.session
    assert "bloqueada" in respuesta.content.decode(), "se dice, y qué hacer"
    assert LogAuditoria.objects.filter(detalle__evento="bloqueo_por_intentos").exists()


def test_nueve_fallos_no_bloquean_y_entrar_pone_el_contador_a_cero(cuenta):
    for intento in range(settings.SIBU_BLOQUEO_CUENTA - 1):
        _intentar(f"{9000 + intento}")
    _intentar(PIN)
    cuenta.refresh_from_db()
    assert cuenta.bloqueada_desde is None and cuenta.intentos_fallidos == 0


def test_administracion_la_desbloquea_y_queda_escrito(cuenta):
    admin = Usuario.objects.create_user(
        username="admin_b", password="x-91827", rol_principal=Rol.ADMIN_GENERAL
    )
    for intento in range(settings.SIBU_BLOQUEO_CUENTA):
        _intentar(f"{9000 + intento}")

    desbloquear(cuenta, por=admin)

    cliente, respuesta = _intentar(PIN)
    assert respuesta.status_code == 302
    assert LogAuditoria.objects.filter(usuario=admin, detalle__evento="desbloqueo").exists()


def test_en_la_portable_el_propio_servidor_no_queda_fuera(cuenta, settings):
    """Si la única cuenta de Administración queda bloqueada, alguien tiene que
    poder abrirla: quien está en el equipo servidor ya tiene la base en su disco."""
    settings.SIBU_PORTABLE = True
    for intento in range(settings.SIBU_BLOQUEO_CUENTA):
        _intentar(f"{9000 + intento}")

    _cliente, respuesta = _intentar(PIN, ip="127.0.0.1")
    assert respuesta.status_code == 302
    _cliente, respuesta = _intentar(PIN, ip="192.168.1.40")
    assert respuesta.status_code == 302, "y al entrar se levantó el bloqueo"


def test_en_el_servidor_de_la_unidad_localhost_no_es_excepcion(cuenta, settings):
    settings.SIBU_PORTABLE = False
    for intento in range(settings.SIBU_BLOQUEO_CUENTA):
        _intentar(f"{9000 + intento}")
    cliente, _ = _intentar(PIN, ip="127.0.0.1")
    assert "_auth_user_id" not in cliente.session


# ------------------------------------------------------------ enlace y sesión


def test_la_direccion_sola_lleva_al_ingreso_corto(db):
    respuesta = Client().get("/")
    assert respuesta.status_code == 302 and respuesta["Location"] == "/ingresar/"
    assert Client().get("/ingresar/").status_code == 200
    assert Client().get("/cuentas/login/").status_code == 200, "los marcadores viejos siguen"


def test_la_sesion_dura_una_jornada_y_no_muere_al_cerrar_el_navegador():
    """Antes: 15 minutos desde el INGRESO en producción, aunque se trabajara."""
    assert settings.SESSION_EXPIRE_AT_BROWSER_CLOSE is False
    assert settings.SESSION_COOKIE_AGE >= 8 * 60 * 60
    from pathlib import Path

    prod = (Path(settings.BASE_DIR) / "config" / "settings" / "prod.py").read_text(encoding="utf-8")
    assert "SESSION_COOKIE_AGE =" not in prod and "SESSION_EXPIRE_AT_BROWSER_CLOSE =" not in prod


def test_usar_la_sesion_la_renueva(cuenta, monkeypatch):
    """La caducidad se cuenta desde la última vez que se usó, no desde el ingreso."""
    import time

    from django.contrib.sessions.models import Session

    cliente, _ = _intentar(PIN)
    clave = cliente.session.session_key
    antes = Session.objects.get(session_key=clave).expire_date

    real = time.time
    monkeypatch.setattr(time, "time", lambda: real() + 2 * 60 * 60)  # dos horas después
    cliente.get(reverse("inicio"))

    assert Session.objects.get(session_key=clave).expire_date > antes


def test_la_consola_abre_la_cuenta_cuando_no_queda_nadie(cuenta):
    from django.core.management import call_command

    for intento in range(settings.SIBU_BLOQUEO_CUENTA):
        _intentar(f"{9000 + intento}")
    call_command("desbloquear", "ana.perez@unl.edu.ec")
    cuenta.refresh_from_db()
    assert cuenta.bloqueada_desde is None and cuenta.intentos_fallidos == 0
