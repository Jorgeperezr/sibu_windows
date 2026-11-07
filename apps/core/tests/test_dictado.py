"""
Dictado por voz (traído de clinube).

El audio sale del equipo hacia Google, Microsoft o Apple. Lo que no se
negocia: en Psicología no hay dictado, ni aunque una plantilla lo pida.
"""

import shutil
import subprocess
from pathlib import Path

import pytest
from django.conf import settings
from django.template import Context, Template
from django.test import Client
from django.urls import reverse

from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.medicina import services as med_services

CLAVE = "clave-larga-12345"
RAIZ = Path(settings.BASE_DIR)


def _panel(codigo):
    return Template("{% load dictado %}{% dictado codigo %}").render(Context({"codigo": codigo}))


@pytest.mark.parametrize("codigo", ["psicologia", "trabajo-social", None, ""])
def test_el_panel_se_niega_donde_el_audio_no_puede_salir(codigo, settings):
    settings.SIBU_DICTADO = True
    assert "data-dictado" not in _panel(codigo)


def test_el_panel_aparece_en_medicina_y_se_apaga_con_la_configuracion(settings):
    settings.SIBU_DICTADO = True
    assert "data-dictado" in _panel("medicina")
    assert "dictado.js" in _panel("medicina")
    settings.SIBU_DICTADO = False
    assert "data-dictado" not in _panel("medicina")


def test_ninguna_plantilla_de_psicologia_pide_el_dictado():
    for plantilla in (RAIZ / "templates" / "psicologia").rglob("*.html"):
        texto = plantilla.read_text(encoding="utf-8")
        assert "dictado" not in texto, plantilla


@pytest.mark.django_db
def test_la_consulta_medica_lleva_el_dictado_con_sus_campos(settings):
    settings.SIBU_DICTADO = True
    est = crear_estructura()
    medico, perfil = crear_profesional("medico_dictado", est["medicina"], est["salud"])
    medico.set_password(CLAVE)
    medico.save()
    hc = med_services.crear_atencion_medicina(
        expediente=crear_expediente(cedula="1100000007"), profesional=perfil, motivo="Fiebre"
    )
    cliente = Client()
    assert cliente.login(username="medico_dictado", password=CLAVE)
    html = cliente.get(reverse("medicina:consulta", args=[hc.pk])).content.decode()
    assert "data-dictado-boton" in html
    for campo in ("enfermedad_actual", "plan_tratamiento", "indicaciones"):
        assert f'name="{campo}" rows' in html
    assert html.count("data-dictado-campo") == 4
    assert "js/dictado_texto.js" in html and "js/dictado.js" in html


@pytest.mark.skipif(shutil.which("node") is None, reason="sin Node no se prueba el JavaScript")
def test_la_logica_del_texto_dictado():
    prueba = RAIZ / "apps" / "core" / "tests" / "js" / "dictado_texto.test.cjs"
    r = subprocess.run(  # noqa: S603
        [shutil.which("node"), "--test", str(prueba)], capture_output=True, text=True, timeout=60
    )
    assert r.returncode == 0, r.stdout + r.stderr
