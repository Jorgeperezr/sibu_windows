"""
Lógica de negocio de Laboratorio (informe 6.4, 12.4).

Flujo completo:
    crear_orden (Medicina/Odontología)
      → tomar_muestra | rechazar_muestra
      → registrar_resultado (técnico)
      → validar_orden (responsable, doble paso)
      → publicar_orden (notifica al solicitante + envía al correo del paciente)
"""

from __future__ import annotations

from datetime import date

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Case, IntegerField, Value, When
from django.utils import timezone

from apps.core import numeros
from apps.expediente.models import Atencion

from .models import (
    Examen,
    OrdenExamen,
    OrdenLaboratorio,
    ParametroExamen,
    ResultadoParametro,
)

# Regla de negocio del informe (5.2): solo Medicina y Odontología solicitan.
SERVICIOS_AUTORIZADOS = {"medicina", "odontologia"}


@transaction.atomic
def crear_orden(
    atencion: Atencion,
    examenes_ids: list[int],
    *,
    prioridad: str = "rutina",
    diagnostico_presuntivo: str = "",
    usuario=None,
) -> OrdenLaboratorio:
    """Crea una orden de laboratorio desde una atención de Medicina/Odontología."""
    if atencion.servicio.codigo not in SERVICIOS_AUTORIZADOS:
        raise ValidationError(
            f"El servicio '{atencion.servicio.codigo}' no puede solicitar exámenes. "
            f"Autorizados: {sorted(SERVICIOS_AUTORIZADOS)}."
        )
    if atencion.inmutable:
        raise ValidationError("No se pueden solicitar exámenes sobre una atención firmada.")
    if not examenes_ids:
        raise ValidationError("Debe solicitar al menos un examen.")

    orden = OrdenLaboratorio.objects.create(
        atencion=atencion,
        prioridad=prioridad,
        diagnostico_presuntivo=diagnostico_presuntivo,
        creado_por=usuario,
    )
    for examen_id in examenes_ids:
        OrdenExamen.objects.create(orden=orden, examen=Examen.objects.get(pk=examen_id))
    return orden


def tomar_muestra(
    orden: OrdenLaboratorio, responsable, *, tipo_muestra: str = "", codigo_barras: str = ""
) -> OrdenLaboratorio:
    """Registra la toma de muestra (fase preanalítica)."""
    if orden.estado != OrdenLaboratorio.Estado.CREADA:
        raise ValidationError(
            f"Solo se toma muestra de órdenes creadas (actual: {orden.get_estado_display()})."
        )
    orden.estado = OrdenLaboratorio.Estado.MUESTRA_TOMADA
    orden.fecha_toma_muestra = timezone.now()
    orden.responsable_toma = responsable
    orden.tipo_muestra = tipo_muestra
    orden.codigo_barras = codigo_barras or f"M{orden.pk:08d}"
    orden.save()
    return orden


def rechazar_muestra(orden: OrdenLaboratorio, motivo: str) -> OrdenLaboratorio:
    """Rechaza la muestra con causa (hemólisis, cantidad insuficiente, etc.)."""
    if not motivo:
        raise ValidationError("Debe indicar el motivo del rechazo.")
    if orden.estado not in {
        OrdenLaboratorio.Estado.CREADA,
        OrdenLaboratorio.Estado.MUESTRA_TOMADA,
    }:
        raise ValidationError("La orden no está en una fase que admita rechazo de muestra.")
    orden.estado = OrdenLaboratorio.Estado.RECHAZADA
    orden.motivo_rechazo = motivo
    orden.save(update_fields=["estado", "motivo_rechazo", "actualizado_en"])
    return orden


def _edad_del_paciente(orden: OrdenLaboratorio) -> int | None:
    nacimiento = orden.atencion.expediente.persona.fecha_nacimiento
    if not nacimiento:
        return None
    hoy = date.today()
    return hoy.year - nacimiento.year - ((hoy.month, hoy.day) < (nacimiento.month, nacimiento.day))


def calcular_marcador(parametro: ParametroExamen, valor: str) -> str:
    """
    Determina el marcador del resultado comparando con los rangos del parámetro.

    Los valores no numéricos siempre se marcan como normales: su interpretación
    corresponde al profesional (se registra en `observacion`).
    """
    if parametro.tipo_valor != ParametroExamen.TipoValor.NUMERICO:
        return ResultadoParametro.Marcador.NORMAL
    # Laboratorio ya leía bien la coma; ahora lo hace con la misma función que
    # el resto del sistema, para que no vuelvan a separarse.
    num = numeros.a_decimal_o(valor, None)
    if num is None:
        return ResultadoParametro.Marcador.NORMAL

    if parametro.critico_min is not None and num < parametro.critico_min:
        return ResultadoParametro.Marcador.CRITICO
    if parametro.critico_max is not None and num > parametro.critico_max:
        return ResultadoParametro.Marcador.CRITICO
    if parametro.ref_min is not None and num < parametro.ref_min:
        return ResultadoParametro.Marcador.BAJO
    if parametro.ref_max is not None and num > parametro.ref_max:
        return ResultadoParametro.Marcador.ALTO
    return ResultadoParametro.Marcador.NORMAL


@transaction.atomic
def registrar_resultado(
    orden_examen: OrdenExamen,
    parametro: ParametroExamen,
    valor: str,
    *,
    registrado_por,
    observacion: str = "",
) -> ResultadoParametro:
    """
    Registra el valor de un parámetro (paso 1 de la validación en dos pasos).

    El marcador (normal/alto/bajo/crítico) se calcula automáticamente contra
    el rango de referencia aplicable al sexo y edad del paciente.
    """
    orden = orden_examen.orden
    if orden.estado in {
        OrdenLaboratorio.Estado.VALIDADO,
        OrdenLaboratorio.Estado.PUBLICADO,
        OrdenLaboratorio.Estado.ANULADA,
        OrdenLaboratorio.Estado.RECHAZADA,
    }:
        raise ValidationError(
            f"No se pueden registrar resultados en una orden {orden.get_estado_display()}."
        )
    if orden.estado == OrdenLaboratorio.Estado.CREADA:
        raise ValidationError("Debe registrarse la toma de muestra antes de los resultados.")
    if parametro.examen_id != orden_examen.examen_id:
        raise ValidationError(
            f"El parámetro '{parametro}' no pertenece al examen '{orden_examen.examen}'."
        )

    resultado, _ = ResultadoParametro.objects.update_or_create(
        orden_examen=orden_examen,
        parametro=parametro,
        defaults={
            "valor": valor,
            "unidad": parametro.unidad,
            "ref_min": str(parametro.ref_min) if parametro.ref_min is not None else "",
            "ref_max": str(parametro.ref_max) if parametro.ref_max is not None else "",
            "marcador": calcular_marcador(parametro, valor),
            "observacion": observacion,
            "registrado_por": registrado_por,
        },
    )
    if orden.estado == OrdenLaboratorio.Estado.MUESTRA_TOMADA:
        orden.estado = OrdenLaboratorio.Estado.EN_PROCESO
        orden.save(update_fields=["estado", "actualizado_en"])
    return resultado


def marcar_resultado_completo(orden: OrdenLaboratorio) -> OrdenLaboratorio:
    """El técnico declara que terminó de registrar todos los parámetros."""
    if orden.estado != OrdenLaboratorio.Estado.EN_PROCESO:
        raise ValidationError("La orden debe estar en proceso para marcarse como resultada.")
    if not ResultadoParametro.objects.filter(orden_examen__orden=orden).exists():
        raise ValidationError("No hay resultados registrados en la orden.")
    orden.estado = OrdenLaboratorio.Estado.RESULTADO
    orden.save(update_fields=["estado", "actualizado_en"])
    return orden


def validar_orden(orden: OrdenLaboratorio, validador) -> OrdenLaboratorio:
    """
    Paso 2 de la validación: el responsable valida los resultados registrados.

    Segregación de funciones (informe 14.2): quien registra no puede validar.
    """
    if orden.estado != OrdenLaboratorio.Estado.RESULTADO:
        raise ValidationError(
            f"Solo se validan órdenes con resultado registrado "
            f"(actual: {orden.get_estado_display()})."
        )
    registradores = set(
        ResultadoParametro.objects.filter(orden_examen__orden=orden).values_list(
            "registrado_por_id", flat=True
        )
    )
    if registradores == {validador.pk}:
        raise ValidationError(
            "Quien registra los resultados no puede validarlos (segregación de funciones)."
        )

    orden.estado = OrdenLaboratorio.Estado.VALIDADO
    orden.validado_por = validador
    orden.validado_en = timezone.now()
    orden.save(update_fields=["estado", "validado_por", "validado_en", "actualizado_en"])
    return orden


@transaction.atomic
def publicar_orden(orden: OrdenLaboratorio, *, enviar_correo: bool = True) -> OrdenLaboratorio:
    """
    Publica los resultados: los hace visibles al solicitante y al paciente,
    notifica al profesional y envía el informe al correo institucional.
    """
    if orden.estado != OrdenLaboratorio.Estado.VALIDADO:
        raise ValidationError("Solo se publican órdenes validadas.")

    orden.estado = OrdenLaboratorio.Estado.PUBLICADO
    orden.publicado_en = timezone.now()
    orden.save(update_fields=["estado", "publicado_en", "actualizado_en"])

    from .notificaciones import notificar_publicacion

    notificar_publicacion(orden, enviar_correo=enviar_correo)
    return orden


def ordenes_pendientes():
    """
    Cola de órdenes por procesar en Laboratorio, urgentes primero.

    El orden es explícito (Case/When) y no alfabético: ordenar por el texto
    del campo pondría "rutina" antes que "urgente".
    """
    orden_prioridad = Case(
        When(prioridad="urgente", then=Value(0)),
        default=Value(1),
        output_field=IntegerField(),
    )
    return (
        OrdenLaboratorio.objects.filter(
            estado__in=[
                OrdenLaboratorio.Estado.CREADA,
                OrdenLaboratorio.Estado.MUESTRA_TOMADA,
                OrdenLaboratorio.Estado.EN_PROCESO,
                OrdenLaboratorio.Estado.RESULTADO,
            ],
        )
        .select_related("atencion__expediente__persona", "atencion__servicio")
        .annotate(_prioridad_orden=orden_prioridad)
        .order_by("_prioridad_orden", "creado_en")
    )


@transaction.atomic
def registrar_examen(
    *,
    codigo: str,
    nombre: str,
    perfil: str = "",
    indicaciones_preparacion: str = "",
    parametros: list[dict] | None = None,
    usuario=None,
) -> Examen:
    """
    Da de alta un examen en el catálogo, con sus parámetros y rangos.

    El catálogo solo lo llenaban los datos de demostración: en un despliegue
    real nacía vacío, Medicina no podía pedir ningún examen y Laboratorio no
    tenía qué informar. Lo único que quedaba era el panel de administración de
    Django, al que el personal de Laboratorio no tiene acceso.

    Los rangos se leen con `core.numeros`: «13,5» es como se escribe aquí.
    Un parámetro sin nombre se ignora —es una fila del formulario que se dejó
    en blanco—, pero un examen sin ningún parámetro no se crea: no habría
    nada que informar.
    """
    from apps.auditoria.models import LogAuditoria

    codigo = (codigo or "").strip().upper()
    nombre = (nombre or "").strip()
    if not codigo or not nombre:
        raise ValidationError("El código y el nombre del examen son obligatorios.")
    if Examen.objects.filter(codigo__iexact=codigo).exists():
        raise ValidationError(f"Ya hay un examen con el código {codigo}.")

    filas = [p for p in (parametros or []) if (p.get("nombre") or "").strip()]
    if not filas:
        raise ValidationError(
            "Añada al menos un parámetro: es lo que Laboratorio informa de este examen."
        )

    leidos = []
    for orden, fila in enumerate(filas, start=1):
        etiqueta = fila["nombre"].strip()
        ref_min = numeros.a_decimal(fila.get("ref_min"), campo=f"mínimo de {etiqueta}")
        ref_max = numeros.a_decimal(fila.get("ref_max"), campo=f"máximo de {etiqueta}")
        if ref_min is not None and ref_max is not None and ref_min > ref_max:
            raise ValidationError(
                f"En {etiqueta}, el mínimo ({ref_min}) es mayor que el máximo ({ref_max})."
            )
        leidos.append(
            {
                "nombre": etiqueta,
                "unidad": (fila.get("unidad") or "").strip(),
                "ref_min": ref_min,
                "ref_max": ref_max,
                "orden": orden,
            }
        )

    examen = Examen.objects.create(
        codigo=codigo,
        nombre=nombre,
        perfil=(perfil or "").strip(),
        indicaciones_preparacion=(indicaciones_preparacion or "").strip(),
    )
    for datos in leidos:
        ParametroExamen.objects.create(examen=examen, **datos)

    cuenta = getattr(usuario, "usuario", usuario)
    LogAuditoria.objects.create(
        usuario=cuenta,
        rol_activo=getattr(cuenta, "rol_principal", ""),
        accion=LogAuditoria.Accion.CREATE,
        modulo="laboratorio",
        entidad="Examen",
        entidad_id=str(examen.pk),
        detalle={"codigo": examen.codigo, "parametros": [d["nombre"] for d in leidos]},
    )
    return examen
