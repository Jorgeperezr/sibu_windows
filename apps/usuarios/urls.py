from django.urls import path

from . import views

app_name = "usuarios"

urlpatterns = [
    path("mi-perfil/", views.mi_perfil, name="mi_perfil"),
    path("perfiles/", views.gestion_perfiles, name="gestion_perfiles"),
    path("perfiles/nueva-cuenta/", views.nueva_cuenta, name="nueva_cuenta"),
    path("perfiles/<int:pk>/", views.editar_perfil, name="editar_perfil"),
    path("perfiles/alta/<int:pk>/", views.alta_perfil, name="alta_perfil"),
    path("perfiles/desbloquear/<int:pk>/", views.desbloquear_cuenta, name="desbloquear"),
]
