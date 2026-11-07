"""
Talleres y actividades grupales.

La regla que gobierna el módulo: un taller NO es una atención clínica. Casi
todas las pruebas defienden alguna consecuencia de eso.
"""

from datetime import date

import pytest
from django.core.exceptions import ValidationError

from apps.core.models import Seccion, Servicio
from apps.expediente.tests.factories import (
    crear_estructura,
    crear_expediente,
    crear_profesional,
)
from apps.talleres import services
from apps.talleres.models import Taller

CEDULA_VALIDA = "1100000007"  # módulo 10 real: el validador del proyecto la acepta
CEDULA_VALIDA_2 = "1700000001"


@pytest.fixture
def escenario(db):
    est = crear_estructura()
    seccion, _ = Seccion.objects.get_or_create(
        codigo="psicopedagogica", defaults={"nombre": "Psicopedagógica"}
    )
    ppedag, _ = Servicio.objects.get_or_create(
        codigo="psicopedagogia",
        defaults={"nombre": "Psicopedagogía", "seccion": seccion},
    )
    ppedag.permite_talleres = True
    ppedag.save()
    u, prof = crear_profesional("orientadora", ppedag, seccion)
    return {"est": est, "servicio": ppedag, "u": u, "prof": prof}


def _taller(e, **extra):
    datos = {
        "servicio": e["servicio"],
        "responsable": e["prof"],
        "tema": "Manejo de la ansiedad ante exámenes",
        "fecha": date(2026, 5, 20),
        "usuario": e["u"],
    }
    datos.update(extra)
    return services.crear_taller(**datos)


# --------------------------------------------------------------------------
# Creación y habilitación
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_crear_taller_genera_codigo(escenario):
    t = _taller(escenario)
    assert t.codigo.startswith("TAL-PSIC-2026-")
    assert t.estado == Taller.Estado.PLANIFICADO
    assert t.seccion == escenario["servicio"].seccion


@pytest.mark.django_db
def test_los_codigos_no_se_repiten(escenario):
    a, b = _taller(escenario), _taller(escenario)
    assert a.codigo != b.codigo


@pytest.mark.django_db
def test_un_servicio_no_habilitado_no_registra_talleres(escenario):
    """Salud solo si el Administrador lo habilita por parámetro."""
    medicina = escenario["est"]["medicina"]
    medicina.permite_talleres = False
    medicina.save()
    with pytest.raises(ValidationError, match="no está habilitado"):
        _taller(escenario, servicio=medicina)


@pytest.mark.django_db
def test_salud_puede_si_el_parametro_lo_habilita(escenario, settings):
    medicina = escenario["est"]["medicina"]
    medicina.permite_talleres = False
    medicina.save()
    settings.SIBU = {**settings.SIBU, "TALLERES_SALUD_HABILITADO": True}
    t = _taller(escenario, servicio=medicina)
    assert t.pk


@pytest.mark.django_db
def test_taller_sin_tema_se_rechaza(escenario):
    with pytest.raises(ValidationError, match="tema"):
        _taller(escenario, tema="   ")


# --------------------------------------------------------------------------
# Participantes: un taller no es una atención clínica
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_registrar_participante_no_crea_expediente(escenario):
    """
    La regla central del módulo.

    Asistir a un taller de prevención no convierte a nadie en paciente. Abrir
    una historia clínica porque alguien entró a una charla sería registrar una
    condición que no existe.
    """
    from apps.expediente.models import Expediente

    t = _taller(escenario)
    antes = Expediente.objects.count()
    p = services.registrar_participante(t, cedula=CEDULA_VALIDA)
    assert Expediente.objects.count() == antes, "El taller creó un expediente clínico"
    assert p.expediente is None
    assert p.cedula_digitada == CEDULA_VALIDA


@pytest.mark.django_db
def test_si_la_persona_ya_existe_se_vincula_sin_duplicar(escenario):
    exp = crear_expediente(cedula=CEDULA_VALIDA)
    t = _taller(escenario)
    p = services.registrar_participante(t, cedula=CEDULA_VALIDA)
    assert p.expediente == exp
    assert p.validado is True


@pytest.mark.django_db
def test_cedula_invalida_se_rechaza(escenario):
    """Se valida con el módulo 10 ecuatoriano, igual que en el resto del sistema."""
    t = _taller(escenario)
    with pytest.raises(ValidationError, match="no es válida"):
        services.registrar_participante(t, cedula="1100000008")


@pytest.mark.django_db
def test_participante_externo_cuenta_aunque_no_este_validado(escenario):
    """
    `validado` significa "la institución lo conoce", no "asistió".

    Un asistente externo asistió igual: descontarlo falsearía la cobertura.
    """
    t = _taller(escenario)
    p = services.registrar_participante(t, cedula=CEDULA_VALIDA)
    assert p.validado is False
    assert p.asistio is True
    assert t.total_participantes == 1


@pytest.mark.django_db
def test_no_se_repite_la_cedula_en_el_mismo_taller(escenario):
    t = _taller(escenario)
    services.registrar_participante(t, cedula=CEDULA_VALIDA)
    with pytest.raises(ValidationError, match="ya está registrada"):
        services.registrar_participante(t, cedula=CEDULA_VALIDA)


@pytest.mark.django_db
def test_no_se_repite_la_persona_ni_cambiando_la_via_de_registro(escenario):
    """Registrar por lista y luego por cédula es la misma persona dos veces."""
    exp = crear_expediente(cedula=CEDULA_VALIDA)
    t = _taller(escenario)
    services.registrar_participante(t, expediente=exp)
    with pytest.raises(ValidationError, match="ya está registrada"):
        services.registrar_participante(t, cedula=CEDULA_VALIDA)


@pytest.mark.django_db
def test_el_snapshot_congela_el_dato_academico(escenario):
    """
    Si la persona cambia de carrera el año próximo, el taller siguió siendo
    para quien era ese día. Sin esto los reportes históricos se reescriben solos.
    """
    from apps.academico.models import DatoAcademico
    from apps.core.models import PeriodoAcademico

    exp = crear_expediente(cedula=CEDULA_VALIDA)
    periodo, _ = PeriodoAcademico.objects.get_or_create(
        codigo="2026-1",
        defaults={
            "nombre": "2026-1",
            "fecha_inicio": date(2026, 3, 1),
            "fecha_fin": date(2026, 7, 31),
            "vigente": True,
        },
    )
    DatoAcademico.objects.create(
        persona=exp.persona, periodo=periodo, carrera="Sistemas", facultad="FEIRNNR"
    )
    t = _taller(escenario)
    p = services.registrar_participante(t, cedula=CEDULA_VALIDA)
    assert p.snapshot_academico["carrera"] == "Sistemas"

    DatoAcademico.objects.filter(persona=exp.persona).update(carrera="Derecho")
    p.refresh_from_db()
    assert p.snapshot_academico["carrera"] == "Sistemas", "El snapshot se reescribió"


# --------------------------------------------------------------------------
# Máquina de estados
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_un_taller_sin_participantes_no_se_ejecuto(escenario):
    t = _taller(escenario)
    with pytest.raises(ValidationError, match="sin participantes"):
        services.marcar_ejecutado(t)


@pytest.mark.django_db
def test_marcar_ejecutado_con_participantes(escenario):
    t = _taller(escenario)
    services.registrar_participante(t, cedula=CEDULA_VALIDA)
    services.marcar_ejecutado(t, usuario=escenario["u"])
    t.refresh_from_db()
    assert t.estado == Taller.Estado.EJECUTADO


@pytest.mark.django_db
def test_no_se_adjunta_evidencia_a_un_taller_planificado(escenario):
    t = _taller(escenario)
    with pytest.raises(ValidationError, match="ejecutado"):
        services.adjuntar_evidencia(t, nombre="foto.jpg", contenido=b"x", mime="image/jpeg")


@pytest.mark.django_db
def test_adjuntar_evidencia_pasa_a_documentado(escenario, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    t = _taller(escenario)
    services.registrar_participante(t, cedula=CEDULA_VALIDA)
    services.marcar_ejecutado(t)
    doc = services.adjuntar_evidencia(
        t,
        nombre="registro.pdf",
        contenido=b"%PDF-1.4",
        mime="application/pdf",
        usuario=escenario["u"],
    )
    t.refresh_from_db()
    assert t.estado == Taller.Estado.DOCUMENTADO
    assert doc.hash_sha256
    assert doc.tamano == 8


@pytest.mark.django_db
def test_no_se_cierra_un_taller_sin_evidencia(escenario):
    """Un taller sin respaldo no es un taller documentado."""
    t = _taller(escenario)
    services.registrar_participante(t, cedula=CEDULA_VALIDA)
    services.marcar_ejecutado(t)
    with pytest.raises(ValidationError, match="sin al menos una evidencia"):
        services.cerrar_taller(t)


@pytest.mark.django_db
def test_cerrar_taller_con_evidencia(escenario, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    t = _taller(escenario)
    services.registrar_participante(t, cedula=CEDULA_VALIDA)
    services.marcar_ejecutado(t)
    services.adjuntar_evidencia(t, nombre="f.pdf", contenido=b"%PDF-1.4", mime="application/pdf")
    services.cerrar_taller(t, usuario=escenario["u"])
    t.refresh_from_db()
    assert t.estado == Taller.Estado.CERRADO


@pytest.mark.django_db
def test_un_taller_cerrado_no_admite_participantes(escenario, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    t = _taller(escenario)
    services.registrar_participante(t, cedula=CEDULA_VALIDA)
    services.marcar_ejecutado(t)
    services.adjuntar_evidencia(t, nombre="f.pdf", contenido=b"%PDF-1.4", mime="application/pdf")
    services.cerrar_taller(t)
    with pytest.raises(ValidationError, match="cerrado"):
        services.registrar_participante(t, cedula=CEDULA_VALIDA_2)


# --------------------------------------------------------------------------
# El almacén como pieza intercambiable
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_por_defecto_el_almacen_es_local(settings):
    """El módulo funciona sin Google: un taller no depende de Drive."""
    from apps.talleres.providers import get_almacen

    del settings.TALLERES_ALMACEN
    almacen = get_almacen()
    assert almacen.codigo == "local"
    assert almacen.disponible() is True


@pytest.mark.django_db
def test_gdrive_sin_configurar_lo_dice(settings):
    from apps.talleres.providers import get_almacen

    settings.TALLERES_ALMACEN = "gdrive"
    settings.GOOGLE_OAUTH = {"CLIENT_SECRETS_FILE": "", "SHARED_DRIVE_ID": ""}
    almacen = get_almacen()
    assert almacen.disponible() is False
    assert "GOOGLE_CLIENT_SECRETS" in almacen.motivo_no_disponible()


@pytest.mark.django_db
def test_almacen_desconocido_se_detecta(settings):
    from apps.talleres.providers import get_almacen

    settings.TALLERES_ALMACEN = "dropbox"
    with pytest.raises(ValidationError, match="no existe"):
        get_almacen()


@pytest.mark.django_db
def test_el_nombre_del_archivo_no_escapa_de_la_carpeta(escenario, settings, tmp_path):
    """El nombre lo propone quien sube: no puede escribir fuera del taller."""
    settings.MEDIA_ROOT = str(tmp_path)
    t = _taller(escenario)
    services.registrar_participante(t, cedula=CEDULA_VALIDA)
    services.marcar_ejecutado(t)
    doc = services.adjuntar_evidencia(
        t, nombre="../../../etc/passwd", contenido=b"x", mime="text/plain"
    )
    assert "/etc/passwd" not in doc.ruta
    assert str(tmp_path) in doc.ruta


# --------------------------------------------------------------------------
# Cobertura
# --------------------------------------------------------------------------


@pytest.mark.django_db
def test_cobertura_cuenta_personas_no_asistencias(escenario):
    """
    Alguien que fue a tres talleres es una persona alcanzada, no tres.
    Confundirlos infla la cobertura.
    """
    t1, t2 = _taller(escenario), _taller(escenario)
    services.registrar_participante(t1, cedula=CEDULA_VALIDA)
    services.registrar_participante(t2, cedula=CEDULA_VALIDA)
    services.registrar_participante(t2, cedula=CEDULA_VALIDA_2)
    datos = services.cobertura()
    assert datos["asistencias"] == 3
    assert datos["personas_alcanzadas"] == 2


@pytest.mark.django_db
def test_sin_media_root_no_se_archiva_en_tmp(escenario, settings):
    """
    Sin MEDIA_ROOT no hay fallback silencioso a /tmp.

    Archivar evidencias institucionales ahí las perdería al reiniciar y las
    dejaría legibles para cualquier usuario del servidor. Mejor decir que falta.
    """
    from apps.talleres.providers import get_almacen

    settings.MEDIA_ROOT = ""
    almacen = get_almacen()
    assert almacen.disponible() is False
    assert "MEDIA_ROOT" in almacen.motivo_no_disponible()

    t = _taller(escenario)
    services.registrar_participante(t, cedula=CEDULA_VALIDA)
    services.marcar_ejecutado(t)
    with pytest.raises(ValidationError, match="MEDIA_ROOT"):
        services.adjuntar_evidencia(t, nombre="f.pdf", contenido=b"%PDF", mime="application/pdf")
