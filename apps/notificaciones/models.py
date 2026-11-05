"""Recordatorios y avisos multicanal (informe 5.2)."""

from django.db import models

from apps.core.models import ModeloBase
from apps.usuarios.models import Usuario


class Notificacion(ModeloBase):
    class Canal(models.TextChoices):
        IN_APP = "in_app", "En la aplicación"
        EMAIL = "email", "Correo"
        SMS = "sms", "SMS"

    class Estado(models.TextChoices):
        PENDIENTE = "pendiente", "Pendiente"
        ENVIADA = "enviada", "Enviada"
        LEIDA = "leida", "Leída"
        FALLIDA = "fallida", "Fallida"

    usuario = models.ForeignKey(
        Usuario,
        on_delete=models.CASCADE,
        related_name="notificaciones",
        null=True,
        blank=True,
        help_text="Destinatario interno; null para notificaciones a personas sin cuenta.",
    )
    tipo = models.CharField(max_length=60)
    titulo = models.CharField(max_length=150)
    mensaje = models.TextField()
    canal = models.CharField(max_length=8, choices=Canal.choices, default=Canal.IN_APP)
    estado = models.CharField(max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    referencia_tipo = models.CharField(max_length=40, blank=True)
    referencia_id = models.PositiveBigIntegerField(null=True, blank=True)
    destinatario_correo = models.EmailField(blank=True)
    destinatario_nombre = models.CharField(max_length=200, blank=True)
    programada_para = models.DateTimeField(null=True, blank=True)
    enviada_en = models.DateTimeField(null=True, blank=True)
    # Cuándo la vio su destinatario, no solo si la vio. Sobre un valor crítico
    # de laboratorio, «a qué hora se enteró» es exactamente lo que habría que
    # poder responder después; un booleano no lo responde.
    leida_en = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "notificación"
        verbose_name_plural = "notificaciones"
        ordering = ["-creado_en"]
        # Sin índice compuesto (usuario, estado) a propósito: se midió con
        # 20 000 notificaciones y el de la clave foránea `usuario` ya resuelve
        # el contador de la cabecera igual de rápido. Añadirlo solo encarecía
        # cada escritura.
