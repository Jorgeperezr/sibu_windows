"""
Ficha propia del profesional.

`PerfilProfesional` solo se llenaba desde el panel de administración, así que
en la práctica el título y el registro profesional quedaban vacíos y no había
manera de corregir la cédula con la que se firma.

Lo que estas pruebas fijan sobre todo es lo que la pantalla NO deja hacer:
ampliarse el propio acceso.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.auditoria.models import LogAuditoria
from apps.expediente.tests.factories import crear_estructura, crear_profesional
from apps.usuarios.models import PerfilProfesional, Rol
from apps.usuarios.services import actualizar_mi_perfil

CLAVE = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    usuario, perfil = crear_profesional("medico_perfil", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()
    return {"est": est, "usuario": usuario, "perfil": perfil}


def _cliente(usuario):
    cliente = Client()
    assert cliente.login(username=usuario.username, password=CLAVE)
    return cliente


# ------------------------------------------------------------------ servicio


@pytest.mark.django_db
def test_guarda_titulo_registro_y_cedula(escenario):
    actualizar_mi_perfil(
        escenario["usuario"],
        {
            "titulo": "Médico General",
            "registro_profesional": "ACESS-1234",
            "cedula": "1101002002",
            "telefono": "0991112223",
        },
    )
    escenario["usuario"].refresh_from_db()
    escenario["perfil"].refresh_from_db()
    assert escenario["perfil"].titulo == "Médico General"
    assert escenario["perfil"].registro_profesional == "ACESS-1234"
    assert escenario["usuario"].cedula == "1101002002"
    assert escenario["usuario"].telefono == "0991112223"


@pytest.mark.django_db
def test_la_cedula_se_valida_con_el_modulo_10(escenario):
    with pytest.raises(ValidationError, match="módulo 10"):
        actualizar_mi_perfil(escenario["usuario"], {"cedula": "1104567890"})
    escenario["usuario"].refresh_from_db()
    assert not escenario["usuario"].cedula


@pytest.mark.django_db
def test_no_se_puede_tomar_la_cedula_de_otra_cuenta(escenario):
    otro, _ = crear_profesional(
        "otro_medico", escenario["est"]["medicina"], escenario["est"]["salud"]
    )
    otro.cedula = "1101002002"
    otro.save(update_fields=["cedula"])
    with pytest.raises(ValidationError, match="ya está registrada"):
        actualizar_mi_perfil(escenario["usuario"], {"cedula": "1101002002"})


@pytest.mark.django_db
def test_dos_cuentas_sin_cedula_conviven(escenario):
    """
    `cedula` es única y admite NULL. Guardar cadena vacía haría chocar a la
    segunda cuenta que se guardara sin cédula, así que se almacena NULL.
    """
    otro, _ = crear_profesional(
        "sin_cedula", escenario["est"]["medicina"], escenario["est"]["salud"]
    )
    actualizar_mi_perfil(escenario["usuario"], {"cedula": "", "titulo": "Médico"})
    actualizar_mi_perfil(otro, {"cedula": "", "titulo": "Médico"})
    escenario["usuario"].refresh_from_db()
    otro.refresh_from_db()
    assert escenario["usuario"].cedula is None
    assert otro.cedula is None


@pytest.mark.django_db
def test_el_cambio_queda_auditado(escenario):
    actualizar_mi_perfil(escenario["usuario"], {"titulo": "Médico General"})
    log = LogAuditoria.objects.filter(
        usuario=escenario["usuario"], accion=LogAuditoria.Accion.UPDATE, modulo="usuarios"
    ).first()
    assert log is not None
    assert log.detalle["campos"] == ["titulo"]


@pytest.mark.django_db
def test_crea_el_perfil_si_la_cuenta_no_lo_tenia(db):
    from apps.usuarios.models import Usuario

    suelto = Usuario.objects.create_user(
        username="sin_perfil", password=CLAVE, rol_principal=Rol.PROFESIONAL
    )
    assert not PerfilProfesional.objects.filter(usuario=suelto).exists()
    perfil = actualizar_mi_perfil(suelto, {"titulo": "Odontólogo"})
    assert perfil.titulo == "Odontólogo"


# ------------------------------------------------------------------- pantalla


@pytest.mark.django_db
def test_la_pantalla_muestra_los_datos_y_el_acceso(escenario):
    escenario["perfil"].titulo = "Médico General"
    escenario["perfil"].save()
    contenido = _cliente(escenario["usuario"]).get(reverse("usuarios:mi_perfil")).content.decode()
    assert "Médico General" in contenido
    assert "Medicina" in contenido  # el servicio asignado, en solo lectura


@pytest.mark.django_db
def test_el_formulario_no_deja_cambiar_rol_servicios_ni_seccion(escenario):
    """
    De estos campos depende el RBAC: una pantalla que los aceptara sería una
    vía para ampliarse el acceso a uno mismo. No se leen del POST.
    """
    psico = escenario["est"]["psicologia"]
    cliente = _cliente(escenario["usuario"])
    cliente.post(
        reverse("usuarios:mi_perfil"),
        {
            "titulo": "Médico General",
            "rol_principal": Rol.ADMIN_GENERAL,
            "servicios": [psico.pk],
            "seccion": psico.seccion_id,
            "puede_firmar_digital": "on",
            "is_superuser": "on",
        },
    )
    escenario["usuario"].refresh_from_db()
    escenario["perfil"].refresh_from_db()
    assert escenario["usuario"].rol_principal == Rol.PROFESIONAL
    assert escenario["usuario"].is_superuser is False
    assert escenario["perfil"].puede_firmar_digital is False
    assert list(escenario["perfil"].servicios.values_list("codigo", flat=True)) == ["medicina"]
    assert escenario["perfil"].seccion_id == escenario["est"]["salud"].pk
    assert escenario["perfil"].titulo == "Médico General"


@pytest.mark.django_db
def test_una_cedula_invalida_avisa_y_no_guarda_nada(escenario):
    cliente = _cliente(escenario["usuario"])
    respuesta = cliente.post(
        reverse("usuarios:mi_perfil"),
        {"cedula": "1104567890", "titulo": "Médico General"},
        follow=True,
    )
    assert "no es válida" in respuesta.content.decode()
    escenario["perfil"].refresh_from_db()
    assert escenario["perfil"].titulo == ""


@pytest.mark.django_db
def test_la_ficha_propia_exige_sesion(escenario):
    respuesta = Client().get(reverse("usuarios:mi_perfil"))
    assert respuesta.status_code == 302
    assert reverse("login") in respuesta.url


@pytest.mark.django_db
def test_guardar_una_cedula_valida_desde_la_pantalla(escenario):
    """
    La comprobación de cédula ajena consultaba `type(usuario).objects`. Desde
    una vista, `request.user` es un SimpleLazyObject y `type(...)` devuelve la
    envoltura, que no tiene manager: la pantalla daba 500. Las pruebas del
    servicio pasaban un Usuario real y no lo veían, y la del rechazo cortaba
    antes de llegar ahí. Esta atraviesa la vista con una cédula válida.
    """
    cliente = _cliente(escenario["usuario"])
    respuesta = cliente.post(
        reverse("usuarios:mi_perfil"),
        {"cedula": "1107008003", "titulo": "Médico General"},
        follow=True,
    )
    assert respuesta.status_code == 200
    escenario["usuario"].refresh_from_db()
    assert escenario["usuario"].cedula == "1107008003"


# ---------------------------------------------------- fecha y denominación


@pytest.mark.django_db
def test_guarda_fecha_de_nacimiento_y_denominacion_del_cargo(escenario):
    from apps.usuarios.services import actualizar_mi_perfil

    actualizar_mi_perfil(
        escenario["usuario"],
        {"fecha_nacimiento": "1990-05-14", "denominacion_cargo": "Médico General 1"},
    )
    escenario["usuario"].refresh_from_db()
    escenario["perfil"].refresh_from_db()
    assert str(escenario["usuario"].fecha_nacimiento) == "1990-05-14"
    assert escenario["perfil"].denominacion_cargo == "Médico General 1"


@pytest.mark.django_db
def test_una_fecha_de_nacimiento_futura_se_rechaza(escenario):
    from apps.usuarios.services import actualizar_mi_perfil

    with pytest.raises(ValidationError, match="futura"):
        actualizar_mi_perfil(escenario["usuario"], {"fecha_nacimiento": "2099-01-01"})
    escenario["usuario"].refresh_from_db()
    assert escenario["usuario"].fecha_nacimiento is None


@pytest.mark.django_db
def test_una_fecha_de_nacimiento_mal_escrita_se_rechaza(escenario):
    from apps.usuarios.services import actualizar_mi_perfil

    with pytest.raises(ValidationError, match="no es válida"):
        actualizar_mi_perfil(escenario["usuario"], {"fecha_nacimiento": "no-es-una-fecha"})


@pytest.mark.django_db
def test_una_fecha_vacia_borra_la_ya_guardada(escenario):
    """
    Igual que la cédula: el formulario reemplaza por completo lo que se envía,
    y dejar la casilla en blanco significa borrar el dato, no conservarlo.
    Cadena vacía tampoco intenta parsearse como fecha.
    """
    from apps.usuarios.services import actualizar_mi_perfil

    actualizar_mi_perfil(escenario["usuario"], {"fecha_nacimiento": "1990-05-14"})
    actualizar_mi_perfil(escenario["usuario"], {"fecha_nacimiento": ""})
    escenario["usuario"].refresh_from_db()
    assert escenario["usuario"].fecha_nacimiento is None
