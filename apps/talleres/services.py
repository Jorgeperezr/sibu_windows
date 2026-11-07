"""
Talleres y actividades grupales.

Un taller NO es una atención clínica: es una actividad grupal. Esa distinción
gobierna todo el módulo, y sobre todo lo que el módulo NO hace.
"""

import logging

from django.core.exceptions import ValidationError
from django.db import transaction

from apps.academico.providers import CargaArchivoProvider
from apps.academico.validators import normalizar_cedula, validar_cedula_ecuatoriana
from apps.auditoria.models import LogAuditoria
from apps.documentos.models import DocumentoAnexo
from apps.expediente.models import Persona

from .models import Taller, TallerParticipante
from .providers import get_almacen

logger = logging.getLogger(__name__)


def _puede_registrar_talleres(servicio) -> bool:
    """
    Psicopedagogía y Trabajo Social siempre; Salud solo si el Administrador lo
    habilitó por parámetro.
    """
    from django.conf import settings

    if servicio.permite_talleres:
        return True
    if servicio.seccion.codigo == "salud":
        return bool(settings.SIBU.get("TALLERES_SALUD_HABILITADO", False))
    return False


@transaction.atomic
def crear_taller(*, servicio, responsable, tema: str, fecha, usuario=None, **extra) -> Taller:
    if not _puede_registrar_talleres(servicio):
        raise ValidationError(
            f"El servicio {servicio.nombre} no está habilitado para registrar talleres."
        )
    if not tema.strip():
        raise ValidationError("El taller necesita un tema.")

    codigo = extra.pop("codigo", "") or _siguiente_codigo(servicio, fecha)
    taller = Taller.objects.create(
        codigo=codigo,
        servicio=servicio,
        seccion=servicio.seccion,
        tema=tema,
        responsable=responsable,
        fecha=fecha,
        creado_por=usuario,
        **extra,
    )
    LogAuditoria.objects.create(
        usuario=usuario,
        accion=LogAuditoria.Accion.CREATE,
        modulo="talleres",
        entidad="Taller",
        entidad_id=str(taller.pk),
        detalle={"codigo": taller.codigo, "tema": tema},
    )
    return taller


def _siguiente_codigo(servicio, fecha) -> str:
    prefijo = f"TAL-{servicio.codigo[:4].upper()}-{fecha.year}"
    ultimo = (
        Taller.objects.filter(codigo__startswith=prefijo)
        .order_by("-codigo")
        .values_list("codigo", flat=True)
        .first()
    )
    n = int(ultimo.rsplit("-", 1)[-1]) + 1 if ultimo else 1
    return f"{prefijo}-{n:04d}"


@transaction.atomic
def registrar_participante(taller: Taller, *, cedula: str = "", expediente=None, asistio=True):
    """
    Añade un participante.

    **No crea expediente.** Asistir a un taller de prevención no convierte a
    nadie en paciente: abrir una historia clínica porque alguien entró a una
    charla sería registrar una condición que no existe. Si la persona ya tiene
    expediente, se vincula para poder medir cobertura; si no, se guarda la
    cédula y basta.
    """
    if taller.estado in (Taller.Estado.CERRADO,):
        raise ValidationError("Un taller cerrado no admite participantes.")

    if expediente is not None:
        if TallerParticipante.objects.filter(taller=taller, expediente=expediente).exists():
            raise ValidationError("Esa persona ya está registrada en este taller.")
        return TallerParticipante.objects.create(
            taller=taller,
            expediente=expediente,
            validado=True,
            asistio=asistio,
            origen=TallerParticipante.Origen.LISTA,
            snapshot_academico=_snapshot(expediente.persona.cedula),
        )

    cedula = normalizar_cedula(cedula)
    if not cedula:
        raise ValidationError("Indique una cédula o seleccione a la persona de la lista.")
    if not validar_cedula_ecuatoriana(cedula):
        raise ValidationError(f"La cédula {cedula} no es válida.")
    if TallerParticipante.objects.filter(taller=taller, cedula_digitada=cedula).exists():
        raise ValidationError("Esa cédula ya está registrada en este taller.")

    # Si la persona ya existe en el sistema, se vincula: no se duplica.
    persona = Persona.objects.filter(cedula=cedula).select_related().first()
    expediente_existente = None
    if persona is not None:
        expediente_existente = getattr(persona, "expediente", None)
        if (
            expediente_existente
            and TallerParticipante.objects.filter(
                taller=taller, expediente=expediente_existente
            ).exists()
        ):
            raise ValidationError("Esa persona ya está registrada en este taller.")

    return TallerParticipante.objects.create(
        taller=taller,
        expediente=expediente_existente,
        cedula_digitada=cedula,
        # "validado" significa que la cédula corresponde a alguien conocido por
        # la institución. Un participante externo no validado sigue contando:
        # asistió igual.
        validado=persona is not None,
        asistio=asistio,
        origen=TallerParticipante.Origen.CEDULA,
        snapshot_academico=_snapshot(cedula),
    )


def _snapshot(cedula: str) -> dict:
    """
    Congela el dato académico al momento del taller.

    Si la persona cambia de carrera el año que viene, el taller siguió siendo
    para quien era ese día. Sin esto, los reportes históricos se reescribirían
    solos.
    """
    datos = CargaArchivoProvider().consultar_persona(cedula) or {}
    return {
        k: datos.get(k, "")
        for k in ("facultad", "carrera", "ciclo", "modalidad", "periodo", "tipo_vinculo")
    }


def marcar_ejecutado(taller: Taller, usuario=None) -> Taller:
    """Un taller sin participantes no se ejecutó."""
    if taller.estado != Taller.Estado.PLANIFICADO:
        raise ValidationError("Solo un taller planificado puede marcarse como ejecutado.")
    if not taller.participantes.exists():
        raise ValidationError(
            "No se puede marcar como ejecutado un taller sin participantes registrados."
        )
    taller.estado = Taller.Estado.EJECUTADO
    taller.save(update_fields=["estado", "actualizado_en"])
    return taller


def adjuntar_evidencia(taller: Taller, *, nombre: str, contenido: bytes, mime: str, usuario=None):
    """Archiva una evidencia con el proveedor configurado."""
    if taller.estado == Taller.Estado.PLANIFICADO:
        raise ValidationError("Marque el taller como ejecutado antes de adjuntar evidencias.")
    if taller.estado == Taller.Estado.CERRADO:
        raise ValidationError("Un taller cerrado no admite nuevas evidencias.")
    if not contenido:
        raise ValidationError("El archivo está vacío.")

    almacen = get_almacen()
    if not almacen.disponible():
        raise ValidationError(almacen.motivo_no_disponible())

    subida = almacen.subir(taller, nombre=nombre, contenido=contenido, mime=mime)
    documento = DocumentoAnexo.objects.create(
        taller=taller,
        modulo="talleres",
        tipo_documento="evidencia",
        nombre_archivo=nombre,
        almacenamiento=(
            DocumentoAnexo.Almacenamiento.GDRIVE
            if almacen.codigo == "gdrive"
            else DocumentoAnexo.Almacenamiento.LOCAL
        ),
        ruta=subida.ruta,
        gdrive_file_id=subida.file_id,
        gdrive_url=subida.url,
        mime=mime,
        tamano=len(contenido),
        hash_sha256=subida.hash_sha256,
        creado_por=usuario,
    )
    if taller.estado == Taller.Estado.EJECUTADO:
        taller.estado = Taller.Estado.DOCUMENTADO
        taller.save(update_fields=["estado", "actualizado_en"])
    return documento


def cerrar_taller(taller: Taller, usuario=None) -> Taller:
    """Cerrar exige evidencia: un taller sin respaldo no es un taller documentado."""
    if taller.estado == Taller.Estado.CERRADO:
        raise ValidationError("El taller ya está cerrado.")
    if taller.estado == Taller.Estado.PLANIFICADO:
        raise ValidationError("Un taller planificado no puede cerrarse.")
    if not taller.evidencias.filter(eliminado_en__isnull=True).exists():
        raise ValidationError("No se puede cerrar un taller sin al menos una evidencia archivada.")
    taller.estado = Taller.Estado.CERRADO
    taller.save(update_fields=["estado", "actualizado_en"])
    LogAuditoria.objects.create(
        usuario=usuario,
        accion=LogAuditoria.Accion.UPDATE,
        modulo="talleres",
        entidad="Taller",
        entidad_id=str(taller.pk),
        detalle={"estado": "cerrado", "participantes": taller.total_participantes},
    )
    return taller


def cobertura(periodo_codigo: str = "") -> dict:
    """
    Cuántas personas distintas alcanzaron los talleres. Alimenta el S9.

    Cuenta personas, no asistencias: alguien que fue a tres talleres es una
    persona alcanzada, no tres. Confundirlos infla la cobertura.
    """
    from django.db.models import Count, Q

    qs = TallerParticipante.objects.filter(asistio=True)
    if periodo_codigo:
        qs = qs.filter(snapshot_academico__periodo=periodo_codigo)

    cedulas = set(qs.exclude(cedula_digitada="").values_list("cedula_digitada", flat=True))
    con_exp = set(
        qs.filter(expediente__isnull=False, cedula_digitada="").values_list(
            "expediente__persona__cedula", flat=True
        )
    )
    por_servicio = (
        Taller.objects.filter(estado=Taller.Estado.CERRADO)
        .values("servicio__nombre")
        .annotate(
            total=Count("id"),
            asistentes=Count("participantes", filter=Q(participantes__asistio=True)),
        )
        .order_by("-asistentes")
    )
    return {
        "personas_alcanzadas": len(cedulas | con_exp),
        "asistencias": qs.count(),
        "por_servicio": list(por_servicio),
    }
