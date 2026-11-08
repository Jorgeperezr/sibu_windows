"""
Administración General da de alta las credenciales y las funciones en un paso,
y después las edita.

Lo pidió la Unidad: desde el equipo servidor, la cuenta principal genera el
acceso de cada profesional —correo, clave (un PIN vale), nombre completo,
sección y funciones— y puede corregirlo luego. Lo que no cambia: solo
Administración General lo hace, la clave nace temporal y la bitácora dice qué
entró, nunca la clave.
"""

import pytest
from django.test import Client
from django.urls import reverse

from apps.auditoria.models import LogAuditoria
from apps.expediente.tests.factories import crear_estructura
from apps.usuarios.models import PerfilProfesional, Rol, Usuario

CLAVE_ADMIN = "clave-larga-12345"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    admin = Usuario.objects.create_user(
        username="1100000007",
        password=CLAVE_ADMIN,
        first_name="Ada",
        last_name="Admin",
        rol_principal=Rol.ADMIN_GENERAL,
    )
    cliente = Client()
    assert cliente.login(username=admin.username, password=CLAVE_ADMIN)
    return {"est": est, "admin": admin, "cliente": cliente}


def _alta(e, **cambios):
    datos = {
        "correo": "Lucia.Pardo@unl.edu.ec",
        "clave": "4826",
        "nombres": "Lucía",
        "apellidos": "Pardo",
        "seccion": str(e["est"]["salud"].pk),
        "rol": Rol.PROFESIONAL,
        "servicios": [str(e["est"]["medicina"].pk)],
    }
    datos.update(cambios)
    return e["cliente"].post(reverse("usuarios:nueva_cuenta"), datos)


def test_un_solo_paso_deja_la_cuenta_lista_para_atender(escenario):
    respuesta = _alta(escenario)

    assert respuesta.status_code == 302
    cuenta = Usuario.objects.get(email="lucia.pardo@unl.edu.ec")
    perfil = PerfilProfesional.objects.get(usuario=cuenta)
    assert perfil.seccion == escenario["est"]["salud"]
    assert list(perfil.servicios.all()) == [escenario["est"]["medicina"]]
    assert cuenta.get_full_name() == "Lucía Pardo"
    assert cuenta.debe_cambiar_clave is True, "la clave la sabe quien la tecleó"
    assert Client().login(username="lucia.pardo@unl.edu.ec", password="4826")


def test_la_bitacora_dice_que_servicios_entraron_y_nunca_la_clave(escenario):
    _alta(escenario)
    escrito = " ".join(str(r.detalle) for r in LogAuditoria.objects.filter(modulo="usuarios"))
    assert "medicina" in escrito
    assert "4826" not in escrito


def test_sin_correo_no_hay_cuenta(escenario):
    respuesta = _alta(escenario, correo="")
    assert respuesta.status_code == 200
    assert not Usuario.objects.filter(first_name="Lucía").exists()


def test_un_correo_ya_usado_no_se_repite(escenario):
    _alta(escenario)
    respuesta = _alta(escenario, correo="LUCIA.PARDO@unl.edu.ec", nombres="Otra")
    assert "Ya hay una cuenta con el correo" in respuesta.content.decode()
    assert Usuario.objects.filter(email__iexact="lucia.pardo@unl.edu.ec").count() == 1


def test_un_pin_trivial_no_crea_nada(escenario):
    respuesta = _alta(escenario, clave="1234")
    assert respuesta.status_code == 200
    assert not Usuario.objects.filter(email="lucia.pardo@unl.edu.ec").exists()


@pytest.mark.parametrize("rol", [Rol.DIRECTOR, Rol.COORDINADOR, Rol.PROFESIONAL])
def test_solo_administracion_general_genera_accesos(escenario, rol):
    otro = Usuario.objects.create_user(username=f"u_{rol}", password=CLAVE_ADMIN, rol_principal=rol)
    cliente = Client()
    cliente.login(username=otro.username, password=CLAVE_ADMIN)
    respuesta = cliente.post(
        reverse("usuarios:nueva_cuenta"),
        {"correo": "x@unl.edu.ec", "clave": "4826", "nombres": "X", "apellidos": "Y"},
    )
    assert respuesta.status_code == 403
    assert not Usuario.objects.filter(email="x@unl.edu.ec").exists()


# ----------------------------------------------------------------- después


def _editar(e, perfil, **cambios):
    cuenta = perfil.usuario
    datos = {
        "first_name": cuenta.first_name,
        "last_name": cuenta.last_name,
        "email": cuenta.email,
        "cedula": cuenta.cedula or "",
        "telefono": cuenta.telefono,
        "seccion": str(perfil.seccion_id or ""),
        "rol": cuenta.rol_principal,
        "servicios": [str(s.pk) for s in perfil.servicios.all()],
    }
    datos.update(cambios)
    return e["cliente"].post(reverse("usuarios:editar_perfil", args=[perfil.pk]), datos)


def test_se_corrigen_nombre_correo_y_funciones(escenario):
    _alta(escenario)
    perfil = PerfilProfesional.objects.get(usuario__email="lucia.pardo@unl.edu.ec")
    psico = escenario["est"]["psicologia"]

    respuesta = _editar(
        escenario,
        perfil,
        first_name="Lucía María",
        email="lmpardo@unl.edu.ec",
        servicios=[str(psico.pk)],
        seccion=str(escenario["est"]["psico"].pk),
    )

    assert respuesta.status_code == 302
    perfil.refresh_from_db()
    cuenta = perfil.usuario
    assert cuenta.first_name == "Lucía María" and cuenta.email == "lmpardo@unl.edu.ec"
    assert list(perfil.servicios.all()) == [psico]
    assert Client().login(username="lmpardo@unl.edu.ec", password="4826"), "entra con el nuevo"
    assert LogAuditoria.objects.filter(detalle__campos__contains=["email"]).exists()


def test_una_clave_nueva_vuelve_a_ser_temporal(escenario):
    _alta(escenario)
    perfil = PerfilProfesional.objects.get(usuario__email="lucia.pardo@unl.edu.ec")
    cuenta = perfil.usuario
    cuenta.debe_cambiar_clave = False
    cuenta.save()

    _editar(escenario, perfil, nueva_clave="7391")

    cuenta.refresh_from_db()
    assert cuenta.check_password("7391") and cuenta.debe_cambiar_clave is True
    assert "7391" not in str(list(LogAuditoria.objects.values_list("detalle", flat=True)))


def test_un_error_no_deja_guardada_la_mitad(escenario):
    """El correo nuevo no puede quedar guardado bajo un aviso de error porque
    falló la otra mitad del formulario (quitarse a sí mismo la administración)."""
    admin = escenario["admin"]
    perfil = PerfilProfesional.objects.create(usuario=admin)
    admin.email = "ada@unl.edu.ec"
    admin.save()

    respuesta = _editar(escenario, perfil, email="otro@unl.edu.ec", rol=Rol.PROFESIONAL)

    assert respuesta.status_code == 200
    admin.refresh_from_db()
    assert admin.email == "ada@unl.edu.ec"


def test_desbloquear_es_de_administracion_y_por_post(escenario):
    _alta(escenario)
    cuenta = Usuario.objects.get(email="lucia.pardo@unl.edu.ec")
    from django.utils import timezone

    Usuario.objects.filter(pk=cuenta.pk).update(
        bloqueada_desde=timezone.now(), intentos_fallidos=10
    )
    url = reverse("usuarios:desbloquear", args=[cuenta.pk])

    assert escenario["cliente"].get(url).status_code == 405
    lista = escenario["cliente"].get(reverse("usuarios:gestion_perfiles")).content.decode()
    assert "bloqueada" in lista and url in lista
    assert escenario["cliente"].post(url).status_code == 302
    cuenta.refresh_from_db()
    assert cuenta.bloqueada_desde is None


def test_mi_perfil_sigue_sin_dar_funciones_a_uno_mismo(escenario):
    """La cuenta editada por su dueño no puede tocar sección, rol ni servicios."""
    _alta(escenario)
    cuenta = Usuario.objects.get(email="lucia.pardo@unl.edu.ec")
    cuenta.debe_cambiar_clave = False
    cuenta.save()
    cliente = Client()
    cliente.login(username=cuenta.username, password="4826")
    cliente.post(
        reverse("usuarios:mi_perfil"),
        {
            "accion": "actualizar",
            "first_name": "Lucía",
            "last_name": "Pardo",
            "rol_principal": Rol.ADMIN_GENERAL,
            "servicios": [str(escenario["est"]["psicologia"].pk)],
        },
    )
    cuenta.refresh_from_db()
    assert cuenta.rol_principal == Rol.PROFESIONAL
    assert not cuenta.perfil.servicios.filter(codigo="psicologia").exists()


def test_desde_mi_perfil_no_se_toma_el_correo_de_otro(escenario):
    _alta(escenario)
    admin = escenario["admin"]
    escenario["cliente"].post(
        reverse("usuarios:mi_perfil"),
        {
            "accion": "actualizar",
            "first_name": "Ada",
            "last_name": "Admin",
            "email": "LUCIA.PARDO@unl.edu.ec",
        },
    )
    admin.refresh_from_db()
    assert admin.email.lower() != "lucia.pardo@unl.edu.ec"
    assert Client().login(username="lucia.pardo@unl.edu.ec", password="4826")
