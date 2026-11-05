"""
Cuántas consultas hace cada página, y que no vuelvan a crecer.

Medido con una base de 5 y de 20 pacientes: ninguna pantalla crecía con los
datos —no hay N+1—, pero todas pagaban un piso fijo inflado:

- El procesador de contexto `navegacion` calculaba los módulos visibles y
  luego `modulos_por_grupo` los volvía a calcular por su cuenta. Todo el
  recorrido del RBAC, dos veces, en cada página.
- `servicios_del_usuario` iba a la base en cada llamada: el expediente lo
  preguntaba seis veces.
- Las cuatro banderas de la matrícula (gestación, lactancia, catastrófica,
  NEE) hacían cuatro consultas casi iguales.

Resultado: portada de 14 a 10 consultas, expediente de 29 a 21.

Los topes de abajo son los medidos. Si una pantalla los pasa, alguien añadió
una consulta: que sea a propósito.
"""

import pytest
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from apps.expediente.models import AlertaClinica
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.usuarios import rbac


@pytest.fixture
def medica(db):
    est = crear_estructura()
    usuario, perfil = crear_profesional("medica_q", est["medicina"], est["salud"])
    return usuario, perfil, est


def _consultas(client, url):
    with CaptureQueriesContext(connection) as q:
        respuesta = client.get(url)
    assert respuesta.status_code == 200, url
    return [c["sql"] for c in q.captured_queries]


@pytest.mark.django_db
def test_la_portada_no_repite_el_calculo_del_menu(medica, client):
    usuario, _perfil, _est = medica
    client.force_login(usuario)

    sql = _consultas(client, reverse("inicio"))

    servicios = [s for s in sql if "usuarios_perfilprofesional_servicios" in s]
    assert len(servicios) == 1, f"los servicios del usuario se leyeron {len(servicios)} veces"
    assert len(sql) <= 10, f"la portada hace {len(sql)} consultas"


@pytest.mark.django_db
def test_el_expediente_lee_las_banderas_de_la_matricula_una_vez(medica, client):
    usuario, _perfil, _est = medica
    client.force_login(usuario)
    expediente = crear_expediente(cedula="1104346091")
    AlertaClinica.objects.create(expediente=expediente, tipo="gestacion", descripcion="x")

    sql = _consultas(client, reverse("expediente:detalle", args=[expediente.pk]))

    servicios = [s for s in sql if "usuarios_perfilprofesional_servicios" in s]
    assert len(servicios) == 1, f"los servicios del usuario se leyeron {len(servicios)} veces"
    assert len(sql) <= 21, f"el expediente hace {len(sql)} consultas"


@pytest.mark.django_db
def test_la_bandera_de_la_matricula_sigue_diciendo_la_verdad(medica):
    """Leerlas de una vez no puede cambiar lo que dicen."""
    from apps.expediente.selectors import valores_efectivos

    _usuario, _perfil, est = medica
    expediente = crear_expediente(cedula="1104346091")
    AlertaClinica.objects.create(expediente=expediente, tipo="gestacion", descripcion="x")
    AlertaClinica.objects.create(
        expediente=expediente, tipo="lactancia", descripcion="x", activa=False
    )

    filas = {f["variable"]: f["institucional"] for f in valores_efectivos(expediente, None)}

    assert filas["gestacion"] == "Sí"
    assert filas["lactancia"] == "No", "una alerta apagada no cuenta"


@pytest.mark.django_db
def test_una_asignacion_se_ve_en_el_acto_aunque_se_recuerden_los_servicios(medica):
    """
    Lo que podía salir mal al recordarlos: dar un servicio y que el mismo
    objeto siguiera diciendo que no lo tiene. Si eso pasara en la gestión de
    perfiles, quitar Psicología a alguien no surtiría efecto hasta la
    siguiente petición —y retirar acceso a lo sellado tiene que ser inmediato—.
    """
    usuario, perfil, est = medica
    assert rbac.servicios_del_usuario(usuario) == {est["medicina"].pk}

    perfil.servicios.add(est["psicologia"])
    assert rbac.servicios_del_usuario(usuario) == {est["medicina"].pk, est["psicologia"].pk}

    perfil.servicios.remove(est["psicologia"])
    assert rbac.servicios_del_usuario(usuario) == {est["medicina"].pk}

    perfil.servicios.set([])
    assert rbac.servicios_del_usuario(usuario) == set()


@pytest.mark.django_db
def test_lo_devuelto_no_altera_lo_recordado(medica):
    usuario, _perfil, est = medica
    copia = rbac.servicios_del_usuario(usuario)
    copia.add(999)

    assert rbac.servicios_del_usuario(usuario) == {est["medicina"].pk}


@pytest.mark.django_db
def test_solo_un_servicio_sellado_no_ofrece_exportar(db):
    """
    La comprobación de «exportable» dejó de ser una consulta propia y pasó a
    leerse de memoria. Tiene que seguir negando a quien solo atiende en uno
    sellado.
    """
    from apps.core.navegacion import modulos_visibles

    est = crear_estructura()
    usuario, _ = crear_profesional("psico_q", est["psicologia"], est["psico"])
    nombres = {m.url_name for m in modulos_visibles(usuario)}

    assert "reportes:exportar_hoja" not in nombres


@pytest.mark.django_db
def test_con_un_servicio_no_sellado_si_se_ofrece_exportar(medica):
    """La otra mitad: sin esta, la de arriba pasaría aunque nadie viera nunca el enlace."""
    from apps.core.navegacion import modulos_visibles

    usuario, _perfil, _est = medica
    assert "reportes:exportar_hoja" in {m.url_name for m in modulos_visibles(usuario)}
