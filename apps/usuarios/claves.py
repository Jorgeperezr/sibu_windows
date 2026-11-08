"""
Reglas de las claves de acceso.

La Unidad pidió poder usar claves breves, incluso un PIN de 4 dígitos: un
profesional entra decenas de veces al día desde equipos compartidos, y una
clave de 12 caracteres acababa escrita en un papel pegado a la pantalla.

Una clave corta solo es aceptable si:

1. Se rechazan las que un atacante prueba primero. Las 20 más usadas cubren
   cerca de una de cada cuatro claves de 4 dígitos (Berry, 2012); con diez
   intentos antes del bloqueo, aceptarlas sería regalar la cuenta.
2. Los intentos son pocos. Eso lo pone el bloqueo de la cuenta
   (`apps/usuarios/ingreso.py`), no estas reglas.

Referencias: Berry, N. (2012). *PIN analysis*. DataGenetics.
"""

from django.core.exceptions import ValidationError

LONGITUD_MINIMA = 4

# Los más usados según Berry (2012), más un par de secuencias de cuatro.
PIN_TRIVIALES = frozenset(
    "1234 1111 0000 1212 7777 1004 2000 4444 2222 6969 9999 3333 5555 6666 "
    "1122 1313 8888 4321 2001 1010 0123 9876".split()
)


def _es_secuencia(texto: str) -> bool:
    if len(texto) < 3 or not texto.isdigit():
        return False
    pasos = {int(b) - int(a) for a, b in zip(texto, texto[1:], strict=False)}
    return pasos in ({1}, {-1})


class LongitudMinima:
    def __init__(self, min_length: int = LONGITUD_MINIMA):
        self.min_length = min_length

    def validate(self, password, user=None):
        if len(password or "") < self.min_length:
            raise ValidationError(
                f"La clave tiene que tener al menos {self.min_length} caracteres "
                "(un PIN de 4 dígitos vale).",
                code="clave_corta",
            )

    def get_help_text(self):
        return f"Al menos {self.min_length} caracteres; un PIN de 4 dígitos vale."


class ClaveNoTrivial:
    """Ni repetida, ni en secuencia, ni de las más usadas, ni sacada de la cédula."""

    def validate(self, password, user=None):
        clave = (password or "").strip()
        motivo = None
        if len(set(clave)) == 1:
            motivo = "repite el mismo carácter"
        elif _es_secuencia(clave):
            motivo = "es una secuencia (como 1234 o 9876)"
        elif clave in PIN_TRIVIALES:
            motivo = "está entre las más usadas"
        elif user is not None:
            for dato in (getattr(user, "cedula", None), getattr(user, "username", None)):
                dato = (dato or "").strip()
                if dato and clave.isdigit() and clave in dato:
                    motivo = "sale de su cédula"
                    break
        if motivo:
            raise ValidationError(
                f"Esa clave {motivo}: es de las primeras que prueba quien intenta entrar. "
                "Elija otra.",
                code="clave_trivial",
            )

    def get_help_text(self):
        return "No puede ser repetida, en secuencia, de las más usadas ni parte de la cédula."
