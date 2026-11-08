"""
Usuario del sistema y perfil profesional.

El RBAC (informe, sección 10) se apoya en los grupos nativos de Django más
permisos por objeto (guardian) filtrados por `servicio`. Los roles canónicos
se definen como grupos cargados por fixture; aquí solo se modela la cuenta y
su relación con servicios y sección.
"""

from django.contrib.auth.models import AbstractUser, UserManager
from django.db import models

from apps.core.models import Seccion, Servicio


class Rol(models.TextChoices):
    ADMIN_GENERAL = "admin_general", "Administrador General"
    DIRECTOR = "director", "Director de la Unidad"
    COORDINADOR = "coordinador", "Coordinador de Sección"
    PROFESIONAL = "profesional", "Profesional de Servicio"
    LABORATORIO = "laboratorio", "Personal de Laboratorio"
    FARMACIA = "farmacia", "Personal de Farmacia"
    ADMINISTRATIVO = "administrativo", "Personal Administrativo"
    CONSULTA = "consulta", "Consulta Restringida"
    USUARIO_FINAL = "usuario_final", "Usuario Final (paciente/beneficiario)"


class GestorDeUsuarios(UserManager):
    """
    El superusuario nace con rol de Administrador General.

    `rol_principal` sale por omisión como «Consulta Restringida», así que la
    cuenta creada con `createsuperuser` —la primera del sistema, la del día del
    despliegue— entraba y no veía ni Reportes, ni la Bitácora, ni la carga de la
    base institucional: seis módulos de diecisiete. Quien acaba de instalar el
    sistema concluye que está roto.

    No amplía nada: `rbac.es_admin` ya trata al superusuario como administrador,
    y esto solo hace que la navegación diga lo mismo que el RBAC. El contenido
    clínico sigue fuera de su alcance —`atenciones_visibles` devuelve `.none()`
    para CUALQUIER administrador, por separación de funciones—, y el sello de
    Psicología no se toca.
    """

    def create_superuser(self, *args, **kwargs):
        kwargs.setdefault("rol_principal", Rol.ADMIN_GENERAL)
        return super().create_superuser(*args, **kwargs)


class Usuario(AbstractUser):
    """Cuenta de acceso. `username` = cédula o usuario institucional."""

    objects = GestorDeUsuarios()

    cedula = models.CharField(max_length=13, unique=True, null=True, blank=True)
    rol_principal = models.CharField(max_length=20, choices=Rol.choices, default=Rol.CONSULTA)
    mfa_habilitado = models.BooleanField(default=False)
    telefono = models.CharField(max_length=20, blank=True)
    fecha_nacimiento = models.DateField(null=True, blank=True)
    # Una cuenta recién creada por Administración General nace con una clave
    # temporal que el administrador tuvo que teclear y decir en voz alta. Hasta
    # que la persona ponga la suya, quien la creó puede entrar como ella —y si
    # la cuenta es de Psicología, eso sería una puerta al contenido sellado—.
    # El sistema la obliga a cambiarla antes de hacer nada.
    debe_cambiar_clave = models.BooleanField(
        default=False,
        verbose_name="debe cambiar la clave",
        help_text="La cuenta tiene una clave temporal y no puede usarse hasta cambiarla.",
    )
    # Con un PIN de 4 dígitos hay 10 000 claves posibles: el bloqueo de 15
    # minutos por equipo de axes, solo, deja probarlas todas en unas semanas.
    # Tras `SIBU_BLOQUEO_CUENTA` fallos seguidos la cuenta queda cerrada hasta
    # que Administración General la abra: diez intentos sobre diez mil.
    intentos_fallidos = models.PositiveSmallIntegerField(default=0)
    bloqueada_desde = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "usuario"
        verbose_name_plural = "usuarios"

    def __str__(self):
        return self.get_full_name() or self.username


class PerfilProfesional(models.Model):
    """Datos del profesional que atiende: servicios, registro y firma."""

    usuario = models.OneToOneField(Usuario, on_delete=models.CASCADE, related_name="perfil")
    seccion = models.ForeignKey(Seccion, null=True, blank=True, on_delete=models.SET_NULL)
    servicios = models.ManyToManyField(Servicio, related_name="profesionales", blank=True)
    titulo = models.CharField(max_length=120, blank=True)
    registro_profesional = models.CharField(
        max_length=60, blank=True, help_text="Registro (ACESS/SENESCYT) del profesional."
    )
    denominacion_cargo = models.CharField(
        max_length=150, blank=True, help_text="Denominación del cargo según el manual de puestos."
    )
    puede_firmar_digital = models.BooleanField(default=False)

    class Meta:
        verbose_name = "perfil profesional"
        verbose_name_plural = "perfiles profesionales"

    def __str__(self):
        return f"Perfil de {self.usuario}"


class ActividadEsencial(models.Model):
    """
    Una actividad esencial del manual de puestos (LOSEP) del profesional.

    El manual real numera entre diez y trece actividades; la última suele ser
    "las demás actividades que le asigne su jefe inmediato", y bajo esa
    entrada se acumulan con el tiempo tareas concretas delegadas. Por eso una
    actividad admite sub-actividades vía `actividad_superior`: no es una lista
    plana forzada a serlo, es la misma jerarquía de dos niveles que trae el
    manual de puestos.

    `perfil` se guarda también en las sub-actividades —no solo en la raíz— para
    no tener que subir la cadena en cada consulta; se valida en el servicio
    que coincida con el de `actividad_superior`.
    """

    perfil = models.ForeignKey(
        PerfilProfesional, on_delete=models.CASCADE, related_name="actividades_esenciales"
    )
    actividad_superior = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.CASCADE, related_name="subactividades"
    )
    orden = models.PositiveSmallIntegerField()
    descripcion = models.CharField(max_length=500)

    class Meta:
        verbose_name = "actividad esencial"
        verbose_name_plural = "actividades esenciales"
        ordering = ["orden"]

    def __str__(self):
        return self.descripcion[:60]
