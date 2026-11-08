"""
El ingreso: con el correo o con la cuenta, y con el bloqueo que hace
aceptable una clave corta.

Tres piezas:

- `IngresoPorCorreoOCuenta`: el método de autenticación. Admite el nombre de
  la cuenta (la cédula, en las cuentas de siempre) o el correo, sin distinguir
  mayúsculas. Si dos cuentas comparten correo no entra ninguna por correo:
  adivinar cuál es la buena sería abrir la ajena.
- El bloqueo de la cuenta. axes ya cierra 15 minutos al EQUIPO tras 5 fallos;
  eso solo, con un PIN de 4 dígitos, deja probar las 10 000 combinaciones en
  unas semanas cambiando de equipo o esperando. Tras `SIBU_BLOQUEO_CUENTA`
  fallos seguidos (10) la CUENTA queda cerrada, venga de donde venga el
  intento, hasta que Administración General la abra.
- `FormularioIngreso`: dice que la cuenta está bloqueada y qué hacer, en vez
  del «usuario o contraseña incorrectos» que haría creer al dueño que olvidó su
  clave.

En la portable, desde el propio computador servidor, el bloqueo de la cuenta
no aplica: si la única cuenta de Administración queda bloqueada, nadie podría
abrirla, y quien está sentado en ese equipo ya tiene el archivo de la base en
el disco. El bloqueo de axes —15 minutos tras 5 fallos— sigue valiendo ahí.
"""

from __future__ import annotations

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import F
from django.dispatch import receiver
from django.utils import timezone

RUTA_METODO = "apps.usuarios.ingreso.IngresoPorCorreoOCuenta"


def limite_bloqueo() -> int:
    return int(getattr(settings, "SIBU_BLOQUEO_CUENTA", 10))


def buscar_cuenta(identificador: str):
    """La cuenta que corresponde a lo escrito en «correo o usuario», o None."""
    Usuario = get_user_model()
    texto = (identificador or "").strip()
    if not texto:
        return None
    cuenta = Usuario.objects.filter(username__iexact=texto).first()
    if cuenta is not None:
        return cuenta
    if "@" in texto:
        por_correo = list(Usuario.objects.filter(email__iexact=texto)[:2])
        if len(por_correo) == 1:
            return por_correo[0]
    return None


def desde_el_propio_servidor(request) -> bool:
    return bool(
        request is not None
        and getattr(settings, "SIBU_PORTABLE", False)
        and request.META.get("REMOTE_ADDR") in {"127.0.0.1", "::1"}
    )


class IngresoPorCorreoOCuenta(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        Usuario = get_user_model()
        if username is None:
            username = kwargs.get(Usuario.USERNAME_FIELD)
        if not username or password is None:
            return None
        cuenta = buscar_cuenta(username)
        if cuenta is None:
            # El mismo trabajo que con una cuenta que existe: sin esto, lo que
            # tarda la respuesta diría qué correos tienen cuenta.
            Usuario().set_password(password)
            return None
        if cuenta.bloqueada_desde and not desde_el_propio_servidor(request):
            # PermissionDenied y no None: detiene la cadena de métodos, así
            # que ninguno otro puede dejar entrar a una cuenta cerrada.
            raise PermissionDenied("Cuenta bloqueada por intentos fallidos.")
        if cuenta.check_password(password) and self.user_can_authenticate(cuenta):
            return cuenta
        return None


@receiver(user_login_failed)
def contar_fallo(sender, credentials, request=None, **kwargs):
    Usuario = get_user_model()
    cuenta = buscar_cuenta(credentials.get("username", ""))
    if cuenta is None or cuenta.bloqueada_desde:
        return
    Usuario.objects.filter(pk=cuenta.pk).update(intentos_fallidos=F("intentos_fallidos") + 1)
    cuenta.refresh_from_db(fields=["intentos_fallidos"])
    if cuenta.intentos_fallidos >= limite_bloqueo():
        Usuario.objects.filter(pk=cuenta.pk, bloqueada_desde__isnull=True).update(
            bloqueada_desde=timezone.now()
        )
        from apps.auditoria.models import LogAuditoria

        LogAuditoria.objects.create(
            usuario=None,
            accion=LogAuditoria.Accion.UPDATE,
            modulo="usuarios",
            entidad="Usuario",
            entidad_id=str(cuenta.pk),
            ip=(request.META.get("REMOTE_ADDR") if request is not None else None),
            detalle={
                "cuenta": cuenta.username,
                "evento": "bloqueo_por_intentos",
                "intentos": cuenta.intentos_fallidos,
            },
        )


@receiver(user_logged_in)
def marcar_renovacion(sender, user, request=None, **kwargs):
    """La sesión recién creada ya está al día: la primera página no la reescribe."""
    import time

    if request is not None and hasattr(request, "session"):
        request.session["_renovada"] = int(time.time())


@receiver(user_logged_in)
def reiniciar_fallos(sender, user, request=None, **kwargs):
    if getattr(user, "intentos_fallidos", 0) or getattr(user, "bloqueada_desde", None):
        get_user_model().objects.filter(pk=user.pk).update(
            intentos_fallidos=0, bloqueada_desde=None
        )


def desbloquear(cuenta, *, por) -> None:
    """Administración General abre una cuenta bloqueada. Queda escrito quién."""
    from apps.auditoria.models import LogAuditoria

    get_user_model().objects.filter(pk=cuenta.pk).update(intentos_fallidos=0, bloqueada_desde=None)
    LogAuditoria.objects.create(
        usuario=por,
        rol_activo=getattr(por, "rol_principal", "") if por else "",
        accion=LogAuditoria.Accion.UPDATE,
        modulo="usuarios",
        entidad="Usuario",
        entidad_id=str(cuenta.pk),
        detalle={"cuenta": cuenta.username, "evento": "desbloqueo"},
    )


class FormularioIngreso(AuthenticationForm):
    error_messages = {
        **AuthenticationForm.error_messages,
        "invalid_login": "Correo, usuario o clave incorrectos. Verifique e intente de nuevo.",
        "bloqueada": (
            "Esta cuenta quedó bloqueada tras varios intentos fallidos. Pida a "
            "Administración General que la desbloquee desde «Perfiles»."
        ),
    }

    def __init__(self, request=None, *args, **kwargs):
        super().__init__(request, *args, **kwargs)
        self.fields["username"].label = "Correo o usuario"
        self.bloqueada = False

    def clean(self):
        try:
            return super().clean()
        except ValidationError:
            cuenta = buscar_cuenta(self.cleaned_data.get("username", ""))
            if (
                cuenta is not None
                and cuenta.bloqueada_desde
                and not desde_el_propio_servidor(self.request)
            ):
                self.bloqueada = True
                raise ValidationError(self.error_messages["bloqueada"], code="bloqueada") from None
            raise
