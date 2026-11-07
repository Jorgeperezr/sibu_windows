"""
`{% dictado "<codigo de servicio>" %}`: el panel del dictado por voz.

El audio del dictado sale del equipo hacia el servicio de voz del navegador
(Google, Microsoft o Apple). Por eso el panel se NIEGA, aunque una plantilla
lo pida:

- en los servicios confidenciales (Psicología): el sello es absoluto y una
  sesión dictada sería contenido clínico entregado a un tercero;
- en Trabajo Social: la ficha socioeconómica del hogar orienta una beca;
- cuando `SIBU_DICTADO` está apagado.

La negativa vive aquí y no en cada plantilla para que copiar el panel a una
pantalla nueva no baste para abrir la rendija.
"""

from __future__ import annotations

from django import template
from django.conf import settings

from apps.usuarios.rbac import SERVICIOS_CONFIDENCIALES

registro = template.Library()
register = registro  # Django busca el nombre en inglés.

SERVICIOS_SIN_DICTADO = frozenset(SERVICIOS_CONFIDENCIALES | {"trabajo-social"})


def dictado_permitido(codigo_servicio: str | None) -> bool:
    if not getattr(settings, "SIBU_DICTADO", False):
        return False
    if not codigo_servicio:
        return False
    return codigo_servicio not in SERVICIOS_SIN_DICTADO


@registro.inclusion_tag("core/_dictado.html")
def dictado(codigo_servicio: str | None = None):
    return {"permitido": dictado_permitido(codigo_servicio)}
