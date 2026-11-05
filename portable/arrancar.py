#!/usr/bin/env python3
"""
SIBU portable: lo que hay detrás del icono.

Pulsar el icono tiene que hacer una sola cosa visible —abrirse el navegador en
la pantalla de credenciales— y por debajo hace cuatro:

1. Prepara la carpeta la primera vez (migraciones, servicios, roles, catálogos).
2. Elige un puerto libre del propio computador.
3. Levanta el servidor ahí, en segundo plano.
4. Abre el navegador y espera. Cerrar la ventana cierra el sistema.

Se usa `waitress` y no `gunicorn`: gunicorn no funciona en Windows, y la
portable es sobre todo para Windows.

    python portable/arrancar.py
    python portable/arrancar.py --puerto 8800   # si se quiere uno fijo
    python portable/arrancar.py --sin-navegador # para dejarlo corriendo
"""

from __future__ import annotations

import argparse
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

ANFITRION = "127.0.0.1"

# Si la carpeta trae este archivo con una dirección dentro, la portable NO
# levanta su propio servidor: abre el navegador contra el servidor de la
# Unidad. El mismo paquete y el mismo icono sirven para los dos modos, que es
# lo que hace viable la arquitectura de `docs/CONEXION_ENTRE_PORTABLES.md`
# —una sola instancia con los datos, portables como clientes— sin repartir un
# segundo instalador.
ARCHIVO_SERVIDOR = RAIZ / "portable" / "servidor.txt"


def servidor_central() -> str | None:
    """
    La dirección del servidor de la Unidad, si esta carpeta es un cliente.

    Se admite escrita como la escribiría una persona —`sibu.unl.edu.ec`,
    `10.0.0.5:8000`— y se le pone el esquema. Sin esto, `webbrowser.open`
    recibía algo que no es una URL y abría una búsqueda o un archivo local:
    el profesional veía cualquier cosa menos SIBU, y nada que explicara por qué.

    Las líneas que empiezan por `#` se ignoran, para poder dejar la dirección
    comentada sin borrarla al volver al modo de carpeta sola.
    """
    if not ARCHIVO_SERVIDOR.exists():
        return None
    for linea in ARCHIVO_SERVIDOR.read_text(encoding="utf-8").splitlines():
        direccion = linea.strip()
        if not direccion or direccion.startswith("#"):
            continue
        if "://" not in direccion:
            # http y no https: una instancia en la red privada no suele tener
            # certificado, y https contra un servidor que habla http no abre
            # nada. Con nombre público se escribe el esquema en el archivo.
            direccion = f"http://{direccion}"
        return direccion.rstrip("/")
    return None


def responde(url: str, segundos: float = 4.0) -> bool:
    """
    ¿Contesta algo en esa dirección?

    En modo cliente los datos no están aquí: si la red privada está caída, el
    navegador enseña «no se puede conectar» y eso no distingue entre la red, el
    servidor y una dirección mal escrita. Comprobarlo antes permite decirlo.
    """
    from urllib.parse import urlsplit

    partes = urlsplit(url)
    puerto = partes.port or (443 if partes.scheme == "https" else 80)
    if not partes.hostname:
        return False
    try:
        with socket.create_connection((partes.hostname, puerto), timeout=segundos):
            return True
    except OSError:
        return False


def puerto_libre(preferido: int | None = None) -> int:
    """
    Un puerto que nadie esté usando.

    Con uno fijo, la segunda vez que alguien abre el programa sin haber cerrado
    la primera recibe «address already in use» y no entiende por qué. Se pide
    al sistema operativo que elija, salvo que se indique uno.
    """
    if preferido:
        return preferido
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind((ANFITRION, 0))
        return s.getsockname()[1]


def preparar_django(puerto: int) -> None:
    """
    Deja Django listo para arrancar.

    El origen se fija ANTES de importar los ajustes: `CSRF_TRUSTED_ORIGINS` se
    evalúa al cargarlos, y añadirlo después no tendría efecto. Sin él, el
    sistema levanta, todas las páginas responden y el formulario de acceso
    devuelve 403 — el sitio en pie con todo el mundo fuera.
    """
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.portable")
    os.environ["SIBU_ORIGENES"] = f"http://{ANFITRION}:{puerto},http://localhost:{puerto}"

    import django

    django.setup()


def preparar_carpeta(detallado: bool) -> None:
    """
    La primera vez: migraciones, servicios, roles y catálogo CIE-10.

    Es idempotente —`preparar --si-cambio` compara lo que hay con lo que el
    código define—, así que corre en cada arranque y no cuesta nada cuando no
    hay nada que hacer. Hacerlo aquí y no pedirle al profesional que ejecute un
    comando es la diferencia entre una portable y un proyecto de Django.
    """
    from django.core.management import call_command

    verbosidad = 1 if detallado else 0
    call_command("migrate", interactive=False, verbosity=verbosidad)
    call_command("preparar", "--si-cambio", "--sin-demo", verbosity=verbosidad)
    call_command("collectstatic", interactive=False, verbosity=0)

    # Los recordatorios de cita. En un servidor los dispararía Celery beat; en
    # una portable no hay demonio detrás, así que se repasan al abrir: los que
    # ya tocaba enviar y nadie envió. Es idempotente —no duplica— y cuesta una
    # consulta sobre las citas de los próximos dos días.
    #
    # Con la portable cerrada nadie avisa a nadie: es el límite de no tener un
    # servicio corriendo, y está dicho en `docs/PORTABLE.md`.
    call_command("recordatorios", "--silencioso", verbosity=verbosidad)

    optimizar_base()

    # Una copia al día, la primera vez que se abre SIBU ese día. Sin esto no
    # había ninguna: perder el disco era perder todas las historias clínicas.
    # Si falla, se dice y se sigue: no poder respaldar no puede impedir atender.
    try:
        call_command("respaldar", "--si-no-hay-de-hoy", verbosity=verbosidad)
    except Exception as exc:  # noqa: BLE001 - se informa, no se aborta el arranque
        print(f"  AVISO: no se pudo hacer la copia de seguridad de hoy: {exc}")


def optimizar_base() -> None:
    """
    Pone al día las estadísticas que SQLite usa para elegir índices.

    SQLite no las recoge solo: sin `ANALYZE`, su planificador decide a ciegas
    y puede recorrer una tabla entera teniendo un índice al lado. `PRAGMA
    optimize` hace el análisis únicamente donde hace falta, así que en una
    carpeta sin cambios no cuesta nada. Es lo que la documentación de SQLite
    recomienda hacer de vez en cuando en una base de larga vida, y una
    portable no tiene a nadie que lo haga por ella.
    """
    from django.db import connection

    if connection.vendor != "sqlite":
        return
    with connection.cursor() as cursor:
        cursor.execute("PRAGMA optimize")


def hay_cuentas() -> bool:
    """
    ¿Hay alguna cuenta de persona?

    No vale `Usuario.objects.exists()`: la migración de django-guardian deja su
    fila `AnonymousUser` y eso siempre es cierto, así que el aviso de «no hay
    ninguna cuenta todavía» no habría salido nunca.
    """
    from apps.usuarios.selectors import cuentas_de_persona

    return cuentas_de_persona().exists()


def abrir_navegador(url: str) -> None:
    """
    Abre el navegador cuando el servidor ya responde.

    Abrirlo antes enseña un «no se puede conectar», y quien lo ve recarga a
    mano o cierra el programa pensando que no funciona.
    """

    def esperar_y_abrir():
        for _ in range(100):  # 10 s de margen
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                if s.connect_ex((ANFITRION, int(url.rsplit(":", 1)[1].split("/")[0]))) == 0:
                    break
            time.sleep(0.1)
        webbrowser.open(url)

    threading.Thread(target=esperar_y_abrir, daemon=True).start()


def main() -> int:
    parser = argparse.ArgumentParser(description="Arranca SIBU portable.")
    parser.add_argument("--puerto", type=int, default=None, help="Puerto fijo.")
    parser.add_argument("--sin-navegador", action="store_true", help="No abrir el navegador.")
    parser.add_argument("--detallado", action="store_true", help="Enseñar lo que hace al preparar.")
    parser.add_argument("--servidor", default=None, help="Abrir contra el servidor de la Unidad.")
    opciones = parser.parse_args()

    central = opciones.servidor or servidor_central()
    if central:
        # Modo cliente: no hay base local que preparar ni servidor que levantar.
        print("SIBU — Unidad de Bienestar Universitario · UNL")
        print(f"Abriendo el sistema de la Unidad: {central}")
        print()
        print("Esta carpeta es un cliente: los datos están en el servidor, no aquí.")
        alcanzable = responde(central)
        if not alcanzable:
            # Abrir el navegador igual, porque puede ser cosa de un segundo y
            # el aviso queda detrás; pero con el aviso delante, que es lo que
            # convierte un «no funciona» en algo que se puede arreglar.
            print()
            print("  AVISO: ese servidor no contesta ahora mismo.")
            print("  Suele ser una de tres cosas:")
            print("    1. La red privada (NetBird) no está conectada en este")
            print("       computador. Ábrala y vuelva a intentarlo.")
            print("    2. El servidor de la Unidad está apagado.")
            print(f"    3. La dirección de portable/servidor.txt no es la buena: {central}")
            print()
            print("  Sus datos no están en esta carpeta, así que no hay nada que")
            print("  perder: cuando la red vuelva, vuelva a pulsar el icono.")
            print()
        if not opciones.sin_navegador:
            webbrowser.open(central)
        return 0 if alcanzable else 1

    puerto = puerto_libre(opciones.puerto)
    preparar_django(puerto)

    print("SIBU — Unidad de Bienestar Universitario · UNL")
    print("Preparando la carpeta…")
    preparar_carpeta(opciones.detallado)

    url = f"http://{ANFITRION}:{puerto}/"
    destino = url
    if not hay_cuentas():
        # Sin ninguna cuenta, el sistema levanta y luego rechaza a cualquiera
        # que se escriba. El navegador se abre directamente donde se crea la
        # primera: antes había que escribir un comando de Python en una consola,
        # que en un Windows sin Python es justo lo que no se puede pedir.
        destino = f"{url}cuentas/primera/"
        print()
        print("  Todavía no hay ninguna cuenta: el navegador se abrirá para crear")
        print("  la primera, que será la de Administración General.")
        print()

    print(f"SIBU está en {url}")
    print("Para cerrarlo, cierre esta ventana o pulse Ctrl+C.")

    if not opciones.sin_navegador:
        abrir_navegador(destino)

    from waitress import serve

    from config.wsgi import application

    try:
        serve(application, host=ANFITRION, port=puerto, threads=8)
    except KeyboardInterrupt:
        print("\nSIBU cerrado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
