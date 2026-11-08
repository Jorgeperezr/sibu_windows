"""
La primera cuenta de la portable, desde el navegador.

Antes solo se creaba con `python portable/crear_cuenta.py` en una consola. En
un Windows sin Python instalado eso significa abrir una consola, ir a la
carpeta y escribir la ruta del Python que viaja dentro: justo lo que una
portable promete que no hace falta.

Lo que no se negocia: la pantalla existe SOLO en una portable, SOLO desde el
propio computador y SOLO mientras no hay ninguna cuenta. En el servidor de la
Unidad, un SIBU recién desplegado y sin cuentas sería de quien llegara primero.
"""

import pytest
from django.urls import reverse

from apps.usuarios.models import Rol, Usuario
from apps.usuarios.selectors import cuentas_de_persona

CLAVE = "Clave-Windows-2026!"
DATOS = {
    "cedula": "1100000007",
    "nombres": "Ana",
    "apellidos": "Primera",
    "clave": CLAVE,
    "clave2": CLAVE,
}


@pytest.fixture
def portable(settings):
    settings.SIBU_PORTABLE = True
    return settings


@pytest.mark.django_db
def test_sin_cuentas_el_ingreso_lleva_a_crear_la_primera(portable, client):
    respuesta = client.get(reverse("login"))

    assert respuesta.status_code == 302
    assert respuesta.headers["Location"] == reverse("primera_cuenta")


@pytest.mark.django_db
def test_la_primera_cuenta_es_de_administracion_y_entra_sola(portable, client):
    respuesta = client.post(reverse("primera_cuenta"), DATOS, follow=True)

    cuenta = Usuario.objects.get(username="1100000007")
    assert cuenta.rol_principal == Rol.ADMIN_GENERAL
    assert cuenta.check_password(CLAVE)
    assert cuenta.debe_cambiar_clave is False, "la clave la escribió su dueño"
    assert respuesta.wsgi_request.user == cuenta, "tras crearla, ya está dentro"
    assert "Nueva cuenta" in respuesta.content.decode() or "Perfiles" in respuesta.content.decode()


@pytest.mark.django_db
def test_con_una_cuenta_la_pantalla_deja_de_existir(portable, client):
    client.post(reverse("primera_cuenta"), DATOS)
    client.logout()

    assert client.get(reverse("primera_cuenta")).status_code == 404
    otra = {**DATOS, "cedula": "1700000001"}
    assert client.post(reverse("primera_cuenta"), otra).status_code == 404
    assert cuentas_de_persona().count() == 1


@pytest.mark.django_db
def test_con_cuentas_el_ingreso_es_el_de_siempre(portable, client):
    Usuario.objects.create_user(username="ya_hay", password="x")

    assert client.get(reverse("login")).status_code == 200


@pytest.mark.django_db
def test_en_el_servidor_no_existe(settings, client):
    """Un SIBU desplegado y vacío no puede ser de quien llegue primero."""
    settings.SIBU_PORTABLE = False

    assert client.get(reverse("primera_cuenta")).status_code == 404
    assert client.post(reverse("primera_cuenta"), DATOS).status_code == 404
    assert client.get(reverse("login")).status_code == 200
    assert not cuentas_de_persona().exists()


@pytest.mark.django_db
def test_desde_otro_computador_no_existe(portable, client):
    """Aunque alguien abriera el puerto de la portable a la red."""
    respuesta = client.post(reverse("primera_cuenta"), DATOS, REMOTE_ADDR="192.168.1.20")

    assert respuesta.status_code == 404
    assert not cuentas_de_persona().exists()


@pytest.mark.django_db
def test_una_cedula_invalida_no_crea_nada(portable, client):
    respuesta = client.post(reverse("primera_cuenta"), {**DATOS, "cedula": "1104567890"})

    assert respuesta.status_code == 200
    assert "no es válida" in respuesta.content.decode()
    assert not cuentas_de_persona().exists()


@pytest.mark.django_db
def test_las_claves_distintas_se_dicen_y_no_se_crea(portable, client):
    respuesta = client.post(reverse("primera_cuenta"), {**DATOS, "clave2": "otra-cosa-2026"})

    assert "no coinciden" in respuesta.content.decode()
    assert not cuentas_de_persona().exists()


@pytest.mark.django_db
def test_la_clave_no_puede_ser_la_cedula(portable, client):
    client.post(reverse("primera_cuenta"), {**DATOS, "clave": "1100000007", "clave2": "1100000007"})

    assert not cuentas_de_persona().exists()


def test_el_arranque_abre_el_navegador_en_la_primera_cuenta():
    """Sin cuentas, el navegador se abre donde se crea la primera."""
    from pathlib import Path

    fuente = (Path(__file__).resolve().parents[3] / "portable" / "arrancar.py").read_text(
        encoding="utf-8"
    )
    assert 'destino = f"{url}cuentas/primera/"' in fuente
    assert "abrir_navegador(destino, puerto)" in fuente
    assert "crear_cuenta.py" not in fuente, "ya no se manda a escribir comandos"


@pytest.mark.django_db
def test_la_cuenta_principal_puede_entrar_con_su_correo_y_un_pin(portable, client):
    client.post(
        "/cuentas/primera/",
        {
            "cedula": "1100000007",
            "nombres": "Ada",
            "apellidos": "Admin",
            "correo": "Ada@unl.edu.ec",
            "clave": "4826",
            "clave2": "4826",
        },
        REMOTE_ADDR="127.0.0.1",
    )
    from django.test import Client

    otro = Client(REMOTE_ADDR="192.168.1.40")
    assert otro.login(username="ada@unl.edu.ec", password="4826")
