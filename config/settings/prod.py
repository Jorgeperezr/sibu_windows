"""
Ajustes de producción.

Las comprobaciones de que esto esté bien puesto viven en apps/core/checks.py y
corren con `manage.py check --deploy`. Este archivo define; aquel verifica.
"""

from pathlib import Path

from .base import *  # noqa: F403
from .base import BASE_DIR, MIDDLEWARE, env  # explícito: evita ambigüedad del star-import

DEBUG = False

# ALLOWED_HOSTS y CSRF_TRUSTED_ORIGINS son obligatorios: sin ellos Django
# rechaza peticiones o falla los POST detrás del proxy, y el fallo aparece
# tarde, en forma de "CSRF verification failed" en un formulario que
# funcionaba en local.
# Sin valor por defecto, la ausencia de una variable aborta la importación
# de los ajustes y `check --deploy` no llega a ejecutarse: la configuración
# que falta se descubriría de una en una. Con el defecto vacío, los checks
# informan de todo junto (sibu.E003/E004/E020) en una sola pasada.
ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=[])
CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", default=[])

# --- HTTPS / cabeceras de seguridad ---
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_REFERRER_POLICY = "same-origin"
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
# El CSRF se envía por formulario ({% csrf_token %}), nunca leído por JS: se
# puede ocultar a scripts. El polling del panel de firma solo hace GET.
CSRF_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_EXPIRE_AT_BROWSER_CLOSE = True
SESSION_COOKIE_AGE = 60 * 15  # 15 min de inactividad en estaciones clínicas
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# --- Límites de entrada ---
# Talleres y firma aceptan archivos. Sin techo, una subida grande agota la
# memoria del proceso; sin límite de campos, un POST con miles de claves
# consume CPU antes de llegar a ninguna vista.
DATA_UPLOAD_MAX_MEMORY_SIZE = 16 * 1024 * 1024  # 16 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 5 * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FIELDS = 1000

# --- Base de datos ---
# Conexiones persistentes: abrir una por petición contra PostgreSQL es caro.
DATABASES["default"]["CONN_MAX_AGE"] = env.int("DB_CONN_MAX_AGE", default=60)  # noqa: F405
# Con conexiones reutilizadas, una que murió —PostgreSQL reiniciado, la red
# privada caída un momento— se descubría al usarla: la primera petición después
# respondía 500. Con esto Django la comprueba antes y abre otra.
DATABASES["default"]["CONN_HEALTH_CHECKS"] = True  # noqa: F405
DATABASES["default"].setdefault("OPTIONS", {})  # noqa: F405
if env("DB_SSLMODE", default=""):
    DATABASES["default"]["OPTIONS"]["sslmode"] = env("DB_SSLMODE")  # noqa: F405

# --- Content Security Policy (django-csp) ---
MIDDLEWARE.insert(1, "csp.middleware.CSPMiddleware")
CSP_DEFAULT_SRC = ("'self'",)
CSP_STYLE_SRC = ("'self'", "https://cdn.jsdelivr.net")
CSP_SCRIPT_SRC = ("'self'", "https://cdn.jsdelivr.net")
CSP_IMG_SRC = ("'self'", "data:")
CSP_FRAME_ANCESTORS = ("'none'",)
CSP_FORM_ACTION = ("'self'",)
# El botón de firma abre un enlace firmaec://, que el navegador entrega al
# sistema operativo. Sin esto la CSP lo bloquearía y el firmador no abriría.
CSP_DEFAULT_SRC += ("firmaec:",)

# --- Archivos estáticos servidos por WhiteNoise ---
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")

# --- Correo institucional (SMTP UNL / Google Workspace) ---
# El portal depende de esto: sin SMTP nadie puede vincular su cuenta.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
# Mismo motivo: que falte el SMTP lo reporta el check sibu.W040/E041,
# no una excepción al arrancar.
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = True
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="bienestar@unl.edu.ec")
SERVER_EMAIL = DEFAULT_FROM_EMAIL

# --- Registro ---
# Sin logging explícito, los errores de producción no van a ninguna parte.
# `sibu.auditoria` se separa porque su retención es distinta: es evidencia.
# El handler de archivo falla al arrancar si el directorio no existe, y el
# error aparece como un ValueError críptico durante django.setup(): la
# aplicación no llega ni a levantar. Se crea aquí.
_LOG_FILE = Path(env("LOG_FILE", default=str(BASE_DIR / "logs" / "sibu.log")))
_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "detallado": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        }
    },
    "handlers": {
        "consola": {"class": "logging.StreamHandler", "formatter": "detallado"},
        "archivo": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(_LOG_FILE),
            "maxBytes": 10 * 1024 * 1024,
            "backupCount": 10,
            "formatter": "detallado",
        },
    },
    "root": {"handlers": ["consola", "archivo"], "level": "INFO"},
    "loggers": {
        "django.security": {"handlers": ["consola", "archivo"], "level": "WARNING"},
        # Los rechazos de firma y las vinculaciones sospechosas pasan por aquí.
        "apps.firma": {"handlers": ["consola", "archivo"], "level": "INFO"},
        "apps.portal": {"handlers": ["consola", "archivo"], "level": "INFO"},
    },
}

ADMINS = [("Soporte SIBU", env("ADMIN_EMAIL", default="soporte@unl.edu.ec"))]

# --- Observabilidad (opcional) ---
# Import guardado: si sentry-sdk no está instalado, la aplicación arranca igual.
# Antes se importaba a nivel de módulo y su ausencia impedía el arranque.
if env("SENTRY_DSN", default=""):
    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration

        sentry_sdk.init(
            dsn=env("SENTRY_DSN"),
            integrations=[DjangoIntegration()],
            traces_sample_rate=env.float("SENTRY_TRACES_SAMPLE_RATE", default=0.1),
            # Nunca enviar datos personales a un tercero: este sistema maneja
            # historias clínicas.
            send_default_pii=False,
        )
    except ImportError:  # pragma: no cover
        import logging

        logging.getLogger(__name__).warning(
            "SENTRY_DSN definido pero sentry-sdk no está instalado; se continúa sin Sentry."
        )
