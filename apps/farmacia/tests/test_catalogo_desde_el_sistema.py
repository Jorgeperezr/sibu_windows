"""
El catálogo de Farmacia y el de Laboratorio nacían vacíos.

Solo los datos de demostración los llenaban. En un despliegue real —una
portable, o un servidor preparado con `--sin-demo`— no había ni un
medicamento ni un examen: Medicina abría la consulta y el desplegable de la
receta decía «—», el de exámenes estaba en blanco, y no había pantalla para
remediarlo. Farmacia podía ingresar lotes de un medicamento que YA existiera.
Lo único que quedaba era el panel de administración de Django, al que el
personal de Farmacia y de Laboratorio no tiene acceso.

Comprobado ejercitándolo: una portable recién preparada tenía 56 códigos
CIE-10, 0 medicamentos y 0 exámenes.
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from apps.auditoria.models import LogAuditoria
from apps.core.models import Servicio
from apps.expediente.tests.factories import crear_estructura, crear_profesional
from apps.farmacia import services as farmacia
from apps.farmacia.models import Medicamento
from apps.laboratorio import services as laboratorio
from apps.laboratorio.models import Examen
from apps.usuarios.models import Rol

CLAVE = "clave-larga-12345"


def _profesional(username, codigo, nombre, rol):
    est = crear_estructura()
    servicio, _ = Servicio.objects.get_or_create(
        codigo=codigo, defaults={"nombre": nombre, "seccion": est["salud"]}
    )
    usuario, perfil = crear_profesional(username, servicio, est["salud"], rol=rol)
    usuario.set_password(CLAVE)
    usuario.save()
    return usuario, perfil


# --------------------------------------------------------------- farmacia


@pytest.mark.django_db
def test_farmacia_da_de_alta_un_medicamento_desde_su_pantalla(client):
    _profesional("farm", "farmacia", "Farmacia", Rol.FARMACIA)
    client.login(username="farm", password=CLAVE)

    respuesta = client.post(
        reverse("farmacia:inventario"),
        {
            "accion": "nuevo_medicamento",
            "codigo": "pct500",
            "dci": "Paracetamol",
            "concentracion": "500 mg",
            "forma_farmaceutica": "Tableta",
            "stock_minimo": "",
            "requiere_receta": "1",
        },
        follow=True,
    )

    medicamento = Medicamento.objects.get()
    assert medicamento.codigo == "PCT500"
    assert medicamento.stock_minimo == 0, "un stock mínimo en blanco es cero, no un error"
    assert "ya está en el catálogo" in respuesta.content.decode()
    assert LogAuditoria.objects.filter(entidad="Medicamento").exists()


@pytest.mark.django_db
def test_el_codigo_no_se_repite_aunque_cambien_las_mayusculas(db):
    farmacia.registrar_medicamento(codigo="PCT500", dci="Paracetamol")

    with pytest.raises(ValidationError, match="Ya hay"):
        farmacia.registrar_medicamento(codigo="pct500", dci="Paracetamol")


@pytest.mark.django_db
def test_sin_principio_activo_no_hay_medicamento(db):
    with pytest.raises(ValidationError, match="DCI"):
        farmacia.registrar_medicamento(codigo="X1", dci="  ")


@pytest.mark.django_db
def test_con_el_catalogo_vacio_la_pantalla_lo_dice(client):
    _profesional("farm", "farmacia", "Farmacia", Rol.FARMACIA)
    client.login(username="farm", password=CLAVE)

    contenido = client.get(reverse("farmacia:inventario")).content.decode()

    assert "El catálogo está vacío" in contenido
    assert 'value="nuevo_medicamento"' in contenido


@pytest.mark.django_db
def test_solo_farmacia_toca_su_catalogo(client):
    # El servicio tiene que existir: si no, la vista da 404 antes de mirar el
    # permiso y la prueba no comprobaría nada.
    _profesional("farm", "farmacia", "Farmacia", Rol.FARMACIA)
    _profesional("medica", "medicina", "Medicina", Rol.PROFESIONAL)
    client.login(username="medica", password=CLAVE)

    respuesta = client.post(
        reverse("farmacia:inventario"),
        {"accion": "nuevo_medicamento", "codigo": "X", "dci": "Y"},
    )

    assert respuesta.status_code == 403
    assert not Medicamento.objects.exists()


# ------------------------------------------------------------ laboratorio


@pytest.mark.django_db
def test_laboratorio_da_de_alta_un_examen_con_rangos_con_coma(client):
    _profesional("lab", "laboratorio-clinico", "Laboratorio Clínico", Rol.LABORATORIO)
    client.login(username="lab", password=CLAVE)

    respuesta = client.post(
        reverse("laboratorio:catalogo"),
        {
            "codigo": "bh",
            "nombre": "Biometría hemática",
            "perfil": "Hematología",
            "param-0-nombre": "Hemoglobina",
            "param-0-unidad": "g/dL",
            "param-0-ref_min": "12",
            "param-0-ref_max": "15,5",
            "param-1-nombre": "",  # fila en blanco: se ignora
        },
        follow=True,
    )

    examen = Examen.objects.get()
    parametro = examen.parametros.get()
    assert (examen.codigo, parametro.nombre, str(parametro.ref_max)) == (
        "BH",
        "Hemoglobina",
        "15.500",
    )
    contenido = respuesta.content.decode()
    assert "Medicina puede pedirlo" in contenido
    assert "Hemoglobina" in contenido, "lo creado tiene que aparecer en la lista"


@pytest.mark.django_db
def test_un_examen_sin_parametros_no_se_crea(db):
    with pytest.raises(ValidationError, match="al menos un parámetro"):
        laboratorio.registrar_examen(codigo="X", nombre="Vacío", parametros=[{"nombre": " "}])
    assert not Examen.objects.exists()


@pytest.mark.django_db
def test_un_rango_al_reves_se_rechaza_entero(db):
    """
    Y no deja el examen creado a medias, sin el parámetro que falló.

    Lo que esto protege es el ORDEN: el servicio lee y valida todos los
    parámetros antes de escribir nada. Al falsificar quitando la transacción
    no falló, porque no es ella la que lo evita.
    """
    with pytest.raises(ValidationError, match="mayor que el máximo"):
        laboratorio.registrar_examen(
            codigo="GLU",
            nombre="Glucosa",
            parametros=[{"nombre": "Glucosa", "ref_min": "110", "ref_max": "70"}],
        )
    assert not Examen.objects.exists()


@pytest.mark.django_db
def test_un_rango_ilegible_se_dice(db):
    with pytest.raises(ValidationError):
        laboratorio.registrar_examen(
            codigo="GLU",
            nombre="Glucosa",
            parametros=[{"nombre": "Glucosa", "ref_min": "setenta"}],
        )


@pytest.mark.django_db
def test_la_bandeja_enlaza_el_catalogo(client):
    _profesional("lab", "laboratorio-clinico", "Laboratorio Clínico", Rol.LABORATORIO)
    client.login(username="lab", password=CLAVE)

    contenido = client.get(reverse("laboratorio:bandeja")).content.decode()

    assert reverse("laboratorio:catalogo") in contenido


@pytest.mark.django_db
def test_solo_laboratorio_toca_su_catalogo(client):
    _profesional("lab", "laboratorio-clinico", "Laboratorio Clínico", Rol.LABORATORIO)
    _profesional("medica", "medicina", "Medicina", Rol.PROFESIONAL)
    client.login(username="medica", password=CLAVE)

    assert client.get(reverse("laboratorio:catalogo")).status_code == 403
