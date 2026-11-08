"""
Mientras la clave sea la que tecleó otro, no se usa el sistema.

Administración General crea la cuenta de un profesional y tiene que teclear
una clave y decírsela. Durante ese rato la clave la saben dos personas. Si el
sistema dejara trabajar así, quien administra podría entrar como la psicóloga
—y el sello de Psicología es absoluto también frente a quien administra: no es
una cuestión de confianza, es que el sello no admite excepciones—.

`debe_cambiar_clave` se enciende al crear la cuenta y se apaga cuando su dueño
pone la suya. Entre medias, toda la navegación lleva a la misma pantalla.
"""

from django.shortcuts import redirect
from django.urls import reverse

# Lo que sigue abierto con la clave temporal puesta. Sin estas excepciones, el
# propio cambio de clave redirigiría al cambio de clave: un bucle, y la cuenta
# quedaría inservible en vez de protegida.
NOMBRES_PERMITIDOS = ("password_change", "logout", "login")


class ExigirCambioDeClave:
    """Redirige a cambiar la clave mientras la cuenta tenga una temporal."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        usuario = getattr(request, "user", None)
        if (
            usuario is not None
            and usuario.is_authenticated
            and getattr(usuario, "debe_cambiar_clave", False)
            and self._hay_que_desviar(request)
        ):
            return redirect("password_change")
        return self.get_response(request)

    @staticmethod
    def _hay_que_desviar(request) -> bool:
        # Los estáticos y los adjuntos no: la pantalla del cambio los necesita
        # para dibujarse, y desviarlos la dejaría sin estilos.
        ruta = request.path
        if ruta.startswith(("/static/", "/media/")):
            return False
        coincidencia = getattr(request, "resolver_match", None)
        nombre = coincidencia.url_name if coincidencia else None
        if nombre in NOMBRES_PERMITIDOS:
            return False
        # `resolver_match` todavía no está resuelto cuando el middleware corre
        # antes de la vista, así que se compara también la ruta escrita.
        return ruta not in {reverse(n) for n in NOMBRES_PERMITIDOS}


class RenovarSesion:
    """
    La sesión dura mientras se trabaja: se renueva al usarla, como mucho una
    vez cada `CADA_S` segundos.

    Antes caducaba a los 15 minutos de INGRESAR, aunque se estuviera
    escribiendo, y la consulta a medias se perdía en el envío. Con
    `SESSION_SAVE_EVERY_REQUEST` se arreglaba, pero cada página escribía la
    sesión: tres consultas más en todas, y en la portable cada escritura
    compite en SQLite con el guardado de un compañero.
    """

    CADA_S = 5 * 60

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        import time

        sesion = getattr(request, "session", None)
        usuario = getattr(request, "user", None)
        if sesion is not None and usuario is not None and usuario.is_authenticated:
            ahora = int(time.time())
            if ahora - int(sesion.get("_renovada", 0)) >= self.CADA_S:
                sesion["_renovada"] = ahora  # marca la sesión: se guarda con su nueva caducidad
        return self.get_response(request)
