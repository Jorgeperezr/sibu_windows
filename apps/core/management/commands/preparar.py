"""
Deja la base lista para trabajar, con un solo comando.

Antes había que recordar y teclear cinco comandos en el orden correcto
—`migrate`, `seed_inicial`, `configurar_rbac`, `cargar_cie10`,
`createsuperuser`— y si uno se saltaba, el síntoma aparecía más tarde y en otro
sitio: sin `seed_inicial` no hay servicios y las bandejas salen vacías; sin
`configurar_rbac` los grupos existen sin permisos; sin una cuenta creada, la
pantalla de inicio de sesión rechaza todo lo que se escriba en ella.

    python manage.py preparar          # todo, con datos de demostración
    python manage.py preparar --sin-demo
    python manage.py preparar --si-cambio   # solo si hace falta (lo usa `make up`)

Es idempotente: cada paso que compone se puede repetir sin duplicar nada, así
que volver a ejecutarlo sobre una base ya preparada es seguro.

En producción (`DEBUG=False`) hace los cuatro primeros pasos —que son
exactamente el arranque correcto de un despliegue— y omite los datos de
demostración, igual que haría `datos_demo` por su cuenta.
"""

import hashlib
from pathlib import Path

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import DatabaseError, connection
from django.db.migrations.executor import MigrationExecutor
from django.db.migrations.loader import MigrationLoader


class Command(BaseCommand):
    help = "Migraciones, datos base, RBAC, catálogo CIE-10 y cuentas de prueba."

    def add_arguments(self, parser):
        parser.add_argument(
            "--sin-demo",
            action="store_true",
            dest="sin_demo",
            help="No sembrar usuarios ni pacientes de demostración.",
        )
        parser.add_argument(
            "--si-cambio",
            action="store_true",
            dest="si_cambio",
            help="Preparar solo si la base está vacía o la siembra cambió desde la última vez.",
        )

    def handle(self, *args, **opciones):
        detalle = opciones.get("verbosity", 1)

        if opciones.get("si_cambio") and not self._hace_falta(detalle):
            return

        pasos = [
            ("Aplicando migraciones", "migrate", {"interactive": False}),
            ("Cargando secciones, servicios y roles", "seed_inicial", {}),
            ("Configurando permisos por rol", "configurar_rbac", {}),
            ("Cargando el catálogo CIE-10", "cargar_cie10", {}),
        ]
        # Los datos de demostración traen contraseñas conocidas y pacientes
        # inventados: en un servidor real serían una puerta abierta con
        # historias clínicas falsas dentro del expediente único.
        sembrar_demo = not opciones["sin_demo"] and settings.DEBUG

        total = len(pasos) + (1 if sembrar_demo else 0)
        for numero, (titulo, comando, extra) in enumerate(pasos, start=1):
            if detalle:
                self.stdout.write(f"[{numero}/{total}] {titulo}...")
            call_command(comando, verbosity=detalle, **extra)

        if sembrar_demo:
            if detalle:
                self.stdout.write(f"[{total}/{total}] Sembrando datos de prueba...")
            # `datos_demo` termina imprimiendo las credenciales, que es lo único
            # de toda la preparación que hay que leer; por eso no se silencia
            # salvo que quien llama pida silencio explícitamente.
            call_command("datos_demo", verbosity=detalle)

        # Después de todos los pasos, no antes: si alguno revienta, la huella no
        # se anota y el siguiente arranque vuelve a intentarlo. Anotarla primero
        # dejaría una base a medio preparar marcada como al día.
        self._anotar_huella()

        if sembrar_demo or not detalle:
            return
        if opciones["sin_demo"]:
            self.stdout.write(self.style.SUCCESS("\nBase preparada, sin datos de demostración."))
        else:
            self.stdout.write(
                self.style.WARNING(
                    "\nBase preparada. Los datos de demostración se omiten con DEBUG=False."
                )
            )
        self.stdout.write(self._como_crear_cuenta())

    @staticmethod
    def _como_crear_cuenta() -> str:
        """
        El comando que de verdad hay que escribir AQUÍ.

        En una portable no es `createsuperuser`: es `portable/crear_cuenta.py`,
        que pide cédula y nombres —`createsuperuser` no los pide y deja la
        cuenta sin ficha de persona—. Decir el otro dejaba dos instrucciones
        contradictorias seguidas en la misma pantalla, y la primera era la mala.
        """
        from django.conf import settings

        if getattr(settings, "SIBU_PORTABLE", False):
            # En la portable, el navegador se abre solo en «primera cuenta».
            return "Al abrir SIBU, el navegador le pedirá crear la primera cuenta."
        return "Cree una cuenta con: python manage.py createsuperuser"

    # ------------------------------------------------------------------
    # Detección de cambios en la siembra
    # ------------------------------------------------------------------
    # Archivos que DEFINEN qué se siembra. Si cambia alguno, lo que hay en la
    # base quedó viejo: cuentas con otro nombre, un servicio nuevo sin permisos,
    # un código CIE-10 que no está.
    ARCHIVOS_DE_SIEMBRA = (
        "apps/core/management/commands/datos_demo.py",
        "apps/core/management/commands/seed_inicial.py",
        "apps/core/management/commands/cargar_cie10.py",
        "apps/usuarios/management/commands/configurar_rbac.py",
    )
    CLAVE_HUELLA = "huella_de_siembra"

    def _huella(self) -> str:
        """
        Resumen del contenido de los archivos que definen la siembra.

        Del contenido y no de la fecha: `git pull` reescribe fechas aunque el
        contenido sea el mismo, y eso volvería a sembrar en cada arranque.
        """
        h = hashlib.sha256()
        for relativo in self.ARCHIVOS_DE_SIEMBRA:
            ruta = Path(settings.BASE_DIR) / relativo
            h.update(ruta.read_bytes() if ruta.exists() else b"")
        return h.hexdigest()

    def _hace_falta(self, detalle: int) -> bool:
        """
        ¿Hay que preparar? Sí si la base está vacía o si la siembra cambió.

        Es lo que quita el paso manual: tras un `git pull` que trae cuentas
        nuevas, `make up` lo nota solo. Antes había que acordarse de `make demo`,
        y no acordarse se parecía a «las credenciales no funcionan».
        """
        from apps.core.models import ParametroSistema, Servicio
        from apps.usuarios.models import Usuario

        # Una base recién creada no tiene ni tablas: preguntar por Servicio
        # revienta con ProgrammingError. Eso no es un fallo, es exactamente el
        # caso «hay que preparar», y es el primer arranque de cualquiera.
        try:
            vacia = not (Servicio.objects.exists() and Usuario.objects.exists())
            anterior = (
                ParametroSistema.objects.filter(clave=self.CLAVE_HUELLA)
                .values_list("valor", flat=True)
                .first()
            )
        except DatabaseError:
            # Postgres deja la conexión en estado abortado tras un error; sin
            # cerrarla, `migrate` fallaría a continuación por arrastre.
            connection.close()
            if detalle:
                self.stdout.write("Base sin migrar: preparándola desde cero...")
            return True

        if vacia:
            if detalle:
                self.stdout.write("Base sin preparar: creando estructura, permisos y cuentas...")
            return True

        if self._hay_migraciones_pendientes():
            if detalle:
                self.stdout.write("Hay migraciones sin aplicar: poniendo la base al día...")
            return True

        if (anterior or {}).get("sha256") == self._huella():
            if detalle:
                self.stdout.write("Base al día; no hace falta volver a sembrar.")
            return False

        if detalle:
            self.stdout.write(
                self.style.WARNING("La siembra cambió desde la última vez: actualizando...")
            )
        return True

    def _hay_migraciones_pendientes(self) -> bool:
        """
        Una migración nueva no cambia la huella de siembra, pero sí obliga a
        preparar: sin ella la tabla nueva no existe y la pantalla que la usa
        revienta. Antes esto lo miraba el script de arranque; vivir aquí
        mantiene la decisión en un solo sitio.
        """
        objetivo = MigrationExecutor(connection).migration_plan(
            MigrationLoader(connection).graph.leaf_nodes()
        )
        return bool(objetivo)

    def _anotar_huella(self):
        """Deja constancia de con qué versión de la siembra quedó esta base."""
        from apps.core.models import ParametroSistema

        ParametroSistema.objects.update_or_create(
            clave=self.CLAVE_HUELLA,
            defaults={
                "valor": {"sha256": self._huella()},
                "descripcion": "Contenido de los comandos de siembra usados al preparar la base.",
            },
        )
