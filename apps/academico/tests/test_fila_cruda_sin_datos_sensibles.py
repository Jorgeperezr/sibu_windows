"""
La fila cruda guardaba en claro lo que el sistema decía cifrar.

La pantalla de carga anunciaba «Persona (cifrado)», «Ficha socioeconómica
(cifrado)» y «Beca (cifrado)», y SIBU no cifra nada: no hay dependencia de
cifrado ni custodia de claves. Esas columnas tampoco iban a ningún campo
propio. Quedaban, en claro, en `DatoAcademico.ficha_raw` —la fila completa—,
y el panel de administración la enseñaba entera: religión, orientación
sexual, violencia familiar, consumo de drogas y número de cuenta bancaria de
cada estudiante, a la vista de Administración General.

Becas ya había decidido «SIBU no almacena datos bancarios», y cada carga lo
desmentía.
"""

import importlib

import pandas as pd
import pytest
from django.urls import reverse

from apps.academico import mapping, selectors
from apps.academico.models import CargaInstitucional, DatoAcademico
from apps.academico.services import LectorFicha, ProcesadorCarga
from apps.core.models import PeriodoAcademico
from apps.expediente.models import AlertaClinica
from apps.usuarios.models import Rol, Usuario

CEDULA = "1104567894"
SENSIBLES = {
    "orientacion_sexual": "Bisexual",
    "religion": "Testigo de Jehová",
    "violencia_familiar": "Sí",
    "droga_consume": "Sí",
    "frecuencia_consumo_droga": "Semanal",
    "beca_unl_cuenta_banco": "Banco de Loja",
    "beca_unl_cuenta_tipo": "Ahorros",
    "beca_unl_cuenta_numero": "2904123456",
}


@pytest.fixture
def periodo(db):
    return PeriodoAcademico.objects.create(
        codigo="2026-1",
        nombre="Abril–Agosto 2026",
        fecha_inicio="2026-04-01",
        fecha_fin="2026-08-31",
        vigente=True,
    )


def _cargar(tmp_path, periodo, fila: dict, mapeo=None):
    ruta = tmp_path / "ficha.csv"
    base = {
        "cedula": CEDULA,
        "nombres": "María José",
        "apellidos": "Pérez Ríos",
        "carrera": "Medicina",
    }
    pd.DataFrame([{**base, **fila}]).to_csv(ruta, index=False)
    carga = CargaInstitucional.objects.create(
        periodo=periodo,
        nombre_archivo="ficha.csv",
        hash_archivo="x",
        formato="csv",
        mapeo_columnas=mapeo or {},
    )
    ProcesadorCarga(carga, mapeo or {}).procesar(LectorFicha(str(ruta), "csv"), aplicar=True)
    return DatoAcademico.objects.get(persona__cedula=CEDULA)


@pytest.mark.django_db
def test_la_fila_cruda_no_guarda_lo_sensible(tmp_path, periodo):
    dato = _cargar(tmp_path, periodo, SENSIBLES)

    guardado = set(dato.ficha_raw)
    assert not guardado & set(SENSIBLES), f"quedó en claro: {guardado & set(SENSIBLES)}"
    escrito = str(dato.ficha_raw)
    assert "2904123456" not in escrito, "el número de cuenta sigue en la base"
    assert "Testigo de Jehová" not in escrito


@pytest.mark.django_db
def test_lo_demas_de_la_fila_si_se_conserva(tmp_path, periodo):
    """Quitar lo sensible no puede vaciar la fila: sirve para reprocesar."""
    dato = _cargar(tmp_path, periodo, SENSIBLES)

    assert dato.ficha_raw["cedula"] == int(CEDULA) or str(dato.ficha_raw["cedula"]) == CEDULA
    assert dato.ficha_raw["carrera"] == "Medicina"


@pytest.mark.django_db
def test_las_alertas_siguen_saliendo(tmp_path, periodo):
    """
    Lo operativo no se pierde: violencia familiar avisa a Trabajo Social y el
    consumo a Psicología, porque se calculan leyendo la fila al cargar, no
    `ficha_raw`.
    """
    _cargar(tmp_path, periodo, SENSIBLES)

    # Los tipos son los de `mapping.REGLAS_ALERTA`: violencia familiar es
    # «social» (Trabajo Social) y el consumo, «riesgo» (Psicología).
    tipos = set(AlertaClinica.objects.values_list("tipo", flat=True))
    assert {"social", "riesgo"} <= tipos


@pytest.mark.django_db
def test_tambien_se_quitan_cuando_la_columna_viene_con_otro_nombre(tmp_path, periodo):
    """
    La base de cada estamento llama distinto a sus columnas. Quitar solo por
    el nombre canónico dejaría pasar la cuenta bancaria con el suyo.
    """
    dato = _cargar(
        tmp_path,
        periodo,
        {"NUM_CUENTA": "2904123456"},
        mapeo={"beca_unl_cuenta_numero": "NUM_CUENTA"},
    )

    assert "NUM_CUENTA" not in dato.ficha_raw
    assert "2904123456" not in str(dato.ficha_raw)


@pytest.mark.django_db
def test_el_panel_de_administracion_no_ensena_la_fila_cruda(tmp_path, periodo, client):
    dato = _cargar(tmp_path, periodo, {"ingreso_familiar": "450,50"})
    Usuario.objects.create_superuser(
        username="1100000007", password="clave-larga-12345", rol_principal=Rol.ADMIN_GENERAL
    )
    client.login(username="1100000007", password="clave-larga-12345")

    respuesta = client.get(reverse("admin:academico_datoacademico_change", args=[dato.pk]))

    assert respuesta.status_code == 200
    assert "ficha_raw" not in respuesta.content.decode()


def test_la_pantalla_de_carga_no_promete_un_cifrado_que_no_existe():
    destinos = " ".join(destino for _g, destino, _c in selectors.GRUPOS)

    assert "cifrado" not in destinos.lower()


def test_lo_que_no_se_conserva_es_exactamente_lo_que_se_anunciaba_protegido():
    """Si alguien añade una columna sensible a un grupo, tiene que añadirla aquí."""
    assert mapping.NO_SE_CONSERVAN == frozenset(
        [*mapping.IDENTIDAD_SENSIBLE, *mapping.FICHA_SENSIBLE, *mapping.DATOS_BANCARIOS]
    )


@pytest.mark.django_db
def test_la_migracion_limpia_lo_cargado_antes(tmp_path, periodo):
    """Sin ella, las filas cargadas antes de este arreglo lo conservan."""
    from django.apps import apps as registro

    carga = CargaInstitucional.objects.create(
        periodo=periodo,
        nombre_archivo="vieja.csv",
        hash_archivo="v",
        formato="csv",
        mapeo_columnas={"beca_unl_cuenta_numero": "NUM_CUENTA"},
    )
    from apps.expediente.models import Persona

    persona = Persona.objects.create(cedula=CEDULA, nombres="María José", apellidos="Pérez Ríos")
    dato = DatoAcademico.objects.create(
        persona=persona,
        periodo=periodo,
        carga=carga,
        ficha_raw={"cedula": CEDULA, "carrera": "Medicina", "religion": "X", "NUM_CUENTA": "29"},
    )

    migracion = importlib.import_module(
        "apps.academico.migrations.0004_fila_cruda_sin_datos_sensibles"
    )
    migracion.limpiar(registro, None)

    dato.refresh_from_db()
    assert dato.ficha_raw == {"cedula": CEDULA, "carrera": "Medicina"}
