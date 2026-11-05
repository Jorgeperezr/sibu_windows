"""Consultas de lectura del expediente (con filtrado RBAC)."""

from __future__ import annotations

from django.db.models import Q

from apps.usuarios.rbac import atenciones_visibles, servicios_del_usuario

from .models import AlertaClinica, Atencion, Expediente, Persona


def timeline(expediente: Expediente, usuario, break_glass: bool = False):
    """
    Línea de tiempo consolidada de todas las atenciones del expediente,
    filtrada por lo que el rol del usuario puede ver (informe 5.2 RF-EXP-02).
    """
    base = (
        Atencion.objects.filter(expediente=expediente)
        .select_related("servicio", "profesional", "profesional__usuario")
        .order_by("-fecha_hora")
    )
    return atenciones_visibles(usuario, base, break_glass=break_glass)


# Con menos de tres letras la consulta devuelve medio padrón: no es una
# búsqueda, es un volcado.
MINIMO_TEXTO = 3
LIMITE_RESULTADOS = 25


def buscar_personas(texto: str, limite: int = LIMITE_RESULTADOS):
    """
    Personas cuyo nombre o apellido contiene TODAS las palabras del texto.

    Solo lee: a diferencia de `resolver_por_cedula`, no consulta al proveedor
    académico ni crea nada. Buscar por nombre no debe materializar expedientes.

    Devuelve la persona y su expediente si lo tiene; nunca el servicio que la
    atiende, que es lo que delataría un paso por un servicio confidencial.
    """
    texto = (texto or "").strip()
    if len(texto) < MINIMO_TEXTO:
        return Persona.objects.none()

    consulta = Persona.objects.all()
    for palabra in texto.split():
        consulta = consulta.filter(Q(nombres__icontains=palabra) | Q(apellidos__icontains=palabra))
    return consulta.select_related("expediente").order_by("apellidos", "nombres")[:limite]


def alertas_activas(expediente: Expediente):
    return AlertaClinica.objects.filter(expediente=expediente, activa=True)


def resumen_expediente(expediente: Expediente, usuario, break_glass: bool = False):
    """Encabezado + alertas + conteo de atenciones visibles para el usuario."""
    atenciones = list(timeline(expediente, usuario, break_glass))
    # De qué atenciones puede derivar este usuario. Es la misma regla que aplica
    # `derivaciones.views.derivar` (solo desde un servicio propio): calcularla
    # aquí evita ofrecer un botón que respondería 403. Ver una atención por
    # break-glass no habilita derivar desde ella.
    mis_servicios = servicios_del_usuario(usuario)
    for atencion in atenciones:
        atencion.puede_derivar = atencion.servicio_id in mis_servicios
    return {
        "expediente": expediente,
        "persona": expediente.persona,
        "alertas": list(alertas_activas(expediente)),
        "atenciones": atenciones,
        "total_atenciones": len(atenciones),
    }


# ============================================================
# Valores efectivos: lo institucional, con los ajustes del servicio encima
# ============================================================


def _valor_institucional(expediente, variable: str, tipos_activos=None) -> str:
    """
    Lo que dice la matrícula sobre esa variable, como texto.

    Las cuatro condiciones —gestación, lactancia, enfermedad catastrófica y
    necesidad educativa especial— no son campos sino banderas: existen como
    `AlertaClinica` activa o no existen. Se traducen a «Sí»/«No» para poder
    compararlas con un ajuste, que sí es texto.
    """
    from .models import AjusteDeServicio

    V = AjusteDeServicio.Variable
    if variable == V.SEXO:
        return expediente.persona.sexo or ""
    if variable == V.GRUPO_SANGUINEO:
        return expediente.grupo_sanguineo or ""
    if variable == V.DISCAPACIDAD_TIPO:
        return expediente.discapacidad_tipo or ""
    if variable == V.DISCAPACIDAD_PORCENTAJE:
        porcentaje = expediente.discapacidad_porcentaje
        return "" if porcentaje is None else str(porcentaje)

    tipos = {V.GESTACION, V.LACTANCIA, V.ENF_CATASTROFICA, V.NEE}
    if variable in tipos:
        if tipos_activos is None:
            tipos_activos = _tipos_de_alerta_activos(expediente)
        return "Sí" if variable in tipos_activos else "No"
    return ""


def _tipos_de_alerta_activos(expediente) -> set[str]:
    """
    Los tipos de alerta activos del expediente, en UNA consulta.

    Antes cada una de las cuatro banderas preguntaba por su cuenta si existía:
    cuatro consultas casi iguales en cada apertura del expediente.
    """
    return set(
        AlertaClinica.objects.filter(expediente=expediente, activa=True).values_list(
            "tipo", flat=True
        )
    )


def valores_efectivos(expediente, servicio) -> list[dict]:
    """
    Cada variable ajustable con el valor que este servicio debe usar.

    El valor institucional salvo que el servicio haya anotado otro. Se devuelven
    los dos —`institucional` y `valor`— y de dónde sale cada uno, porque un
    dato corregido sin poder ver contra qué se corrigió no se puede revisar.

    Sin `servicio` (o desde uno que no ajustó nada) sale la foto de la
    matrícula tal cual.
    """
    from .models import AjusteDeServicio

    ajustes = {}
    if servicio is not None:
        ajustes = {
            a.variable: a
            for a in AjusteDeServicio.objects.filter(expediente=expediente, servicio=servicio)
        }

    tipos_activos = _tipos_de_alerta_activos(expediente)
    filas = []
    for codigo, etiqueta in AjusteDeServicio.Variable.choices:
        institucional = _valor_institucional(expediente, codigo, tipos_activos)
        ajuste = ajustes.get(codigo)
        filas.append(
            {
                "variable": codigo,
                "etiqueta": etiqueta,
                "institucional": institucional,
                "valor": ajuste.valor if ajuste else institucional,
                "ajustado": ajuste is not None,
                "nota": ajuste.nota if ajuste else "",
                "ajuste": ajuste,
            }
        )
    return filas


def expedientes_con_ajuste(servicio, variable: str, valor: str) -> set[int]:
    """
    Qué expedientes ajustó este servicio para esa variable con ese valor.

    Lo usa el informe estadístico: contar «embarazo» tiene que incluir lo que el
    servicio comprobó en consulta, no solo lo que se declaró al matricularse.
    """
    from .models import AjusteDeServicio

    return set(
        AjusteDeServicio.objects.filter(
            servicio=servicio, variable=variable, valor__iexact=valor
        ).values_list("expediente_id", flat=True)
    )
