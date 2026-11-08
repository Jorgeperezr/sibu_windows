"""Interfaz web de Odontología: odontograma interactivo."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.models import CIE10, Servicio
from apps.core.selectors import diagnosticos_por_servicio
from apps.expediente.models import Atencion, Expediente
from apps.expediente.selectors import alertas_activas
from apps.expediente.services import borrador_abierto, exigir_atencion_editable
from apps.medicina.models import Diagnostico
from apps.medicina.services import agregar_diagnostico
from apps.usuarios.decorators import verificar_acceso_atencion, verificar_es_del_servicio

from . import presentacion, services
from .models import (
    AtencionOdontologia,
    CatalogoProcedimiento,
    EstadoPieza,
    OdontogramaDetalle,
)

# Distribución de las piezas para dibujar la boca (arcada superior / inferior).
ARCADA_SUPERIOR = [
    "18",
    "17",
    "16",
    "15",
    "14",
    "13",
    "12",
    "11",
    "21",
    "22",
    "23",
    "24",
    "25",
    "26",
    "27",
    "28",
]
ARCADA_INFERIOR = [
    "48",
    "47",
    "46",
    "45",
    "44",
    "43",
    "42",
    "41",
    "31",
    "32",
    "33",
    "34",
    "35",
    "36",
    "37",
    "38",
]

# El color y la inicial de cada estado viven en `presentacion`, que es también
# de donde sale la leyenda: escritos por separado, la leyenda acabó enseñando
# seis de los diez estados. Y no se usan los colores semánticos de Bootstrap:
# `primary` está teñido con el verde de la UNL, así que el diente obturado
# salía del mismo verde que el sano.


@login_required
def bandeja(request):
    """
    Cola de trabajo de Odontología: las historias aún abiertas del servicio.

    El mismo criterio que usa el menú (`servicios_del_usuario`): quien ve el
    enlace entra, y quien no lo ve recibe 403. No basta `@login_required`, que
    dejaría listar los pacientes del servicio a cualquier autenticado.
    """
    servicio = get_object_or_404(Servicio, codigo="odontologia")
    verificar_es_del_servicio(request.user, servicio)

    historias = (
        AtencionOdontologia.objects.filter(
            atencion__servicio=servicio, atencion__estado=Atencion.Estado.BORRADOR
        )
        .select_related("atencion__expediente__persona", "atencion__profesional__usuario")
        .order_by("-atencion__fecha_hora")
    )
    return render(request, "odontologia/bandeja.html", {"historias": historias})


# Solo POST: abrir una atención CREA la historia clínica, y una vista que
# escribe no puede responder a un GET. Bastaría un `<img
# src="/odontologia/iniciar/37/">` en cualquier página que abriera un profesional
# para dejar una historia a su nombre sobre alguien a quien no ha visto. El
# expediente la abre con un formulario.
@require_POST
@login_required
def iniciar_consulta(request, expediente_id):
    """Crea la HC odontológica y redirige al odontograma."""
    expediente = get_object_or_404(Expediente, pk=expediente_id)
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        messages.error(request, "Su usuario no tiene perfil profesional asignado.")
        return redirect("expediente:detalle", pk=expediente.id)

    servicio = Servicio.objects.filter(codigo="odontologia").first()
    if servicio is None:
        messages.error(request, "El servicio 'odontologia' no está configurado.")
        return redirect("expediente:detalle", pk=expediente.id)

    # Si este profesional ya tiene un borrador abierto con esta persona, se
    # continúa ese. Antes se creaba una atención NUEVA en cada entrada: pulsar
    # la acción, volver atrás y volver a pulsar dejaba dos fichas en blanco en
    # el expediente de la misma persona, y una ficha clínica no se borra.
    abierto = borrador_abierto(expediente, servicio, perfil, "odontologia")
    if abierto is not None:
        return redirect("odontologia:consulta", pk=abierto.pk)

    try:
        hc = services.crear_atencion_odontologia(
            expediente=expediente,
            profesional=perfil,
            motivo=request.POST.get("motivo", ""),
            usuario=request.user,
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("expediente:detalle", pk=expediente.id)
    return redirect("odontologia:consulta", pk=hc.pk)


def _arcada(piezas, vigente):
    """Arma la fila de piezas con su estado y color para la plantilla."""
    fila = []
    for pieza in piezas:
        registro = vigente.get(pieza)
        estado = registro.estado_codigo if registro else ""
        clase, inicial = presentacion.estilo(estado)
        fila.append(
            {
                "pieza": pieza,
                "estado": estado,
                "estado_display": registro.get_estado_codigo_display()
                if registro
                else "Sin registrar",
                "clase": clase,
                "inicial": inicial,
                "observacion": registro.observacion if registro else "",
            }
        )
    return fila


@login_required
def consulta(request, pk):
    """Odontograma interactivo + procedimientos + plan."""
    hc = get_object_or_404(
        AtencionOdontologia.objects.select_related(
            "atencion__expediente__persona", "atencion__servicio"
        ),
        pk=pk,
    )
    # Sin esto, cualquier usuario autenticado abre la historia de cualquier
    # paciente cambiando el id en la URL.
    verificar_acceso_atencion(request.user, hc.atencion)
    perfil = getattr(request.user, "perfil", None)

    if request.method == "POST":
        try:
            exigir_atencion_editable(hc.atencion)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("odontologia:consulta", pk=hc.pk)

        accion = request.POST.get("accion")
        try:
            if accion == "pieza":
                services.registrar_estado_pieza(
                    hc.atencion,
                    request.POST["pieza_fdi"],
                    request.POST["estado"],
                    superficie=request.POST.get("superficie", ""),
                    tipo=request.POST.get("tipo", OdontogramaDetalle.TipoRegistro.INICIAL),
                    observacion=request.POST.get("observacion", ""),
                )
                messages.success(request, f"Pieza {request.POST['pieza_fdi']} actualizada.")

            elif accion == "procedimiento":
                if perfil is None:
                    raise ValidationError("Su usuario no tiene perfil profesional.")
                services.ejecutar_procedimiento(
                    hc.atencion,
                    request.POST["catalogo"],
                    ejecutado_por=perfil,
                    pieza_fdi=request.POST.get("pieza_fdi", ""),
                    observacion=request.POST.get("observacion", ""),
                )
                messages.success(request, "Procedimiento registrado.")

            elif accion == "diagnostico":
                agregar_diagnostico(
                    hc.atencion,
                    request.POST["cie10"],
                    tipo=request.POST.get("tipo", Diagnostico.TipoDx.PRESUNTIVO),
                    principal=request.POST.get("principal") == "on",
                )
                messages.success(request, "Diagnóstico agregado.")

            elif accion == "guardar":
                hc.plan_tratamiento = request.POST.get("plan_tratamiento", "")
                hc.indicaciones = request.POST.get("indicaciones", "")
                hc.save()
                messages.success(request, "Consulta guardada.")

            elif accion == "cerrar":
                services.cerrar_atencion(hc.atencion, usuario=request.user)
                messages.success(request, "Atención cerrada.")
                return redirect("expediente:detalle", pk=hc.atencion.expediente_id)

        except (
            ValidationError,
            KeyError,
            CatalogoProcedimiento.DoesNotExist,
            CIE10.DoesNotExist,
        ) as exc:
            msg = (
                "; ".join(exc.messages)
                if hasattr(exc, "messages")
                else "Procedimiento o código CIE-10 no encontrado."
            )
            messages.error(request, msg)
        return redirect("odontologia:consulta", pk=hc.pk)

    vigente = services.odontograma_vigente(hc.atencion.expediente)
    return render(
        request,
        "odontologia/consulta.html",
        {
            "hc": hc,
            "alertas": list(alertas_activas(hc.atencion.expediente)),
            "atencion": hc.atencion,
            "persona": hc.atencion.expediente.persona,
            "superior": _arcada(ARCADA_SUPERIOR, vigente),
            "inferior": _arcada(ARCADA_INFERIOR, vigente),
            "estados": EstadoPieza.choices,
            # La leyenda sale de la misma fuente que las piezas: escrita a mano
            # enseñaba seis de los diez estados.
            "leyenda": presentacion.leyenda(),
            "catalogo": CatalogoProcedimiento.objects.filter(activo=True),
            "procedimientos": hc.atencion.procedimientos_odonto.select_related("catalogo"),
            "indices": services.calcular_indices(hc.atencion.expediente),
            "diagnosticos": Diagnostico.objects.filter(atencion=hc.atencion).select_related(
                "cie10"
            ),
            "cie10_disponibles": diagnosticos_por_servicio("odontologia"),
            "tipos_dx": Diagnostico.TipoDx.choices,
        },
    )
