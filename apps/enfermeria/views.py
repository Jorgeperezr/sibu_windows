"""Interfaz web de Enfermería: registro de triaje / signos vitales."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.core import numeros
from apps.core.mensajes import detalle_de_error
from apps.core.models import Servicio
from apps.expediente.models import Expediente
from apps.usuarios.decorators import verificar_es_del_servicio

from .models import SignosVitales
from .services import signos_del_dia, triajes_del_dia


def _dec(valor, campo=""):
    """
    El número que dice el texto, o None si no dice nada.

    Devolvía None también para lo ilegible, así que una temperatura escrita
    «36,5» —que es como se escribe un decimal aquí— se guardaba VACÍA y la
    pantalla respondía «signos vitales registrados». Un dato clínico no se
    pierde en silencio: ahora `core.numeros` lee la coma, y lo que no sea un
    número lanza y se le dice a quien lo escribió.
    """
    return numeros.a_decimal(valor, campo=campo)


def _int(valor, campo=""):
    leido = numeros.a_decimal(valor, campo=campo)
    return None if leido is None else int(leido)


def _servicio():
    """El servicio de Enfermería, fuente única del criterio de acceso."""
    return get_object_or_404(Servicio, codigo="enfermeria")


@login_required
def bandeja(request):
    """Cola de trabajo de Enfermería: los triajes tomados hoy."""
    verificar_es_del_servicio(request.user, _servicio())
    return render(request, "enfermeria/bandeja.html", {"triajes": triajes_del_dia()})


# Los campos del formulario de triaje. Si ninguno trae un valor, no se guarda.
CAMPOS_SIGNOS = (
    "temperatura",
    "fc",
    "fr",
    "pa_sistolica",
    "pa_diastolica",
    "sat_o2",
    "peso",
    "talla",
    "perimetro_abdominal",
    "glicemia_capilar",
)


@login_required
def triaje(request, expediente_id):
    """Registra signos vitales del expediente (triaje previo a Medicina)."""
    # Los signos vitales son contenido clínico: sin esto cualquier autenticado
    # los leía y los registraba sobre el expediente de cualquiera.
    verificar_es_del_servicio(request.user, _servicio())
    expediente = get_object_or_404(Expediente, pk=expediente_id)
    perfil = getattr(request.user, "perfil", None)

    if request.method == "POST":
        if perfil is None:
            messages.error(request, "Su usuario no tiene perfil profesional asignado.")
            return redirect("expediente:detalle", pk=expediente.id)
        # Un triaje sin un solo signo vital no es un triaje. Guardarlo hacía
        # desaparecer de la consulta médica el aviso «Sin triaje reciente»,
        # que es justo lo que Medicina tiene que ver en ese caso, y la pantalla
        # confirmaba «Signos vitales registrados. Disponibles para Medicina».
        if not any((request.POST.get(c) or "").strip() for c in CAMPOS_SIGNOS):
            messages.error(
                request, "No se registró nada: anote al menos un signo vital antes de guardar."
            )
            return redirect("enfermeria:triaje", expediente_id=expediente.id)
        try:
            signos = SignosVitales(
                expediente=expediente,
                temperatura=_dec(request.POST.get("temperatura"), "temperatura"),
                fc=_int(request.POST.get("fc"), "frecuencia cardiaca"),
                fr=_int(request.POST.get("fr"), "frecuencia respiratoria"),
                pa_sistolica=_int(request.POST.get("pa_sistolica"), "presión sistólica"),
                pa_diastolica=_int(request.POST.get("pa_diastolica"), "presión diastólica"),
                sat_o2=_int(request.POST.get("sat_o2"), "saturación de oxígeno"),
                peso=_dec(request.POST.get("peso"), "peso"),
                talla=_dec(request.POST.get("talla"), "talla"),
                perimetro_abdominal=_int(
                    request.POST.get("perimetro_abdominal"), "perímetro abdominal"
                ),
                glicemia_capilar=_int(request.POST.get("glicemia_capilar"), "glicemia capilar"),
                responsable=perfil,
            )
            # Las restricciones de plausibilidad se comprueban AQUÍ, antes de
            # escribir. Sin esto, un 368 llegaba a la base, la restricción lo
            # rechazaba con un IntegrityError y la enfermera veía un error de
            # servidor en vez de «quiso decir 36,8».
            signos.validate_constraints()
            signos.save()
        except ValidationError as exc:
            # Se avisa y no se guarda nada. Guardar el resto y callar el dato
            # ilegible dejaría un triaje incompleto que nadie sabría revisar.
            messages.error(request, detalle_de_error(exc, "Revise los signos vitales."))
            return redirect("enfermeria:triaje", expediente_id=expediente.id)
        messages.success(request, "Signos vitales registrados. Disponibles para Medicina.")
        return redirect("enfermeria:triaje", expediente_id=expediente.id)

    return render(
        request,
        "enfermeria/triaje.html",
        {
            "expediente": expediente,
            "persona": expediente.persona,
            "signos_hoy": signos_del_dia(expediente),
        },
    )
