"""Derivación interna y referencia/contrarreferencia externa (informe 5.2, 12.2, 12.3)."""

from django.db import models

from apps.core.models import ModeloBase, Servicio
from apps.expediente.models import Atencion


class Derivacion(ModeloBase):
    class Estado(models.TextChoices):
        ENVIADA = "enviada", "Enviada"
        ACEPTADA = "aceptada", "Aceptada"
        AGENDADA = "agendada", "Agendada"
        ATENDIDA = "atendida", "Atendida"
        RETORNADA = "retornada", "Retornada"
        RECHAZADA = "rechazada", "Rechazada"

    atencion_origen = models.ForeignKey(
        Atencion, on_delete=models.PROTECT, related_name="derivaciones_emitidas"
    )
    servicio_destino = models.ForeignKey(
        Servicio, on_delete=models.PROTECT, related_name="derivaciones_recibidas"
    )
    motivo = models.CharField(max_length=255)
    resumen = models.TextField(blank=True)
    prioridad = models.CharField(
        max_length=10, choices=[("normal", "Normal"), ("urgente", "Urgente")], default="normal"
    )
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.ENVIADA)
    atencion_destino = models.ForeignKey(
        Atencion,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="derivaciones_atendidas",
    )
    retorno_texto = models.TextField(blank=True)

    class Meta:
        verbose_name = "derivación"
        verbose_name_plural = "derivaciones"
        indexes = [
            # La bandeja de cada servicio: las abiertas hacia él.
            models.Index(fields=["servicio_destino", "estado"], name="ix_deriv_destino_estado"),
        ]


class ReferenciaExterna(ModeloBase):
    atencion = models.ForeignKey(Atencion, on_delete=models.PROTECT, related_name="referencias")
    institucion_destino = models.CharField(max_length=200)
    especialidad = models.CharField(max_length=120, blank=True)
    motivo = models.CharField(max_length=255)
    resumen_clinico = models.TextField(blank=True)

    class Meta:
        verbose_name = "referencia externa"
        verbose_name_plural = "referencias externas"


class Contrarreferencia(models.Model):
    referencia = models.OneToOneField(
        ReferenciaExterna, on_delete=models.CASCADE, related_name="contrarreferencia"
    )
    fecha_recepcion = models.DateField()
    hallazgos = models.TextField(blank=True)
    tratamiento_instaurado = models.TextField(blank=True)

    def __str__(self):
        return f"Contrarreferencia de {self.referencia}"
