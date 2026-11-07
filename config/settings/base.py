"""
Configuración base de SIBU - Sistema Integral de Bienestar Universitario (UNL).
Ajustes compartidos por todos los ambientes. Ver dev.py y prod.py.
"""

from pathlib import Path

import environ
from django.contrib.messages import constants as niveles_mensaje

BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
)
environ.Env.read_env(BASE_DIR / ".env")

SECRET_KEY = env("SECRET_KEY", default="dev-insecure-change-me")
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")

# ---------------------------------------------------------------------------
# Aplicaciones
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    "rest_framework",
    "rest_framework_simplejwt",
    "django_filters",
    "drf_spectacular",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "axes",
    "guardian",
    "simple_history",
    "django_celery_beat",
]

# Apps del proyecto. El orden respeta dependencias: core y usuarios primero.
LOCAL_APPS = [
    "apps.core",
    "apps.usuarios",
    "apps.academico",
    "apps.expediente",
    "apps.citas",
    "apps.medicina",
    "apps.enfermeria",
    "apps.odontologia",
    "apps.laboratorio",
    "apps.farmacia",
    "apps.psicologia",
    "apps.psicopedagogia",
    "apps.trabajo_social",
    "apps.becas",
    "apps.derivaciones",
    "apps.documentos",
    "apps.notificaciones",
    "apps.firma",
    "apps.auditoria",
    "apps.reportes",
    "apps.talleres",
    "apps.portal",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "simple_history.middleware.HistoryRequestMiddleware",
    "apps.auditoria.middleware.AuditoriaMiddleware",
    # Después de la auditoría a propósito: el desvío por clave temporal también
    # se registra, que es lo que permite ver si alguien intentó trabajar con la
    # clave que le tecleó otro.
    "apps.usuarios.middleware.ExigirCambioDeClave",
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.core.navegacion.navegacion",
                "apps.core.navegacion.entorno",
                "apps.core.navegacion.confidenciales",
                "apps.notificaciones.context.notificaciones",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Base de datos
# ---------------------------------------------------------------------------
DATABASES = {"default": env.db("DATABASE_URL", default="postgres://sibu:sibu@localhost:5432/sibu")}
DATABASES["default"]["ATOMIC_REQUESTS"] = True

# ---------------------------------------------------------------------------
# Autenticación
# ---------------------------------------------------------------------------
AUTH_USER_MODEL = "usuarios.Usuario"

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
    "guardian.backends.ObjectPermissionBackend",
]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
        "OPTIONS": {"min_length": 12},
    },
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "login"
LOGIN_REDIRECT_URL = "inicio"
LOGOUT_REDIRECT_URL = "login"

# Django etiqueta los errores como "error"; Bootstrap solo define
# `alert-danger`. Sin esta traducción, `alert-{{ m.tags }}` producía
# `alert-error`, una clase que no existe: el aviso de error salía sin color,
# indistinguible de uno informativo.
MESSAGE_TAGS = {niveles_mensaje.ERROR: "danger"}

# ---------------------------------------------------------------------------
# Internacionalización (UNL - Ecuador)
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "es-ec"
TIME_ZONE = "America/Guayaquil"
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Archivos estáticos y media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATICFILES_DIRS = [BASE_DIR / "static"]
MEDIA_URL = "media/"
MEDIA_ROOT = env("MEDIA_ROOT", default=str(BASE_DIR / "media"))
# Los documentos del expediente, FUERA de MEDIA_ROOT: `/media/` se sirve sin
# comprobar quién pide, y un informe de Psicología no puede estar a una URL de
# distancia. Salen solo por `documentos:archivo`, que mira el acceso.
SIBU_DOCUMENTOS_ROOT = env("SIBU_DOCUMENTOS_ROOT", default=str(BASE_DIR / "privado"))
# Dictado por voz en las consultas. El reconocimiento lo hace el navegador y
# Chrome/Edge envían el audio a Google/Microsoft: quien no pueda aceptarlo lo
# apaga aquí y el botón desaparece de todas las pantallas.
SIBU_DICTADO = env.bool("SIBU_DICTADO", default=True)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": (
        "rest_framework_simplejwt.authentication.JWTAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.AnonRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {"user": "1000/hour", "anon": "50/hour"},
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 25,
}

SPECTACULAR_SETTINGS = {
    "TITLE": "SIBU API",
    "DESCRIPTION": "API del Sistema Integral de Bienestar Universitario - UNL",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
}

# ---------------------------------------------------------------------------
# Celery
# ---------------------------------------------------------------------------
CELERY_BROKER_URL = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_RESULT_BACKEND = env("REDIS_URL", default="redis://localhost:6379/0")
CELERY_TIMEZONE = TIME_ZONE
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

# ---------------------------------------------------------------------------
# django-axes (bloqueo de intentos de acceso)
# ---------------------------------------------------------------------------
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 0.25  # 15 minutos
AXES_RESET_ON_SUCCESS = True
# La pantalla de bloqueo, en español y dentro de la línea gráfica. La de axes
# sale en inglés y no dice cuánto hay que esperar; en una portable, donde no
# hay administrador a quien llamar, eso se lee como «el sistema se rompió».
AXES_LOCKOUT_CALLABLE = "apps.core.bloqueo.vista_bloqueado"

# ---------------------------------------------------------------------------
# Parámetros de negocio SIBU
# ---------------------------------------------------------------------------
SIBU = {
    "DOMINIO_CORREO_INSTITUCIONAL": env("DOMINIO_CORREO", default="unl.edu.ec"),
    "RECETA_VALIDEZ_HORAS": 72,
    "CITA_RECORDATORIOS_HORAS": [48, 24],
    "CARGA_VARIACION_UMBRAL": 0.20,  # alerta si el padrón varía > 20 % entre períodos
    "GDRIVE_CARPETA_RAIZ": "SIBU/Talleres",
    # Servicios de la Sección Salud habilitados para registrar talleres:
    "TALLERES_SALUD_HABILITADO": env.bool("TALLERES_SALUD_HABILITADO", default=False),
    # Cuenta de servicio para volcar el historial de atenciones a una hoja de
    # Google. Vacío por defecto: sin ella la pantalla lo dice y ofrece el CSV,
    # que trae las mismas filas. La hoja debe estar compartida con el correo de
    # esa cuenta CON PERMISO DE EDITOR.
    "GOOGLE_CREDENCIALES_JSON": env("GOOGLE_CREDENCIALES_JSON", default=""),
}

# Cifrado a nivel de campo (datos sensibles). Clave separada de SECRET_KEY.
FIELD_ENCRYPTION_KEY = env("FIELD_ENCRYPTION_KEY", default="")

# Almacén de evidencias de talleres. Google Drive es una implementación, no un
# supuesto: mientras el OAuth del Workspace institucional no exista, el módulo
# funciona con el almacén local. Ver apps/talleres/providers.py.
#   "local"  (por defecto) | "gdrive"
TALLERES_ALMACEN = env("TALLERES_ALMACEN", default="local")

# Integración Google Workspace
GOOGLE_OAUTH = {
    "CLIENT_SECRETS_FILE": env("GOOGLE_CLIENT_SECRETS", default=""),
    "SCOPES": ["https://www.googleapis.com/auth/drive.file"],
    "SHARED_DRIVE_ID": env("GOOGLE_SHARED_DRIVE_ID", default=""),
}


# ---------------------------------------------------------------------------
# Firma electrónica — proveedor
# ---------------------------------------------------------------------------
# La firma es una pieza intercambiable, no un supuesto del sistema.
#   "local" (por defecto): SIBU genera el PDF, el profesional lo descarga y lo
#       firma en su computador. Puede volver a subirlo o quedárselo.
#   "deshabilitada": SIBU funciona sin firmar en absoluto.
#   "firmaec": FirmaEC del MINTEL. Requiere el registro de SIBU ante el MINTEL.
# Ver apps/firma/providers.py.
FIRMA_PROVIDER = env("FIRMA_PROVIDER", default="local")

# ---------------------------------------------------------------------------
# FirmaEC (MINTEL) — parámetros del proveedor "firmaec"
# ---------------------------------------------------------------------------
# SIBU no hace criptografía: genera el PDF, pide un token al servicio FirmaEC y
# el usuario firma con la aplicación de escritorio instalada en su equipo. Ni la
# clave privada ni la contraseña del .p12 llegan nunca al servidor.
#
# Referencia: Manual de Implementación Institucional FirmaEC Descentralizada
# 2.1.0 (MINTEL). Requiere autorización del MINTEL y un Administrador
# Institucional de FirmaEC (AIF) delegado por la máxima autoridad.

# URL del proyecto `firmadigital-servicio`. Preproducción del MINTEL:
# https://impws.firmadigital.gob.ec/servicio
FIRMAEC_SERVICIO_URL = env("FIRMAEC_SERVICIO_URL", default="")

# Nombre del sistema requirente registrado ante FirmaEC (viaja en firmaec://).
FIRMAEC_SISTEMA = env("FIRMAEC_SISTEMA", default="")

# API Key que SIBU presenta AL llamar a FirmaEC.
FIRMAEC_API_KEY = env("FIRMAEC_API_KEY", default="")

# API Key que FirmaEC presenta al devolver el documento firmado. Es distinta de
# la anterior y protege un endpoint sin sesión: tratarla como un secreto.
FIRMAEC_CALLBACK_API_KEY = env("FIRMAEC_CALLBACK_API_KEY", default="")

FIRMAEC_RAZON = env("FIRMAEC_RAZON", default="Firma de responsabilidad")
FIRMAEC_PREPRODUCCION = env.bool("FIRMAEC_PREPRODUCCION", default=True)

# Firmar implica que el PDF SALE de SIBU hacia el servicio FirmaEC. Poner esto
# en True afirma que ese servicio corre en infraestructura de la propia UNL
# (despliegue descentralizado). Solo entonces se permite firmar contenido de
# servicios confidenciales como Psicología. Ver apps/firma/policy.py.
FIRMAEC_DESCENTRALIZADO_PROPIO = env.bool("FIRMAEC_DESCENTRALIZADO_PROPIO", default=False)
