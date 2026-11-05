"""Servicios de usuarios: acceso de emergencia (break the glass) y auditoría RBAC."""

from __future__ import annotations

from apps.auditoria.models import LogAuditoria


def registrar_break_glass(user, expediente_id, motivo, ip=None, user_agent=""):
    """
    Registra un acceso de emergencia justificado (informe 10.2, 14.5).
    Deja constancia destacada en la auditoría; la notificación al Director la
    dispara una señal a partir de este log.
    """
    return LogAuditoria.objects.create(
        usuario=user,
        rol_activo=getattr(user, "rol_principal", ""),
        accion=LogAuditoria.Accion.BREAK_GLASS,
        modulo="expediente",
        entidad="Expediente",
        entidad_id=str(expediente_id),
        expediente_id=expediente_id,
        detalle={"motivo": motivo},
        ip=ip,
        user_agent=user_agent[:255] if user_agent else "",
    )


# Lo que un profesional puede corregir de su propia ficha. Deliberadamente NO
# están aquí `servicios`, `seccion`, `rol_principal` ni `puede_firmar_digital`:
# de esos depende el RBAC, y quien los editara se ampliaría el acceso a sí
# mismo. Los asigna quien administra, desde el panel.
CAMPOS_CUENTA = ("first_name", "last_name", "cedula", "telefono", "email", "fecha_nacimiento")
CAMPOS_PERFIL = ("titulo", "registro_profesional", "denominacion_cargo")
# `fecha_nacimiento` llega como texto ISO ("YYYY-MM-DD") de un <input
# type="date">, o cadena vacía: no se le aplica `.strip()` como al resto.
CAMPOS_FECHA = ("fecha_nacimiento",)


def actualizar_mi_perfil(usuario, datos: dict):
    """
    Actualiza los datos propios del profesional y devuelve su perfil.

    La cédula se normaliza y se valida con el módulo 10: es la que identifica
    al firmante ante FirmaEC, así que una mal digitada aquí bloquearía la firma
    más tarde y en otro sitio.

    Se valida TODO antes de escribir nada. `ATOMIC_REQUESTS` envuelve la
    petición entera: registrar el rechazo y luego lanzar ValidationError
    revertiría el propio registro, así que aquí no se audita lo rechazado.
    """
    from django.core.exceptions import ValidationError
    from django.db import transaction

    from apps.academico.validators import normalizar_cedula, validar_cedula_ecuatoriana
    from apps.auditoria.models import LogAuditoria

    from .models import PerfilProfesional, Usuario

    cedula = datos.get("cedula", "")
    if cedula:
        cedula = normalizar_cedula(cedula)
        if not validar_cedula_ecuatoriana(cedula):
            raise ValidationError(f"La cédula {cedula} no es válida (módulo 10).")
        # `Usuario` explícito, no `type(usuario)`: desde una vista llega un
        # SimpleLazyObject y `type(...)` devuelve la envoltura, que no tiene
        # manager. Con un objeto real —como en las pruebas del servicio— sí
        # funcionaba, así que el fallo solo salía en pantalla.
        ajena = (
            Usuario.objects.filter(cedula=cedula)
            .exclude(pk=usuario.pk)
            .values_list("username", flat=True)
            .first()
        )
        if ajena:
            raise ValidationError("Esa cédula ya está registrada en otra cuenta.")

    fecha_nacimiento = datos.get("fecha_nacimiento", "")
    if fecha_nacimiento:
        from datetime import date

        from django.utils.dateparse import parse_date

        fecha = parse_date(fecha_nacimiento)
        if fecha is None:
            raise ValidationError("La fecha de nacimiento no es válida.")
        if fecha > date.today():
            raise ValidationError("La fecha de nacimiento no puede ser futura.")

    with transaction.atomic():
        for campo in CAMPOS_CUENTA:
            if campo not in datos:
                continue
            if campo == "cedula":
                # Única y admite NULL: dejarla en cadena vacía haría chocar a
                # la segunda cuenta que se guardara sin cédula.
                valor = cedula or None
            elif campo in CAMPOS_FECHA:
                # DateField.to_python la parsea al guardar; cadena vacía -> None.
                valor = datos[campo] or None
            else:
                valor = datos[campo].strip()
            setattr(usuario, campo, valor)
        usuario.save(update_fields=[c for c in CAMPOS_CUENTA if c in datos])

        perfil, _ = PerfilProfesional.objects.get_or_create(usuario=usuario)
        for campo in CAMPOS_PERFIL:
            if campo in datos:
                setattr(perfil, campo, datos[campo].strip())
        perfil.save(update_fields=[c for c in CAMPOS_PERFIL if c in datos] or None)

        LogAuditoria.objects.create(
            usuario=usuario,
            rol_activo=getattr(usuario, "rol_principal", ""),
            accion=LogAuditoria.Accion.UPDATE,
            modulo="usuarios",
            entidad="PerfilProfesional",
            entidad_id=str(perfil.pk),
            detalle={"campos": sorted(set(datos) & set(CAMPOS_CUENTA + CAMPOS_PERFIL))},
        )
    return perfil


# ============================================================
# Actividades esenciales del manual de puestos
# ============================================================


def agregar_actividad(perfil, descripcion: str, actividad_superior=None):
    """
    Agrega una actividad esencial al final de su lista.

    Sin `actividad_superior` es una fila de primer nivel (una de las diez a
    trece del manual). Con ella, es una sub-actividad de las que suelen
    acumularse bajo la última —"las demás que asigne el jefe inmediato"—; se
    numera dentro de esa lista propia, no en la general.

    El siguiente `orden` se calcula, no se recibe: quien agrega una actividad
    no tiene por qué saber cuántas hay ya, y dejarlo a su cargo abriría la
    puerta a huecos o choques de numeración.
    """
    from django.core.exceptions import ValidationError

    from .models import ActividadEsencial

    descripcion = (descripcion or "").strip()
    if not descripcion:
        raise ValidationError("La actividad necesita una descripción.")

    if actividad_superior is not None and actividad_superior.perfil_id != perfil.pk:
        raise ValidationError("Esa actividad superior no pertenece a este perfil.")

    hermanas = ActividadEsencial.objects.filter(
        perfil=perfil, actividad_superior=actividad_superior
    )
    siguiente_orden = (hermanas.order_by("-orden").values_list("orden", flat=True).first() or 0) + 1

    return ActividadEsencial.objects.create(
        perfil=perfil,
        actividad_superior=actividad_superior,
        orden=siguiente_orden,
        descripcion=descripcion,
    )


def eliminar_actividad(actividad):
    """
    Quita una actividad esencial. Si tenía sub-actividades, se van con ella
    —`on_delete=CASCADE`—: no puede quedar una sub-actividad huérfana de la
    fila del manual que la contiene.
    """
    actividad.delete()


# ============================================================
# Gestión de perfiles (solo Administración General)
# ============================================================
#
# Lo que `actualizar_mi_perfil` deja fuera a propósito —servicios, sección, rol
# y firma digital— se asigna aquí. Hasta ahora solo desde `/admin/` de Django,
# que ni explica lo que concede ni deja un rastro legible.
#
# Y lo que se concede no es poca cosa: asignar el servicio de Psicología da
# acceso al contenido clínico sellado. Por eso cada cambio de servicios, rol o
# firma deja una entrada en la bitácora que dice QUÉ entró y QUÉ salió, no un
# «se actualizó el perfil» que obliga a comparar dos versiones para enterarse.


def _nombres(servicios) -> list[str]:
    return sorted(s.codigo for s in servicios)


def asignar_perfil(
    *,
    perfil,
    seccion=None,
    servicios=None,
    rol_principal: str | None = None,
    puede_firmar_digital: bool | None = None,
    usuario_que_asigna,
):
    """
    Asigna sección, servicios, rol y firma digital a un profesional.

    Solo la llama la pantalla de Administración General; el permiso se
    comprueba en la vista, que es donde está la petición. Aquí se protege lo
    que ninguna pantalla puede saltarse:

    - **Nadie se quita a sí mismo la administración.** Si el único
      administrador se degrada, no queda quien pueda devolverle el rol y la
      gestión de perfiles se cierra para todos. Es un callejón sin salida que
      solo se abre volviendo al shell.
    - **Lo concedido y lo retirado quedan escritos**, servicio por servicio.
    """
    from django.core.exceptions import ValidationError
    from django.db import transaction

    from apps.auditoria.models import LogAuditoria

    from .models import Rol

    antes = {
        "seccion": perfil.seccion.codigo if perfil.seccion else "",
        "servicios": _nombres(perfil.servicios.all()),
        "rol": perfil.usuario.rol_principal,
        "firma": perfil.puede_firmar_digital,
    }

    if (
        rol_principal is not None
        and perfil.usuario_id == usuario_que_asigna.pk
        and antes["rol"] == Rol.ADMIN_GENERAL
        and rol_principal != Rol.ADMIN_GENERAL
    ):
        raise ValidationError(
            "No puede quitarse a usted mismo la Administración General: si nadie "
            "más la tiene, se quedaría sin quien pueda devolvérsela."
        )

    with transaction.atomic():
        if seccion is not None:
            perfil.seccion = seccion
        if puede_firmar_digital is not None:
            perfil.puede_firmar_digital = puede_firmar_digital
        perfil.save()

        if servicios is not None:
            perfil.servicios.set(servicios)

        if rol_principal is not None:
            perfil.usuario.rol_principal = rol_principal
            perfil.usuario.save(update_fields=["rol_principal"])

        perfil.refresh_from_db()
        despues = {
            "seccion": perfil.seccion.codigo if perfil.seccion else "",
            "servicios": _nombres(perfil.servicios.all()),
            "rol": perfil.usuario.rol_principal,
            "firma": perfil.puede_firmar_digital,
        }
        concedidos = sorted(set(despues["servicios"]) - set(antes["servicios"]))
        retirados = sorted(set(antes["servicios"]) - set(despues["servicios"]))

        LogAuditoria.objects.create(
            usuario=usuario_que_asigna,
            rol_activo=getattr(usuario_que_asigna, "rol_principal", ""),
            accion=LogAuditoria.Accion.UPDATE,
            modulo="usuarios",
            entidad="PerfilProfesional",
            entidad_id=str(perfil.pk),
            detalle={
                "sobre": perfil.usuario.username,
                "antes": antes,
                "despues": despues,
                "servicios_concedidos": concedidos,
                "servicios_retirados": retirados,
            },
        )
    return perfil


def crear_perfil(*, usuario, usuario_que_asigna, **asignacion):
    """
    Da de alta la ficha profesional de una cuenta que no la tenía.

    Sin perfil, una cuenta no aparece en ninguna bandeja, no admite cita y no
    puede tener horario. Crear el perfil es lo que convierte una cuenta en
    alguien que atiende, así que va por el mismo camino auditado.
    """
    from django.conf import settings
    from django.core.exceptions import ValidationError
    from guardian.conf import settings as guardian

    from .models import PerfilProfesional

    # La lista ya lo esconde; aquí se niega. Un `pk` en el POST no es un
    # permiso, y `AnonymousUser` es la fila que django-guardian usa para colgar
    # los permisos del usuario anónimo: no es una persona y no atiende a nadie.
    centinela = getattr(settings, "ANONYMOUS_USER_NAME", guardian.ANONYMOUS_USER_NAME)
    if usuario.username == centinela:
        raise ValidationError("Esa no es una cuenta de persona: es el usuario anónimo interno.")

    if PerfilProfesional.objects.filter(usuario=usuario).exists():
        raise ValidationError("Esa cuenta ya tiene ficha profesional.")

    perfil = PerfilProfesional.objects.create(usuario=usuario)
    return asignar_perfil(perfil=perfil, usuario_que_asigna=usuario_que_asigna, **asignacion)


def crear_cuenta(
    *,
    cedula: str,
    nombres: str,
    apellidos: str,
    clave_temporal: str,
    rol_principal: str,
    usuario_que_crea,
    correo: str = "",
    telefono: str = "",
    con_ficha: bool = True,
):
    """
    Da de alta la cuenta de acceso de una persona del equipo.

    Hasta ahora no había forma de hacerlo desde el sistema: las cuentas solo
    existían si alguien abría una terminal y ejecutaba `createsuperuser` o
    `portable/crear_cuenta.py`. Una unidad con diez profesionales no puede
    arrancar así, y en una portable —una carpeta en el computador de alguien—
    menos todavía.

    Tres cosas que no se negocian aquí:

    - **La cédula es la identidad.** Es el `username`, y tiene que pasar el
      módulo 10 ecuatoriano: una cédula inventada deja una cuenta que luego no
      casa con ninguna ficha de persona.
    - **La clave es temporal y el sistema lo sabe.** Quien crea la cuenta tiene
      que teclear una clave y decírsela a su dueño, así que durante un rato la
      sabe alguien más. `debe_cambiar_clave` obliga a cambiarla antes de hacer
      nada; sin eso, Administración General podría entrar como la psicóloga, y
      el sello de Psicología es absoluto también frente a quien administra.
    - **Queda escrito quién creó a quién.** Nunca la clave: ni en claro, ni
      cifrada, ni su longitud.

    `con_ficha` crea además la ficha profesional, que es lo que convierte la
    cuenta en alguien que atiende. No se crea para un USUARIO_FINAL: esa es la
    cuenta de un estudiante en el portal, y una ficha profesional la pondría en
    las bandejas del personal.
    """
    from django.conf import settings
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    from django.db import transaction
    from guardian.conf import settings as guardian

    from apps.academico.validators import normalizar_cedula, validar_cedula_ecuatoriana
    from apps.auditoria.models import LogAuditoria

    from .models import Rol, Usuario

    cedula = normalizar_cedula(cedula)
    nombres = (nombres or "").strip()
    apellidos = (apellidos or "").strip()
    correo = (correo or "").strip()

    if not cedula:
        raise ValidationError("La cédula es obligatoria: es con lo que la persona ingresa.")

    # ANTES del dígito verificador, y no después: con «AnonymousUser» —el
    # nombre que trae guardian— la cédula ya falla el módulo 10, así que el
    # guardia puesto detrás no se ejecutaba nunca. Era código muerto que
    # parecía una protección. Delante sí actúa, y el nombre del centinela es
    # configurable: nada impide que un día sea algo que el módulo 10 acepte.
    centinela = getattr(settings, "ANONYMOUS_USER_NAME", guardian.ANONYMOUS_USER_NAME)
    if cedula == centinela:
        raise ValidationError("Ese nombre lo usa el sistema para el usuario anónimo interno.")

    if not validar_cedula_ecuatoriana(cedula):
        raise ValidationError(
            f"La cédula {cedula} no es válida (no pasa el dígito verificador). "
            "Compruébela antes de crear la cuenta."
        )
    if not nombres or not apellidos:
        raise ValidationError("Hacen falta los nombres y los apellidos.")

    if (
        Usuario.objects.filter(username=cedula).exists()
        or Usuario.objects.filter(cedula=cedula).exists()
    ):
        raise ValidationError(
            f"Ya hay una cuenta con la cédula {cedula}. Búsquela en la lista de perfiles."
        )

    if rol_principal not in dict(Rol.choices):
        raise ValidationError("Ese rol no existe.")

    # Las reglas de contraseña de Django, con el nombre y la cédula delante:
    # así rechaza «1100000007» como clave de la cuenta 1100000007.
    candidato = Usuario(username=cedula, first_name=nombres, last_name=apellidos, email=correo)
    validate_password(clave_temporal, user=candidato)

    with transaction.atomic():
        usuario = Usuario.objects.create_user(
            username=cedula,
            password=clave_temporal,
            first_name=nombres,
            last_name=apellidos,
            email=correo,
            cedula=cedula,
            telefono=telefono.strip(),
            rol_principal=rol_principal,
            debe_cambiar_clave=True,
        )

        LogAuditoria.objects.create(
            usuario=usuario_que_crea,
            rol_activo=getattr(usuario_que_crea, "rol_principal", ""),
            accion=LogAuditoria.Accion.CREATE,
            modulo="usuarios",
            entidad="Usuario",
            entidad_id=str(usuario.pk),
            # Sin rastro de la clave: ni en claro, ni su longitud.
            detalle={
                "cuenta": usuario.username,
                "nombre": usuario.get_full_name(),
                "rol": rol_principal,
                "correo": correo,
                "con_ficha": bool(con_ficha and rol_principal != Rol.USUARIO_FINAL),
            },
        )

        if con_ficha and rol_principal != Rol.USUARIO_FINAL:
            crear_perfil(usuario=usuario, usuario_que_asigna=usuario_que_crea)

    return usuario


def clave_cambiada(usuario):
    """
    La persona puso su propia clave: la temporal deja de serlo.

    Se llama desde la vista del cambio, que es la única que sabe que el cambio
    salió bien.
    """
    if usuario.debe_cambiar_clave:
        usuario.debe_cambiar_clave = False
        usuario.save(update_fields=["debe_cambiar_clave"])
    return usuario


def crear_primera_cuenta(*, cedula: str, nombres: str, apellidos: str, clave: str):
    """
    La primera cuenta de una portable, creada desde el navegador.

    Antes solo se podía con `python portable/crear_cuenta.py` en una consola.
    En un Windows sin Python instalado eso significa abrir una consola, ir a la
    carpeta y escribir la ruta del Python que viaja dentro: justo lo que una
    portable promete que no hace falta.

    Nace con Administración General —si no, nadie podría dar de alta al resto—
    y con la clave que su dueño escribe, no una temporal: aquí no hay nadie
    más que la haya visto.

    Solo funciona mientras NO hay ninguna cuenta de persona. Se vuelve a
    comprobar dentro de la transacción: dos pestañas abiertas a la vez no
    pueden crear dos administraciones.
    """
    from django.contrib.auth.password_validation import validate_password
    from django.core.exceptions import ValidationError
    from django.db import transaction

    from apps.academico.validators import normalizar_cedula, validar_cedula_ecuatoriana

    from .models import Rol, Usuario
    from .selectors import cuentas_de_persona

    cedula = normalizar_cedula(cedula)
    nombres, apellidos = (nombres or "").strip(), (apellidos or "").strip()
    if not validar_cedula_ecuatoriana(cedula or ""):
        raise ValidationError("Esa cédula no es válida (no pasa el dígito verificador).")
    if not nombres or not apellidos:
        raise ValidationError("Hacen falta los nombres y los apellidos.")
    validate_password(clave, user=Usuario(username=cedula, first_name=nombres, last_name=apellidos))

    with transaction.atomic():
        if cuentas_de_persona().select_for_update().exists():
            raise ValidationError("Este SIBU ya tiene cuentas: ingrese con la suya.")
        return Usuario.objects.create_superuser(
            username=cedula,
            password=clave,
            email="",
            first_name=nombres,
            last_name=apellidos,
            cedula=cedula,
            rol_principal=Rol.ADMIN_GENERAL,
        )
