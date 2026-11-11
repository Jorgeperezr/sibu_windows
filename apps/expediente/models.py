"""
Expediente único de la persona y modelo base de atención.

Toda ficha de servicio (Medicina, Enfermería, …) extiende `Atencion` mediante
una relación OneToOne (patrón "clase base + extensión", informe 4.2 y 11.3).
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.academico.validators import normalizar_cedula, validar_cedula_ecuatoriana
from apps.core.models import ModeloBase, Servicio
from apps.usuarios.models import PerfilProfesional


class Persona(ModeloBase):
    """Datos demográficos consolidados. Clave de vinculación: cédula."""

    class TipoVinculo(models.TextChoices):
        """
        El vínculo con la UNL. Los cuatro primeros valores son los ESTAMENTOS
        universitarios; el quinto no lo es.

        No se añade un campo `estamento` aparte teniendo esto: serían dos
        columnas con los mismos cuatro valores, y el día que una se actualice y
        la otra no, el informe y el expediente dirán cosas distintas de la
        misma persona. `estamento` es el nombre de dominio de este campo cuando
        se reporta —así lo pide la Unidad— y `ESTAMENTOS` es la lista que
        excluye a quien no pertenece a la comunidad universitaria.
        """

        ESTUDIANTE = "estudiante", "Estudiante"
        DOCENTE = "docente", "Docente"
        ADMINISTRATIVO = "administrativo", "Administrativo"
        TRABAJADOR = "trabajador", "Trabajador"
        EXTERNO = "externo", "Externo/Particular"

    # Los cuatro estamentos, en el orden en que la Unidad los nombra. Un
    # externo —un familiar, alguien de la comunidad— se atiende igual, pero no
    # es un estamento y por eso no puede ser el destino de una carga
    # institucional: no hay base institucional de externos.
    ESTAMENTOS = [
        TipoVinculo.ESTUDIANTE,
        TipoVinculo.DOCENTE,
        TipoVinculo.ADMINISTRATIVO,
        TipoVinculo.TRABAJADOR,
    ]
    ESTAMENTOS_CHOICES = [(v.value, v.label) for v in ESTAMENTOS]

    cedula = models.CharField(max_length=13, unique=True, db_index=True)
    tipo_documento = models.CharField(max_length=20, default="cedula")
    nombres = models.CharField(max_length=120)
    apellidos = models.CharField(max_length=120)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    sexo = models.CharField(max_length=20, blank=True)
    genero = models.CharField(max_length=30, blank=True)
    # Identidad de género y orientación sexual: un solo ítem, no dos campos.
    # Libre y no obligatorio, igual que sexo/género.
    identidad_orientacion_sexual = models.CharField(max_length=60, blank=True)
    tipo_vinculo = models.CharField(max_length=20, choices=TipoVinculo.choices)
    correo_institucional = models.EmailField(blank=True)
    correo_personal = models.EmailField(blank=True)
    telefono = models.CharField(max_length=20, blank=True)
    celular = models.CharField(max_length=20, blank=True)

    # Estructuras semi-variables (informe 7.3)
    procedencia = models.JSONField(default=dict, blank=True)
    residencia_actual = models.JSONField(default=dict, blank=True)
    contacto_referencia = models.JSONField(default=dict, blank=True)

    class Meta:
        verbose_name = "persona"
        verbose_name_plural = "personas"
        ordering = ["apellidos", "nombres"]

    def __str__(self):
        return f"{self.apellidos} {self.nombres} ({self.cedula})"

    @property
    def nombre_completo(self):
        return f"{self.apellidos} {self.nombres}".strip()

    @property
    def edad(self):
        """
        Los años cumplidos hoy, o None si no consta la fecha de nacimiento.

        Se calcula, no se guarda, y eso es lo que la hace fiable: una edad
        almacenada envejece mal —queda congelada en la carga que la escribió— y
        al año siguiente el expediente afirma una edad que ya no es cierta. La
        fecha de nacimiento no cambia nunca; la edad, cada año.

        `(hoy.month, hoy.day) < (…)` resta el año que aún no se ha cumplido: sin
        eso, quien nació en diciembre aparece un año mayor durante once meses.
        """
        if not self.fecha_nacimiento:
            return None
        hoy = timezone.localdate()
        nacimiento = self.fecha_nacimiento
        cumplido = (hoy.month, hoy.day) >= (nacimiento.month, nacimiento.day)
        return hoy.year - nacimiento.year - (0 if cumplido else 1)

    def save(self, *args, **kwargs):
        """
        Normaliza y valida la cédula antes de tocar la base.

        La cédula es la clave de vinculación del expediente único: una mal
        digitada crea una persona fantasma que ya no se puede cruzar con nada.
        `academico`, `talleres` y `portal` validaban en su propio servicio, pero
        el modelo aceptaba cualquier cadena, así que cualquier otra vía de
        creación —el admin, el shell, una migración de datos— la colaba.

        Se valida solo el documento de tipo cédula: un externo con pasaporte no
        pasa el módulo 10 ecuatoriano y es un caso legítimo.
        """
        if self.tipo_documento == "cedula":
            self.cedula = normalizar_cedula(self.cedula)
            if not validar_cedula_ecuatoriana(self.cedula):
                raise ValidationError(
                    {"cedula": f"La cédula {self.cedula} no es válida (módulo 10 ecuatoriano)."}
                )
        return super().save(*args, **kwargs)


class Expediente(ModeloBase):
    """Carpeta digital única que consolida todas las atenciones de la persona."""

    persona = models.OneToOneField(Persona, on_delete=models.PROTECT, related_name="expediente")
    numero_expediente = models.CharField(max_length=20, unique=True, db_index=True)
    grupo_sanguineo = models.CharField(max_length=5, blank=True)
    discapacidad_tipo = models.CharField(max_length=60, blank=True)
    discapacidad_porcentaje = models.PositiveSmallIntegerField(null=True, blank=True)
    # Lo que la persona declaró de su salud en la ficha de matrícula: problema
    # de salud y diagnóstico, COVID, vacunas, enfermedad catastrófica o rara…
    # Antes solo quedaba en la fila cruda de cada período, sin pantalla que lo
    # enseñara. Es lo DECLARADO, no lo comprobado: se fusiona en cada carga y un
    # vacío nunca borra lo anterior. Lo ven los servicios clínicos de Salud.
    salud_declarada = models.JSONField(default=dict, blank=True)
    fecha_apertura = models.DateField(auto_now_add=True)

    class Meta:
        verbose_name = "expediente"
        verbose_name_plural = "expedientes"
        constraints = [
            # PositiveSmallIntegerField solo impide el negativo: un 250 % de
            # discapacidad entraba sin protestar.
            models.CheckConstraint(
                condition=models.Q(discapacidad_porcentaje__isnull=True)
                | models.Q(discapacidad_porcentaje__lte=100),
                name="ck_expediente_discapacidad_hasta_100",
            ),
        ]

    def __str__(self):
        return f"Expediente {self.numero_expediente}"


class AlertaClinica(ModeloBase):
    """Banderas visibles en todo el expediente (alergias, riesgo, alertas sociales)."""

    class Tipo(models.TextChoices):
        ALERGIA = "alergia", "Alergia"
        RIESGO = "riesgo", "Riesgo clínico"
        SOCIAL = "social", "Alerta social"
        NEE = "nee", "Necesidad educativa especial"
        GESTACION = "gestacion", "Gestación"
        LACTANCIA = "lactancia", "Lactancia"
        ENF_CATASTROFICA = "enf_catastrofica", "Enfermedad catastrófica"

    class Origen(models.TextChoices):
        MATRICULA = "matricula", "Declarada en matrícula"
        PROFESIONAL = "profesional", "Registrada por un profesional"

    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name="alertas")
    # Se ensancha de 12 a 20: "enf_catastrofica" no cabía en el ancho original.
    tipo = models.CharField(max_length=20, choices=Tipo.choices)
    descripcion = models.CharField(max_length=255)
    activa = models.BooleanField(default=True)
    # Quién la puso, y esto decide quién puede apagarla.
    #
    # La gestación y la lactancia cambian de un período al siguiente, y la carga
    # institucional solo sabía encenderlas: `get_or_create` creaba la alerta y
    # nada la desactivaba nunca, así que un embarazo declarado en 2026-1 seguía
    # activo en 2027 y el informe lo seguía contando.
    #
    # La carga puede apagar lo que la carga encendió. Lo que registró un
    # profesional en consulta no lo toca: él lo comprobó, la ficha de matrícula
    # no, y una recarga no es una segunda opinión.
    origen = models.CharField(max_length=12, choices=Origen.choices, default=Origen.MATRICULA)

    class Meta:
        verbose_name = "alerta clínica"
        verbose_name_plural = "alertas clínicas"

    def __str__(self):
        return f"[{self.get_tipo_display()}] {self.descripcion}"


class Consentimiento(ModeloBase):
    """Consentimiento informado digitalizado (informe 14.3)."""

    expediente = models.ForeignKey(
        Expediente, on_delete=models.CASCADE, related_name="consentimientos"
    )
    tipo = models.CharField(max_length=80)
    texto_version = models.CharField(max_length=20)
    otorgado = models.BooleanField(default=False)
    fecha = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "consentimiento"
        verbose_name_plural = "consentimientos"


class Atencion(ModeloBase):
    """
    Base común de toda atención. Las apps de servicio la extienden 1:1.
    Una atención firmada es inmutable; las correcciones se hacen por enmienda.
    """

    class Tipo(models.TextChoices):
        PRIMERA = "primera", "Primera"
        SUBSECUENTE = "subsecuente", "Subsecuente"

    class Origen(models.TextChoices):
        CITA = "cita", "Cita"
        ESPONTANEA = "espontanea", "Demanda espontánea"
        DERIVACION = "derivacion", "Derivación"
        EMERGENCIA = "emergencia", "Emergencia"

    class Estado(models.TextChoices):
        BORRADOR = "borrador", "Borrador"
        CERRADA = "cerrada", "Cerrada"
        FIRMADA = "firmada", "Firmada"
        ENMENDADA = "enmendada", "Enmendada"

    expediente = models.ForeignKey(Expediente, on_delete=models.PROTECT, related_name="atenciones")
    servicio = models.ForeignKey(Servicio, on_delete=models.PROTECT, related_name="atenciones")
    profesional = models.ForeignKey(
        PerfilProfesional, on_delete=models.PROTECT, related_name="atenciones"
    )
    fecha_hora = models.DateTimeField(db_index=True)
    tipo = models.CharField(max_length=12, choices=Tipo.choices, default=Tipo.PRIMERA)
    origen = models.CharField(max_length=12, choices=Origen.choices, default=Origen.CITA)
    motivo_consulta = models.TextField(blank=True)
    estado = models.CharField(max_length=12, choices=Estado.choices, default=Estado.BORRADOR)

    # Instantánea de los datos institucionales al momento de la atención (7.5)
    snapshot_academico = models.JSONField(default=dict, blank=True)

    firmada_en = models.DateTimeField(null=True, blank=True)
    hash_firma = models.CharField(max_length=64, blank=True)

    class Meta:
        verbose_name = "atención"
        verbose_name_plural = "atenciones"
        ordering = ["-fecha_hora"]
        indexes = [
            models.Index(fields=["expediente", "fecha_hora"]),
            models.Index(fields=["servicio", "fecha_hora"]),
        ]

    def __str__(self):
        return f"Atención {self.servicio} — {self.expediente} ({self.fecha_hora:%Y-%m-%d})"

    @property
    def inmutable(self):
        return self.estado in {self.Estado.FIRMADA, self.Estado.ENMENDADA}


class AjusteDeServicio(ModeloBase):
    """
    Corrección de una variable de la persona, válida SOLO dentro de un servicio.

    La base institucional viene de la matrícula y es una foto del momento en que
    el estudiante llenó la ficha. Un servicio encuentra otra realidad: la ficha
    dice que no hay embarazo y en Medicina se registra uno. Ese hallazgo tiene
    que poder anotarse sin reescribir la base institucional, que es la fuente
    para el resto del sistema y que nadie autorizó a corregir desde una consulta.

    De ahí el alcance por servicio: cada uno trabaja y reporta con lo que él
    mismo comprobó, y lo que no haya comprobado lo toma de la institución. La
    foto original queda intacta y se puede volver a ella quitando el ajuste.

    Hay dos variables que NO se pueden ajustar, y no por omisión: el género y la
    identidad u orientación sexual son declaraciones de la persona sobre sí
    misma. Que un servicio las «corrija» sería asignarle una identidad a
    alguien. Se cambian donde se declaran —el alta o el portal—, no aquí.
    """

    class Variable(models.TextChoices):
        SEXO = "sexo", "Sexo"
        GRUPO_SANGUINEO = "grupo_sanguineo", "Grupo sanguíneo"
        DISCAPACIDAD_TIPO = "discapacidad_tipo", "Tipo de discapacidad"
        DISCAPACIDAD_PORCENTAJE = "discapacidad_porcentaje", "Porcentaje de discapacidad"
        GESTACION = "gestacion", "Embarazo"
        LACTANCIA = "lactancia", "Lactancia"
        ENF_CATASTROFICA = "enf_catastrofica", "Enfermedad catastrófica"
        NEE = "nee", "Necesidad educativa especial"

    expediente = models.ForeignKey(Expediente, on_delete=models.CASCADE, related_name="ajustes")
    servicio = models.ForeignKey(Servicio, on_delete=models.CASCADE, related_name="ajustes")
    variable = models.CharField(max_length=30, choices=Variable.choices)
    valor = models.CharField(max_length=120)
    # Por qué se cambió. No es adorno: un dato que contradice a la matrícula sin
    # explicación es indistinguible de un error de digitación.
    nota = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "ajuste de servicio"
        verbose_name_plural = "ajustes de servicio"
        ordering = ["variable"]
        constraints = [
            # Uno por variable y servicio: dos filas para lo mismo dejarían el
            # valor efectivo a merced del orden de la consulta.
            models.UniqueConstraint(
                fields=["expediente", "servicio", "variable"],
                name="uniq_ajuste_por_servicio_y_variable",
            )
        ]

    def __str__(self):
        return f"{self.get_variable_display()}={self.valor} ({self.servicio})"
