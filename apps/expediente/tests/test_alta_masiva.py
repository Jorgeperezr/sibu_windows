"""
Alta de expedientes por lote de cédulas.

La búsqueda resolvía una cédula por vez, y preparar una jornada —una brigada de
salud, un taller, la lista de un curso— obligaba a repetir la misma pantalla
decenas de veces.

Lo que estas pruebas fijan, además de que registre: que una cédula mal digitada
en medio de doscientas no tumbe el lote, que nueve dígitos se completen con el
cero que Excel se come, y que una cédula desconocida NO se registre con el
nombre en blanco.
"""

import pytest
from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse

from apps.academico.models import DatoAcademico
from apps.core.models import PeriodoAcademico
from apps.expediente.models import Expediente, Persona
from apps.expediente.services import (
    registrar_lote_de_cedulas,
    separar_cedulas,
)
from apps.expediente.tests.factories import crear_estructura, crear_profesional
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"

# Pasan el módulo 10 ecuatoriano. `1104567890` NO lo pasa, y se usa a propósito.
EN_EL_PADRON = "1104567894"
TAMBIEN_EN_EL_PADRON = "1101002002"
VALIDA_PERO_DESCONOCIDA = "1103004006"
INVALIDA = "1104567890"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    usuario, _ = crear_profesional("medico_lote", est["medicina"], est["salud"])
    usuario.set_password(CLAVE)
    usuario.save()

    periodo = PeriodoAcademico.objects.create(
        codigo="2026-1",
        nombre="Abril–Agosto 2026",
        fecha_inicio="2026-04-01",
        fecha_fin="2026-08-31",
        vigente=True,
    )
    # Dos personas en el padrón institucional, sin expediente todavía: es el
    # estado en que las deja una carga de la ficha de matrícula.
    for cedula, nombres, apellidos in [
        (EN_EL_PADRON, "María José", "Pérez Ríos"),
        (TAMBIEN_EN_EL_PADRON, "Luis Alberto", "Torres Ochoa"),
    ]:
        persona = Persona.objects.create(
            cedula=cedula,
            nombres=nombres,
            apellidos=apellidos,
            tipo_vinculo=Persona.TipoVinculo.ESTUDIANTE,
        )
        DatoAcademico.objects.create(persona=persona, periodo=periodo, carrera="Medicina")

    cliente = Client()
    assert cliente.login(username="medico_lote", password=CLAVE)
    return {"est": est, "usuario": usuario, "cliente": cliente}


def _por_cedula(resultado):
    return {f["cedula"]: f["estado"] for f in resultado["filas"]}


# --------------------------------------------------------------- separar


def test_separa_por_saltos_de_linea_comas_y_espacios():
    """
    Se aceptan los tres a la vez: quien pega una lista la trae de donde la
    trae —una columna de Excel, un correo, un oficio— y no tiene por qué
    reformatearla.
    """
    assert separar_cedulas("1104567894\n1101002002, 1103004006;1105006009") == [
        "1104567894",
        "1101002002",
        "1103004006",
        "1105006009",
    ]


def test_no_repite_ni_reordena():
    """
    El informe se lee contra la lista que la persona pegó: reordenarlo la
    obligaría a buscar cada línea. Y la misma cédula dos veces es un error de
    copiado, no una orden de registrar a alguien dos veces.
    """
    assert separar_cedulas("1101002002\n1104567894\n1101002002") == [
        "1101002002",
        "1104567894",
    ]


def test_un_texto_vacio_no_produce_cedulas():
    assert separar_cedulas("") == []
    assert separar_cedulas("   \n\n  ") == []


# ---------------------------------------------------------------- servicio


@pytest.mark.django_db
def test_abre_el_expediente_de_cada_cedula_del_padron(escenario):
    resultado = registrar_lote_de_cedulas(
        f"{EN_EL_PADRON}\n{TAMBIEN_EN_EL_PADRON}", usuario=escenario["usuario"]
    )
    assert _por_cedula(resultado) == {EN_EL_PADRON: "abierto", TAMBIEN_EN_EL_PADRON: "abierto"}
    assert Expediente.objects.filter(persona__cedula=EN_EL_PADRON).exists()
    assert Expediente.objects.filter(persona__cedula=TAMBIEN_EN_EL_PADRON).exists()


@pytest.mark.django_db
def test_nueve_digitos_se_completan_con_el_cero_que_excel_se_come(escenario):
    """
    Excel trata la cédula como número y se lleva por delante el cero inicial.
    Nueve dígitos son una cédula de diez a la que le falta ese cero.
    """
    # `0101045672` es de Azuay y pasa el módulo 10: una inventada a ojo no
    # entraría, porque `Persona.save()` la valida.
    Persona.objects.create(
        cedula="0101045672",
        nombres="Ana",
        apellidos="Cuenca",
        tipo_vinculo=Persona.TipoVinculo.ESTUDIANTE,
    )

    resultado = registrar_lote_de_cedulas("101045672", usuario=escenario["usuario"])
    fila = resultado["filas"][0]
    assert fila["original"] == "101045672"  # nueve dígitos, tal como se pegó
    assert fila["cedula"] == "0101045672"  # diez, con el cero repuesto
    assert fila["estado"] == "abierto"


@pytest.mark.django_db
def test_una_cedula_invalida_no_tumba_el_resto_del_lote(escenario):
    """
    Cada cédula se procesa por separado: una mal digitada en medio de
    doscientas no puede dejar el lote a medias sin decir dónde se cortó.
    """
    resultado = registrar_lote_de_cedulas(
        f"{EN_EL_PADRON}\n{INVALIDA}\n{TAMBIEN_EN_EL_PADRON}", usuario=escenario["usuario"]
    )
    assert _por_cedula(resultado) == {
        EN_EL_PADRON: "abierto",
        INVALIDA: "invalida",
        TAMBIEN_EN_EL_PADRON: "abierto",
    }
    assert resultado["resumen"]["abierto"] == 2
    assert resultado["resumen"]["invalida"] == 1


@pytest.mark.django_db
def test_una_cedula_desconocida_no_se_registra_con_el_nombre_en_blanco(escenario):
    """
    Un expediente sin nombre no identifica a nadie y ensucia el padrón para
    siempre. Se informa para completarlo a mano; no se inventa.
    """
    resultado = registrar_lote_de_cedulas(VALIDA_PERO_DESCONOCIDA, usuario=escenario["usuario"])
    assert resultado["filas"][0]["estado"] == "desconocida"
    assert not Persona.objects.filter(cedula=VALIDA_PERO_DESCONOCIDA).exists()
    assert not Expediente.objects.filter(persona__cedula=VALIDA_PERO_DESCONOCIDA).exists()


@pytest.mark.django_db
def test_distingue_lo_que_ya_existia_de_lo_que_abrio_ahora(escenario):
    """
    `resolver_por_cedula` crea el expediente si falta, así que preguntar
    después ya no distinguiría una cosa de la otra.
    """
    registrar_lote_de_cedulas(EN_EL_PADRON, usuario=escenario["usuario"])
    segundo = registrar_lote_de_cedulas(EN_EL_PADRON, usuario=escenario["usuario"])
    assert segundo["filas"][0]["estado"] == "existente"
    assert segundo["resumen"]["abierto"] == 0


@pytest.mark.django_db
def test_repetir_el_lote_no_duplica_expedientes(escenario):
    lote = f"{EN_EL_PADRON}\n{TAMBIEN_EN_EL_PADRON}"
    registrar_lote_de_cedulas(lote, usuario=escenario["usuario"])
    registrar_lote_de_cedulas(lote, usuario=escenario["usuario"])
    assert Expediente.objects.filter(persona__cedula=EN_EL_PADRON).count() == 1


@pytest.mark.django_db
def test_un_lote_vacio_se_rechaza(escenario):
    with pytest.raises(ValidationError, match="No se reconoció ninguna cédula"):
        registrar_lote_de_cedulas("   ", usuario=escenario["usuario"])


@pytest.mark.django_db
def test_un_lote_demasiado_grande_se_rechaza(escenario):
    """
    Cada cédula consulta el padrón y puede abrir un expediente: una petición
    web que haga eso diez mil veces se cae por tiempo y deja el trabajo a
    medias.
    """
    from apps.expediente.services import MAXIMO_POR_LOTE

    texto = "\n".join(str(1100000000 + n) for n in range(MAXIMO_POR_LOTE + 1))
    with pytest.raises(ValidationError, match="máximo por tanda"):
        registrar_lote_de_cedulas(texto, usuario=escenario["usuario"])


@pytest.mark.django_db
def test_el_lote_queda_auditado(escenario):
    from apps.auditoria.models import LogAuditoria

    registrar_lote_de_cedulas(f"{EN_EL_PADRON}\n{INVALIDA}", usuario=escenario["usuario"])
    log = LogAuditoria.objects.filter(
        modulo="expediente", entidad_id="lote", usuario=escenario["usuario"]
    ).first()
    assert log is not None
    assert log.detalle["total"] == 2
    assert log.detalle["abierto"] == 1
    assert log.detalle["invalida"] == 1


# ---------------------------------------------------------------- pantalla


@pytest.mark.django_db
def test_la_pantalla_registra_y_muestra_el_resultado(escenario):
    respuesta = escenario["cliente"].post(
        reverse("expediente:alta_masiva"),
        {"cedulas": f"{EN_EL_PADRON}, {INVALIDA}"},
    )
    contenido = respuesta.content.decode()
    assert "Pérez Ríos" in contenido
    assert "Expediente abierto" in contenido
    assert "Inválida" in contenido


@pytest.mark.django_db
def test_la_pantalla_exige_el_mismo_permiso_que_la_busqueda(escenario):
    """
    Esto consulta el padrón institucional y abre expedientes. La versión de una
    en una ya estuvo abierta a cualquier autenticado y hubo que cerrarla; una
    puerta de doscientas a la vez habría sido peor.
    """
    Usuario.objects.create_user(
        username="estudiante_curioso", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    cliente = Client()
    assert cliente.login(username="estudiante_curioso", password=CLAVE)
    assert cliente.get(reverse("expediente:alta_masiva")).status_code == 403
    assert (
        cliente.post(reverse("expediente:alta_masiva"), {"cedulas": EN_EL_PADRON}).status_code
        == 403
    )


@pytest.mark.django_db
def test_sin_sesion_no_se_entra(escenario):
    respuesta = Client().get(reverse("expediente:alta_masiva"))
    assert respuesta.status_code == 302
    assert reverse("login") in respuesta.url


@pytest.mark.django_db
def test_un_estudiante_no_abre_expedientes_por_lote(escenario):
    """El control anterior, comprobado por su efecto y no solo por el código."""
    Usuario.objects.create_user(
        username="otro_estudiante", password=CLAVE, rol_principal=Rol.USUARIO_FINAL
    )
    cliente = Client()
    assert cliente.login(username="otro_estudiante", password=CLAVE)
    cliente.post(reverse("expediente:alta_masiva"), {"cedulas": EN_EL_PADRON})
    assert not Expediente.objects.filter(persona__cedula=EN_EL_PADRON).exists()
