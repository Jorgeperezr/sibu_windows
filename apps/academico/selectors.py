"""
Consultas de lectura de la base institucional cargada.

Tres cosas viven aquí:

1. El **diccionario de columnas** que la institución debe entregar, derivado de
   `mapping` y no de una lista escrita a mano: si mañana se añade una columna al
   mapeo, aparece sola en la plantilla y en la pantalla del diccionario. Una
   segunda lista paralela se desincronizaría el día que nadie mire.
2. El **padrón**: lo que efectivamente quedó cargado, para que quien administra
   pueda comprobarlo en pantalla en vez de fiarse del resumen de la carga.
3. El **autocompletado** por cédula o por nombres, que es lo que el profesional
   usa para no volver a digitar lo que la institución ya sabe.

Nada de lo que sale de aquí es contenido clínico: son datos de identificación y
matrícula. En particular, ninguna consulta revela qué servicio atiende a una
persona, porque eso delataría el paso por un servicio confidencial.
"""

from __future__ import annotations

from django.db.models import Q

from . import mapping

# Grupos del archivo, en el orden en que se esperan las columnas. Cada fila es
# (nombre del grupo, a dónde va el dato, columnas). El orden importa: es el de
# la plantilla CSV que se descarga, y coincidir con él le ahorra a quien prepara
# el archivo tener que reordenar nada.
GRUPOS = [
    ("Identificación", "Persona", list(mapping.IDENTIFICACION)),
    ("Datos académicos", "Dato académico", list(mapping.ACADEMICO)),
    ("Identidad (sensible)", "No se guarda", list(mapping.IDENTIDAD_SENSIBLE)),
    ("Salud básica", "Expediente", list(mapping.SALUD_EXPEDIENTE)),
    ("Procedencia", "Persona (JSON)", mapping.PERSONA_JSONB["procedencia"]),
    ("Residencia actual", "Persona (JSON)", mapping.PERSONA_JSONB["residencia_actual"]),
    ("Contacto de referencia", "Persona (JSON)", mapping.PERSONA_JSONB["contacto_referencia"]),
    ("Situación laboral", "Ficha socioeconómica", mapping.FICHA_JSONB["situacion_laboral"]),
    # Decía «Ficha socioeconómica» y la ficha no tiene dónde guardarlo: queda
    # en la fila del período, que es lo que se consulta en el padrón.
    ("Grupo familiar", "Fila del período", mapping.FICHA_JSONB["grupo_familiar"]),
    ("Convivencia", "Ficha socioeconómica", mapping.FICHA_JSONB["convivencia"]),
    ("Vivienda del estudiante", "Ficha socioeconómica", mapping.FICHA_JSONB["vivienda_estudiante"]),
    ("Vivienda familiar", "Ficha socioeconómica", mapping.FICHA_JSONB["vivienda_familiar"]),
    ("Salud familiar", "Ficha socioeconómica", mapping.FICHA_JSONB["salud_familiar"]),
    (
        "Salud del estudiante",
        "Expediente (salud declarada)",
        mapping.FICHA_JSONB["salud_estudiante"],
    ),
    ("Bienes y negocio", "Fila del período", mapping.FICHA_JSONB["bienes_negocio"]),
    ("Ingresos", "Ficha socioeconómica", mapping.FICHA_JSONB["ingresos"]),
    ("Egresos", "Ficha socioeconómica", mapping.FICHA_JSONB["egresos"]),
    ("Situaciones sensibles", "Solo genera la alerta; no se guarda", mapping.FICHA_SENSIBLE),
    ("Datos bancarios de beca", "No se guarda", mapping.DATOS_BANCARIOS),
    ("Control del formulario", "solo la fila cruda", mapping.CONTROL),
]

# Columnas que disparan una alerta hacia un servicio al cargarse.
COLUMNAS_CON_ALERTA = set(mapping.REGLAS_ALERTA)


ESTAMENTO_POR_DEFECTO = "estudiante"


def _omitidas(estamento: str) -> set[str]:
    """Columnas que no aplican al estamento pedido."""
    estamento = estamento or ESTAMENTO_POR_DEFECTO
    if estamento == ESTAMENTO_POR_DEFECTO:
        return set()
    return set(mapping.COLUMNAS_SOLO_ESTUDIANTE)


def columnas_ordenadas(estamento: str = ESTAMENTO_POR_DEFECTO) -> list[str]:
    """
    Los encabezados del archivo, en el orden de `GRUPOS` y sin repetir.

    Tres columnas viven en dos grupos a la vez —`pais_procedencia`,
    `discapacidad_tipo` y `discapacidad_porcentaje`, que alimentan dos destinos
    distintos—. En el archivo van una sola vez: quien lo prepara escribe el dato
    una vez y el sistema lo reparte.

    `estamento` recorta las columnas de matrícula que solo tiene el estudiante.
    """
    omitidas = _omitidas(estamento)
    vistas: list[str] = []
    conocidas: set[str] = set()
    for _grupo, _destino, columnas in GRUPOS:
        for columna in columnas:
            if columna not in conocidas and columna not in omitidas:
                conocidas.add(columna)
                vistas.append(columna)
    return vistas


def diccionario(estamento: str = ESTAMENTO_POR_DEFECTO) -> list[dict]:
    """
    El diccionario de columnas, grupo por grupo, para mostrarlo en pantalla.

    Cada columna se lista una sola vez, en el primer grupo donde aparece: es el
    mismo criterio que `columnas_ordenadas()`, así que lo que se ve en pantalla
    y lo que trae la plantilla descargada no pueden discrepar. El estamento
    recorta lo mismo en los dos sitios, por la misma razón.
    """
    omitidas = _omitidas(estamento)
    ya_listadas: set[str] = set()
    filas = []
    for grupo, destino, columnas in GRUPOS:
        propias = []
        for columna in columnas:
            if columna in ya_listadas or columna in omitidas:
                continue
            ya_listadas.add(columna)
            propias.append(
                {
                    "nombre": columna,
                    "obligatoria": columna in mapping.COLUMNAS_OBLIGATORIAS,
                    "alerta": columna in COLUMNAS_CON_ALERTA,
                }
            )
        if propias:
            filas.append({"grupo": grupo, "destino": destino, "columnas": propias})
    return filas


def total_columnas(estamento: str = ESTAMENTO_POR_DEFECTO) -> int:
    """Cuántas columnas distintas espera el archivo de ese estamento."""
    return len(columnas_ordenadas(estamento))


# Fila de ejemplo de la plantilla. Solo se llenan las columnas que ilustran algo
# —lo obligatorio, un formato de fecha, un sí/no—; el resto va en blanco a
# propósito, porque una plantilla con 157 valores inventados se copia tal cual.
# La cédula es válida según el módulo 10: una de ejemplo que no lo fuera haría
# que la primera prueba de carga de quien lea esto fallara sin motivo.
EJEMPLO = {
    "tipo_documento": "cedula",
    "cedula": "1104567894",
    "nombres": "María José",
    "apellidos": "Pérez Ríos",
    "fecha_nacimiento": "2003-03-15",
    "sexo": "Mujer",
    "genero": "Femenino",
    "celular": "0991234567",
    "facultad": "Facultad de la Salud Humana",
    "carrera": "Medicina",
    "nivel": "Tercero",
    "modalidad": "Presencial",
    "ciclo": "3",
    "estado": "Matriculado",
    "paralelo": "A",
    "jornada": "Matutina",
    "email_institucional": "mjperez@unl.edu.ec",
    "orientacion_sexual": "Heterosexual",
    "tipo_sangre": "O+",
    "discapacidad": "No",
    "estudiante_gestacion": "No",
    "estudiante_lactancia": "No",
    "estudiante_necesidades_educativas_especiales": "No",
    "ingreso_mensual": "450.00",
    "gastos_mensual_familia": "500.00",
}


def plantilla_csv(estamento: str = ESTAMENTO_POR_DEFECTO) -> str:
    """
    La plantilla del archivo: encabezados canónicos y una fila de ejemplo.

    Se genera, no se guarda como archivo estático, para que no pueda quedarse
    atrás del mapeo. Separador coma y codificación UTF-8, que es lo que el
    lector espera; el BOM lo añade la vista, porque lo necesita Excel y no el
    lector.
    """
    import csv
    import io

    columnas = columnas_ordenadas(estamento)
    buffer = io.StringIO()
    escritor = csv.DictWriter(buffer, fieldnames=columnas, extrasaction="ignore")
    escritor.writeheader()
    escritor.writerow({c: EJEMPLO.get(c, "") for c in columnas})
    return buffer.getvalue()


# ---------------------------------------------------------------- el padrón


# Por qué columnas se puede ordenar el padrón, y a qué campos corresponden.
#
# Una lista blanca y no el parámetro tal cual: `order_by()` acepta cualquier
# cadena, incluida la que recorra una relación hasta un campo que no debería
# poder consultarse desde aquí. Lo que no esté en este diccionario se ignora y
# se cae al orden por defecto.
#
# Cada una lleva su desempate por apellidos: sin él, dos filas con la misma
# facultad salen en un orden que PostgreSQL no garantiza entre página y página,
# y una persona puede aparecer dos veces o ninguna al pasar de la 1 a la 2.
ORDENES = {
    "nombre": ["persona__apellidos", "persona__nombres"],
    "cedula": ["persona__cedula"],
    "facultad": ["facultad", "persona__apellidos", "persona__nombres"],
    "carrera": ["carrera", "persona__apellidos", "persona__nombres"],
    "estamento": ["persona__tipo_vinculo", "persona__apellidos", "persona__nombres"],
    "ciclo": ["ciclo", "persona__apellidos", "persona__nombres"],
    "estado": ["estado", "persona__apellidos", "persona__nombres"],
    "periodo": ["periodo__fecha_inicio", "persona__apellidos", "persona__nombres"],
    "fecha": ["cargado_en", "persona__apellidos", "persona__nombres"],
}
ORDEN_POR_DEFECTO = "nombre"


def campos_de_orden(orden: str, descendente: bool) -> list[str]:
    """Traduce (columna, sentido) a lo que entiende `order_by`."""
    campos = ORDENES.get(orden) or ORDENES[ORDEN_POR_DEFECTO]
    if not descendente:
        return list(campos)
    # Solo se invierte la columna pedida: invertir también el desempate haría
    # que «facultad descendente» cambiara además el orden de los nombres dentro
    # de cada facultad, que no es lo que nadie pide al pulsar una cabecera.
    return [f"-{campos[0]}", *campos[1:]]


# Filtros de columna exacta que ofrece la pantalla. Clave del formulario ->
# campo. Lista blanca, igual que el orden: lo que no esté aquí no llega a la
# consulta.
FILTROS = {
    "facultad": "facultad",
    "carrera": "carrera",
    "nivel": "nivel",
    "modalidad": "modalidad",
    "jornada": "jornada",
    "estado": "estado",
    "ciclo": "ciclo",
    "paralelo": "paralelo",
    "sexo": "persona__sexo",
    # El estamento de la persona. La clave se llama como el concepto que la
    # Unidad reporta; el campo sigue siendo `tipo_vinculo`, que es donde vive.
    "estamento": "persona__tipo_vinculo",
}


def opciones_de_filtro() -> dict[str, list[str]]:
    """
    Los valores que EXISTEN en lo cargado, para cada filtro.

    Salen de la propia base y no de una lista escrita a mano: un desplegable con
    facultades que nadie cargó ofrece búsquedas que no devuelven nada, y omite
    las que sí están porque el archivo del período traía otro nombre.
    """
    from .models import DatoAcademico

    opciones = {}
    for clave, campo in FILTROS.items():
        valores = (
            DatoAcademico.objects.exclude(**{f"{campo}__in": ["", None]})
            .values_list(campo, flat=True)
            .distinct()
            .order_by(campo)
        )
        opciones[clave] = [v for v in valores if v]
    return opciones


def padron(
    texto: str = "",
    periodo_id=None,
    orden: str = ORDEN_POR_DEFECTO,
    descendente=False,
    filtros: dict | None = None,
):
    """
    Lo que quedó cargado, con su persona y su período.

    El texto busca a la vez en cédula, nombres, apellidos, correo, facultad,
    carrera, nivel, modalidad, jornada, estado y paralelo: quien busca «Medicina
    matutina» no tiene por qué saber en qué columna vive cada palabra. Se exigen
    TODAS las palabras, así que añadir una estrecha el resultado en vez de
    ensancharlo.

    `filtros` acota por columna exacta, que es otra cosa: el texto explora, el
    filtro delimita. Cada clave admite VARIOS valores: dentro de una columna son
    alternativas —«Energía o Salud Humana»—, y entre columnas se acumulan. Sin
    nada devuelve todo —quien administra necesita ver la carga completa— y la
    vista lo pagina.
    """
    from .models import DatoAcademico

    consulta = DatoAcademico.objects.select_related("persona", "periodo", "carga").order_by(
        *campos_de_orden(orden, descendente)
    )
    if periodo_id:
        consulta = consulta.filter(periodo_id=periodo_id)

    for clave, valores in (filtros or {}).items():
        campo = FILTROS.get(clave)
        if not campo or not valores:
            continue
        # Varios valores de la MISMA columna son alternativas: «Energía o
        # Salud Humana». Columnas distintas se acumulan y estrechan. Es lo que
        # se espera al marcar dos casillas en la misma lista y una en otra.
        if isinstance(valores, str):
            valores = [valores]
        valores = [v for v in valores if v]
        if valores:
            consulta = consulta.filter(**{f"{campo}__in": valores})

    texto = (texto or "").strip()
    if texto:
        for palabra in texto.split():
            consulta = consulta.filter(
                Q(persona__cedula__icontains=palabra)
                | Q(persona__nombres__icontains=palabra)
                | Q(persona__apellidos__icontains=palabra)
                | Q(email_institucional__icontains=palabra)
                | Q(facultad__icontains=palabra)
                | Q(carrera__icontains=palabra)
                | Q(nivel__icontains=palabra)
                | Q(modalidad__icontains=palabra)
                | Q(jornada__icontains=palabra)
                | Q(estado__icontains=palabra)
                | Q(paralelo__icontains=palabra)
            )
    return consulta


# ------------------------------------------------------------ autocompletado

# Con menos de tres caracteres la búsqueda por nombre devuelve medio padrón. La
# cédula se exceptúa más abajo: se busca completa o no se busca.
MINIMO_TEXTO = 3
LIMITE_SUGERENCIAS = 10


def sugerencias(texto: str, limite: int = LIMITE_SUGERENCIAS) -> list[dict]:
    """
    Candidatos para autocompletar, por cédula o por nombres.

    Si el texto son solo dígitos se trata como cédula y se busca por prefijo;
    si no, como nombre, exigiendo TODAS las palabras. Devuelve identificación y
    matrícula, jamás nada clínico ni el servicio que atiende a la persona.

    A diferencia de `resolver_por_cedula`, esto no escribe: teclear en una caja
    de autocompletado no puede abrirle expediente a nadie.
    """
    from apps.expediente.models import Persona

    texto = (texto or "").strip()
    if len(texto) < MINIMO_TEXTO:
        return []

    consulta = Persona.objects.all()
    if texto.replace("-", "").isdigit():
        consulta = consulta.filter(cedula__startswith=texto.replace("-", ""))
    else:
        for palabra in texto.split():
            consulta = consulta.filter(
                Q(nombres__icontains=palabra) | Q(apellidos__icontains=palabra)
            )

    consulta = consulta.prefetch_related("datos_academicos__periodo").order_by(
        "apellidos", "nombres"
    )[:limite]

    resultados = []
    for persona in consulta:
        # El más reciente por fecha de inicio del período: una persona puede
        # tener varias matrículas y la vigente es la que interesa precargar.
        dato = max(
            persona.datos_academicos.all(),
            key=lambda d: d.periodo.fecha_inicio,
            default=None,
        )
        resultados.append(
            {
                "cedula": persona.cedula,
                "nombres": persona.nombres,
                "apellidos": persona.apellidos,
                "nombre_completo": f"{persona.apellidos} {persona.nombres}".strip(),
                "fecha_nacimiento": (
                    persona.fecha_nacimiento.isoformat() if persona.fecha_nacimiento else ""
                ),
                "sexo": persona.sexo,
                "genero": persona.genero,
                "celular": persona.celular,
                "correo_institucional": persona.correo_institucional,
                "facultad": getattr(dato, "facultad", ""),
                "carrera": getattr(dato, "carrera", ""),
                "ciclo": getattr(dato, "ciclo", ""),
                "estado": getattr(dato, "estado", ""),
                "periodo": getattr(getattr(dato, "periodo", None), "codigo", ""),
            }
        )
    return resultados
