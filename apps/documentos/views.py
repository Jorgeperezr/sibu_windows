"""
Pantallas de los documentos del expediente.

La lista enseña SOLO lo que este usuario puede ver: un documento de
Psicología no aparece ni como nombre para Medicina. El archivo sale por
`archivo`, nunca por una URL de `/media/`.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.models import Servicio
from apps.expediente.models import Expediente
from apps.usuarios import rbac

from . import services
from .models import DocumentoAnexo


def _expediente(request, expediente_id):
    if not rbac.puede_ver_expediente(request.user):
        raise PermissionDenied("No tiene permisos para ver expedientes.")
    return get_object_or_404(Expediente, pk=expediente_id)


def _servicio_elegido(request):
    servicio = Servicio.objects.filter(pk=request.POST.get("servicio") or 0).first()
    if servicio is None:
        raise ValidationError("Elija el servicio al que pertenece el documento.")
    return servicio


@login_required
def lista(request, expediente_id):
    expediente = _expediente(request, expediente_id)

    if request.method == "POST":
        accion = request.POST.get("accion")
        try:
            servicio = _servicio_elegido(request)
            comun = {
                "expediente": expediente,
                "servicio": servicio,
                "usuario": request.user,
                "tipo_documento": request.POST.get("tipo_documento", ""),
                "descripcion": request.POST.get("descripcion", ""),
            }
            if accion == "subir":
                archivo = request.FILES.get("archivo")
                if archivo is None:
                    raise ValidationError("Elija un archivo.")
                documento = services.subir_documento(
                    nombre=archivo.name, contenido=archivo.read(), **comun
                )
            elif accion == "escanear":
                fotos = request.FILES.getlist("fotos")
                if len(fotos) > services.MAXIMO_PAGINAS:
                    raise ValidationError(
                        f"Como mucho {services.MAXIMO_PAGINAS} páginas por documento."
                    )
                pdf = services.armar_pdf(
                    [f.read() for f in fotos], request.POST.get("modo", "documento")
                )
                nombre = (request.POST.get("descripcion") or "documento escaneado").strip()
                documento = services.subir_documento(nombre=f"{nombre}.pdf", contenido=pdf, **comun)
            else:
                raise ValidationError("Acción no reconocida.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        except PermissionDenied as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"«{documento.nombre_archivo}» quedó en el expediente.")
            return redirect("documentos:lista", expediente_id=expediente.pk)

    return render(
        request,
        "documentos/lista.html",
        {
            "expediente": expediente,
            "persona": expediente.persona,
            "documentos": services.documentos_visibles(request.user, expediente),
            "servicios": services.servicios_para_subir(request.user),
            "tipos": DocumentoAnexo.TipoDocumento.choices,
            "modos": services.MODOS_ESCANEO,
            "maximo_mb": services.TAMANO_MAXIMO // (1024 * 1024),
            "maximo_paginas": services.MAXIMO_PAGINAS,
        },
    )


def _documento(request, pk) -> DocumentoAnexo:
    documento = get_object_or_404(
        DocumentoAnexo.objects.select_related("servicio", "expediente"),
        pk=pk,
        expediente__isnull=False,
    )
    # 404 y no 403: decir «existe pero no es suyo» ya cuenta que esa persona
    # tiene un documento en un servicio sellado.
    if not services.puede_ver_documento(request.user, documento):
        raise Http404
    return documento


@login_required
def archivo(request, pk):
    """El archivo, en línea o como descarga, tras comprobar el acceso."""
    documento = _documento(request, pk)
    try:
        contenido = services.leer_documento(request.user, documento)
    except (FileNotFoundError, ValidationError) as exc:
        detalle = exc.messages[0] if hasattr(exc, "messages") else "El archivo ya no está en disco."
        messages.error(request, detalle)
        return redirect("documentos:lista", expediente_id=documento.expediente_id)

    respuesta = HttpResponse(contenido, content_type=documento.mime)
    modo = "attachment" if request.GET.get("descargar") else "inline"
    nombre = documento.nombre_archivo.replace('"', "")
    respuesta["Content-Disposition"] = f'{modo}; filename="{nombre}"'
    # Lo que venga dentro no se ejecuta con la sesión de quien lo abre. Solo
    # se admitieron PDF e imágenes, reconocidos por sus primeros bytes; con
    # `nosniff` el navegador no adivina otro tipo. A las imágenes se les niega
    # además todo lo demás. A los PDF no: con `sandbox`, Chrome se niega a
    # abrirlos en su visor.
    respuesta["X-Content-Type-Options"] = "nosniff"
    if documento.es_imagen:
        respuesta["Content-Security-Policy"] = "default-src 'none'; img-src 'self'"
    respuesta["Cache-Control"] = "private, no-store"
    return respuesta


@login_required
def marcar(request, pk):
    """
    Marcar una foto con flechas, círculos o texto. La marcada se guarda como
    documento NUEVO; la original queda intacta.
    """
    documento = _documento(request, pk)
    if not documento.es_imagen:
        raise Http404
    if request.method == "POST":
        imagen = request.FILES.get("imagen")
        try:
            if imagen is None:
                raise ValidationError("No llegó la imagen marcada.")
            nueva = services.subir_documento(
                expediente=documento.expediente,
                servicio=documento.servicio,
                usuario=request.user,
                nombre=f"{documento.nombre_archivo.rsplit('.', 1)[0]} (marcada).png",
                contenido=imagen.read(),
                tipo_documento=documento.tipo_documento,
                descripcion=(request.POST.get("descripcion") or documento.descripcion),
                original=documento,
            )
        except (ValidationError, PermissionDenied) as exc:
            texto = "; ".join(exc.messages) if hasattr(exc, "messages") else str(exc)
            messages.error(request, texto)
            return redirect("documentos:marcar", pk=documento.pk)
        messages.success(request, f"Guardada «{nueva.nombre_archivo}». La original sigue igual.")
        return redirect("documentos:lista", expediente_id=documento.expediente_id)

    return render(request, "documentos/marcar.html", {"documento": documento})


@login_required
@require_POST
def retirar(request, pk):
    documento = _documento(request, pk)
    try:
        services.retirar_documento(request.user, documento)
    except PermissionDenied as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"«{documento.nombre_archivo}» se retiró de la lista.")
    return redirect("documentos:lista", expediente_id=documento.expediente_id)
