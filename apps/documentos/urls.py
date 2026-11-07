from django.urls import path

from . import views

app_name = "documentos"

urlpatterns = [
    path("expediente/<int:expediente_id>/", views.lista, name="lista"),
    path("<int:pk>/archivo/", views.archivo, name="archivo"),
    path("<int:pk>/marcar/", views.marcar, name="marcar"),
    path("<int:pk>/retirar/", views.retirar, name="retirar"),
]
