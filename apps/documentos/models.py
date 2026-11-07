"""
Gestión documental: los documentos del expediente (órdenes, informes,
exámenes de fuera, consentimientos escaneados, fotos clínicas) y las
evidencias de los talleres.

Los del expediente se guardan en una carpeta PRIVADA, fuera de `MEDIA_ROOT`,
y solo se sirven a través de una vista que comprueba el acceso: `/media/` se
sirve sin preguntar a nadie, y un informe de Psicología no puede estar a una
URL de distancia de quien la adivine.

No se cifran en disco —SIBU no tiene custodia de claves—: lo que protege los
archivos en reposo es el cifrado del disco del equipo (BitLocker).
"""

from django.db import models

from apps.core.models import ModeloBase
from apps.expediente.models import Atencion, Expediente


class DocumentoAnexo(ModeloBase):
    class Almacenamiento(models.TextChoices):
        # «cifrado» decía la etiqueta, y nada se cifraba.
        LOCAL = "local", "Almacén local"
        GDRIVE = "gdrive", "Google Drive institucional"

    expediente = models.ForeignKey(
        Expediente, null=True, blank=True, on_delete=models.CASCADE, related_name="documentos"
    )
    atencion = models.ForeignKey(
        Atencion, null=True, blank=True, on_delete=models.CASCADE, related_name="documentos"
    )
    taller = models.ForeignKey(
        "talleres.Taller",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="evidencias",
    )
    modulo = models.CharField(max_length=40)
    # El servicio que lo subió, y por tanto quién puede verlo. Es la misma
    # regla que el contenido clínico: un documento de Psicología no sale de
    # Psicología. Vacío en las evidencias de talleres.
    servicio = models.ForeignKey(
        "core.Servicio", null=True, blank=True, on_delete=models.PROTECT, related_name="documentos"
    )
    descripcion = models.CharField(max_length=255, blank=True)
    # Una foto marcada se guarda como documento NUEVO que apunta a la que
    # marcó: la original no se toca. Una historia clínica no pierde el
    # original por haberle pintado encima.
    original = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="versiones"
    )
    tipo_documento = models.CharField(max_length=60)
    nombre_archivo = models.CharField(max_length=255)
    almacenamiento = models.CharField(
        max_length=8, choices=Almacenamiento.choices, default=Almacenamiento.LOCAL
    )
    # Se llamaba `ruta_cifrada` y la ruta apuntaba a un archivo en claro.
    ruta = models.CharField(max_length=500, blank=True)
    gdrive_file_id = models.CharField(max_length=120, blank=True)
    gdrive_url = models.URLField(blank=True)
    mime = models.CharField(max_length=100, blank=True)
    tamano = models.PositiveIntegerField(default=0)
    hash_sha256 = models.CharField(max_length=64, blank=True)

    class TipoDocumento(models.TextChoices):
        ORDEN = "orden", "Orden o pedido"
        REFERENCIA = "referencia", "Referencia o contrarreferencia"
        EXAMEN = "examen", "Examen o resultado externo"
        INFORME = "informe", "Informe"
        CONSENTIMIENTO = "consentimiento", "Consentimiento firmado"
        IDENTIFICACION = "identificacion", "Identificación"
        FOTO = "foto", "Foto clínica"
        OTRO = "otro", "Otro"

    class Meta:
        verbose_name = "documento anexo"
        verbose_name_plural = "documentos anexos"
        indexes = [
            models.Index(fields=["expediente", "servicio"], name="ix_doc_expediente_servicio")
        ]

    @property
    def es_imagen(self) -> bool:
        return self.mime.startswith("image/")

    @property
    def es_pdf(self) -> bool:
        return self.mime == "application/pdf"
