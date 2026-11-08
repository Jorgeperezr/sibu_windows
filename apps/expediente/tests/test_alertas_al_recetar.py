"""
Al recetar, la consulta cruza el medicamento con las alertas del expediente.

Traído de clinube. Avisa, no decide: con confirmación se receta igual, pero
sin ella el servidor no lo añade, aunque falle el JavaScript o el formulario
se envíe a mano.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.expediente import alertas_receta
from apps.expediente.models import AlertaClinica
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.farmacia.models import Medicamento, Receta
from apps.medicina import services as med_services

CLAVE = "clave-larga-12345"


def _alerta(expediente, tipo, descripcion):
    return AlertaClinica.objects.create(
        expediente=expediente,
        tipo=tipo,
        descripcion=descripcion,
        origen=AlertaClinica.Origen.PROFESIONAL,
    )


def _med(dci, codigo):
    return Medicamento.objects.create(codigo=codigo, dci=dci, concentracion="500 mg")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "tipo,descripcion,dci,nivel",
    [
        ("alergia", "Alergia a la penicilina", "Amoxicilina", "alto"),
        ("alergia", "Penicilina (urticaria)", "Cefalexina", "medio"),
        ("alergia", "AINE: broncoespasmo con ibuprofeno", "Diclofenaco", "alto"),
        ("gestacion", "Gestación 20 semanas", "Doxiciclina", "alto"),
        ("riesgo", "Toma warfarina", "Ibuprofeno", "alto"),
    ],
)
def test_el_choque_se_detecta(tipo, descripcion, dci, nivel):
    exp = crear_expediente(cedula="1100000007")
    alertas = alertas_receta.alertas_del_expediente([_alerta(exp, tipo, descripcion)])
    resultado = alertas_receta.choques(_med(dci, "M1"), alertas)
    assert [c["nivel"] for c in resultado] == [nivel]
    assert descripcion in resultado[0]["fuente"], "dice de qué alerta salió"


@pytest.mark.django_db
@pytest.mark.parametrize("descripcion", ["Niega alergia a penicilina", "Sin alergias conocidas"])
def test_una_negacion_no_avisa(descripcion):
    exp = crear_expediente(cedula="1100000007")
    alertas = alertas_receta.alertas_del_expediente([_alerta(exp, "alergia", descripcion)])
    assert alertas_receta.choques(_med("Amoxicilina", "M1"), alertas) == []


@pytest.mark.django_db
def test_sin_alertas_paracetamol_no_choca():
    exp = crear_expediente(cedula="1100000007")
    alertas = alertas_receta.alertas_del_expediente([_alerta(exp, "alergia", "Penicilina")])
    assert alertas_receta.choques(_med("Paracetamol", "M1"), alertas) == []


@pytest.fixture
def consulta(db):
    est = crear_estructura()
    medico, perfil = crear_profesional("medico_alerta", est["medicina"], est["salud"])
    medico.set_password(CLAVE)
    medico.save()
    exp = crear_expediente(cedula="1100000007")
    _alerta(exp, "alergia", "Alergia a la penicilina")
    hc = med_services.crear_atencion_medicina(
        expediente=exp, profesional=perfil, motivo="Faringitis"
    )
    cliente = Client()
    assert cliente.login(username="medico_alerta", password=CLAVE)
    return {
        "hc": hc,
        "cliente": cliente,
        "amoxi": _med("Amoxicilina", "M1"),
        "url": reverse("medicina:consulta", args=[hc.pk]),
    }


def _recetar(c, **extra):
    datos = {"accion": "recetar", "medicamento": c["amoxi"].pk, "cantidad": 10, "dosis": "1"}
    datos.update(extra)
    return c["cliente"].post(c["url"], datos, follow=True)


def test_la_consulta_enseña_las_alertas_y_marca_el_medicamento(consulta):
    html = consulta["cliente"].get(consulta["url"]).content.decode()
    assert "Alergia a la penicilina" in html
    assert 'data-choque="Amoxicilina es una penicilina' in html
    assert "js/receta_alertas.js" in html


def test_sin_confirmar_no_se_receta(consulta):
    respuesta = _recetar(consulta)
    assert "No se añadió" in respuesta.content.decode()
    assert not Receta.objects.filter(atencion=consulta["hc"].atencion).exists()


def test_confirmado_se_receta_y_lo_dice(consulta):
    respuesta = _recetar(consulta, acepto_alerta="1")
    assert "Recetado pese a la alerta" in respuesta.content.decode()
    assert Receta.objects.filter(atencion=consulta["hc"].atencion).exists()
