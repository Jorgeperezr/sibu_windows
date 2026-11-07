"""
Ajustes del modo PORTABLE: SIBU corriendo desde una carpeta, sin instalar.

El profesional copia la carpeta a su computador —o la lleva en una memoria—,
pulsa el icono y se abre el navegador en la pantalla de credenciales. No hay
PostgreSQL que instalar, ni nginx, ni servicio que registrar: todo vive dentro
de la carpeta y se va con ella.

Qué cambia respecto de producción, y por qué:

- **La base es SQLite, dentro de la carpeta.** Es lo único que viaja sin
  instalación. Tiene una consecuencia que conviene saber y que está escrita en
  `docs/PORTABLE.md`: en SQLite `select_for_update()` NO bloquea —el backend de
  Django declara `has_select_for_update = False`—, así que las protecciones de
  concurrencia de farmacia y de la ficha socioeconómica quedan sin efecto. Con
  un profesional trabajando en su propia carpeta eso da igual, porque no hay
  dos escrituras a la vez. Compartir el mismo archivo entre varios por una
  carpeta de red NO es una opción: SQLite sobre red se corrompe, y ahí sí
  habría dos escrituras a la vez.

- **Escucha solo en el propio computador.** `ALLOWED_HOSTS` se queda en
  127.0.0.1. Una portable no es un servidor: si hay que compartir datos, se
  hace contra la instancia central, no abriendo el puerto de la portátil.

- **La clave se genera y se guarda la primera vez.** Regenerarla en cada
  arranque invalidaría la sesión abierta en cada arranque, que es otra forma
  del mismo error.

- **Sin Celery ni Redis.** Los recordatorios de cita se ejecutan en el momento
  o no se ejecutan; una portable no tiene un demonio detrás.
"""

import os
from pathlib import Path

from .base import *  # noqa
from .base import BASE_DIR, env  # explícito: evita la ambigüedad del star-import

# ---------------------------------------------------------------- la carpeta
#
# Todo lo que el sistema escribe vive junto al código, no en el perfil del
# usuario ni en /var: es lo que hace que la carpeta se pueda copiar entera a
# otro computador —o a una memoria— y siga siendo la misma instalación.

CARPETA_DATOS = Path(env("SIBU_DATOS", default=str(Path(BASE_DIR) / "datos")))
CARPETA_DATOS.mkdir(parents=True, exist_ok=True)

DEBUG = False

# Una portable lleva DEBUG=False y NO es un servidor de producción: es una
# carpeta en el computador de un profesional. Sin este indicador,
# `check --deploy` llamaba errores a las tres cosas que aquí son correctas —la
# base en SQLite, `ALLOWED_HOSTS` solo con localhost y `MEDIA_ROOT` dentro de
# la carpeta—, y un check que grita donde no hay problema deja de leerse donde
# sí lo hay.
SIBU_PORTABLE = True

# Solo el propio computador. El launcher abre el navegador en 127.0.0.1.
ALLOWED_HOSTS = [
    "127.0.0.1",
    "localhost",
    # En MODO SERVIDOR —un computador de la oficina atiende a los demás por la
    # WiFi— el launcher añade aquí el nombre del equipo y sus direcciones de
    # red. Sin él, la lista se queda en el propio computador.
    *env.list("SIBU_HOSTS", default=[]),
]
CSRF_TRUSTED_ORIGINS = [
    "http://127.0.0.1",
    "http://localhost",
    # El puerto lo elige el launcher al arrancar —uno libre— y lo añade aquí
    # por entorno. Sin esto, el primer formulario respondería 403 y el sistema
    # quedaría en pie con todo el mundo fuera, que es el fallo más caro que ya
    # conocemos.
    *env.list("SIBU_ORIGENES", default=[]),
]


def _clave_persistente(carpeta: Path) -> str:
    """
    La clave de esta instalación, generada una vez y guardada en la carpeta.

    No se puede fijar en el código —sería la misma en todas las copias— ni
    regenerarse en cada arranque, porque eso cierra la sesión cada vez que se
    abre el programa.
    """
    archivo = carpeta / "clave.txt"
    if archivo.exists():
        return archivo.read_text(encoding="utf-8").strip()

    import secrets

    clave = secrets.token_urlsafe(64)
    archivo.write_text(clave, encoding="utf-8")
    try:
        archivo.chmod(0o600)
    except OSError:
        # En Windows sobre FAT32 —una memoria USB— no hay permisos POSIX. No es
        # motivo para no arrancar; sí lo es para decirlo en la documentación.
        pass
    return clave


SECRET_KEY = env("SECRET_KEY", default="") or _clave_persistente(CARPETA_DATOS)

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": str(CARPETA_DATOS / "sibu.sqlite3"),
        # Cada petición es una transacción, como en el servidor. `base.py` lo
        # activa, pero este bloque redefine DATABASES entero y lo PERDÍA: la
        # portable era el único entorno donde una pantalla que escribe dos
        # registros y falla entre medias dejaba la mitad guardada. Las pruebas
        # corren contra PostgreSQL con los ajustes de base, así que no podían
        # verlo. El código está escrito contando con esto.
        "ATOMIC_REQUESTS": True,
        "OPTIONS": {
            # WAL y un tiempo de espera: con una sola persona escribiendo no
            # hacen falta, pero el navegador abre varias peticiones a la vez
            # (la página y sus estáticos) y sin esto salta «database is locked»
            # en mitad de un guardado.
            #
            # cache_size negativo son KiB: 20 MB de páginas en memoria en vez
            # de los 2 MB por omisión, que con un expediente entero se quedaban
            # cortos. temp_store en memoria para los ORDER BY y los DISTINCT
            # del informe, que si no escriben archivos temporales en el disco
            # —una memoria USB, a veces—.
            "init_command": (
                "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; "
                "PRAGMA cache_size=-20000; PRAGMA temp_store=MEMORY;"
            ),
            "timeout": 20,
        },
    }
}

MEDIA_ROOT = str(CARPETA_DATOS / "media")
SIBU_DOCUMENTOS_ROOT = str(CARPETA_DATOS / "documentos")
STATIC_ROOT = str(Path(BASE_DIR) / "staticfiles")

# WhiteNoise sirve los estáticos: no hay nginx en una portable.
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
}
MIDDLEWARE.insert(1, "whitenoise.middleware.WhiteNoiseMiddleware")  # noqa: F405

# Sin HTTPS: esto es http://127.0.0.1, dentro del propio computador. Exigir
# cookies seguras aquí impediría iniciar sesión.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False

# Sin demonio detrás: lo que se encole se ejecuta en el acto o no se ejecuta.
CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

# Correo: lo normal en una portable es no tener SMTP. Se escribe en un archivo
# dentro de la carpeta en vez de fallar, para que el aviso quede registrado y
# se pueda reenviar a mano.
EMAIL_BACKEND = "django.core.mail.backends.filebased.EmailBackend"
EMAIL_FILE_PATH = str(CARPETA_DATOS / "correo")
os.makedirs(EMAIL_FILE_PATH, exist_ok=True)

# El registro va también a la carpeta: en una portable no hay journalctl donde
# mirar después, y una excepción que solo salió en la consola se pierde al
# cerrar la ventana.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {"detallado": {"format": "{asctime} {levelname} {name} {message}", "style": "{"}},
    "handlers": {
        "consola": {"class": "logging.StreamHandler", "formatter": "detallado"},
        "archivo": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": str(CARPETA_DATOS / "sibu.log"),
            "maxBytes": 5 * 1024 * 1024,
            "backupCount": 3,
            "formatter": "detallado",
        },
    },
    "root": {"handlers": ["consola", "archivo"], "level": "INFO"},
}
