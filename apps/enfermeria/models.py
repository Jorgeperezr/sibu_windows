"""
Ficha de enfermería y signos vitales (informe 6.2).

Los signos vitales registrados aquí son reutilizables por Medicina dentro del
mismo día (la HC médica los muestra automáticamente cuando existen).
"""

from decimal import Decimal, InvalidOperation

from django.db import models

from apps.expediente.models import Atencion, Expediente
from apps.usuarios.models import PerfilProfesional


def _a_decimal(valor):
    """Decimal, o None si el valor no es un número utilizable."""
    if valor is None or valor == "":
        return None
    try:
        return Decimal(str(valor))
    except (InvalidOperation, TypeError, ValueError):
        return None


class SignosVitales(models.Model):
    """
    Registro de signos vitales. Puede tomarse como parte del triaje previo a
    Medicina o como registro autónomo en Enfermería.

    - `expediente` es la clave para reutilizarlos desde Medicina (todos los
      signos del día del expediente están disponibles al abrir la HC).
    - `atencion` es opcional: se llena si el registro forma parte de una
      atención de enfermería específica.
    """

    expediente = models.ForeignKey(
        Expediente,
        on_delete=models.PROTECT,
        related_name="signos_vitales",
        null=True,
        blank=True,
        help_text="Se puede rellenar por FK directa aunque no exista atención.",
    )
    atencion = models.ForeignKey(
        Atencion,
        on_delete=models.CASCADE,
        related_name="signos_vitales",
        null=True,
        blank=True,
    )
    fecha_hora = models.DateTimeField(auto_now_add=True, db_index=True)

    temperatura = models.DecimalField(
        max_digits=4, decimal_places=1, null=True, blank=True, help_text="°C"
    )
    fc = models.PositiveSmallIntegerField(null=True, blank=True, verbose_name="frecuencia cardíaca")
    fr = models.PositiveSmallIntegerField(
        null=True, blank=True, verbose_name="frecuencia respiratoria"
    )
    pa_sistolica = models.PositiveSmallIntegerField(null=True, blank=True)
    pa_diastolica = models.PositiveSmallIntegerField(null=True, blank=True)
    sat_o2 = models.PositiveSmallIntegerField(null=True, blank=True, help_text="Saturación O2 (%)")
    peso = models.DecimalField(
        max_digits=5, decimal_places=2, null=True, blank=True, help_text="kg"
    )
    talla = models.DecimalField(
        max_digits=4, decimal_places=2, null=True, blank=True, help_text="metros"
    )
    imc = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
        help_text="Calculado automáticamente si hay peso y talla.",
    )
    perimetro_abdominal = models.PositiveSmallIntegerField(null=True, blank=True, help_text="cm")
    glicemia_capilar = models.PositiveSmallIntegerField(null=True, blank=True, help_text="mg/dL")
    responsable = models.ForeignKey(
        PerfilProfesional, on_delete=models.PROTECT, related_name="signos_tomados"
    )

    class Meta:
        verbose_name = "signos vitales"
        verbose_name_plural = "signos vitales"
        ordering = ["-fecha_hora"]
        indexes = [models.Index(fields=["expediente", "fecha_hora"])]
        constraints = [
            # Rangos amplios a propósito: no son rangos de normalidad clínica
            # —un paciente grave sale de ellos— sino de plausibilidad. Atrapan
            # el error de digitación (36 °C tecleado como 366) sin estorbar al
            # caso extremo real. `talla` en metros: 1.75, no 175.
            models.CheckConstraint(
                condition=models.Q(temperatura__isnull=True)
                | models.Q(temperatura__gte=25, temperatura__lte=45),
                name="ck_signos_temperatura_plausible",
                violation_error_message=(
                    "La temperatura tiene que estar entre 25 y 45 °C: "
                    "revise la coma (36,8 y no 368)."
                ),
            ),
            models.CheckConstraint(
                condition=models.Q(sat_o2__isnull=True) | models.Q(sat_o2__lte=100),
                name="ck_signos_saturacion_hasta_100",
                violation_error_message="La saturación de oxígeno no puede pasar de 100 %.",
            ),
            models.CheckConstraint(
                condition=models.Q(talla__isnull=True) | models.Q(talla__gt=0, talla__lte=3),
                name="ck_signos_talla_en_metros",
                violation_error_message="La talla va en metros: 1,62 y no 162.",
            ),
            models.CheckConstraint(
                condition=models.Q(peso__isnull=True) | models.Q(peso__gt=0, peso__lte=500),
                name="ck_signos_peso_plausible",
                violation_error_message=(
                    "El peso tiene que estar entre 0 y 500 kg: revise la coma (58,5 y no 585)."
                ),
            ),
            # La presión sistólica va por encima de la diastólica; invertirlas
            # es el error de captura más común del triaje.
            models.CheckConstraint(
                condition=models.Q(pa_sistolica__isnull=True)
                | models.Q(pa_diastolica__isnull=True)
                | models.Q(pa_sistolica__gt=models.F("pa_diastolica")),
                name="ck_signos_sistolica_mayor_que_diastolica",
                violation_error_message=(
                    "La presión sistólica tiene que ser mayor que la diastólica: ¿están invertidas?"
                ),
            ),
        ]

    def __str__(self):
        return f"Signos vitales {self.fecha_hora:%d/%m/%Y %H:%M} — {self.expediente}"

    def save(self, *args, **kwargs):
        # `self.talla` es lo que se asignó, no lo que el campo convertirá: al
        # crear con `talla="1.65"` —desde el shell, el admin o una carga— aquí
        # sigue siendo una cadena, y comparar cadena con entero reventaba con
        # TypeError. La vista de triaje se salvaba porque convierte antes; el
        # resto de caminos, no. Se convierte aquí, que es donde se calcula.
        peso, talla = _a_decimal(self.peso), _a_decimal(self.talla)
        if peso and talla and talla > 0:
            self.imc = Decimal(str(round(float(peso) / (float(talla) ** 2), 1)))
        super().save(*args, **kwargs)


class AtencionEnfermeria(models.Model):
    """
    Ficha de la atención de enfermería (procedimientos, inmunizaciones, notas).

    Los signos vitales se registran por separado en SignosVitales para que
    Medicina pueda reutilizarlos aunque la atención de enfermería no exista
    formalmente (p. ej. triaje rápido).
    """

    atencion = models.OneToOneField(
        Atencion,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name="enfermeria",
    )
    procedimientos = models.JSONField(
        default=list,
        blank=True,
        help_text="Lista de procedimientos: [{tipo, detalle, observaciones}]",
    )
    inmunizaciones = models.JSONField(
        default=list, blank=True, help_text="[{vacuna, dosis, lote, laboratorio, proxima_dosis}]"
    )
    charla_educativa = models.CharField(max_length=200, blank=True, help_text="Tema si aplica.")
    n_asistentes = models.PositiveSmallIntegerField(null=True, blank=True)
    notas = models.TextField(blank=True)

    class Meta:
        verbose_name = "atención de enfermería"
        verbose_name_plural = "atenciones de enfermería"

    def __str__(self):
        return f"Ficha de enfermería: {self.atencion}"
