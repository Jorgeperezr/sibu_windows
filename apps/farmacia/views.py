"""
Interfaz web de Farmacia: mostrador de despacho e inventario.

TODAS las vistas comprueban la pertenencia al servicio. Con solo
`@login_required`, cualquier usuario autenticado veía la cola de recetas —con
el nombre y el diagnóstico de cada paciente— y por POST despachaba medicación
o anulaba una receta ajena.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.dateparse import parse_date

from apps.core.models import Servicio
from apps.usuarios.decorators import verificar_es_del_servicio

from . import services
from .models import Lote, Medicamento, Receta, RecetaDetalle


def _servicio():
    """El servicio de Farmacia, fuente única del criterio de acceso."""
    return get_object_or_404(Servicio, codigo="farmacia")


def _entero(valor):
    """Un formulario devuelve cadenas; el servicio valida el rango, no el tipo."""
    try:
        return int(valor)
    except (TypeError, ValueError):
        raise ValidationError("La cantidad debe ser un número entero.") from None


def _fecha(valor):
    fecha = parse_date(valor or "")
    if fecha is None:
        raise ValidationError("La fecha de caducidad no es válida.")
    return fecha


@login_required
def mostrador(request):
    """Cola de recetas por despachar."""
    verificar_es_del_servicio(request.user, _servicio())
    return render(
        request,
        "farmacia/mostrador.html",
        {
            "recetas": services.recetas_pendientes(),
            "alertas_stock": services.alertas_stock(),
        },
    )


@login_required
def despachar(request, pk):
    """Ficha de la receta: despacho ítem por ítem con FEFO."""
    verificar_es_del_servicio(request.user, _servicio())
    receta = get_object_or_404(
        Receta.objects.select_related("atencion__expediente__persona").prefetch_related(
            "detalles__medicamento", "detalles__dispensaciones__lote"
        ),
        pk=pk,
    )
    perfil = getattr(request.user, "perfil", None)

    if request.method == "POST":
        if perfil is None:
            messages.error(request, "Su usuario no tiene perfil profesional asignado.")
            return redirect("farmacia:despachar", pk=receta.pk)

        accion = request.POST.get("accion")
        try:
            if accion == "despachar_item":
                detalle = receta.detalles.get(pk=request.POST["detalle"])
                dispensaciones = services.despachar_item(
                    detalle, int(request.POST["cantidad"]), usuario=perfil
                )
                lotes = ", ".join(
                    f"{d.lote.numero_lote} ({d.cantidad_despachada})" for d in dispensaciones
                )
                messages.success(request, f"Despachado de lote(s): {lotes}")

            elif accion == "despachar_todo":
                resumen = services.despachar_receta_completa(receta, usuario=perfil)
                if resumen["despachado"]:
                    messages.success(request, f"Despachados {len(resumen['despachado'])} ítem(s).")
                for faltante in resumen["sin_stock"]:
                    messages.warning(
                        request,
                        f"Sin stock suficiente de {faltante['medicamento']}: "
                        f"faltan {faltante['faltante']} unidades.",
                    )

            elif accion == "anular":
                services.anular_receta(receta, request.POST.get("motivo", ""))
                messages.warning(request, "Receta anulada.")

        except (ValidationError, KeyError, ValueError, RecetaDetalle.DoesNotExist) as exc:
            msg = "; ".join(exc.messages) if hasattr(exc, "messages") else "Ítem no encontrado."
            messages.error(request, msg)
        return redirect("farmacia:despachar", pk=receta.pk)

    items = []
    for detalle in receta.detalles.select_related("medicamento"):
        items.append(
            {
                "detalle": detalle,
                "pendiente": services.pendiente_por_despachar(detalle),
                "stock": services.stock_disponible(detalle.medicamento),
                "lotes_fefo": services.lotes_fefo(detalle.medicamento)[:3],
            }
        )

    return render(
        request,
        "farmacia/despachar.html",
        {
            "receta": receta,
            "persona": receta.atencion.expediente.persona,
            "items": items,
            "Estado": Receta.Estado,
        },
    )


@login_required
def inventario(request):
    """
    Inventario por lote: ingreso de mercadería, ajuste por conteo físico y
    baja de caducados. Hasta ahora todo esto solo se podía hacer por el shell
    o por el panel de administración —que escribe el saldo sin dejar
    movimiento y rompe la trazabilidad—.
    """
    verificar_es_del_servicio(request.user, _servicio())
    perfil = getattr(request.user, "perfil", None)

    if request.method == "POST":
        if perfil is None:
            messages.error(request, "Su usuario no tiene perfil profesional asignado.")
            return redirect("farmacia:inventario")
        try:
            accion = request.POST.get("accion")
            if accion == "nuevo_medicamento":
                medicamento = services.registrar_medicamento(
                    codigo=request.POST.get("codigo", ""),
                    dci=request.POST.get("dci", ""),
                    concentracion=request.POST.get("concentracion", ""),
                    forma_farmaceutica=request.POST.get("forma_farmaceutica", ""),
                    nombre_comercial=request.POST.get("nombre_comercial", ""),
                    stock_minimo=_entero((request.POST.get("stock_minimo") or "").strip() or "0"),
                    requiere_receta=request.POST.get("requiere_receta") == "1",
                    usuario=perfil,
                )
                messages.success(
                    request,
                    f"{medicamento.dci} {medicamento.concentracion} ya está en el catálogo. "
                    "Ingrese su primer lote para que se pueda despachar.",
                )

            elif accion == "ingresar":
                lote = services.ingresar_lote(
                    get_object_or_404(Medicamento, pk=request.POST["medicamento"]),
                    request.POST.get("numero_lote", "").strip(),
                    _entero(request.POST.get("cantidad")),
                    _fecha(request.POST.get("fecha_caducidad")),
                    usuario=perfil,
                    proveedor=request.POST.get("proveedor", "").strip(),
                    referencia_doc=request.POST.get("referencia_doc", "").strip(),
                )
                messages.success(
                    request,
                    f"Ingresado al lote {lote.numero_lote}: saldo {lote.cantidad_actual}.",
                )

            elif accion == "ajustar":
                lote = services.ajustar_lote(
                    get_object_or_404(Lote, pk=request.POST["lote"]),
                    _entero(request.POST.get("diferencia")),
                    request.POST.get("motivo", ""),
                    usuario=perfil,
                )
                messages.success(
                    request,
                    f"Lote {lote.numero_lote} ajustado: saldo {lote.cantidad_actual}.",
                )

            elif accion == "baja_caducados":
                unidades = services.dar_de_baja_caducados(perfil)
                if unidades:
                    messages.warning(request, f"Dadas de baja {unidades} unidades caducadas.")
                else:
                    messages.info(request, "No hay lotes caducados con existencias.")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
        return redirect("farmacia:inventario")

    medicamentos = []
    for medicamento in Medicamento.objects.filter(activo=True).order_by("dci"):
        disponible = services.stock_disponible(medicamento)
        medicamentos.append(
            {
                "medicamento": medicamento,
                "disponible": disponible,
                "bajo_minimo": 0 < medicamento.stock_minimo >= disponible,
                "sin_stock": disponible == 0,
            }
        )
    return render(
        request,
        "farmacia/inventario.html",
        {
            "medicamentos": medicamentos,
            "catalogo": Medicamento.objects.filter(activo=True).order_by("dci"),
            "por_caducar": services.alertas_caducidad(90),
            "lotes": Lote.objects.select_related("medicamento")
            .filter(cantidad_actual__gt=0)
            .order_by("fecha_caducidad")[:50],
        },
    )
