from django.contrib import admin

from .models import CargaInstitucional, DatoAcademico


@admin.register(CargaInstitucional)
class CargaInstitucionalAdmin(admin.ModelAdmin):
    list_display = (
        "periodo",
        "nombre_archivo",
        "estado",
        "total_filas",
        "altas",
        "actualizaciones",
        "errores",
        "creado_en",
    )
    list_filter = ("estado", "periodo")
    readonly_fields = ("hash_archivo", "bitacora")


@admin.register(DatoAcademico)
class DatoAcademicoAdmin(admin.ModelAdmin):
    list_display = ("persona", "periodo", "facultad", "carrera", "ciclo", "estado")
    list_filter = ("periodo", "facultad", "modalidad", "jornada")
    search_fields = ("persona__cedula", "persona__nombres", "persona__apellidos")
    # La fila cruda trae la ficha socioeconómica entera —ingresos, salud
    # familiar, vivienda—, que es materia de Trabajo Social. Quien entra al
    # panel es Administración General, que por separación de funciones no ve
    # contenido de los servicios. Antes de esto el formulario de edición la
    # pintaba completa, religión y consumo de drogas incluidos.
    exclude = ("ficha_raw",)
