"""
Las notificaciones se creaban y nadie las veía.

Seis sitios del sistema las escriben —cuatro en Laboratorio, uno en Psicología,
uno en el recordatorio de citas— y no había ninguna pantalla que las mostrara:
`apps/notificaciones/views.py` tenía una línea, `services.py` era un comentario
y no existía `urls.py`. El único lector era la propia tarea de citas,
comprobando duplicados.

Lo que eso significa en la práctica: Laboratorio publica un **valor crítico**,
el sistema avisa al médico que lo pidió, y el aviso no aparece en ninguna
parte. Un valor crítico que nadie ve es el peor de los silencios de un sistema
clínico.

Las notificaciones se aíslan por identidad, como el portal: cada quien ve las
suyas y nadie más las ve. No hay pantalla que liste las de otro, y no es un
olvido: el título de una notificación de Psicología ya diría de qué servicio es
el destinatario y sobre quién.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.notificaciones.models import Notificacion
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


def _usuario(nombre, rol=Rol.PROFESIONAL):
    usuario = Usuario.objects.create_user(username=nombre, password=CLAVE, rol_principal=rol)
    return usuario


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


@pytest.fixture
def escenario(db):
    medico = _usuario("med_notif")
    otro = _usuario("otro_notif")
    critica = Notificacion.objects.create(
        usuario=medico,
        tipo="resultado_critico",
        titulo="⚠ VALOR CRÍTICO — orden #7",
        mensaje="Potasio 7.1 mmol/L en Pérez Ríos María José.",
        referencia_tipo="OrdenLaboratorio",
        referencia_id=7,
    )
    normal = Notificacion.objects.create(
        usuario=medico,
        tipo="resultado_laboratorio",
        titulo="Resultados disponibles — orden #8",
        mensaje="La orden #8 tiene resultados publicados.",
    )
    ajena = Notificacion.objects.create(
        usuario=otro, tipo="resultado_laboratorio", titulo="No es suya", mensaje="."
    )
    return {"medico": medico, "otro": otro, "critica": critica, "normal": normal, "ajena": ajena}


# ------------------------------------------------------------- la bandeja


@pytest.mark.django_db
def test_cada_quien_ve_las_suyas(escenario):
    respuesta = _cliente(escenario["medico"]).get(reverse("notificaciones:bandeja"))
    assert respuesta.status_code == 200
    ids = {n.pk for n in respuesta.context["notificaciones"]}
    assert ids == {escenario["critica"].pk, escenario["normal"].pk}


@pytest.mark.django_db
def test_no_se_ven_las_de_otro_ni_cambiando_el_id(escenario):
    """
    Aislamiento por identidad, como el portal: la consulta parte del usuario de
    la sesión, no de un id de la URL.
    """
    cliente = _cliente(escenario["medico"])
    contenido = cliente.get(reverse("notificaciones:bandeja")).content.decode()
    assert "No es suya" not in contenido

    respuesta = cliente.post(reverse("notificaciones:leer", args=[escenario["ajena"].pk]))
    assert respuesta.status_code == 404
    escenario["ajena"].refresh_from_db()
    assert escenario["ajena"].estado != Notificacion.Estado.LEIDA


@pytest.mark.django_db
def test_un_anonimo_no_entra(escenario):
    respuesta = Client().get(reverse("notificaciones:bandeja"))
    assert respuesta.status_code in (302, 403)


# --------------------------------------------------------------- marcarlas


@pytest.mark.django_db
def test_marcar_una_como_leida_deja_constancia_de_cuando(escenario):
    """
    La hora importa y no es un adorno: sobre un valor crítico, «cuándo se vio»
    es exactamente lo que habría que poder responder después.
    """
    cliente = _cliente(escenario["medico"])
    cliente.post(reverse("notificaciones:leer", args=[escenario["critica"].pk]))

    escenario["critica"].refresh_from_db()
    assert escenario["critica"].estado == Notificacion.Estado.LEIDA
    assert escenario["critica"].leida_en is not None


@pytest.mark.django_db
def test_marcarlas_todas(escenario):
    cliente = _cliente(escenario["medico"])
    cliente.post(reverse("notificaciones:leer_todas"))

    pendientes = Notificacion.objects.filter(usuario=escenario["medico"]).exclude(
        estado=Notificacion.Estado.LEIDA
    )
    assert not pendientes.exists()
    # Y no toca las de nadie más.
    escenario["ajena"].refresh_from_db()
    assert escenario["ajena"].estado != Notificacion.Estado.LEIDA


@pytest.mark.django_db
def test_marcar_dos_veces_no_mueve_la_hora(escenario):
    """La primera lectura es la que cuenta; volver a pulsar no la reescribe."""
    from apps.notificaciones import services

    cliente = _cliente(escenario["medico"])
    cliente.post(reverse("notificaciones:leer", args=[escenario["critica"].pk]))
    escenario["critica"].refresh_from_db()
    primera = escenario["critica"].leida_en

    services.marcar_leida(escenario["critica"], escenario["medico"])
    escenario["critica"].refresh_from_db()
    assert escenario["critica"].leida_en == primera


# ------------------------------------------------- que se note que hay algo


@pytest.mark.django_db
def test_el_contador_de_no_leidas_sale_en_cualquier_pantalla(escenario):
    """
    Una bandeja que hay que ir a mirar no sirve para avisar de un valor
    crítico. El contador viaja en el contexto de todas las páginas.
    """
    respuesta = _cliente(escenario["medico"]).get(reverse("expediente:buscar"))
    assert respuesta.context["notificaciones_sin_leer"] == 2
    assert "notificaciones" in respuesta.content.decode().lower()


@pytest.mark.django_db
def test_el_contador_baja_al_leerlas(escenario):
    cliente = _cliente(escenario["medico"])
    cliente.post(reverse("notificaciones:leer", args=[escenario["critica"].pk]))
    respuesta = cliente.get(reverse("expediente:buscar"))
    assert respuesta.context["notificaciones_sin_leer"] == 1


@pytest.mark.django_db
def test_el_contador_de_un_anonimo_es_cero_y_no_revienta(escenario):
    """El ingreso es público: el procesador de contexto corre igual. (La
    portada ya no lo es: sin sesión lleva al ingreso.)"""
    respuesta = Client().get(reverse("login"))
    assert respuesta.status_code == 200
    assert respuesta.context["notificaciones_sin_leer"] == 0
