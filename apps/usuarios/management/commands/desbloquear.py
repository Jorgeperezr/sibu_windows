"""
Abrir una cuenta bloqueada por intentos fallidos, desde la consola.

Lo normal es hacerlo desde «Perfiles», con otra cuenta de Administración
General. Esto es para cuando la bloqueada es la única que podía hacerlo, en el
servidor de la Unidad (en la portable basta entrar desde el propio equipo):

    python manage.py desbloquear 1100000007
    python manage.py desbloquear ana.perez@unl.edu.ec
"""

from django.core.management.base import BaseCommand, CommandError

from apps.usuarios.ingreso import buscar_cuenta, desbloquear


class Command(BaseCommand):
    help = "Desbloquea una cuenta cerrada por intentos fallidos."

    def add_arguments(self, parser):
        parser.add_argument("cuenta", help="Cédula, nombre de cuenta o correo.")

    def handle(self, *args, **opciones):
        cuenta = buscar_cuenta(opciones["cuenta"])
        if cuenta is None:
            raise CommandError(f"No hay ninguna cuenta «{opciones['cuenta']}».")
        if not cuenta.bloqueada_desde:
            self.stdout.write(f"{cuenta.username} no estaba bloqueada.")
            return
        desbloquear(cuenta, por=None)
        self.stdout.write(self.style.SUCCESS(f"{cuenta.username} desbloqueada."))
