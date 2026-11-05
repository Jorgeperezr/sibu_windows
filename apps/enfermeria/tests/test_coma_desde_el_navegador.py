"""
El servidor leía «36,8»; el navegador nunca se lo dejaba llegar.

Un arreglo anterior hizo que el triaje leyera la coma decimal con
`core.numeros`, y su prueba lo comprobaba enviando «36,5» desde el cliente de
pruebas. Pasaba. Pero el cliente de pruebas no es un navegador: en la
pantalla, temperatura, peso y talla eran `<input type="number">`, y el campo
numérico de Chromium se COME la coma —en cualquier idioma del navegador—.
Comprobado con un navegador real: «36,8», «58,5» y «1,62» salían como 368, 585
y 162. La restricción de la base rechazaba 368 °C con un IntegrityError, y la
enfermera veía un error de servidor por escribir lo más normal.

Lo mismo en Psicopedagogía: «8,5» de promedio salía como 85 y el servicio, que
sí sabía leer la coma, respondía «debe estar entre 0 y 10».
"""

import re
from pathlib import Path

import pytest
from django.urls import reverse

from apps.core.models import Servicio
from apps.enfermeria.models import SignosVitales
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional

CLAVE = "clave-larga-12345"
PLANTILLAS = Path(__file__).resolve().parents[3] / "templates"
NUMERICO_CON_DECIMALES = re.compile(
    r'<input[^>]*type="number"[^>]*step="(0?\.\d+|any)"|<input[^>]*step="(0?\.\d+|any)"[^>]*type="number"'
)


@pytest.mark.parametrize(
    "plantilla", sorted(PLANTILLAS.rglob("*.html")), ids=lambda p: str(p.relative_to(PLANTILLAS))
)
def test_ningun_campo_decimal_es_type_number(plantilla):
    """
    Un `type="number"` con decimales destruye «36,8» antes de enviarlo. Use
    texto con `inputmode="decimal"` y deje la lectura a `core.numeros`.
    """
    assert not NUMERICO_CON_DECIMALES.search(plantilla.read_text(encoding="utf-8"))


@pytest.fixture
def cliente_enfermera(db, client):
    est = crear_estructura()
    enfermeria, _ = Servicio.objects.get_or_create(
        codigo="enfermeria", defaults={"nombre": "Enfermería", "seccion": est["salud"]}
    )
    usuario, _ = crear_profesional("enf_nav", enfermeria, est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    client.login(username="enf_nav", password=CLAVE)
    return client


@pytest.mark.django_db
def test_lo_que_mandaba_el_navegador_da_un_aviso_y_no_un_500(cliente_enfermera):
    """
    Si otro navegador vuelve a comerse la coma, la persona tiene que leer
    «quiso decir 36,8», no una página de error.
    """
    expediente = crear_expediente(cedula="1104346091")

    respuesta = cliente_enfermera.post(
        reverse("enfermeria:triaje", args=[expediente.pk]),
        {"temperatura": "368", "peso": "585", "talla": "162"},
        follow=True,
    )

    assert respuesta.status_code == 200
    assert not SignosVitales.objects.exists()
    contenido = respuesta.content.decode()
    assert "36,8" in contenido, "el aviso tiene que decir qué quiso escribir"


@pytest.mark.django_db
def test_presion_invertida_se_explica(cliente_enfermera):
    expediente = crear_expediente(cedula="1104346091")

    respuesta = cliente_enfermera.post(
        reverse("enfermeria:triaje", args=[expediente.pk]),
        {"pa_sistolica": "70", "pa_diastolica": "110"},
        follow=True,
    )

    assert not SignosVitales.objects.exists()
    assert "invertidas" in respuesta.content.decode()


@pytest.mark.django_db
def test_la_toma_correcta_con_coma_se_guarda_leida(cliente_enfermera):
    expediente = crear_expediente(cedula="1104346091")

    cliente_enfermera.post(
        reverse("enfermeria:triaje", args=[expediente.pk]),
        {"temperatura": "36,8", "peso": "58,5", "talla": "1,62"},
    )

    signos = SignosVitales.objects.get()
    assert (str(signos.temperatura), str(signos.peso), str(signos.talla)) == (
        "36.8",
        "58.50",
        "1.62",
    )
    assert signos.imc is not None, "con peso y talla el IMC se calcula"
