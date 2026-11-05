"""
Señales de usuarios.

`servicios_del_usuario` recuerda los servicios de un perfil para no
preguntarlos seis veces por página. Cuando cambian, lo recordado se descarta:
una asignación tiene que verse en el acto.
"""

from django.db.models.signals import m2m_changed
from django.dispatch import receiver

from .models import PerfilProfesional
from .rbac import olvidar_servicios


@receiver(m2m_changed, sender=PerfilProfesional.servicios.through)
def servicios_cambiados(sender, instance, action, reverse, **kwargs):
    if not action.startswith("post_"):
        return
    if reverse:
        # Se tocó desde el lado del servicio (`servicio.profesionales.add(...)`):
        # `instance` es el servicio. Los perfiles afectados vienen en pk_set,
        # pero sus objetos en memoria no son alcanzables desde aquí; ninguna
        # pantalla asigna por ese lado, y la próxima petición lee de nuevo.
        return
    olvidar_servicios(instance)
