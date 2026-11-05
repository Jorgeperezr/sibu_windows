"""URLs raíz de SIBU."""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.generic import TemplateView
from django.views.static import serve
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from apps.firma import api as firma_api
from apps.usuarios import views as usuarios_views

urlpatterns = [
    # FirmaEC exige que la acción se llame así (manual 11.4.2).
    path(
        "grabar_archivos_firmados",
        firma_api.grabar_archivos_firmados,
        name="firmaec-callback",
    ),
    path("admin/", admin.site.urls),
    path("", TemplateView.as_view(template_name="inicio.html"), name="inicio"),
    # El cambio de contraseña, ANTES del include de Django: el suyo existe pero
    # se dibuja con la plantilla del panel de administración —otra cabecera,
    # otra tipografía y un enlace a «Administración del sitio»—, y no estaba
    # enlazado desde ningún sitio, así que nadie podía cambiar su contraseña.
    # Declarado aquí primero, `password_change` resuelve a la pantalla de SIBU.
    # El ingreso lleva a crear la primera cuenta en una portable que aún no
    # tiene ninguna; y esa pantalla, que solo existe en la portable y desde el
    # propio computador. Antes del include de `auth` para que resuelvan aquí.
    path("cuentas/login/", usuarios_views.ingresar, name="login"),
    path("cuentas/primera/", usuarios_views.primera_cuenta, name="primera_cuenta"),
    path(
        "cuentas/password_change/",
        usuarios_views.cambiar_clave,
        name="password_change",
    ),
    path("cuentas/", include("django.contrib.auth.urls")),  # login/logout/password
    # API v1
    path("auditoria/", include("apps.auditoria.urls")),
    path("notificaciones/", include("apps.notificaciones.urls")),
    path("api/v1/", include("api.v1.urls")),
    path("usuarios/", include("apps.usuarios.urls")),
    path("academico/", include("apps.academico.urls")),
    path("expediente/", include("apps.expediente.urls")),
    path("citas/", include("apps.citas.urls")),
    path("enfermeria/", include("apps.enfermeria.urls")),
    path("medicina/", include("apps.medicina.urls")),
    path("laboratorio/", include("apps.laboratorio.urls")),
    path("odontologia/", include("apps.odontologia.urls")),
    path("farmacia/", include("apps.farmacia.urls")),
    path("psicologia/", include("apps.psicologia.urls")),
    path("psicopedagogia/", include("apps.psicopedagogia.urls")),
    path("trabajo-social/", include("apps.trabajo_social.urls")),
    path("derivaciones/", include("apps.derivaciones.urls")),
    path("firma/", include("apps.firma.urls")),
    path("becas/", include("apps.becas.urls")),
    path("talleres/", include("apps.talleres.urls")),
    path("portal/", include("apps.portal.urls")),
    path("reportes/", include("apps.reportes.urls")),
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="docs"),
]

# Los adjuntos los sirve Django en desarrollo y en la portable. En producción
# es trabajo de nginx; en una portable NO HAY nginx, y sin esto el profesional
# sube una evidencia a un taller y después no puede abrirla: 404 sobre un
# archivo que está en su propio disco.
#
# No vale el atajo `static()` de Django: devuelve una lista VACÍA cuando
# `DEBUG=False`, así que envolverlo en una condición propia no hace nada. Lo
# escribí así primero y la prueba lo delató, que es justo para lo que está.
if getattr(settings, "SIBU_PORTABLE", False):
    urlpatterns += [
        re_path(
            r"^{}(?P<path>.*)$".format(settings.MEDIA_URL.lstrip("/")),
            serve,
            {"document_root": settings.MEDIA_ROOT},
        )
    ]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    try:
        import debug_toolbar

        urlpatterns += [path("__debug__/", include(debug_toolbar.urls))]
    except ImportError:
        pass
