"""
Lo que la persona declaró de su salud en la ficha de matrícula, para la
pantalla del expediente.

Es un dato de salud: lo ven los servicios clínicos de Salud (Medicina,
Enfermería, Odontología), que son quienes lo usan para atender. No Becas, ni
Trabajo Social, ni la Dirección. Y es lo DECLARADO, no lo comprobado: la
pantalla lo dice.
"""

from __future__ import annotations

from apps.usuarios import rbac

SERVICIOS_QUE_LA_VEN = frozenset({"medicina", "enfermeria", "odontologia"})

# Las columnas de la ficha, con su nombre para una persona, en este orden.
ETIQUETAS = {
    "estudiante_problema_salud": "Problema de salud",
    "estudiante_salud_diagnostico": "Diagnóstico declarado",
    "tiene_enfermedad_catastrofica": "Enfermedad catastrófica",
    "enfermedades_catastroficas": "Cuál",
    "tiene_enfermedad_rara_huerfana": "Enfermedad rara o huérfana",
    "discapacidad": "Discapacidad",
    "discapacidad_tipo": "Tipo de discapacidad",
    "discapacidad_porcentaje": "Porcentaje",
    "discapacidad_grado": "Grado",
    "carnet_conadis": "Carné CONADIS",
    "estudiante_gestacion": "Gestación",
    "estudiante_lactancia": "Lactancia",
    "estudiante_covid": "COVID",
    "estudiante_vacunas_covid": "Vacunas COVID (dosis)",
    "estudiante_vacunas_hepatitis": "Vacunas hepatitis (dosis)",
    "estudiante_vacunas_tetanos": "Vacunas tétanos (dosis)",
    "necesita_ayuda_bienestar": "Pide ayuda de Bienestar",
}


def la_ve(user) -> bool:
    if not getattr(user, "is_authenticated", False):
        return False
    from apps.core.models import Servicio

    ids = rbac.servicios_del_usuario(user)
    return Servicio.objects.filter(pk__in=ids, codigo__in=SERVICIOS_QUE_LA_VEN).exists()


def para_pantalla(expediente) -> list[tuple[str, str]]:
    datos = expediente.salud_declarada or {}
    return [(etiqueta, datos[c]) for c, etiqueta in ETIQUETAS.items() if datos.get(c)]
