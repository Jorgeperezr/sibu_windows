"""
Documentos del expediente: subirlos, escanearlos, verlos y marcarlos.

Traído de clinube (`patients.PatientDocument`, `lib/DocumentScanner.js`,
`lib/realceDocumento.mjs`, `lib/FotoAnotada.js`), con dos cambios para SIBU:

- **El sello.** Cada documento pertenece al servicio que lo subió y lo ve quien
  ve el contenido clínico de ese servicio: en Psicología, solo sus
  profesionales —ni Dirección, ni administración, ni Coordinación—.
- **El escaneo se arma en el servidor**, con Pillow, que ya es dependencia.
  clinube lo hacía en el navegador con jsPDF y la cámara en vivo, que exige
  https: en la portable compartida por la WiFi (`http://RECEPCION:8000`) el
  navegador no da la cámara en vivo. Elegir fotos sí funciona en todas partes,
  y en un teléfono abre la cámara del sistema.

Los archivos van a una carpeta privada, fuera de `MEDIA_ROOT`, y solo salen por
`documentos:archivo`, que comprueba el acceso y deja constancia.
"""

from __future__ import annotations

import hashlib
import io
import uuid
from pathlib import Path

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.usuarios.models import Rol
from apps.usuarios.rbac import SERVICIOS_CONFIDENCIALES, puede_ver_servicio, servicios_del_usuario

from .models import DocumentoAnexo

# Un consentimiento escaneado o un examen de fuera, no un estudio de imagen.
TAMANO_MAXIMO = 20 * 1024 * 1024
# Lado mayor de una página escaneada: legible, y sin PDFs de 50 MB.
LADO_MAXIMO = 2200
MAXIMO_PAGINAS = 30

# Se reconoce el tipo por los PRIMEROS BYTES, no por la extensión ni por lo que
# diga el navegador. Un «informe.pdf» que en realidad es HTML, servido en
# línea, ejecutaría su JavaScript con la sesión de quien lo abre.
FIRMAS = (
    (b"%PDF-", "application/pdf", ".pdf"),
    (b"\xff\xd8\xff", "image/jpeg", ".jpg"),
    (b"\x89PNG\r\n\x1a\n", "image/png", ".png"),
)


def tipo_de(contenido: bytes) -> tuple[str, str]:
    """(mime, extensión) por los primeros bytes; ValidationError si no es admitido."""
    for firma, mime, extension in FIRMAS:
        if contenido.startswith(firma):
            return mime, extension
    if contenido[:4] == b"RIFF" and contenido[8:12] == b"WEBP":
        return "image/webp", ".webp"
    raise ValidationError("Solo se admiten PDF y fotos (JPG, PNG o WebP).")


def carpeta_privada() -> Path:
    return Path(getattr(settings, "SIBU_DOCUMENTOS_ROOT", Path(settings.BASE_DIR) / "privado"))


# ------------------------------------------------------------------ acceso


def puede_ver_documento(user, documento: DocumentoAnexo) -> bool:
    """
    La misma regla que `rbac.puede_ver_atencion`, sin acceso de emergencia.

    En un servicio confidencial, solo un PROFESIONAL de ese servicio: ni el
    coordinador de la sección, ni Dirección, ni administración. En los demás,
    quien ve el contenido clínico del servicio.
    """
    if not getattr(user, "is_authenticated", False) or documento.servicio_id is None:
        return False
    servicio = documento.servicio
    if servicio.codigo in SERVICIOS_CONFIDENCIALES:
        return user.rol_principal == Rol.PROFESIONAL and servicio.pk in servicios_del_usuario(user)
    return puede_ver_servicio(user, servicio)


def documentos_visibles(user, expediente):
    """Los documentos de este expediente que este usuario puede ver."""
    candidatos = (
        DocumentoAnexo.objects.filter(expediente=expediente, servicio__isnull=False)
        .select_related("servicio", "creado_por", "original")
        .order_by("-creado_en")
    )
    return [d for d in candidatos if puede_ver_documento(user, d)]


def servicios_para_subir(user):
    """Los servicios en los que este usuario puede adjuntar: los suyos."""
    from apps.core.models import Servicio

    return Servicio.objects.filter(pk__in=servicios_del_usuario(user)).order_by("nombre")


def _exigir_servicio_propio(usuario, servicio) -> None:
    """
    Se adjunta en un servicio PROPIO. Si no, bastaría con elegir Psicología en
    el formulario para dejar un documento que sus profesionales leerían como
    suyo —o, al revés, para sacar uno de su sello—.
    """
    if servicio is None or servicio.pk not in servicios_del_usuario(usuario):
        raise PermissionDenied("Solo puede adjuntar documentos en los servicios donde atiende.")


# ------------------------------------------------------------------ escritura


def _auditar(usuario, accion, documento, **detalle) -> None:
    from apps.auditoria.models import LogAuditoria

    LogAuditoria.objects.create(
        usuario=usuario,
        rol_activo=getattr(usuario, "rol_principal", ""),
        accion=accion,
        modulo="documentos",
        entidad="DocumentoAnexo",
        entidad_id=str(documento.pk),
        detalle={
            "expediente": documento.expediente_id,
            "servicio": documento.servicio_id,
            **detalle,
        },
    )


@transaction.atomic
def subir_documento(
    *,
    expediente,
    servicio,
    usuario,
    nombre: str,
    contenido: bytes,
    tipo_documento: str = DocumentoAnexo.TipoDocumento.OTRO,
    descripcion: str = "",
    original: DocumentoAnexo | None = None,
) -> DocumentoAnexo:
    """Guarda el archivo en la carpeta privada y lo registra en el expediente."""
    from apps.auditoria.models import LogAuditoria

    _exigir_servicio_propio(usuario, servicio)
    if not contenido:
        raise ValidationError("El archivo está vacío.")
    if len(contenido) > TAMANO_MAXIMO:
        raise ValidationError(
            f"El archivo pasa de {TAMANO_MAXIMO // (1024 * 1024)} MB. Si es un escaneo, "
            "use menos páginas o la opción «Documento», que pesa menos."
        )
    mime, extension = tipo_de(contenido)
    if tipo_documento not in DocumentoAnexo.TipoDocumento.values:
        tipo_documento = DocumentoAnexo.TipoDocumento.OTRO

    # El nombre en disco no sale de lo que escribió nadie: un «../../x» no
    # puede escribir fuera de la carpeta, y el nombre de un informe de
    # Psicología no queda a la vista en el sistema de archivos.
    relativa = Path(str(expediente.pk)) / f"{uuid.uuid4().hex}{extension}"
    destino = carpeta_privada() / relativa
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_bytes(contenido)

    nombre_visible = Path(nombre or "documento").name[:200] or "documento"
    if not nombre_visible.lower().endswith(extension):
        nombre_visible = Path(nombre_visible).stem + extension

    documento = DocumentoAnexo.objects.create(
        expediente=expediente,
        servicio=servicio,
        modulo=servicio.codigo,
        tipo_documento=tipo_documento,
        descripcion=(descripcion or "").strip()[:255],
        nombre_archivo=nombre_visible,
        almacenamiento=DocumentoAnexo.Almacenamiento.LOCAL,
        ruta=str(relativa),
        mime=mime,
        tamano=len(contenido),
        hash_sha256=hashlib.sha256(contenido).hexdigest(),
        original=original,
        creado_por=usuario,
    )
    _auditar(usuario, LogAuditoria.Accion.CREATE, documento, tipo=tipo_documento, mime=mime)
    return documento


def leer_documento(usuario, documento: DocumentoAnexo) -> bytes:
    """El contenido, si este usuario puede verlo. Deja constancia de la lectura."""
    from apps.auditoria.models import LogAuditoria

    if not puede_ver_documento(usuario, documento) or documento.eliminado_en is not None:
        raise PermissionDenied("Este documento no es de su servicio.")
    ruta = (carpeta_privada() / documento.ruta).resolve()
    # Una `ruta` manipulada en la base no puede sacar un archivo de fuera.
    if carpeta_privada().resolve() not in ruta.parents:
        raise PermissionDenied("Ruta de documento no válida.")
    contenido = ruta.read_bytes()
    if hashlib.sha256(contenido).hexdigest() != documento.hash_sha256:
        raise ValidationError("El archivo en disco no coincide con el que se subió: está dañado.")
    _auditar(usuario, LogAuditoria.Accion.READ, documento)
    return contenido


def retirar_documento(usuario, documento: DocumentoAnexo) -> None:
    """
    Lo quita de la lista sin borrar el archivo: un documento de una historia
    clínica no se destruye, se retira y queda quién y cuándo.
    """
    from django.utils import timezone

    from apps.auditoria.models import LogAuditoria

    _exigir_servicio_propio(usuario, documento.servicio)
    documento.eliminado_en = timezone.now()
    documento.eliminado_por = usuario
    documento.save(update_fields=["eliminado_en", "eliminado_por", "actualizado_en"])
    _auditar(usuario, LogAuditoria.Accion.SOFT_DELETE, documento)


# ------------------------------------------------------------------ escaneo


MODOS_ESCANEO = {
    "documento": "Documento: grises, papel blanco y tinta negra. El más legible.",
    "color": "Color: niveles ajustados, conserva sellos y firmas en azul.",
    "original": "Original: las fotos tal cual.",
}


def niveles(gris, bajo: float = 0.02, alto: float = 0.96) -> tuple[int, int]:
    """
    Los niveles de negro y blanco de ESTA foto: percentiles del histograma.

    El realce de un contraste fijo deja oscura una foto oscura y quema los
    blancos de una con buena luz (lo cuenta clinube en realceDocumento.mjs).
    Una página casi uniforme —en blanco, o una foto movida— no se estira:
    amplificaría el ruido hasta dejar una mancha.
    """
    histograma = gris.histogram()
    total = sum(histograma)
    if not total:
        return 0, 255

    def buscar(fraccion):
        objetivo, acumulado = total * fraccion, 0
        for valor, cuenta in enumerate(histograma):
            acumulado += cuenta
            if acumulado >= objetivo:
                return valor
        return 255

    negro, blanco = buscar(bajo), buscar(alto)
    if blanco - negro < 24:
        return 0, 255
    return negro, blanco


def realzar(imagen, modo: str):
    """Una página escaneada, realzada según el modo. Devuelve una imagen de Pillow."""
    from PIL import ImageOps

    imagen = ImageOps.exif_transpose(imagen)  # la orientación con la que se tomó
    imagen = imagen.convert("RGB")
    imagen.thumbnail((LADO_MAXIMO, LADO_MAXIMO))
    if modo == "original":
        return imagen
    negro, blanco = niveles(imagen.convert("L"))
    escala = 255 / (blanco - negro)

    def estirar(v):
        return max(0, min(255, round((v - negro) * escala)))

    if modo == "documento":
        # Una curva suave aclara el gris del papel sin comerse los trazos finos
        # de un bolígrafo.
        tabla = [round(255 * (estirar(v) / 255) ** 0.85) for v in range(256)]
        return imagen.convert("L").point(tabla)
    return imagen.point([estirar(v) for v in range(256)] * 3)


def armar_pdf(imagenes: list[bytes], modo: str = "documento") -> bytes:
    """Varias fotos → un PDF, una página por foto."""
    from PIL import Image, UnidentifiedImageError

    if not imagenes:
        raise ValidationError("Elija al menos una foto.")
    if len(imagenes) > MAXIMO_PAGINAS:
        raise ValidationError(f"Como mucho {MAXIMO_PAGINAS} páginas por documento.")
    if modo not in MODOS_ESCANEO:
        modo = "documento"
    paginas = []
    for numero, datos in enumerate(imagenes, start=1):
        try:
            mime, _ = tipo_de(datos)
            if not mime.startswith("image/"):
                raise ValidationError("")
            paginas.append(realzar(Image.open(io.BytesIO(datos)), modo))
        except (ValidationError, UnidentifiedImageError, OSError) as exc:
            raise ValidationError(f"La foto {numero} no se pudo leer como imagen.") from exc
    salida = io.BytesIO()
    paginas[0].save(salida, "PDF", save_all=True, append_images=paginas[1:], resolution=150)
    return salida.getvalue()
