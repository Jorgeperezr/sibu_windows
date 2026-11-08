"""
El certificado de atención (traído de clinube): prellenado, editable, para
imprimir desde el navegador y sin diagnóstico salvo que se pida.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.auditoria.models import LogAuditoria
from apps.core.models import CIE10
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.medicina import services as med_services

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    medico, perfil = crear_profesional("medica_cert", est["medicina"], est["salud"])
    medico.set_password(CLAVE)
    medico.save()
    perfil.registro_profesional = "MSP-4471"
    perfil.save()
    psicologa, _ = crear_profesional("psico_cert", est["psicologia"], est["psico"])
    psicologa.set_password(CLAVE)
    psicologa.save()
    hc = med_services.crear_atencion_medicina(
        expediente=crear_expediente(cedula="1100000007"), profesional=perfil, motivo="Gripe"
    )
    CIE10.objects.get_or_create(codigo="J00", defaults={"descripcion": "Rinofaringitis aguda"})
    med_services.agregar_diagnostico(hc.atencion, "J00", principal=True)
    hc.dias_reposo = 2
    hc.save()
    cliente = Client()
    assert cliente.login(username="medica_cert", password=CLAVE)
    return {"hc": hc, "cliente": cliente, "url": reverse("medicina:certificado", args=[hc.pk])}


def test_viene_prellenado(escenario):
    html = escenario["cliente"].get(escenario["url"]).content.decode()
    assert 'value="2"' in html, "los días de reposo de la consulta"
    assert "J00 — Rinofaringitis aguda" in html


def test_sin_marcarlo_el_diagnostico_no_se_imprime(escenario):
    html = (
        escenario["cliente"]
        .post(
            escenario["url"],
            {
                "fecha": "2026-11-07",
                "dias_reposo": "2",
                "diagnostico": "J00 — Rinofaringitis aguda",
            },
        )
        .content.decode()
    )
    assert "Rinofaringitis" not in html
    assert escenario["hc"].atencion.expediente.persona.nombre_completo in html
    assert "MSP-4471" in html and "data-imprimir" in html


def test_marcado_se_imprime_y_queda_en_la_bitacora(escenario):
    html = (
        escenario["cliente"]
        .post(
            escenario["url"],
            {
                "fecha": "2026-11-07",
                "dias_reposo": "3",
                "incluir_diagnostico": "1",
                "diagnostico": "J00 — Rinofaringitis aguda",
            },
        )
        .content.decode()
    )
    assert "Rinofaringitis" in html and "<strong>3</strong>" in html
    registro = LogAuditoria.objects.get(entidad="CertificadoAtencion")
    assert registro.detalle == {"dias_reposo": "3", "con_diagnostico": True}


def test_quien_no_puede_ver_la_atencion_no_saca_su_certificado(escenario):
    otro = Client()
    otro.login(username="psico_cert", password=CLAVE)
    assert otro.get(escenario["url"]).status_code == 403
