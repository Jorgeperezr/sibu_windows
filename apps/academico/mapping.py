"""
Mapeo oficial de la ficha socioeconómica de matrícula de la UNL.

Congela el diccionario de columnas del archivo Excel/CSV entregado por la
institución (sección 7.3 del informe) y define cómo cada columna se distribuye
entre los modelos `Persona`, `DatoAcademico`, `Expediente` y las estructuras
JSONB de `FichaSocioeconomica`. La fila cruda completa se conserva siempre en
`DatoAcademico.ficha_raw`.

Si en un período la institución renombra encabezados, NO se edita este archivo:
el asistente de carga permite mapear los alias contra estas claves canónicas y
guarda ese mapeo por período (CargaInstitucional.mapeo_columnas).
"""

# --- Columnas académicas -> campos relacionales de DatoAcademico ---
ACADEMICO = {
    "facultad": "facultad",
    "carrera": "carrera",
    "nivel": "nivel",
    "modalidad": "modalidad",
    "ciclo": "ciclo",
    "oferta_academica": "oferta_academica",
    "estado": "estado",
    "paralelo": "paralelo",
    "jornada": "jornada",
    "email_institucional": "email_institucional",
}

# --- Identificación -> campos de Persona ---
IDENTIFICACION = {
    "tipo_documento": "tipo_documento",
    "cedula": "cedula",
    "nombres": "nombres",
    "apellidos": "apellidos",
    "fecha_nacimiento": "fecha_nacimiento",
    "sexo": "sexo",
    "genero": "genero",
    "celular": "celular",
    "telefono": "telefono",
}

# --- Datos de identidad sensibles -> Persona (campos a cifrar) ---
IDENTIDAD_SENSIBLE = ["orientacion_sexual", "religion"]

# --- Salud básica precargada -> Expediente ---
SALUD_EXPEDIENTE = {
    "tipo_sangre": "grupo_sanguineo",
    "discapacidad_tipo": "discapacidad_tipo",
    "discapacidad_porcentaje": "discapacidad_porcentaje",
}

# --- Grupos que se guardan como JSONB en Persona ---
PERSONA_JSONB = {
    "procedencia": [
        "pais_procedencia",
        "provincia_procedencia",
        "canton_procedencia",
        "parroquia_procedencia",
        "barrio_procedencia",
        "direccion_procedencia",
    ],
    "residencia_actual": [
        "pais_actual",
        "provincia_actual",
        "canton_actual",
        "parroquia_actual",
        "barrio_actual",
        "calle_principal_actual",
        "calle_secundaria_actual",
        "referencia_actual",
        "numero_casa_actual",
        "zona_actual",
    ],
    "contacto_referencia": [
        "representante_nombres",
        "representante_direccion",
        "representante_referencia",
        "representante_telefono",
        "responsable_persona",
    ],
}

# --- Grupos que se guardan como JSONB en FichaSocioeconomica ---
FICHA_JSONB = {
    "situacion_laboral": [
        "trabajo_empresa",
        "trabajo_telefono",
        "trabajo_relacion_dependencia",
        "trabajo_relacion_dependencia_otro",
        "trabajo_direccion",
        "trabajo_pais",
        "trabajo_provincia",
        "trabajo_canton",
        "trabajo_parroquia",
        "trabajo_telefono-2",
        "trabajo_empresa-2",
    ],
    "grupo_familiar": [
        "numero_familiares_grupo_hogar",
        "integrantes_familia",
        "numero_aportan_economia",
        "observacion_situacion_familiar",
        "ciudad_grupo_familiar",
        "direccion_grupo_familiar",
        "referencia_direccion_grupo_familiar",
        "relacion_familiar_tipo",
        "numero_hijos",
        "estado_civil",
        "etnia",
        "nacionalidad_indigena",
        "pais_procedencia",
    ],
    "convivencia": [
        "estudiante_necesidades_educativas_especiales",
        "dificultad_docentes",
        "dificultad_companieros",
        "tipo_maltrato_recibido",
        "ambiente_estudio_tipo",
        "novedades_aula",
        "dificultad_con_trabajador_administrativo",
    ],
    "vivienda_estudiante": [
        "viv_est_tipo",
        "viv_est_estructura",
        "viv_est_piso",
        "viv_est_cubierta",
        "viv_est_servicio_agua_potable",
        "viv_est_servicio_alcantarillado",
        "viv_est_servicio_energia_electrica",
        "viv_est_servicio_telefono",
        "viv_est_servicio_internet",
        "viv_est_servicio_tv_satelital",
    ],
    "vivienda_familiar": [
        "viv_fam_tipo",
        "viv_fam_estructura",
        "viv_fam_piso",
        "viv_fam_cubierta",
        "viv_fam_servicio_agua_potable",
        "viv_fam_servicio_alcantarillado",
        "viv_fam_servicio_energia_electrica",
        "viv_fam_servicio_telefono",
        "viv_fam_servicio_internet",
        "viv_fam_servicio_tv_satelital",
    ],
    "salud_familiar": [
        "familiar_problema_salud",
        "familiar_salud_parentesco",
        "familiar_salud_diagnostico",
        "familiar_discapacidad",
        "familiar_discapacidad_tipo",
        "familiar_carnet_conadis",
    ],
    "salud_estudiante": [
        "estudiante_problema_salud",
        "estudiante_salud_diagnostico",
        "estudiante_covid",
        "discapacidad",
        "carnet_conadis",
        "discapacidad_tipo",
        "discapacidad_porcentaje",
        "discapacidad_grado",
        "estudiante_gestacion",
        "estudiante_lactancia",
        "estudiante_vacunas_covid",
        "estudiante_vacunas_hepatitis",
        "estudiante_vacunas_tetanos",
    ],
    "bienes_negocio": [
        "num_bienes",
        "familiar_negocio_tipo",
        "familiar_negocio_otro",
        "familiar_negocio_ganancia",
        "estudiante_negocio_tipo",
        "estudiante_negocio_otro",
        "estudiante_negocio_ganancia",
    ],
    "ingresos": [
        "ingreso_estudiante",
        "ingreso_conyuge",
        "ingreso_padre",
        "ingreso_madre",
        "ingreso_otro_familiar",
        "ingreso_arriendo",
        "ingreso_pension_judicial",
        "ingreso_fondo_estado",
        "ingreso_beca_senescyt",
        "ingreso_beca_unl",
        "ingreso_otro",
        "ingreso_mensual",
    ],
    "egresos": [
        "gastos_vivienda",
        "gastos_alimentacion",
        "gastos_estudios",
        "gastos_transporte",
        "gastos_salud",
        "gastos_vestuario",
        "gastos_servicio_basico",
        "gastos_tarjeta_credito",
        "gastos_otro",
        "gastos_mensual_familia",
        "quien_financia_estudios",
        "credito_educativo",
        "credito_educativo_valor",
        "familiar_deuda_por_pagar",
        "familiar_deuda_detalle",
        "seguro",
        "descripcion_seguro",
    ],
}

# --- Campos sensibles cifrados en FichaSocioeconomica (categoría especial) ---
FICHA_SENSIBLE = ["violencia_familiar", "droga_consume", "frecuencia_consumo_droga"]

# --- Datos bancarios de beca -> BecaBeneficiario (cifrados) ---
DATOS_BANCARIOS = ["beca_unl_cuenta_banco", "beca_unl_cuenta_tipo", "beca_unl_cuenta_numero"]

# --- Lo que NO se conserva en la fila cruda ---
#
# La pantalla de carga decía que estas columnas iban «(cifrado)» y SIBU no
# cifra nada: no hay dependencia de cifrado ni custodia de claves. Lo que
# pasaba era peor que no guardarlas: quedaban en claro en
# `DatoAcademico.ficha_raw` —la fila completa—, que el panel de administración
# enseña entera. Religión, orientación sexual, violencia familiar, consumo de
# drogas y el número de cuenta bancaria de cada estudiante, a la vista de
# Administración General, que por separación de funciones no ve contenido
# clínico.
#
# Becas ya lo había decidido para las cuentas —«SIBU no almacena datos
# bancarios»— y la fila cruda lo desmentía en cada carga.
#
# Lo operativo no se pierde: las alertas (violencia familiar → Trabajo Social,
# consumo → Psicología) se calculan leyendo la fila en el momento de la carga,
# no `ficha_raw`. Lo que se deja de hacer es GUARDAR el dato.
NO_SE_CONSERVAN = (
    frozenset(IDENTIDAD_SENSIBLE) | frozenset(FICHA_SENSIBLE) | frozenset(DATOS_BANCARIOS)
)

# --- Columnas de control del formulario: solo en ficha_raw ---
CONTROL = ["case", "case-2", "case-3"]

# --- Reglas que disparan alertas hacia bandejas de servicios (sección 12.7) ---
# columna origen -> (tipo de alerta, servicio destino, plantilla de descripción)
REGLAS_ALERTA = {
    "violencia_familiar": ("social", "trabajo-social", "Violencia familiar declarada en matrícula"),
    "tipo_maltrato_recibido": ("social", "trabajo-social", "Maltrato reportado: {valor}"),
    "estudiante_necesidades_educativas_especiales": (
        "nee",
        "psicopedagogia",
        "Necesidad educativa especial declarada",
    ),
    "discapacidad": ("riesgo", "medicina", "Discapacidad declarada: {valor}"),
    # `gestacion` y `lactancia` eran ambas "riesgo" o no existían. El informe
    # estadístico cuenta por TIPO de alerta, así que una gestación declarada en
    # matrícula quedaba fuera del conteo aunque el dato estuviera cargado.
    "estudiante_gestacion": ("gestacion", "medicina", "Estado de gestación declarado"),
    "estudiante_lactancia": ("lactancia", "medicina", "Lactancia declarada en matrícula"),
    "droga_consume": ("riesgo", "psicologia", "Consumo declarado en matrícula"),
}


def columnas_canonicas():
    """Devuelve el conjunto de todas las columnas canónicas esperadas."""
    cols = set()
    cols |= set(ACADEMICO) | set(IDENTIFICACION) | set(IDENTIDAD_SENSIBLE)
    cols |= set(SALUD_EXPEDIENTE)
    for grupo in PERSONA_JSONB.values():
        cols |= set(grupo)
    for grupo in FICHA_JSONB.values():
        cols |= set(grupo)
    cols |= set(FICHA_SENSIBLE) | set(DATOS_BANCARIOS) | set(CONTROL)
    return cols


# Columnas mínimas sin las cuales una fila no puede procesarse
COLUMNAS_OBLIGATORIAS = ["cedula", "nombres", "apellidos"]

# Columnas que solo existen en la base de ESTUDIANTES. Un docente, un
# administrativo o un trabajador no tienen nivel, ciclo, paralelo ni jornada de
# clases: pedírselas en la plantilla obliga a quien prepara el archivo a
# inventar columnas vacías, y una columna vacía obligatoria acaba rellenándose
# con cualquier cosa. Facultad, carrera y correo institucional sí se mantienen
# para todos —un docente pertenece a una facultad—.
#
# Lo que un estamento no trae no rompe la carga: `_get` devuelve None y el
# campo queda en blanco. Esta lista es para la PLANTILLA y el DICCIONARIO, que
# es donde una columna de más confunde.
COLUMNAS_SOLO_ESTUDIANTE = [
    "nivel",
    "modalidad",
    "ciclo",
    "oferta_academica",
    "paralelo",
    "jornada",
]
