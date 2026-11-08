"""Interfaz web de Medicina: escritorio de consulta."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.mensajes import detalle_de_error
from apps.core.models import CIE10, Servicio
from apps.core.selectors import diagnosticos_por_servicio
from apps.enfermeria.services import ultimo_triaje
from apps.expediente import alertas_receta
from apps.expediente.models import Atencion, Expediente
from apps.expediente.selectors import alertas_activas
from apps.expediente.services import borrador_abierto, exigir_atencion_editable
from apps.farmacia import services as farmacia_services
from apps.farmacia.models import Medicamento
from apps.laboratorio import services as laboratorio_services
from apps.laboratorio.models import Examen
from apps.usuarios.decorators import verificar_acceso_atencion, verificar_es_del_servicio

from . import services
from .models import AtencionMedicina


@login_required
def bandeja(request):
    """
    Cola de trabajo de Medicina: las historias aún en borrador del servicio.

    Mismo criterio que el menú (`servicios_del_usuario`): quien ve el enlace
    entra y quien no lo ve recibe 403.
    """
    servicio = get_object_or_404(Servicio, codigo="medicina")
    verificar_es_del_servicio(request.user, servicio)

    historias = (
        AtencionMedicina.objects.filter(
            atencion__servicio=servicio, atencion__estado=Atencion.Estado.BORRADOR
        )
        .select_related("atencion__expediente__persona", "atencion__profesional__usuario")
        .order_by("-atencion__fecha_hora")
    )
    return render(request, "medicina/bandeja.html", {"historias": historias})


# Solo POST: abrir una atención CREA la historia clínica, y una vista que
# escribe no puede responder a un GET. Bastaría un `<img
# src="/medicina/iniciar/37/">` en cualquier página que abriera un profesional
# para dejar una historia a su nombre sobre alguien a quien no ha visto. El
# expediente la abre con un formulario.
@require_POST
@login_required
def iniciar_consulta(request, expediente_id):
    """Crea la HC médica en borrador y redirige al escritorio de consulta."""
    expediente = get_object_or_404(Expediente, pk=expediente_id)
    perfil = getattr(request.user, "perfil", None)
    if perfil is None:
        messages.error(request, "Su usuario no tiene perfil profesional asignado.")
        return redirect("expediente:detalle", pk=expediente.id)

    servicio = Servicio.objects.filter(codigo="medicina").first()
    if servicio is None:
        messages.error(request, "El servicio 'medicina' no está configurado.")
        return redirect("expediente:detalle", pk=expediente.id)
    # Si este profesional ya tiene un borrador abierto con esta persona, se
    # continúa ese. Antes se creaba una atención NUEVA en cada entrada: pulsar
    # la acción, volver atrás y volver a pulsar dejaba dos historias clínicas
    # en blanco en el mismo expediente, y una historia clínica no se borra
    # —queda ahí y hay que explicar de dónde salió—.
    abierto = borrador_abierto(expediente, servicio, perfil, "medicina")
    if abierto is not None:
        return redirect("medicina:consulta", pk=abierto.pk)

    try:
        hc = services.crear_atencion_medicina(
            expediente=expediente,
            profesional=perfil,
            motivo=request.POST.get("motivo", ""),
            usuario=request.user,
        )
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("expediente:detalle", pk=expediente.id)
    return redirect("medicina:consulta", pk=hc.pk)


@login_required
def consulta(request, pk):
    """
    Escritorio de consulta: anamnesis, examen físico, diagnósticos y plan.
    Muestra automáticamente el triaje de Enfermería si existe.
    """
    hc = get_object_or_404(
        AtencionMedicina.objects.select_related(
            "atencion__expediente__persona", "atencion__servicio"
        ),
        pk=pk,
    )
    # Sin esto, cualquier usuario autenticado abría la historia clínica de
    # cualquier paciente cambiando el id en la URL.
    verificar_acceso_atencion(request.user, hc.atencion)

    if request.method == "POST":
        try:
            exigir_atencion_editable(hc.atencion)
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            return redirect("medicina:consulta", pk=hc.pk)

        accion = request.POST.get("accion")

        if accion == "guardar":
            # El motivo vive en la atención, no en la historia: es lo que dijo
            # la persona al llegar, y lo comparten todos los servicios.
            hc.atencion.motivo_consulta = request.POST.get("motivo_consulta", "")
            hc.atencion.save(update_fields=["motivo_consulta"])
            hc.enfermedad_actual = request.POST.get("enfermedad_actual", "")
            hc.plan_tratamiento = request.POST.get("plan_tratamiento", "")
            hc.indicaciones = request.POST.get("indicaciones", "")
            dias = request.POST.get("dias_reposo")
            hc.dias_reposo = int(dias) if dias else None
            hc.save()
            messages.success(request, "Consulta guardada.")

        elif accion == "diagnostico":
            try:
                services.agregar_diagnostico(
                    hc.atencion,
                    request.POST["cie10"],
                    tipo=request.POST.get("tipo", "presuntivo"),
                    principal=request.POST.get("principal") == "on",
                )
                messages.success(request, "Diagnóstico agregado.")
            except (ValidationError, KeyError, CIE10.DoesNotExist) as exc:
                msg = (
                    "; ".join(exc.messages)
                    if hasattr(exc, "messages")
                    else "Código CIE-10 no encontrado."
                )
                messages.error(request, msg)

        elif accion == "recetar":
            # Un medicamento por envío: la receta lleva varios y en consulta se
            # añaden de uno en uno. Si ya hay una receta abierta de esta
            # atención se le suma; si no, se emite una nueva.
            try:
                medicamento = Medicamento.objects.get(pk=request.POST["medicamento"])
                choques = alertas_receta.choques(
                    medicamento,
                    alertas_receta.alertas_del_expediente(alertas_activas(hc.atencion.expediente)),
                )
                # Avisa, no decide: si choca con una alerta, hace falta
                # confirmarlo. La pantalla lo pregunta; sin JavaScript, o si
                # alguien envía el formulario a mano, lo exige el servidor.
                if choques and request.POST.get("acepto_alerta") != "1":
                    messages.error(
                        request,
                        "No se añadió: "
                        + alertas_receta.aviso(choques)
                        + " Si aun así quiere recetarlo, vuelva a añadirlo y confírmelo.",
                    )
                    return redirect("medicina:consulta", pk=hc.pk)
                if choques:
                    messages.warning(
                        request, "Recetado pese a la alerta: " + alertas_receta.aviso(choques)
                    )
                item = {
                    "medicamento_id": request.POST["medicamento"],
                    "cantidad_prescrita": request.POST.get("cantidad", 0),
                    "dosis": request.POST.get("dosis", ""),
                    "via": request.POST.get("via", ""),
                    "frecuencia": request.POST.get("frecuencia", ""),
                    "duracion": request.POST.get("duracion", ""),
                }
                abierta = farmacia_services.receta_abierta(hc.atencion)
                if abierta:
                    farmacia_services.agregar_medicamento(abierta, item)
                    messages.success(request, f"Añadido a la receta {abierta.numero}.")
                else:
                    receta = farmacia_services.emitir_receta(
                        hc.atencion, [item], usuario=request.user
                    )
                    messages.success(request, f"Receta {receta.numero} emitida.")
            except (ValidationError, KeyError, ValueError, Medicamento.DoesNotExist) as exc:
                messages.error(request, detalle_de_error(exc, "Medicamento no encontrado."))

        elif accion == "examenes":
            try:
                orden = laboratorio_services.crear_orden(
                    hc.atencion,
                    request.POST.getlist("examenes"),
                    prioridad=request.POST.get("prioridad", "rutina"),
                    diagnostico_presuntivo=request.POST.get("diagnostico_presuntivo", ""),
                    usuario=request.user,
                )
                messages.success(request, f"Orden de laboratorio #{orden.pk} creada.")
            except (ValidationError, Examen.DoesNotExist) as exc:
                messages.error(request, detalle_de_error(exc, "Examen no encontrado."))

        elif accion == "cerrar":
            try:
                services.cerrar_atencion(hc.atencion, usuario=request.user)
                messages.success(request, "Atención cerrada correctamente.")
                return redirect("expediente:detalle", pk=hc.atencion.expediente_id)
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))

        return redirect("medicina:consulta", pk=hc.pk)

    alertas = list(alertas_activas(hc.atencion.expediente))
    alertas_de_receta = alertas_receta.alertas_del_expediente(alertas)
    return render(
        request,
        "medicina/consulta.html",
        {
            "hc": hc,
            "atencion": hc.atencion,
            "persona": hc.atencion.expediente.persona,
            "triaje": ultimo_triaje(hc.atencion.expediente),
            "diagnosticos": hc.atencion.diagnosticos.select_related("cie10"),
            "recetas": hc.atencion.recetas.prefetch_related("detalles__medicamento"),
            "ordenes": hc.atencion.ordenes_lab.prefetch_related("examenes__examen"),
            "cie10_disponibles": diagnosticos_por_servicio("medicina"),
            # Los catálogos para los formularios. Sin ellos habría que teclear
            # ids, que es lo que hacía falta antes de tener estas pantallas.
            "medicamentos": _con_choques(
                Medicamento.objects.filter(activo=True).order_by("dci"), alertas_de_receta
            ),
            "alertas": alertas,
            "examenes_catalogo": Examen.objects.filter(activo=True).order_by("nombre"),
            # Una atención firmada no admite receta ni orden; el servicio lo
            # valida igual, pero un formulario que siempre falla estorba.
            "editable": not hc.atencion.inmutable,
        },
    )


def _con_choques(medicamentos, alertas_de_receta):
    """Cada medicamento con su aviso ya escrito (`choque`), o vacío."""
    lista = list(medicamentos)
    for m in lista:
        m.choque = alertas_receta.aviso(alertas_receta.choques(m, alertas_de_receta))
    return lista


@login_required
def certificado(request, pk):
    """
    Certificado de atención, prellenado y editable, para imprimir desde el
    navegador. Traído de clinube.

    Se rellena con lo que ya hay —la fecha y la hora de la atención, quién
    atendió, los días de reposo— y todo se puede cambiar antes de imprimir.
    El diagnóstico NO va por omisión: un certificado suele acabar en manos de
    un empleador o de un docente, y el diagnóstico es de la persona. Quien
    atiende lo incluye si hace falta.

    No se guarda: se imprime (o se guarda como PDF desde el navegador, que es
    lo que hay en la portable de Windows, sin WeasyPrint). Queda en la
    bitácora que se emitió, con qué días de reposo y si llevaba diagnóstico.
    """
    from django.utils import timezone

    from apps.auditoria.models import LogAuditoria

    hc = get_object_or_404(
        AtencionMedicina.objects.select_related(
            "atencion__expediente__persona", "atencion__profesional__usuario"
        ),
        pk=pk,
    )
    verificar_acceso_atencion(request.user, hc.atencion)
    atencion = hc.atencion
    local = timezone.localtime(atencion.fecha_hora)
    principal = atencion.diagnosticos.select_related("cie10").filter(principal=True).first()
    profesional = atencion.profesional

    if request.method == "POST":
        datos = {
            c: request.POST.get(c, "").strip()
            for c in (
                "lugar",
                "fecha",
                "hora_inicio",
                "hora_fin",
                "dias_reposo",
                "diagnostico",
                "observaciones",
            )
        }
        incluir = request.POST.get("incluir_diagnostico") == "1"
        if not incluir:
            datos["diagnostico"] = ""
        LogAuditoria.objects.create(
            usuario=request.user,
            rol_activo=getattr(request.user, "rol_principal", ""),
            accion=LogAuditoria.Accion.PRINT,
            modulo="medicina",
            entidad="CertificadoAtencion",
            entidad_id=str(atencion.pk),
            expediente_id=atencion.expediente_id,
            servicio="medicina",
            detalle={"dias_reposo": datos["dias_reposo"], "con_diagnostico": incluir},
        )
        return render(
            request,
            "medicina/certificado_impreso.html",
            {"datos": datos, "persona": atencion.expediente.persona, "profesional": profesional},
        )

    return render(
        request,
        "medicina/certificado.html",
        {
            "hc": hc,
            "persona": atencion.expediente.persona,
            "profesional": profesional,
            "inicial": {
                "lugar": "Loja",
                "fecha": local.date().isoformat(),
                "hora_inicio": local.strftime("%H:%M"),
                "dias_reposo": hc.dias_reposo if hc.dias_reposo is not None else 0,
                "diagnostico": f"{principal.cie10.codigo} — {principal.cie10.descripcion}"
                if principal
                else "",
            },
        },
    )
