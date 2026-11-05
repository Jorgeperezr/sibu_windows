"""
Recetas, dispensación e inventario con control por lote (FEFO) — informe 5.2, 6.5.
"""

from django.db import models

from apps.core.models import ModeloBase
from apps.expediente.models import Atencion
from apps.usuarios.models import PerfilProfesional


class Medicamento(ModeloBase):
    codigo = models.CharField(max_length=20, unique=True)
    dci = models.CharField(max_length=150, verbose_name="denominación común internacional")
    nombre_comercial = models.CharField(max_length=150, blank=True)
    concentracion = models.CharField(max_length=60, blank=True)
    forma_farmaceutica = models.CharField(max_length=60, blank=True)
    unidad_medida = models.CharField(max_length=30, blank=True)
    stock_minimo = models.PositiveIntegerField(default=0)
    stock_maximo = models.PositiveIntegerField(default=0)
    requiere_receta = models.BooleanField(default=True)
    activo = models.BooleanField(default=True)

    class Meta:
        verbose_name = "medicamento"
        verbose_name_plural = "medicamentos"
        constraints = [
            # stock_maximo=0 significa "sin máximo definido", no un máximo real.
            models.CheckConstraint(
                condition=models.Q(stock_maximo=0)
                | models.Q(stock_maximo__gte=models.F("stock_minimo")),
                name="ck_medicamento_min_no_supera_max",
            ),
        ]

    def __str__(self):
        return f"{self.dci} {self.concentracion}".strip()


class Lote(models.Model):
    medicamento = models.ForeignKey(Medicamento, on_delete=models.PROTECT, related_name="lotes")
    numero_lote = models.CharField(max_length=60)
    fecha_caducidad = models.DateField(db_index=True)
    cantidad_actual = models.IntegerField(default=0)
    costo_unitario = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    proveedor = models.CharField(max_length=150, blank=True)

    class Meta:
        verbose_name = "lote"
        verbose_name_plural = "lotes"
        indexes = [models.Index(fields=["medicamento", "fecha_caducidad"])]  # soporte FEFO
        constraints = [
            # `ingresar_lote` hace get_or_create sobre esta pareja: sin la
            # restricción, dos ingresos simultáneos crean dos lotes gemelos y
            # el stock del medicamento queda partido en dos filas.
            models.UniqueConstraint(
                fields=["medicamento", "numero_lote"], name="uniq_lote_por_medicamento"
            ),
            # El saldo de un lote nunca puede quedar en negativo: sería stock
            # que no existe. La lógica ya lo evita; esto lo hace imposible.
            models.CheckConstraint(
                condition=models.Q(cantidad_actual__gte=0),
                name="ck_lote_cantidad_no_negativa",
            ),
        ]

    def __str__(self):
        return f"{self.medicamento} · lote {self.numero_lote} (cad. {self.fecha_caducidad})"


class MovimientoInventario(models.Model):
    class Tipo(models.TextChoices):
        INGRESO = "ingreso", "Ingreso"
        EGRESO = "egreso", "Egreso"
        AJUSTE_MAS = "ajuste_mas", "Ajuste (+)"
        AJUSTE_MENOS = "ajuste_menos", "Ajuste (-)"
        BAJA = "baja", "Baja"
        TRANSFERENCIA = "transferencia", "Transferencia"

    lote = models.ForeignKey(Lote, on_delete=models.PROTECT, related_name="movimientos")
    tipo = models.CharField(max_length=14, choices=Tipo.choices)
    cantidad = models.IntegerField()
    saldo_resultante = models.IntegerField()
    referencia_doc = models.CharField(max_length=60, blank=True)
    usuario = models.ForeignKey(PerfilProfesional, on_delete=models.PROTECT)
    fecha_hora = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "movimiento de inventario"
        verbose_name_plural = "movimientos de inventario"

    def __str__(self):
        return f"{self.get_tipo_display()} {self.cantidad} — {self.lote}"


class Receta(ModeloBase):
    class Estado(models.TextChoices):
        EMITIDA = "emitida", "Emitida"
        PARCIAL = "despachada_parcial", "Despachada parcial"
        DESPACHADA = "despachada", "Despachada"
        CADUCADA = "caducada", "Caducada"
        ANULADA = "anulada", "Anulada"

    atencion = models.ForeignKey(Atencion, on_delete=models.PROTECT, related_name="recetas")
    numero = models.CharField(max_length=20, unique=True)
    valida_hasta = models.DateTimeField()
    estado = models.CharField(max_length=20, choices=Estado.choices, default=Estado.EMITIDA)

    class Meta:
        verbose_name = "receta"
        verbose_name_plural = "recetas"
        indexes = [
            # El mostrador: las emitidas o parciales, de la más antigua a la
            # más nueva. Sin esto, recorre todas las recetas de la historia.
            models.Index(fields=["estado", "creado_en"], name="ix_receta_estado_creada"),
        ]


class RecetaDetalle(models.Model):
    receta = models.ForeignKey(Receta, on_delete=models.CASCADE, related_name="detalles")
    medicamento = models.ForeignKey(Medicamento, on_delete=models.PROTECT)
    cantidad_prescrita = models.PositiveIntegerField()
    dosis = models.CharField(max_length=120, blank=True)
    via = models.CharField(max_length=40, blank=True)
    frecuencia = models.CharField(max_length=60, blank=True)
    duracion = models.CharField(max_length=60, blank=True)
    indicaciones = models.CharField(max_length=255, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad_prescrita__gt=0),
                name="ck_receta_detalle_cantidad_positiva",
            ),
        ]

    def __str__(self):
        return f"{self.medicamento} x{self.cantidad_prescrita}"


class Dispensacion(models.Model):
    receta_detalle = models.ForeignKey(
        RecetaDetalle, on_delete=models.PROTECT, related_name="dispensaciones"
    )
    lote = models.ForeignKey(Lote, on_delete=models.PROTECT)
    cantidad_despachada = models.PositiveIntegerField()
    despachado_por = models.ForeignKey(PerfilProfesional, on_delete=models.PROTECT)
    fecha_hora = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "dispensación"
        verbose_name_plural = "dispensaciones"
        constraints = [
            models.CheckConstraint(
                condition=models.Q(cantidad_despachada__gt=0),
                name="ck_dispensacion_cantidad_positiva",
            ),
        ]

    def __str__(self):
        return f"Despacho {self.cantidad_despachada} — {self.receta_detalle}"
