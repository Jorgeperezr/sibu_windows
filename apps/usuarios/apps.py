from django.apps import AppConfig


class UsuariosConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.usuarios"
    verbose_name = "Usuarios y roles"

    def ready(self):
        from . import ingreso, signals  # noqa: F401  (registra los receptores)
