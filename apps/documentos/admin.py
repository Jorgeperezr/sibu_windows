from django.apps import apps as django_apps
from django.contrib import admin

from .models import DocumentoAnexo


@admin.register(DocumentoAnexo)
class DocumentoAnexoAdmin(admin.ModelAdmin):
    """
    Solo las evidencias de talleres.

    Los documentos del expediente NO aparecen aquí. El panel lo abre
    Administración General, que por separación de funciones no ve contenido
    clínico, y el nombre o la descripción de un documento de Psicología
    («informe de valoración por ideación…») ya son contenido sellado.
    """

    list_display = ("nombre_archivo", "taller", "tipo_documento", "creado_en")

    def get_queryset(self, request):
        return super().get_queryset(request).filter(expediente__isnull=True)


for _model in django_apps.get_app_config("documentos").get_models():
    try:
        admin.site.register(_model)
    except admin.sites.AlreadyRegistered:
        pass
