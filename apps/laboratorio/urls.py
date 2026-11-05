from django.urls import path

from . import views

app_name = "laboratorio"

urlpatterns = [
    path("", views.bandeja, name="bandeja"),
    path("catalogo/", views.catalogo, name="catalogo"),
    path("<int:pk>/", views.detalle_orden, name="detalle"),
]
