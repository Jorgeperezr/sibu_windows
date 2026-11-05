"""
Interfaz web de Laboratorio: bandeja de órdenes y registro de resultados.

TODAS las vistas comprueban la pertenencia al servicio. Un resultado de
laboratorio es contenido clínico: con solo `@login_required`, cualquier
usuario autenticado leía los de cualquier paciente cambiando el id de la URL,
y por POST registraba, validaba o publicaba resultados ajenos.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render

from apps.core.mensajes import detalle_de_error
from apps.core.models import Servicio
from apps.usuarios.decorators import verificar_es_del_servicio

from . import services
from .models import Examen, OrdenExamen, OrdenLaboratorio, ParametroExamen


def _servicio():
    """El servicio de Laboratorio Clínico, fuente única del criterio de acceso."""
    return get_object_or_404(Servicio, codigo="laboratorio-clinico")


@login_required
def bandeja(request):
    """Cola de trabajo del laboratorio (urgentes primero)."""
    verificar_es_del_servicio(request.user, _servicio())
    return render(
        request,
        "laboratorio/bandeja.html",
        {"ordenes": services.ordenes_pendientes()},
    )


@login_required
def detalle_orden(request, pk):
    """
    Ficha de la orden: toma de muestra, registro de resultados, validación
    y publicación según el estado.
    """
    verificar_es_del_servicio(request.user, _servicio())
    orden = get_object_or_404(
        OrdenLaboratorio.objects.select_related("atencion__expediente__persona"), pk=pk
    )
    perfil = getattr(request.user, "perfil", None)

    if request.method == "POST":
        if perfil is None:
            messages.error(request, "Su usuario no tiene perfil profesional asignado.")
            return redirect("laboratorio:detalle", pk=orden.pk)

        accion = request.POST.get("accion")
        try:
            if accion == "tomar_muestra":
                services.tomar_muestra(
                    orden, perfil, tipo_muestra=request.POST.get("tipo_muestra", "")
                )
                messages.success(request, "Muestra registrada.")

            elif accion == "rechazar_muestra":
                services.rechazar_muestra(orden, request.POST.get("motivo", ""))
                messages.warning(request, "Muestra rechazada.")

            elif accion == "resultado":
                orden_examen = orden.examenes.get(pk=request.POST["orden_examen"])
                parametro = ParametroExamen.objects.get(pk=request.POST["parametro"])
                services.registrar_resultado(
                    orden_examen,
                    parametro,
                    request.POST["valor"],
                    registrado_por=perfil,
                    observacion=request.POST.get("observacion", ""),
                )
                messages.success(request, f"Resultado de {parametro.nombre} registrado.")

            elif accion == "completar":
                services.marcar_resultado_completo(orden)
                messages.success(request, "Resultados completos. Pendiente de validación.")

            elif accion == "validar":
                services.validar_orden(orden, perfil)
                messages.success(request, "Orden validada.")

            elif accion == "publicar":
                services.publicar_orden(orden)
                messages.success(
                    request, "Resultados publicados y enviados al correo del paciente."
                )
        except (
            ValidationError,
            KeyError,
            OrdenExamen.DoesNotExist,
            ParametroExamen.DoesNotExist,
        ) as exc:
            messages.error(request, detalle_de_error(exc, "Dato del formulario incompleto."))

        return redirect("laboratorio:detalle", pk=orden.pk)

    # Parámetros disponibles por examen para el formulario de registro
    examenes = []
    for oe in orden.examenes.select_related("examen").prefetch_related("resultados"):
        registrados = {r.parametro_id: r for r in oe.resultados.all()}
        examenes.append(
            {
                "orden_examen": oe,
                "parametros": [
                    {"parametro": p, "resultado": registrados.get(p.pk)}
                    for p in oe.examen.parametros.all()
                ],
            }
        )

    return render(
        request,
        "laboratorio/detalle.html",
        {
            "orden": orden,
            "persona": orden.atencion.expediente.persona,
            "examenes": examenes,
            "Estado": OrdenLaboratorio.Estado,
        },
    )


# Filas de parámetros que ofrece el formulario de alta. Las que se dejan sin
# nombre se ignoran. Ocho cubren una biometría o un perfil lipídico.
FILAS_DE_PARAMETROS = 8


@login_required
def catalogo(request):
    """
    El catálogo de exámenes que este laboratorio realiza.

    No existía: los exámenes solo los creaban los datos de demostración, así
    que en un despliegue real Medicina no podía pedir ninguno. Lo mantiene
    Laboratorio, que es quien sabe qué hace y con qué rangos.
    """
    verificar_es_del_servicio(request.user, _servicio())

    if request.method == "POST":
        parametros = [
            {
                "nombre": request.POST.get(f"param-{i}-nombre", ""),
                "unidad": request.POST.get(f"param-{i}-unidad", ""),
                "ref_min": request.POST.get(f"param-{i}-ref_min", ""),
                "ref_max": request.POST.get(f"param-{i}-ref_max", ""),
            }
            for i in range(FILAS_DE_PARAMETROS)
        ]
        try:
            examen = services.registrar_examen(
                codigo=request.POST.get("codigo", ""),
                nombre=request.POST.get("nombre", ""),
                perfil=request.POST.get("perfil", ""),
                indicaciones_preparacion=request.POST.get("indicaciones_preparacion", ""),
                parametros=parametros,
                usuario=request.user,
            )
        except ValidationError as exc:
            messages.error(request, detalle_de_error(exc, "Revise el examen."))
        else:
            messages.success(
                request, f"{examen.nombre} ya está en el catálogo: Medicina puede pedirlo."
            )
            return redirect("laboratorio:catalogo")

    return render(
        request,
        "laboratorio/catalogo.html",
        {
            "examenes": Examen.objects.prefetch_related("parametros").order_by("perfil", "nombre"),
            "filas": range(FILAS_DE_PARAMETROS),
            "datos": request.POST if request.method == "POST" else {},
        },
    )
