"""
Un triaje en blanco no es un triaje.

Pulsar «Triaje» desde el expediente acabó mandando un POST vacío —una
regresión al pasar a POST todas las acciones del expediente—, y la vista lo
guardaba: un registro de signos vitales sin un solo valor, con el mensaje
«Signos vitales registrados. Disponibles para Medicina». Lo peor no era el
registro vacío: con él, la consulta médica dejaba de mostrar «Sin triaje
reciente», que es justo el aviso que Medicina necesita ver en ese caso.

Dos arreglos, cada uno con su prueba: el botón vuelve a ser un enlace, y la
vista ya no acepta un envío sin ningún signo.
"""

import pytest
from django.urls import reverse

from apps.core.models import Servicio
from apps.core.navegacion import ACCIONES_EXPEDIENTE
from apps.enfermeria.models import SignosVitales
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional

CLAVE = "clave-larga-12345"


@pytest.fixture
def enfermera(db):
    est = crear_estructura()
    enfermeria, _ = Servicio.objects.get_or_create(
        codigo="enfermeria", defaults={"nombre": "Enfermería", "seccion": est["salud"]}
    )
    usuario, _perfil = crear_profesional("enfermera", enfermeria, est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    return usuario


@pytest.mark.django_db
def test_un_envio_sin_signos_no_guarda_nada(enfermera, client):
    client.login(username="enfermera", password=CLAVE)
    expediente = crear_expediente(cedula="1104346091")

    respuesta = client.post(reverse("enfermeria:triaje", args=[expediente.pk]), follow=True)

    assert not SignosVitales.objects.exists(), "se guardó un triaje en blanco"
    contenido = respuesta.content.decode()
    assert "Signos vitales registrados" not in contenido
    assert "No se registró nada" in contenido


@pytest.mark.django_db
def test_con_un_solo_signo_si_se_guarda(enfermera, client):
    """Exigir un signo no puede convertirse en exigirlos todos."""
    client.login(username="enfermera", password=CLAVE)
    expediente = crear_expediente(cedula="1104346091")

    client.post(reverse("enfermeria:triaje", args=[expediente.pk]), {"temperatura": "36,7"})

    signos = SignosVitales.objects.get()
    assert str(signos.temperatura) == "36.7", "la coma decimal tiene que leerse"


@pytest.mark.django_db
def test_el_boton_de_triaje_es_un_enlace_y_el_de_consulta_un_formulario(enfermera, client):
    """
    Abrir una pantalla va por enlace; abrir una atención —que la CREA— por
    POST. Mezclarlos produce o el triaje en blanco o la historia por GET.
    """
    client.login(username="enfermera", password=CLAVE)
    expediente = crear_expediente(cedula="1104346091")

    contenido = client.get(reverse("expediente:detalle", args=[expediente.pk])).content.decode()
    destino = reverse("enfermeria:triaje", args=[expediente.pk])

    assert f'href="{destino}"' in contenido
    assert f'action="{destino}"' not in contenido


def test_solo_crean_las_acciones_que_abren_una_atencion():
    """
    La lista entera, para que una acción nueva tenga que decidir. Las que
    crean están protegidas con `require_POST`; las demás pintan un formulario.
    """
    crean = {a.url_name for a in ACCIONES_EXPEDIENTE if a.crea}

    assert crean == {
        "medicina:iniciar",
        "odontologia:iniciar",
        "psicologia:iniciar",
        "psicopedagogia:iniciar",
    }
