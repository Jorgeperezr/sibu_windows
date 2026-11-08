"""
Ficha propia del profesional.

Cada profesional mantiene aquí lo que le identifica al atender y al firmar:
título, registro profesional, cédula y —desde hoy— fecha de nacimiento,
denominación del cargo y las actividades esenciales de su manual de puestos.
Antes solo se podía cargar desde el panel de administración, así que en la
práctica quedaba vacío.

Lo que NO se edita aquí son los servicios, la sección y el rol: de ellos
depende el RBAC, y una pantalla que los dejara tocar sería una vía para
ampliarse el acceso a uno mismo. Se muestran, en solo lectura, para que el
profesional pueda comprobar con qué permisos trabaja.
"""

from django.contrib import messages
from django.contrib.auth import update_session_auth_hash
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.core.exceptions import PermissionDenied, ValidationError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.models import Seccion, Servicio

from . import rbac
from .models import ActividadEsencial, PerfilProfesional, Rol, Usuario
from .rbac import SERVICIOS_CONFIDENCIALES
from .selectors import cuentas_sin_perfil, perfiles_para_gestion
from .services import (
    CAMPOS_CUENTA,
    CAMPOS_EDITABLES_POR_ADMINISTRACION,
    CAMPOS_PERFIL,
    actualizar_mi_perfil,
    agregar_actividad,
    asignar_perfil,
    clave_cambiada,
    crear_cuenta,
    crear_perfil,
    editar_cuenta,
    eliminar_actividad,
)


def _mi_perfil_o_404(request):
    """El PerfilProfesional del usuario en sesión, o 404 si no tiene."""
    return get_object_or_404(PerfilProfesional, usuario=request.user)


@login_required
def mi_perfil(request):
    if request.method == "POST":
        accion = request.POST.get("accion", "actualizar")
        try:
            if accion == "actualizar":
                datos = {c: request.POST.get(c, "") for c in CAMPOS_CUENTA + CAMPOS_PERFIL}
                actualizar_mi_perfil(request.user, datos)
                messages.success(request, "Sus datos quedaron actualizados.")

            elif accion == "agregar_actividad":
                perfil = _mi_perfil_o_404(request)
                agregar_actividad(perfil, request.POST.get("descripcion", ""))
                messages.success(request, "Actividad agregada.")

            elif accion == "agregar_subactividad":
                perfil = _mi_perfil_o_404(request)
                superior = get_object_or_404(
                    ActividadEsencial, pk=request.POST.get("actividad_superior"), perfil=perfil
                )
                agregar_actividad(
                    perfil, request.POST.get("descripcion", ""), actividad_superior=superior
                )
                messages.success(request, "Sub-actividad agregada.")

            elif accion == "eliminar_actividad":
                perfil = _mi_perfil_o_404(request)
                actividad = get_object_or_404(
                    ActividadEsencial, pk=request.POST.get("actividad"), perfil=perfil
                )
                eliminar_actividad(actividad)
                messages.success(request, "Actividad eliminada.")

        except ValidationError as exc:
            messages.error(request, " ".join(exc.messages))
        return redirect("usuarios:mi_perfil")

    perfil = (
        PerfilProfesional.objects.filter(usuario=request.user)
        .select_related("seccion")
        .prefetch_related("servicios")
        .first()
    )
    # Solo de primer nivel: cada una trae sus `subactividades` prefetched, en
    # el orden que ya fija `Meta.ordering` del modelo.
    actividades = (
        ActividadEsencial.objects.filter(perfil=perfil, actividad_superior=None)
        .prefetch_related("subactividades")
        .order_by("orden")
        if perfil
        else []
    )
    return render(
        request,
        "usuarios/mi_perfil.html",
        {
            "perfil": perfil,
            "servicios": perfil.servicios.all() if perfil else [],
            "actividades": actividades,
        },
    )


# ============================================================
# Gestión de perfiles (solo Administración General)
# ============================================================


def _solo_administracion(request) -> None:
    """
    Asignar servicios es conceder acceso, y el de Psicología abre contenido
    sellado. Lo decide Administración General y nadie más: ni la Dirección, ni
    la Coordinación, ni quien ya atiende en el servicio.
    """
    if not rbac.es_admin(request.user):
        raise PermissionDenied("La gestión de perfiles es de Administración General.")


@login_required
def gestion_perfiles(request):
    """
    Quién atiende, en qué servicio, con qué rol y si tiene horario.

    Hasta ahora esta pregunta solo se contestaba a mano desde `/admin/` de
    Django, que lista cuentas y perfiles por separado y no dice ni los
    servicios ni si hay franjas. La columna del horario es la que evita el
    desconcierto más común: un profesional bien dado de alta y sin franjas
    **no admite ninguna cita**, y nada en su ficha lo advertía.

    Las cuentas sin perfil van abajo a propósito: son las que no aparecen en
    ninguna bandeja, y la pregunta «¿por qué no sale Fulano?» se contesta aquí.
    """
    _solo_administracion(request)
    return render(
        request,
        "usuarios/gestion_perfiles.html",
        {
            "perfiles": perfiles_para_gestion(
                request.GET.get("q", ""), request.GET.get("seccion") or None
            ),
            "sin_perfil": cuentas_sin_perfil(),
            "secciones": Seccion.objects.order_by("nombre"),
            "q": request.GET.get("q", ""),
            "seccion": request.GET.get("seccion", ""),
            "confidenciales": SERVICIOS_CONFIDENCIALES,
        },
    )


@login_required
def editar_perfil(request, pk):
    """Datos de acceso, sección, servicios, rol y firma digital de un profesional."""
    from django.db import transaction

    _solo_administracion(request)
    perfil = get_object_or_404(
        PerfilProfesional.objects.select_related("usuario", "seccion"), pk=pk
    )

    if request.method == "POST":
        try:
            # Las dos mitades juntas o ninguna: un servicio rechazado no puede
            # dejar guardado el correo nuevo bajo un aviso de error.
            with transaction.atomic():
                if "first_name" in request.POST:
                    editar_cuenta(
                        cuenta=perfil.usuario,
                        datos={
                            c: request.POST.get(c, "") for c in CAMPOS_EDITABLES_POR_ADMINISTRACION
                        },
                        usuario_que_edita=request.user,
                        nueva_clave=request.POST.get("nueva_clave", ""),
                    )
                asignar_perfil(
                    perfil=perfil,
                    seccion=Seccion.objects.filter(pk=request.POST.get("seccion") or 0).first(),
                    servicios=Servicio.objects.filter(pk__in=request.POST.getlist("servicios")),
                    rol_principal=request.POST.get("rol") or None,
                    puede_firmar_digital=request.POST.get("firma") == "1",
                    usuario_que_asigna=request.user,
                )
            aviso = f"Perfil de {perfil.usuario.get_full_name()} actualizado."
            if request.POST.get("nueva_clave"):
                aviso += " La clave nueva es temporal: tendrá que cambiarla al entrar."
            messages.success(request, aviso)
            return redirect("usuarios:gestion_perfiles")
        except ValidationError as exc:
            perfil.usuario.refresh_from_db()
            messages.error(request, "; ".join(exc.messages))

    return render(
        request,
        "usuarios/editar_perfil.html",
        {
            "perfil": perfil,
            "secciones": Seccion.objects.order_by("nombre"),
            "servicios": Servicio.objects.filter(activo=True).order_by("nombre"),
            "mis_servicios": {s.pk for s in perfil.servicios.all()},
            "roles": Rol.choices,
            "confidenciales": SERVICIOS_CONFIDENCIALES,
            "franjas": perfil.agendas.filter(activa=True).count(),
        },
    )


@login_required
@require_POST
def alta_perfil(request, pk):
    """
    Convierte una cuenta en alguien que atiende.

    Solo por POST: crea una ficha, y una vista que escribe no puede responder a
    un GET —bastaría un `<img src="...">` ajeno para dar de alta a alguien—.

    Sin perfil una cuenta no sale en ninguna bandeja, no admite cita y no puede
    tener horario: crear el perfil es lo que la pone a atender, así que va por
    el mismo camino auditado que una asignación.
    """
    _solo_administracion(request)
    usuario = get_object_or_404(Usuario, pk=pk)
    try:
        perfil = crear_perfil(usuario=usuario, usuario_que_asigna=request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
        return redirect("usuarios:gestion_perfiles")
    messages.success(
        request,
        f"{usuario.get_full_name() or usuario.username} ya tiene ficha profesional. "
        "Asígnele sección y servicios para que pueda atender.",
    )
    return redirect("usuarios:editar_perfil", pk=perfil.pk)


@login_required
@require_POST
def desbloquear_cuenta(request, pk):
    """Abre una cuenta cerrada por intentos fallidos. Solo Administración General."""
    from .ingreso import desbloquear

    _solo_administracion(request)
    cuenta = get_object_or_404(Usuario, pk=pk)
    desbloquear(cuenta, por=request.user)
    messages.success(request, f"{cuenta.get_full_name() or cuenta.username} ya puede ingresar.")
    return redirect("usuarios:gestion_perfiles")


def _contexto_alta(datos):
    return {
        "roles": Rol.choices,
        "datos": datos,
        "secciones": Seccion.objects.order_by("nombre"),
        "servicios": Servicio.objects.filter(activo=True).order_by("nombre"),
        "marcados": {int(x) for x in datos.getlist("servicios") if x.isdigit()}
        if hasattr(datos, "getlist")
        else set(),
        "confidenciales": SERVICIOS_CONFIDENCIALES,
    }


@login_required
def nueva_cuenta(request):
    """
    Dar de alta a alguien del equipo, desde el sistema.

    Hasta ahora no se podía: las cuentas solo existían si alguien abría una
    terminal. Una unidad con diez profesionales no arranca así, y en una
    portable —una carpeta en el computador de alguien— menos.

    Termina en la pantalla de servicios del recién creado, que es el paso que
    falta para que pueda atender: una cuenta sin servicios ve el sistema y no
    puede hacer nada en él.
    """
    _solo_administracion(request)

    if request.method == "POST":
        try:
            if not request.POST.get("correo", "").strip():
                raise ValidationError("El correo es obligatorio: es con lo que la persona ingresa.")
            usuario = crear_cuenta(
                cedula=request.POST.get("cedula", ""),
                nombres=request.POST.get("nombres", ""),
                apellidos=request.POST.get("apellidos", ""),
                correo=request.POST.get("correo", ""),
                telefono=request.POST.get("telefono", ""),
                rol_principal=request.POST.get("rol", Rol.PROFESIONAL),
                clave_temporal=request.POST.get("clave", ""),
                usuario_que_crea=request.user,
                seccion=Seccion.objects.filter(pk=request.POST.get("seccion") or 0).first(),
                servicios=Servicio.objects.filter(pk__in=request.POST.getlist("servicios")),
            )
            messages.success(
                request,
                f"Cuenta creada para {usuario.get_full_name()}. Ingresa con su correo "
                f"{usuario.email} y la clave que usted le dé; el sistema le pedirá "
                "cambiarla antes de dejarle hacer nada.",
            )
            return redirect("usuarios:gestion_perfiles")
        except ValidationError as exc:
            messages.error(request, "; ".join(exc.messages))
            # Se devuelve lo tecleado —menos la clave— para no obligar a
            # escribirlo todo otra vez por un correo mal copiado.
            return render(request, "usuarios/nueva_cuenta.html", _contexto_alta(request.POST))

    return render(request, "usuarios/nueva_cuenta.html", _contexto_alta({}))


@login_required
def cambiar_clave(request):
    """
    La pantalla propia para cambiar la contraseña.

    La había, pero era la del panel de administración de Django: otra cabecera,
    otra tipografía y un enlace a «Administración del sitio» que a un
    profesional no le lleva a ninguna parte. Y no estaba enlazada desde ningún
    sitio, así que en la práctica nadie podía cambiar su contraseña.

    Es también la única salida cuando la cuenta tiene clave temporal: el
    middleware trae aquí cada página hasta que su dueño pone la suya.
    """
    if request.method == "POST":
        formulario = PasswordChangeForm(request.user, request.POST)
        if formulario.is_valid():
            usuario = formulario.save()
            clave_cambiada(usuario)
            # Sin esto, cambiar la clave cierra la propia sesión: el hash de la
            # sesión deja de coincidir y la persona acaba en el login sin saber
            # si el cambio se guardó.
            update_session_auth_hash(request, usuario)
            messages.success(request, "Su contraseña quedó cambiada.")
            return redirect("inicio")
    else:
        formulario = PasswordChangeForm(request.user)

    return render(
        request,
        "registration/password_change_form.html",
        {"form": formulario, "temporal": request.user.debe_cambiar_clave},
    )


def _es_portable_local(request) -> bool:
    """
    Una portable, y la petición viene del propio computador.

    La pantalla de la primera cuenta no existe fuera de ahí: en el servidor de
    la Unidad, un SIBU recién desplegado y sin cuentas sería de quien llegara
    primero.
    """
    from django.conf import settings

    return getattr(settings, "SIBU_PORTABLE", False) and request.META.get("REMOTE_ADDR") in {
        "127.0.0.1",
        "::1",
    }


def primera_cuenta(request):
    """La primera cuenta de la portable, sin consola."""
    from django.contrib.auth import login
    from django.http import Http404

    from .selectors import cuentas_de_persona
    from .services import crear_primera_cuenta

    if not _es_portable_local(request) or cuentas_de_persona().exists():
        raise Http404

    datos = {}
    if request.method == "POST":
        datos = request.POST
        if request.POST.get("clave") != request.POST.get("clave2"):
            messages.error(request, "Las dos contraseñas no coinciden.")
        else:
            try:
                cuenta = crear_primera_cuenta(
                    cedula=request.POST.get("cedula", ""),
                    nombres=request.POST.get("nombres", ""),
                    apellidos=request.POST.get("apellidos", ""),
                    clave=request.POST.get("clave", ""),
                    correo=request.POST.get("correo", ""),
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
            else:
                login(request, cuenta, backend="apps.usuarios.ingreso.IngresoPorCorreoOCuenta")
                messages.success(
                    request,
                    "Cuenta creada. Desde «Perfiles → Nueva cuenta» dé de alta "
                    "al resto del equipo.",
                )
                return redirect("inicio")

    return render(request, "registration/primera_cuenta.html", {"datos": datos})


def ingresar(request, *args, **kwargs):
    """
    El inicio de sesión, salvo en una portable que todavía no tiene cuentas.

    Ahí lleva a crear la primera: sin cuentas, el formulario de ingreso
    rechaza a cualquiera, y eso se lee como «las credenciales no funcionan».
    """
    from django.contrib.auth.views import LoginView

    from .ingreso import FormularioIngreso
    from .selectors import cuentas_de_persona

    if _es_portable_local(request) and not cuentas_de_persona().exists():
        return redirect("primera_cuenta")
    if request.user.is_authenticated and not request.GET.get("next"):
        return redirect("inicio")
    return LoginView.as_view(authentication_form=FormularioIngreso)(request, *args, **kwargs)


def inicio(request):
    """La portada. Sin sesión lleva directo al ingreso: `http://EQUIPO` basta."""
    from django.shortcuts import render as pintar

    if not request.user.is_authenticated:
        return redirect("login")
    return pintar(request, "inicio.html")
