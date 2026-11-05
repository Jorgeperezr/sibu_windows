"""
Lógica de negocio de Farmacia (informe 5.2 M09, 6.5).

Dos responsabilidades:
1. Emisión de recetas desde la consulta (Sprint 4).
2. Inventario y despacho FEFO (Sprint 6).

FEFO (First Expired, First Out): al despachar se consumen primero los lotes
con caducidad más próxima. Es el estándar sanitario para medicamentos, y evita
que el stock caduque en percha mientras se despacha de lotes nuevos.
"""

from __future__ import annotations

from datetime import date, timedelta

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.expediente.models import Atencion

from .models import (
    Dispensacion,
    Lote,
    Medicamento,
    MovimientoInventario,
    Receta,
    RecetaDetalle,
)

# ============================================================
# Emisión de recetas
# ============================================================


def _siguiente_numero() -> str:
    """Numeración correlativa anual: RX-2026-000001."""
    anio = timezone.localtime().year
    prefijo = f"RX-{anio}-"
    ultima = Receta.objects.filter(numero__startswith=prefijo).order_by("-numero").first()
    consecutivo = int(ultima.numero.split("-")[-1]) + 1 if ultima else 1
    return f"{prefijo}{consecutivo:06d}"


def _crear_receta_con_numero(atencion: Atencion, horas: int, usuario, intentos: int = 5) -> Receta:
    """
    Crea la receta reintentando si otro proceso tomó el mismo correlativo.

    `_siguiente_numero()` lee el último número y suma uno: dos emisiones
    simultáneas obtienen el mismo. La restricción única de `Receta.numero` lo
    impide a nivel de base —la integridad nunca estuvo en riesgo—, pero el
    segundo usuario recibía un error 500. Cada intento va en su propio
    savepoint para no abortar la transacción exterior.
    """
    for intento in range(intentos):
        try:
            with transaction.atomic():
                return Receta.objects.create(
                    atencion=atencion,
                    numero=_siguiente_numero(),
                    valida_hasta=timezone.now() + timedelta(hours=horas),
                    creado_por=usuario,
                )
        except IntegrityError:
            if intento == intentos - 1:
                raise ValidationError(
                    "No se pudo asignar número de receta por alta concurrencia. "
                    "Vuelva a intentarlo."
                ) from None
    raise AssertionError("inalcanzable")  # pragma: no cover


@transaction.atomic
def emitir_receta(atencion: Atencion, items: list[dict], usuario=None) -> Receta:
    """
    Emite una receta electrónica desde una atención.

    `items`: [{medicamento_id, cantidad_prescrita, dosis, via, frecuencia,
               duracion, indicaciones}]

    Atómica: un ítem inválido a mitad de la lista no puede dejar una receta con
    el correlativo gastado y solo los medicamentos anteriores.
    """
    if atencion.inmutable:
        raise ValidationError("No se puede emitir una receta sobre una atención firmada.")
    if not items:
        raise ValidationError("La receta debe tener al menos un medicamento.")

    horas = settings.SIBU.get("RECETA_VALIDEZ_HORAS", 72)
    receta = _crear_receta_con_numero(atencion, horas, usuario)

    for item in items:
        medicamento = Medicamento.objects.get(pk=item["medicamento_id"])
        cantidad = int(item.get("cantidad_prescrita", 0))
        if cantidad <= 0:
            raise ValidationError(f"La cantidad prescrita de {medicamento} debe ser mayor a cero.")
        RecetaDetalle.objects.create(
            receta=receta,
            medicamento=medicamento,
            cantidad_prescrita=cantidad,
            dosis=item.get("dosis", ""),
            via=item.get("via", ""),
            frecuencia=item.get("frecuencia", ""),
            duracion=item.get("duracion", ""),
            indicaciones=item.get("indicaciones", ""),
        )
    return receta


@transaction.atomic
def agregar_medicamento(receta: Receta, item: dict) -> RecetaDetalle:
    """
    Suma un medicamento a una receta aún sin despachar.

    Una receta lleva varios medicamentos y el profesional los añade de uno en
    uno; sin esto, cada medicamento exigía emitir una receta aparte, que no es
    lo que ocurre en consulta.

    Solo mientras nadie haya despachado nada: cambiar lo prescrito después de
    una entrega dejaría la receta sin corresponder con lo entregado.
    """
    if receta.atencion.inmutable:
        raise ValidationError("No se puede modificar una receta de una atención firmada.")
    if receta.estado != Receta.Estado.EMITIDA:
        raise ValidationError(
            f"La receta está {receta.get_estado_display().lower()}: ya no admite medicamentos."
        )
    # Segunda línea: el estado de arriba ya cubre el caso normal —cualquier
    # despacho mueve la receta fuera de EMITIDA—, pero si ese campo quedara
    # desfasado, esto sigue impidiendo tocar una receta con entregas.
    if Dispensacion.objects.filter(receta_detalle__receta=receta).exists():
        raise ValidationError("La receta ya tiene entregas: no se le pueden añadir medicamentos.")

    medicamento = Medicamento.objects.get(pk=item["medicamento_id"])
    cantidad = int(item.get("cantidad_prescrita", 0))
    if cantidad <= 0:
        raise ValidationError(f"La cantidad prescrita de {medicamento} debe ser mayor a cero.")
    if receta.detalles.filter(medicamento=medicamento).exists():
        raise ValidationError(f"{medicamento} ya consta en esta receta.")

    return RecetaDetalle.objects.create(
        receta=receta,
        medicamento=medicamento,
        cantidad_prescrita=cantidad,
        dosis=item.get("dosis", ""),
        via=item.get("via", ""),
        frecuencia=item.get("frecuencia", ""),
        duracion=item.get("duracion", ""),
        indicaciones=item.get("indicaciones", ""),
    )


def receta_abierta(atencion: Atencion) -> Receta | None:
    """La receta de esta atención que todavía admite medicamentos, si la hay."""
    return (
        Receta.objects.filter(atencion=atencion, estado=Receta.Estado.EMITIDA)
        .exclude(detalles__dispensaciones__isnull=False)
        .order_by("-creado_en")
        .first()
    )


def recetas_pendientes():
    """Cola de recetas vigentes por despachar."""
    return (
        Receta.objects.filter(
            estado__in=[Receta.Estado.EMITIDA, Receta.Estado.PARCIAL],
            valida_hasta__gte=timezone.now(),
        )
        .select_related("atencion__expediente__persona")
        .prefetch_related("detalles__medicamento")
        .order_by("creado_en")
    )


def caducar_recetas_vencidas() -> int:
    """Marca como caducadas las recetas vencidas no despachadas."""
    return Receta.objects.filter(
        estado__in=[Receta.Estado.EMITIDA, Receta.Estado.PARCIAL],
        valida_hasta__lt=timezone.now(),
    ).update(estado=Receta.Estado.CADUCADA)


# ============================================================
# Inventario
# ============================================================


@transaction.atomic
def ingresar_lote(
    medicamento: Medicamento,
    numero_lote: str,
    cantidad: int,
    fecha_caducidad: date,
    *,
    usuario,
    costo_unitario=0,
    proveedor: str = "",
    referencia_doc: str = "",
) -> Lote:
    """
    Ingresa stock al inventario. Si el lote ya existe para ese medicamento,
    suma la cantidad; si no, lo crea.

    Todo ingreso deja un MovimientoInventario: el saldo del lote siempre puede
    reconstruirse desde la bitácora (trazabilidad exigida en el informe 6.5).

    Bloquea el lote antes de sumar. La transacción por sí sola no bastaba: en
    READ COMMITTED dos ingresos simultáneos leen el mismo saldo y el segundo
    pisa al primero —entran 200 unidades y quedan 100, con dos movimientos que
    ya no cuadran con el saldo—. Lo que lo impide es `select_for_update`.
    """
    if cantidad <= 0:
        raise ValidationError("La cantidad a ingresar debe ser mayor a cero.")
    if fecha_caducidad <= timezone.localdate():
        raise ValidationError(
            f"No se puede ingresar un lote ya caducado (caducidad: {fecha_caducidad})."
        )

    lote, creado = Lote.objects.get_or_create(
        medicamento=medicamento,
        numero_lote=numero_lote,
        defaults={
            "fecha_caducidad": fecha_caducidad,
            "cantidad_actual": 0,
            "costo_unitario": costo_unitario,
            "proveedor": proveedor,
        },
    )
    if not creado and lote.fecha_caducidad != fecha_caducidad:
        raise ValidationError(
            f"El lote {numero_lote} ya existe con caducidad {lote.fecha_caducidad}. "
            f"Un mismo número de lote no puede tener dos fechas de caducidad."
        )

    lote = Lote.objects.select_for_update().get(pk=lote.pk)
    lote.cantidad_actual += cantidad
    lote.save(update_fields=["cantidad_actual"])

    MovimientoInventario.objects.create(
        lote=lote,
        tipo=MovimientoInventario.Tipo.INGRESO,
        cantidad=cantidad,
        saldo_resultante=lote.cantidad_actual,
        referencia_doc=referencia_doc,
        usuario=usuario,
    )
    return lote


def stock_disponible(medicamento: Medicamento) -> int:
    """Stock total no caducado de un medicamento."""
    total = Lote.objects.filter(
        medicamento=medicamento,
        fecha_caducidad__gt=timezone.localdate(),
        cantidad_actual__gt=0,
    ).aggregate(total=Sum("cantidad_actual"))["total"]
    return total or 0


def lotes_fefo(medicamento: Medicamento):
    """
    Lotes disponibles ordenados por FEFO: primero los que caducan antes.

    Excluye lotes ya caducados y sin existencias.
    """
    return Lote.objects.filter(
        medicamento=medicamento,
        fecha_caducidad__gt=timezone.localdate(),
        cantidad_actual__gt=0,
    ).order_by("fecha_caducidad", "id")


def stock_disponible_por_medicamento() -> dict[int, int]:
    """
    Stock no caducado de todos los medicamentos, en una sola consulta.

    Mismo criterio que `stock_disponible`, pero agregando por medicamento en la
    base en vez de preguntar uno por uno. Los medicamentos sin existencias no
    aparecen en el resultado: quien lo consulte debe tratar la ausencia como 0.
    """
    filas = (
        Lote.objects.filter(
            fecha_caducidad__gt=timezone.localdate(),
            cantidad_actual__gt=0,
        )
        .values("medicamento_id")
        .annotate(total=Sum("cantidad_actual"))
    )
    return {f["medicamento_id"]: f["total"] for f in filas}


def alertas_stock():
    """
    Medicamentos cuyo stock disponible está por debajo del mínimo.

    Se resuelve en dos consultas fijas. Antes llamaba a `stock_disponible()`
    dentro del bucle: una consulta por medicamento del catálogo, que en la
    farmacia real son cientos en cada carga del mostrador.
    """
    disponibles = stock_disponible_por_medicamento()
    alertas = []
    for medicamento in Medicamento.objects.filter(activo=True, stock_minimo__gt=0):
        disponible = disponibles.get(medicamento.pk, 0)
        if disponible <= medicamento.stock_minimo:
            alertas.append(
                {
                    "medicamento": medicamento,
                    "disponible": disponible,
                    "minimo": medicamento.stock_minimo,
                    "critico": disponible == 0,
                }
            )
    return alertas


def alertas_caducidad(dias: int = 90):
    """Lotes con existencias que caducan dentro de los próximos N días."""
    limite = timezone.localdate() + timedelta(days=dias)
    return (
        Lote.objects.filter(
            cantidad_actual__gt=0,
            fecha_caducidad__lte=limite,
            fecha_caducidad__gt=timezone.localdate(),
        )
        .select_related("medicamento")
        .order_by("fecha_caducidad")
    )


@transaction.atomic
def ajustar_lote(lote: Lote, diferencia: int, motivo: str, *, usuario) -> Lote:
    """
    Corrige el saldo de un lote tras un conteo físico y deja el movimiento.

    `MovimientoInventario` contemplaba AJUSTE_MAS y AJUSTE_MENOS desde el
    Sprint 6, pero nada los creaba: cuando la percha no cuadraba con el
    sistema, la única salida era el shell o el panel de administración, que
    escribe el saldo sin dejar movimiento y rompe la trazabilidad.

    El motivo es obligatorio: un ajuste sin causa escrita es indistinguible de
    un descuadre.
    """
    if diferencia == 0:
        raise ValidationError("El ajuste debe ser distinto de cero.")
    if not motivo.strip():
        raise ValidationError("Todo ajuste de inventario exige un motivo escrito.")

    lote = Lote.objects.select_for_update().get(pk=lote.pk)
    if lote.cantidad_actual + diferencia < 0:
        raise ValidationError(
            f"El ajuste dejaría el lote {lote.numero_lote} en "
            f"{lote.cantidad_actual + diferencia}: el saldo no puede ser negativo."
        )

    lote.cantidad_actual += diferencia
    lote.save(update_fields=["cantidad_actual"])
    MovimientoInventario.objects.create(
        lote=lote,
        tipo=(
            MovimientoInventario.Tipo.AJUSTE_MAS
            if diferencia > 0
            else MovimientoInventario.Tipo.AJUSTE_MENOS
        ),
        cantidad=diferencia,
        saldo_resultante=lote.cantidad_actual,
        referencia_doc=motivo.strip()[:60],
        usuario=usuario,
    )
    return lote


def dar_de_baja_caducados(usuario) -> int:
    """
    Da de baja los lotes caducados con existencias. Devuelve las unidades
    dadas de baja. Deja movimiento de tipo BAJA para la trazabilidad.
    """
    unidades = 0
    caducados = Lote.objects.filter(
        fecha_caducidad__lte=timezone.localdate(), cantidad_actual__gt=0
    )
    for lote in caducados:
        cantidad = lote.cantidad_actual
        lote.cantidad_actual = 0
        lote.save(update_fields=["cantidad_actual"])
        MovimientoInventario.objects.create(
            lote=lote,
            tipo=MovimientoInventario.Tipo.BAJA,
            cantidad=-cantidad,
            saldo_resultante=0,
            referencia_doc="Baja automática por caducidad",
            usuario=usuario,
        )
        unidades += cantidad
    return unidades


# ============================================================
# Despacho FEFO
# ============================================================


def _cantidad_ya_despachada(detalle: RecetaDetalle) -> int:
    total = detalle.dispensaciones.aggregate(total=Sum("cantidad_despachada"))["total"]
    return total or 0


def pendiente_por_despachar(detalle: RecetaDetalle) -> int:
    """Unidades que aún faltan por entregar de un ítem de la receta."""
    return max(detalle.cantidad_prescrita - _cantidad_ya_despachada(detalle), 0)


@transaction.atomic
def despachar_item(detalle: RecetaDetalle, cantidad: int, *, usuario) -> list[Dispensacion]:
    """
    Despacha un ítem de la receta consumiendo lotes por FEFO.

    Puede repartir la cantidad entre varios lotes si el primero no alcanza.
    Devuelve la lista de dispensaciones creadas (una por lote consumido).

    Reglas:
    - La receta debe estar vigente y en estado despachable.
    - No se puede despachar más de lo prescrito.
    - No se puede despachar sin stock suficiente.
    """
    receta = detalle.receta

    if receta.estado not in {Receta.Estado.EMITIDA, Receta.Estado.PARCIAL}:
        raise ValidationError(f"La receta está {receta.get_estado_display()} y no admite despacho.")
    if receta.valida_hasta < timezone.now():
        raise ValidationError(
            f"La receta {receta.numero} caducó el {receta.valida_hasta:%d/%m/%Y %H:%M}."
        )
    if cantidad <= 0:
        raise ValidationError("La cantidad a despachar debe ser mayor a cero.")

    # Bloquear el detalle antes de contar lo ya despachado: sin esto, dos
    # despachos simultáneos del mismo ítem leen el mismo pendiente y entre los
    # dos entregan más de lo prescrito.
    detalle = RecetaDetalle.objects.select_for_update().get(pk=detalle.pk)

    pendiente = pendiente_por_despachar(detalle)
    if cantidad > pendiente:
        raise ValidationError(
            f"Solo quedan {pendiente} unidades por despachar de {detalle.medicamento} "
            f"(prescritas {detalle.cantidad_prescrita})."
        )

    # Bloquear los lotes ANTES de decidir si hay stock. Comprobar con
    # `stock_disponible()` y consumir después dejaba una ventana entre la
    # lectura y el consumo: dos despachos concurrentes pasaban ambos la
    # comprobación y el segundo entregaba de menos en silencio.
    lotes = list(lotes_fefo(detalle.medicamento).select_for_update())
    disponible = sum(lote.cantidad_actual for lote in lotes)
    if cantidad > disponible:
        raise ValidationError(
            f"Stock insuficiente de {detalle.medicamento}: "
            f"disponible {disponible}, solicitado {cantidad}."
        )

    dispensaciones = []
    restante = cantidad
    for lote in lotes:
        if restante <= 0:
            break
        toma = min(lote.cantidad_actual, restante)

        lote.cantidad_actual -= toma
        lote.save(update_fields=["cantidad_actual"])

        MovimientoInventario.objects.create(
            lote=lote,
            tipo=MovimientoInventario.Tipo.EGRESO,
            cantidad=-toma,
            saldo_resultante=lote.cantidad_actual,
            referencia_doc=receta.numero,
            usuario=usuario,
        )
        dispensaciones.append(
            Dispensacion.objects.create(
                receta_detalle=detalle,
                lote=lote,
                cantidad_despachada=toma,
                despachado_por=usuario,
            )
        )
        restante -= toma

    if restante > 0:
        # Los lotes están bloqueados y el disponible se calculó sobre ellos, así
        # que esto no debería ocurrir. Si ocurre, algo descuadró: abortar la
        # transacción antes que entregar de menos sin decirlo.
        raise ValidationError(
            f"No se pudo completar el despacho de {detalle.medicamento}: "
            f"faltaron {restante} unidades. No se registró ninguna entrega."
        )

    _actualizar_estado_receta(receta)
    return dispensaciones


def _actualizar_estado_receta(receta: Receta) -> Receta:
    """
    Recalcula el estado de la receta a partir de lo despachado.

    Lo despachado se anota en la misma consulta que trae los detalles. Antes se
    preguntaba dos veces por línea —una para el pendiente y otra para saber si
    ya se había entregado algo—, y esto se ejecuta en cada despacho.
    """
    detalles = list(
        receta.detalles.annotate(despachado=Coalesce(Sum("dispensaciones__cantidad_despachada"), 0))
    )
    pendientes = sum(max(d.cantidad_prescrita - d.despachado, 0) for d in detalles)
    despachado_algo = any(d.despachado > 0 for d in detalles)

    if pendientes == 0:
        receta.estado = Receta.Estado.DESPACHADA
    elif despachado_algo:
        receta.estado = Receta.Estado.PARCIAL
    else:
        receta.estado = Receta.Estado.EMITIDA
    receta.save(update_fields=["estado", "actualizado_en"])
    return receta


@transaction.atomic
def despachar_receta_completa(receta: Receta, *, usuario) -> dict:
    """
    Intenta despachar todo lo pendiente de la receta.

    Devuelve un resumen con lo entregado y lo que quedó pendiente por falta de
    stock (no falla: entrega lo que hay y deja el resto pendiente, que es como
    opera la farmacia real).
    """
    resumen = {"despachado": [], "sin_stock": []}
    for detalle in receta.detalles.select_related("medicamento"):
        pendiente = pendiente_por_despachar(detalle)
        if pendiente == 0:
            continue
        disponible = stock_disponible(detalle.medicamento)
        entregar = min(pendiente, disponible)
        if entregar > 0:
            despachar_item(detalle, entregar, usuario=usuario)
            resumen["despachado"].append(
                {"medicamento": str(detalle.medicamento), "cantidad": entregar}
            )
        if entregar < pendiente:
            resumen["sin_stock"].append(
                {
                    "medicamento": str(detalle.medicamento),
                    "faltante": pendiente - entregar,
                }
            )
    _actualizar_estado_receta(receta)
    return resumen


def anular_receta(receta: Receta, motivo: str) -> Receta:
    """Anula una receta no despachada (error de prescripción)."""
    if not motivo:
        raise ValidationError("Debe indicar el motivo de la anulación.")
    if receta.estado in {Receta.Estado.DESPACHADA, Receta.Estado.PARCIAL}:
        raise ValidationError("No se puede anular una receta ya despachada total o parcialmente.")
    receta.estado = Receta.Estado.ANULADA
    receta.save(update_fields=["estado", "actualizado_en"])
    return receta


@transaction.atomic
def registrar_medicamento(
    *,
    codigo: str,
    dci: str,
    concentracion: str = "",
    forma_farmaceutica: str = "",
    unidad_medida: str = "",
    nombre_comercial: str = "",
    stock_minimo: int = 0,
    requiere_receta: bool = True,
    usuario=None,
) -> Medicamento:
    """
    Da de alta un medicamento en el catálogo de la farmacia.

    Hasta ahora no había forma de hacerlo desde el sistema: el inventario
    ingresaba lotes de un medicamento que YA existiera, y el catálogo solo lo
    llenaban los datos de demostración. En un despliegue real —una portable,
    o un servidor preparado con `--sin-demo`— el catálogo nacía vacío:
    Medicina no podía recetar nada y Farmacia no tenía qué ingresar. Lo único
    que quedaba era el panel de administración de Django, al que el personal
    de Farmacia no tiene acceso.

    El código es la clave del catálogo: se compara sin distinguir mayúsculas,
    porque «PCT500» y «pct500» son el mismo medicamento escrito dos veces.
    """
    from apps.auditoria.models import LogAuditoria

    codigo = (codigo or "").strip().upper()
    dci = (dci or "").strip()
    if not codigo:
        raise ValidationError("El código es obligatorio: es como se identifica en el catálogo.")
    if not dci:
        raise ValidationError(
            "La denominación común internacional (DCI) es obligatoria: es el principio activo."
        )
    if Medicamento.objects.filter(codigo__iexact=codigo).exists():
        raise ValidationError(f"Ya hay un medicamento con el código {codigo}.")
    if stock_minimo is not None and stock_minimo < 0:
        raise ValidationError("El stock mínimo no puede ser negativo.")

    medicamento = Medicamento.objects.create(
        codigo=codigo,
        dci=dci,
        concentracion=(concentracion or "").strip(),
        forma_farmaceutica=(forma_farmaceutica or "").strip(),
        unidad_medida=(unidad_medida or forma_farmaceutica or "").strip(),
        nombre_comercial=(nombre_comercial or "").strip(),
        stock_minimo=stock_minimo or 0,
        requiere_receta=requiere_receta,
        creado_por=getattr(usuario, "usuario", usuario),
    )
    cuenta = getattr(usuario, "usuario", usuario)
    LogAuditoria.objects.create(
        usuario=cuenta,
        rol_activo=getattr(cuenta, "rol_principal", ""),
        accion=LogAuditoria.Accion.CREATE,
        modulo="farmacia",
        entidad="Medicamento",
        entidad_id=str(medicamento.pk),
        detalle={"codigo": medicamento.codigo, "dci": medicamento.dci},
    )
    return medicamento
