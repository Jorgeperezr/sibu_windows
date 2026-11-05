"""
Quita de las filas ya cargadas lo que SIBU decidió no guardar.

La carga dejaba en claro, en `DatoAcademico.ficha_raw`, la religión, la
orientación sexual, la violencia familiar, el consumo de drogas y la cuenta
bancaria de cada persona, mientras la pantalla de carga decía «(cifrado)» y
Becas declaraba «SIBU no almacena datos bancarios». Desde esta versión la
carga ya no los escribe; esta migración borra los que quedaron de antes.

Las columnas van escritas aquí y no importadas de `mapping`: una migración
tiene que dar el mismo resultado aunque el código cambie después.

No tiene vuelta atrás, a propósito: lo que se borra no debió guardarse.
"""

from django.db import migrations

NO_SE_CONSERVAN = (
    "orientacion_sexual",
    "religion",
    "violencia_familiar",
    "droga_consume",
    "frecuencia_consumo_droga",
    "beca_unl_cuenta_banco",
    "beca_unl_cuenta_tipo",
    "beca_unl_cuenta_numero",
)


def limpiar(apps, schema_editor):
    DatoAcademico = apps.get_model("academico", "DatoAcademico")
    for dato in DatoAcademico.objects.select_related("carga").iterator():
        fila = dato.ficha_raw or {}
        if not fila:
            continue
        # El archivo de un estamento puede llamar distinto a la misma columna:
        # se quita por el nombre canónico y por el alias de esa carga.
        alias = (dato.carga.mapeo_columnas or {}) if dato.carga_id else {}
        fuera = set(NO_SE_CONSERVAN) | {alias.get(c, c) for c in NO_SE_CONSERVAN}
        limpia = {k: v for k, v in fila.items() if k not in fuera}
        if limpia != fila:
            dato.ficha_raw = limpia
            dato.save(update_fields=["ficha_raw"])


class Migration(migrations.Migration):
    dependencies = [("academico", "0003_estamento_en_la_carga")]

    operations = [migrations.RunPython(limpiar, migrations.RunPython.noop)]
