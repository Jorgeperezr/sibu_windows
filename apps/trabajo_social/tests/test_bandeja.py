"""
La bandeja de Trabajo Social.

Era el único de los nueve servicios sin una: su profesional iniciaba sesión y
no tenía por dónde entrar a lo suyo —se llegaba a una ficha solo desde el
expediente abierto en otro módulo, o tecleando la URL con el id a mano—.

Lo que estas pruebas fijan, además de que liste, es a quién NO deja entrar y
qué no enseña: una bandeja que revelara qué otro servicio atiende a la persona
delataría su paso por un servicio confidencial.
"""

from decimal import Decimal

import pytest
from django.test import Client
from django.urls import reverse

from apps.core.models import Servicio
from apps.expediente.models import Expediente, Persona
from apps.expediente.tests.factories import crear_estructura, crear_profesional
from apps.trabajo_social import selectors
from apps.trabajo_social.models import FichaSocioeconomica

CLAVE = "clave-larga-12345"


def _persona_con_ficha(cedula, nombres, apellidos, estrato="", puntaje=None):
    persona = Persona.objects.create(
        cedula=cedula,
        nombres=nombres,
        apellidos=apellidos,
        tipo_vinculo=Persona.TipoVinculo.ESTUDIANTE,
    )
    expediente = Expediente.objects.create(persona=persona, numero_expediente=f"EXP-{cedula}")
    FichaSocioeconomica.objects.create(
        expediente=expediente,
        version=1,
        vigente=True,
        estrato=estrato,
        puntaje=puntaje,
    )
    return expediente


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    ts, _ = Servicio.objects.get_or_create(
        codigo="trabajo-social", defaults={"nombre": "Trabajo Social", "seccion": est["salud"]}
    )
    usuario, perfil = crear_profesional("ts_bandeja", ts, ts.seccion)
    usuario.set_password(CLAVE)
    usuario.save()
    cliente = Client()
    assert cliente.login(username="ts_bandeja", password=CLAVE)

    _persona_con_ficha(
        "1104567894", "María José", "Pérez Ríos", "Extrema vulnerabilidad", Decimal("0.30")
    )
    _persona_con_ficha(
        "1101002002", "Luis Alberto", "Torres Ochoa", "Vulnerabilidad media", Decimal("1.40")
    )
    return {"est": est, "ts": ts, "usuario": usuario, "perfil": perfil, "cliente": cliente}


# ------------------------------------------------------------------ selector


@pytest.mark.django_db
def test_solo_lista_las_fichas_vigentes(escenario):
    """
    Mezclar el historial haría aparecer a la misma persona varias veces con
    puntajes distintos, que es justo lo que no debe pasar en una bandeja.
    """
    expediente = Expediente.objects.get(persona__cedula="1104567894")
    vigente = FichaSocioeconomica.objects.get(expediente=expediente)
    vigente.vigente = False
    vigente.save(update_fields=["vigente"])
    FichaSocioeconomica.objects.create(
        expediente=expediente, version=2, vigente=True, estrato="Vulnerabilidad alta"
    )
    versiones = [f.version for f in selectors.casos() if f.expediente_id == expediente.pk]
    assert versiones == [2]


@pytest.mark.django_db
def test_busca_por_cedula_nombre_o_apellido(escenario):
    assert [f.expediente.persona.cedula for f in selectors.casos("Torres")] == ["1101002002"]
    assert [f.expediente.persona.cedula for f in selectors.casos("1104567894")] == ["1104567894"]
    assert [f.expediente.persona.cedula for f in selectors.casos("María")] == ["1104567894"]


@pytest.mark.django_db
def test_con_menos_de_tres_letras_no_busca(escenario):
    """
    Dos letras devuelven el padrón entero: eso no es una búsqueda, es un
    volcado. Mismo criterio que en el expediente.
    """
    assert selectors.casos("Ma").count() == 2


@pytest.mark.django_db
def test_filtra_por_estrato(escenario):
    resultados = selectors.casos(estrato="Extrema vulnerabilidad")
    assert [f.expediente.persona.cedula for f in resultados] == ["1104567894"]


@pytest.mark.django_db
def test_el_resumen_incluye_los_estratos_en_cero(escenario):
    """
    Un tramo ausente de la tabla se lee como «no lo hemos mirado»; uno con
    cero, como «no hay ninguno». No es lo mismo, y de aquí sale a quién se
    prioriza.

    Aquí se afirmaban los cuatro tramos exactos, y faltaba el que este mismo
    criterio exige: «sin verificar». Los cuatro los produce `calcular_puntaje`,
    y una ficha pre-poblada desde matrícula no ha pasado por ahí — con siete
    así, la pantalla enseñaba cuatro ceros sobre una tabla de siete filas.
    """
    resumen = {r["estrato"]: r["total"] for r in selectors.resumen_por_estrato()}
    assert set(resumen) == set(selectors.ESTRATOS_DEL_FILTRO)
    assert resumen["Extrema vulnerabilidad"] == 1
    assert resumen["Vulnerabilidad alta"] == 0


# ------------------------------------------------------------------ pantalla


@pytest.mark.django_db
def test_la_bandeja_lista_los_casos(escenario):
    contenido = escenario["cliente"].get(reverse("trabajo_social:bandeja")).content.decode()
    assert "Pérez Ríos" in contenido
    assert "Torres Ochoa" in contenido
    assert "Extrema vulnerabilidad" in contenido


@pytest.mark.django_db
def test_la_bandeja_filtra_desde_la_pantalla(escenario):
    contenido = (
        escenario["cliente"]
        .get(reverse("trabajo_social:bandeja"), {"q": "Torres"})
        .content.decode()
    )
    assert "Torres Ochoa" in contenido
    assert "Pérez Ríos" not in contenido


@pytest.mark.django_db
def test_la_bandeja_es_solo_de_quien_es_del_servicio(escenario):
    """
    La ficha socioeconómica lleva ingresos, deudas y salud familiar. Un
    profesional de otro servicio no tiene por qué ver la lista de casos de
    Trabajo Social.
    """
    ajeno, _ = crear_profesional(
        "medico_curioso", escenario["est"]["medicina"], escenario["est"]["salud"]
    )
    ajeno.set_password(CLAVE)
    ajeno.save()
    cliente = Client()
    assert cliente.login(username="medico_curioso", password=CLAVE)
    assert cliente.get(reverse("trabajo_social:bandeja")).status_code == 403


@pytest.mark.django_db
def test_la_bandeja_exige_sesion(escenario):
    respuesta = Client().get(reverse("trabajo_social:bandeja"))
    assert respuesta.status_code == 302
    assert reverse("login") in respuesta.url


@pytest.mark.django_db
def test_la_bandeja_no_dice_que_otro_servicio_atiende_a_nadie(escenario):
    """
    El sello de Psicología: saber que a alguien lo atiende Psicología ya es
    contenido. La bandeja lista fichas socioeconómicas, no atenciones.
    """
    from django.utils import timezone

    from apps.expediente.models import Atencion

    psico_usuario, psico_perfil = crear_profesional(
        "psi_sello", escenario["est"]["psicologia"], escenario["est"]["psico"]
    )
    Atencion.objects.create(
        expediente=Expediente.objects.get(persona__cedula="1104567894"),
        servicio=escenario["est"]["psicologia"],
        profesional=psico_perfil,
        fecha_hora=timezone.now(),
        motivo_consulta="proceso psicológico",
    )
    contenido = escenario["cliente"].get(reverse("trabajo_social:bandeja")).content.decode()
    assert "Pérez Ríos" in contenido  # tiene ficha socioeconómica, así que sale
    assert "Psicología" not in contenido
    assert "psicológico" not in contenido


@pytest.mark.django_db
def test_la_bandeja_aparece_en_el_menu_de_su_profesional(escenario):
    """
    Que la vista exista no basta: sin entrada de menú se llegaba tecleando la
    URL, que es exactamente el problema que esto viene a resolver.
    """
    from apps.core.navegacion import modulos_visibles

    etiquetas = [m.etiqueta for m in modulos_visibles(escenario["usuario"])]
    assert "Trabajo Social" in etiquetas


@pytest.mark.django_db
def test_el_menu_no_ofrece_trabajo_social_a_quien_no_es_del_servicio(escenario):
    from apps.core.navegacion import modulos_visibles

    ajeno, _ = crear_profesional(
        "medico_menu", escenario["est"]["medicina"], escenario["est"]["salud"]
    )
    assert "Trabajo Social" not in [m.etiqueta for m in modulos_visibles(ajeno)]


@pytest.mark.django_db
def test_el_hogar_sin_ingresos_declarados_se_ve_en_la_bandeja(escenario):
    """
    Puntaje 0,00 SBU es «extrema vulnerabilidad», no un dato que falte.

    `{% if f.puntaje %}` es falso con 0, así que la columna pintaba «—» y el
    caso más grave quedaba indistinguible de una ficha sin calcular. Se vio
    mirando la pantalla: el código de estado es 200 y el contexto llega entero.
    """
    _persona_con_ficha(
        "1103003008", "Sin", "Ingresos Declarados", "Extrema vulnerabilidad", Decimal("0.00")
    )
    contenido = escenario["cliente"].get(reverse("trabajo_social:bandeja")).content.decode()
    assert "0 SBU" in contenido
    assert "Extrema vulnerabilidad" in contenido


@pytest.mark.django_db
def test_una_ficha_sin_puntaje_sigue_diciendo_que_no_lo_tiene(escenario):
    """No se trata de borrar la ausencia, sino de distinguirla del cero."""
    _persona_con_ficha("1105005001", "Sin", "Calcular", "", None)
    contenido = escenario["cliente"].get(reverse("trabajo_social:bandeja")).content.decode()
    assert "—" in contenido
