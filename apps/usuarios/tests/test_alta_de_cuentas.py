"""
Dar de alta a alguien del equipo desde el sistema.

Lo que impedía que SIBU estuviera operativo: **no había forma de crear una
cuenta**. La gestión de perfiles administraba cuentas que ya existían, y solo
existían si alguien abría una terminal y ejecutaba `createsuperuser` o
`portable/crear_cuenta.py`. Una unidad con diez profesionales no arranca así,
y en una portable —una carpeta en el computador de alguien— menos todavía.

Y había un segundo agujero en el mismo flujo: quien crea la cuenta teclea la
clave y se la dice a su dueño, así que durante un rato la saben dos personas.
Sin obligar a cambiarla, Administración General podría entrar como la
psicóloga. El sello de Psicología es absoluto **también frente a quien
administra**: no es una cuestión de confianza, es que el sello no admite
excepciones.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.auditoria.models import LogAuditoria
from apps.usuarios.models import PerfilProfesional, Rol, Usuario
from apps.usuarios.selectors import nombre_del_centinela
from apps.usuarios.services import crear_cuenta

CLAVE_ADMIN = "clave-larga-12345"
TEMPORAL = "Temporal-Sibu-2026"


@pytest.fixture
def admin(db):
    return Usuario.objects.create_user(
        username="1100000007",
        password=CLAVE_ADMIN,
        first_name="Ada",
        last_name="Admin",
        rol_principal=Rol.ADMIN_GENERAL,
    )


# ------------------------------------------------------------- el servicio


@pytest.mark.django_db
def test_se_crea_la_cuenta_y_entra_con_su_cedula(admin, client):
    usuario = crear_cuenta(
        cedula="1700000001",
        nombres="Lucía",
        apellidos="Pardo",
        clave_temporal=TEMPORAL,
        rol_principal=Rol.PROFESIONAL,
        usuario_que_crea=admin,
    )

    assert usuario.username == "1700000001", "la cédula es con lo que se ingresa"
    assert usuario.cedula == "1700000001"
    assert client.login(username="1700000001", password=TEMPORAL)


@pytest.mark.django_db
def test_la_cuenta_nace_con_ficha_profesional(admin):
    """Sin ficha no sale en ninguna bandeja, no admite cita y no tiene horario."""
    usuario = crear_cuenta(
        cedula="1700000001",
        nombres="Lucía",
        apellidos="Pardo",
        clave_temporal=TEMPORAL,
        rol_principal=Rol.PROFESIONAL,
        usuario_que_crea=admin,
    )

    assert PerfilProfesional.objects.filter(usuario=usuario).exists()


@pytest.mark.django_db
def test_la_cuenta_de_un_estudiante_no_lleva_ficha_profesional(admin):
    """
    Un USUARIO_FINAL es la cuenta de un paciente en el portal. Con ficha
    profesional aparecería en las bandejas del personal.
    """
    usuario = crear_cuenta(
        cedula="1700000001",
        nombres="Pedro",
        apellidos="Loja",
        clave_temporal=TEMPORAL,
        rol_principal=Rol.USUARIO_FINAL,
        usuario_que_crea=admin,
    )

    assert not PerfilProfesional.objects.filter(usuario=usuario).exists()


@pytest.mark.django_db
def test_una_cedula_que_no_pasa_el_modulo_diez_no_crea_cuenta(admin):
    """Una cédula inventada deja una cuenta que luego no casa con ninguna ficha."""
    with pytest.raises(ValidationError, match="no es válida"):
        crear_cuenta(
            cedula="1104567890",
            nombres="Nadie",
            apellidos="Inventado",
            clave_temporal=TEMPORAL,
            rol_principal=Rol.PROFESIONAL,
            usuario_que_crea=admin,
        )

    assert not Usuario.objects.filter(username="1104567890").exists()


@pytest.mark.django_db
def test_no_se_duplica_una_cedula_ya_dada_de_alta(admin):
    with pytest.raises(ValidationError, match="Ya hay una cuenta"):
        crear_cuenta(
            cedula=admin.username,
            nombres="Otra",
            apellidos="Persona",
            clave_temporal=TEMPORAL,
            rol_principal=Rol.PROFESIONAL,
            usuario_que_crea=admin,
        )


@pytest.mark.django_db
def test_la_clave_temporal_no_puede_ser_la_cedula(admin):
    """
    La tentación evidente de quien da de alta a diez personas seguidas. Es
    también la primera que prueba cualquiera que vea la lista de perfiles.
    """
    with pytest.raises(ValidationError):
        crear_cuenta(
            cedula="1700000001",
            nombres="Lucía",
            apellidos="Pardo",
            clave_temporal="1700000001",
            rol_principal=Rol.PROFESIONAL,
            usuario_que_crea=admin,
        )


@pytest.mark.django_db
def test_el_centinela_de_guardian_no_se_puede_crear(admin):
    """`AnonymousUser` no es una persona: no se crea ni se le da ficha."""
    with pytest.raises(ValidationError, match="anónimo"):
        crear_cuenta(
            cedula=nombre_del_centinela(),
            nombres="No",
            apellidos="Existe",
            clave_temporal=TEMPORAL,
            rol_principal=Rol.PROFESIONAL,
            usuario_que_crea=admin,
        )


@pytest.mark.django_db
def test_queda_en_la_bitacora_quien_creo_a_quien_y_nunca_la_clave(admin):
    usuario = crear_cuenta(
        cedula="1700000001",
        nombres="Lucía",
        apellidos="Pardo",
        clave_temporal=TEMPORAL,
        rol_principal=Rol.PROFESIONAL,
        usuario_que_crea=admin,
    )

    registro = LogAuditoria.objects.get(entidad="Usuario", entidad_id=str(usuario.pk))

    assert registro.usuario == admin
    assert registro.detalle["cuenta"] == "1700000001"
    assert registro.detalle["rol"] == Rol.PROFESIONAL
    escrito = str(registro.detalle)
    assert TEMPORAL not in escrito, "la clave no se escribe nunca"
    assert "clave" not in escrito and "password" not in escrito


@pytest.mark.django_db
def test_una_cedula_invalida_no_deja_nada_a_medias(admin):
    """
    El alta crea cuenta, ficha y dos registros de bitácora. Si revienta a la
    mitad, queda una cuenta sin ficha que nadie sabe de dónde salió.
    """
    cuentas = Usuario.objects.count()
    registros = LogAuditoria.objects.count()

    with pytest.raises(ValidationError):
        crear_cuenta(
            cedula="1104567890",
            nombres="Nadie",
            apellidos="Inventado",
            clave_temporal=TEMPORAL,
            rol_principal=Rol.PROFESIONAL,
            usuario_que_crea=admin,
        )

    assert Usuario.objects.count() == cuentas
    assert LogAuditoria.objects.count() == registros


# ---------------------------------------------------------------- la clave


@pytest.mark.django_db
def test_la_cuenta_nueva_nace_obligada_a_cambiar_la_clave(admin):
    usuario = crear_cuenta(
        cedula="1700000001",
        nombres="Lucía",
        apellidos="Pardo",
        clave_temporal=TEMPORAL,
        rol_principal=Rol.PROFESIONAL,
        usuario_que_crea=admin,
    )

    assert usuario.debe_cambiar_clave is True


@pytest.mark.django_db
def test_con_clave_temporal_toda_pantalla_lleva_a_cambiarla(admin, client):
    """
    Lo que cierra el agujero: mientras la clave la sepan dos personas, esa
    cuenta no hace nada. Si no, Administración General entraría como la
    psicóloga y el sello de Psicología tendría una puerta.
    """
    crear_cuenta(
        cedula="1700000001",
        nombres="Lucía",
        apellidos="Pardo",
        clave_temporal=TEMPORAL,
        rol_principal=Rol.PROFESIONAL,
        usuario_que_crea=admin,
    )
    client.login(username="1700000001", password=TEMPORAL)

    for destino in ("inicio", "usuarios:mi_perfil", "citas:mi_horario"):
        respuesta = client.get(reverse(destino))
        assert respuesta.status_code == 302, f"{destino} no desvió"
        assert respuesta.headers["Location"] == reverse("password_change")


@pytest.mark.django_db
def test_la_propia_pantalla_del_cambio_no_se_desvia_a_si_misma(admin, client):
    """Sin esta excepción el desvío es un bucle y la cuenta queda inservible."""
    crear_cuenta(
        cedula="1700000001",
        nombres="Lucía",
        apellidos="Pardo",
        clave_temporal=TEMPORAL,
        rol_principal=Rol.PROFESIONAL,
        usuario_que_crea=admin,
    )
    client.login(username="1700000001", password=TEMPORAL)

    respuesta = client.get(reverse("password_change"))

    assert respuesta.status_code == 200
    assert "Su clave es temporal" in respuesta.content.decode()


@pytest.mark.django_db
def test_con_clave_temporal_todavia_se_puede_salir(admin, client):
    """Encerrar a alguien sin poder cerrar sesión sería otra forma de romperlo."""
    crear_cuenta(
        cedula="1700000001",
        nombres="Lucía",
        apellidos="Pardo",
        clave_temporal=TEMPORAL,
        rol_principal=Rol.PROFESIONAL,
        usuario_que_crea=admin,
    )
    client.login(username="1700000001", password=TEMPORAL)

    assert client.post(reverse("logout")).status_code in (200, 302)


@pytest.mark.django_db
def test_al_poner_su_clave_se_levanta_la_obligacion_y_sigue_la_sesion(admin, client):
    usuario = crear_cuenta(
        cedula="1700000001",
        nombres="Lucía",
        apellidos="Pardo",
        clave_temporal=TEMPORAL,
        rol_principal=Rol.PROFESIONAL,
        usuario_que_crea=admin,
    )
    client.login(username="1700000001", password=TEMPORAL)

    respuesta = client.post(
        reverse("password_change"),
        {
            "old_password": TEMPORAL,
            "new_password1": "La-Mia-Propia-2026",
            "new_password2": "La-Mia-Propia-2026",
        },
    )

    usuario.refresh_from_db()
    assert usuario.debe_cambiar_clave is False
    assert respuesta.status_code == 302

    # Cambiar la clave cierra la sesión si no se renueva el hash de sesión: la
    # persona acabaría en el login sin saber si el cambio se guardó.
    #
    # Se comprueba contra una pantalla que EXIGE sesión. La primera versión de
    # esta prueba miraba `inicio`, que responde 200 también sin sesión: al
    # falsificarla —quitando `update_session_auth_hash`— no falló, y una
    # prueba que no falla al quitar lo que comprueba no comprueba nada.
    assert "_auth_user_id" in client.session, "la sesión se cerró al cambiar la clave"
    assert client.get(reverse("usuarios:mi_perfil")).status_code == 200


@pytest.mark.django_db
def test_una_cuenta_normal_no_sufre_el_desvio(admin, client):
    client.login(username=admin.username, password=CLAVE_ADMIN)

    assert client.get(reverse("inicio")).status_code == 200


# ---------------------------------------------------------------- la pantalla


@pytest.mark.django_db
def test_solo_administracion_general_da_de_alta(db, client):
    """Crear cuentas es conceder acceso, y eso no lo hace ni Dirección."""
    Usuario.objects.create_user(
        username="dir_alta", password=CLAVE_ADMIN, rol_principal=Rol.DIRECTOR
    )
    client.login(username="dir_alta", password=CLAVE_ADMIN)

    assert client.get(reverse("usuarios:nueva_cuenta")).status_code == 403
    assert (
        client.post(
            reverse("usuarios:nueva_cuenta"),
            {
                "cedula": "1700000001",
                "nombres": "Lucía",
                "apellidos": "Pardo",
                "rol": Rol.PROFESIONAL,
                "clave": TEMPORAL,
            },
        ).status_code
        == 403
    )
    assert not Usuario.objects.filter(username="1700000001").exists()


@pytest.mark.django_db
def test_un_error_devuelve_lo_tecleado_menos_la_clave(admin, client):
    """Volver a escribirlo todo por una cédula mal copiada no es aceptable."""
    client.login(username=admin.username, password=CLAVE_ADMIN)

    respuesta = client.post(
        reverse("usuarios:nueva_cuenta"),
        {
            "cedula": "1104567890",
            "nombres": "Lucía",
            "apellidos": "Pardo",
            "rol": Rol.PROFESIONAL,
            "clave": TEMPORAL,
        },
    )

    contenido = respuesta.content.decode()
    assert respuesta.status_code == 200
    assert "Lucía" in contenido and "Pardo" in contenido
    assert TEMPORAL not in contenido, "la clave no vuelve escrita en el HTML"


@pytest.mark.django_db
def test_la_gestion_de_perfiles_enlaza_el_alta(admin, client):
    """Sin enlace, la pantalla existe y nadie la encuentra."""
    client.login(username=admin.username, password=CLAVE_ADMIN)

    contenido = client.get(reverse("usuarios:gestion_perfiles")).content.decode()

    assert reverse("usuarios:nueva_cuenta") in contenido
