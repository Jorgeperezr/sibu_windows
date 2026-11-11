"""
La base de estudiantes tal como la entrega la UNL (63 columnas).

`FILA` reproduce el FORMATO de la fila de ejemplo que mandó la Unidad, con los
datos personales sustituidos por ficticios —la de la Unidad era de una persona
real y no va a un repositorio—: encabezados en MAYÚSCULAS, la fecha escrita
«14 04 2001», el tipo de sangre «A Rh+», un teléfono «000000000» y cuatro
columnas que el sistema no conocía (enfermedad catastrófica, enfermedad rara o
huérfana y si necesita ayuda de Bienestar).
"""

from datetime import date
from pathlib import Path

import pytest

from apps.academico.models import CargaInstitucional, DatoAcademico
from apps.academico.services import LectorFicha, ProcesadorCarga
from apps.core.models import PeriodoAcademico
from apps.expediente.models import AlertaClinica, Expediente, Persona

CEDULA = "1100000007"  # de prueba: pasa el módulo 10

ENCABEZADOS = (
    "TIPO_DOCUMENTO CEDULA NOMBRES APELLIDOS FECHA_NACIMIENTO SEXO GENERO CELULAR TELEFONO "
    "FACULTAD CARRERA NIVEL MODALIDAD CICLO OFERTA_ACADEMICA PARALELO JORNADA "
    "EMAIL_INSTITUCIONAL ORIENTACION_SEXUAL ETNIA NACIONALIDAD_INDIGENA RELIGION TIPO_SANGRE "
    "PAIS_PROCEDENCIA PROVINCIA_PROCEDENCIA CANTON_PROCEDENCIA PARROQUIA_PROCEDENCIA "
    "BARRIO_PROCEDENCIA DIRECCION_PROCEDENCIA REPRESENTANTE_NOMBRES REPRESENTANTE_DIRECCION "
    "REPRESENTANTE_REFERENCIA REPRESENTANTE_TELEFONO RESPONSABLE_PERSONA PAIS_ACTUAL "
    "PROVINCIA_ACTUAL CANTON_ACTUAL PARROQUIA_ACTUAL BARRIO_ACTUAL CALLE_PRINCIPAL_ACTUAL "
    "CALLE_SECUNDARIA_ACTUAL REFERENCIA_ACTUAL NUMERO_CASA_ACTUAL ZONA_ACTUAL "
    "ESTUDIANTE_NECESIDADES_EDUCATIVAS_ESPECIALES ESTUDIANTE_PROBLEMA_SALUD "
    "ESTUDIANTE_SALUD_DIAGNOSTICO TIENE_ENFERMEDAD_CATASTROFICA ENFERMEDADES_CATASTROFICAS "
    "TIENE_ENFERMEDAD_RARA_HUERFANA NECESITA_AYUDA_BIENESTAR ESTUDIANTE_COVID DISCAPACIDAD "
    "DISCAPACIDAD_TIPO DISCAPACIDAD_PORCENTAJE DISCAPACIDAD_GRADO DROGA_CONSUME "
    "FRECUENCIA_CONSUMO_DROGA ESTUDIANTE_GESTACION ESTUDIANTE_LACTANCIA "
    "ESTUDIANTE_VACUNAS_COVID ESTUDIANTE_VACUNAS_HEPATITIS ESTUDIANTE_VACUNAS_TETANOS"
).split()

FILA = [
    "Cedula",
    CEDULA,
    "CARLOS ANDRÉS",
    "PRUEBA FICTICIO",
    "14 04 2001",
    "hombre",
    "masculino",
    "0999000111",
    "000000000",
    "FARNR",
    "AGRONOMÍA",
    "DE GRADO REGIMEN 2019",
    "presencial",
    "1",
    "septiembre 2026 - marzo 2027",
    "A",
    "matutino",
    "carlos.prueba@unl.edu.ec",
    "Heterosexual",
    "Mestizo",
    "No Aplica",
    "católica",
    "A Rh+",
    "Ecuador",
    "LOJA",
    "LOJA",
    "SAN SEBASTIAN",
    "Barrio de prueba",
    "Calle A y Calle B",
    "Representante Ficticio",
    "Calle A y Calle B",
    "Referencia de prueba",
    "0999000222",
    "",
    "Ecuador",
    "LOJA",
    "LOJA",
    "PUNZARA",
    "Barrio de prueba",
    "Calle A",
    "Calle B",
    "Referencia de prueba",
    "s/n",
    "Sur",
    "Ninguna",
    "No",
    "",
    "No",
    "",
    "No",
    "No",
    "No",
    "No",
    "",
    "0",
    "",
    "",
    "",
    "No",
    "No",
    "2",
    "1",
    "1",
]


@pytest.fixture
def ejemplo(tmp_path):
    import csv

    assert len(ENCABEZADOS) == len(FILA) == 63
    ruta = tmp_path / "estudiantes_unl.csv"
    with open(ruta, "w", newline="", encoding="utf-8") as f:
        escritor = csv.writer(f)
        escritor.writerow(ENCABEZADOS)
        escritor.writerow(FILA)
    return ruta


@pytest.fixture
def periodo(db):
    return PeriodoAcademico.objects.create(
        codigo="2026-2",
        nombre="Septiembre 2026 – Marzo 2027",
        fecha_inicio="2026-09-01",
        fecha_fin="2027-03-31",
        vigente=True,
    )


def _cargar(periodo, ruta):
    carga = CargaInstitucional.objects.create(
        periodo=periodo,
        estamento=Persona.TipoVinculo.ESTUDIANTE,
        nombre_archivo=Path(ruta).name,
        hash_archivo="x",
        formato="csv",
    )
    return ProcesadorCarga(carga).procesar(LectorFicha(str(ruta), "csv"), aplicar=True)


def test_la_fila_de_la_unl_entra_con_sus_encabezados_en_mayusculas(periodo, ejemplo):
    resultado = _cargar(periodo, ejemplo)

    assert resultado.errores == 0, resultado.detalle_errores
    persona = Persona.objects.get(cedula=CEDULA)
    assert persona.nombres == "CARLOS ANDRÉS" and persona.apellidos == "PRUEBA FICTICIO"
    assert persona.celular == "0999000111"
    assert persona.correo_institucional == "carlos.prueba@unl.edu.ec"
    dato = DatoAcademico.objects.get(persona=persona)
    assert (dato.facultad, dato.carrera, dato.ciclo, dato.paralelo) == (
        "FARNR",
        "AGRONOMÍA",
        "1",
        "A",
    )


def test_la_fecha_escrita_con_espacios_se_lee(periodo, ejemplo):
    _cargar(periodo, ejemplo)
    assert Persona.objects.get(cedula=CEDULA).fecha_nacimiento == date(2001, 4, 14)


def test_un_telefono_de_ceros_es_ausencia_de_dato(periodo, ejemplo):
    """«000000000» es lo que se escribe cuando no hay teléfono: guardarlo
    dejaría un número al que no se puede llamar con apariencia de dato."""
    _cargar(periodo, ejemplo)
    assert Persona.objects.get(cedula=CEDULA).telefono == ""


def test_el_tipo_de_sangre_se_escribe_de_una_sola_manera(periodo, ejemplo):
    _cargar(periodo, ejemplo)
    assert Expediente.objects.get(persona__cedula=CEDULA).grupo_sanguineo == "A+"


def test_con_todo_negado_no_se_enciende_ninguna_alerta(periodo, ejemplo):
    """«Ninguna», «No», «0» y «No Aplica»: ninguna alerta."""
    resultado = _cargar(periodo, ejemplo)
    assert resultado.alertas_generadas == 0
    assert not AlertaClinica.objects.exists()


def _cargar_fila(periodo, tmp_path, codigo, **columnas):
    import pandas as pd

    from apps.core.models import PeriodoAcademico

    otro = PeriodoAcademico.objects.get_or_create(
        codigo=codigo,
        defaults={"nombre": codigo, "fecha_inicio": "2027-04-01", "fecha_fin": "2027-08-31"},
    )[0]
    ruta = tmp_path / f"{codigo}.csv"
    base = {"CEDULA": CEDULA, "NOMBRES": "CARLOS ANDRÉS", "APELLIDOS": "PRUEBA FICTICIO"}
    pd.DataFrame([{**base, **columnas}]).to_csv(ruta, index=False)
    return _cargar(otro, ruta)


def _activas():
    return set(AlertaClinica.objects.filter(activa=True).values_list("tipo", "descripcion"))


def test_la_enfermedad_catastrofica_entra_con_su_detalle_y_cuenta_en_el_informe(periodo, tmp_path):
    """El informe estadístico cuenta «enfermedad catastrófica» por la alerta de
    ese tipo, y ninguna columna de la carga la creaba: siempre salía «No»."""
    _cargar_fila(
        periodo,
        tmp_path,
        "2026-2",
        TIENE_ENFERMEDAD_CATASTROFICA="Sí",
        ENFERMEDADES_CATASTROFICAS="Insuficiencia renal crónica",
    )
    assert (
        "enf_catastrofica",
        "Enfermedad catastrófica declarada en matrícula: Insuficiencia renal crónica",
    ) in _activas()


def test_rara_o_huerfana_y_pedir_ayuda_avisan_a_quien_corresponde(periodo, tmp_path):
    _cargar_fila(
        periodo,
        tmp_path,
        "2026-2",
        TIENE_ENFERMEDAD_RARA_HUERFANA="Sí",
        NECESITA_AYUDA_BIENESTAR="Sí",
    )
    activas = _activas()
    assert ("riesgo", "Enfermedad rara o huérfana declarada en matrícula") in activas
    assert ("social", "Pide ayuda de Bienestar en la matrícula") in activas


def test_el_no_de_una_columna_no_apaga_la_alerta_de_otra(periodo, tmp_path):
    """Discapacidad y consumo comparten el tipo «riesgo». Una recarga con
    «discapacidad: No» apagaba TODAS las alertas de riesgo de la matrícula —la
    de consumo incluida—, y como `get_or_create` encontraba la apagada, la de
    consumo no volvía a encenderse aunque el archivo la siguiera declarando."""
    _cargar_fila(periodo, tmp_path, "2026-2", DISCAPACIDAD="Visual", DROGA_CONSUME="Sí")
    _cargar_fila(periodo, tmp_path, "2027-1", DISCAPACIDAD="No", DROGA_CONSUME="Sí")

    activas = _activas()
    assert ("riesgo", "Consumo declarado en matrícula") in activas
    assert not any(d.startswith("Discapacidad declarada") for _, d in activas)


def test_lo_negado_en_un_periodo_y_declarado_en_el_siguiente_vuelve(periodo, tmp_path):
    _cargar_fila(periodo, tmp_path, "2026-2", NECESITA_AYUDA_BIENESTAR="Sí")
    _cargar_fila(periodo, tmp_path, "2027-1", NECESITA_AYUDA_BIENESTAR="No")
    assert not _activas()
    _cargar_fila(periodo, tmp_path, "2027-2", NECESITA_AYUDA_BIENESTAR="Sí")
    assert ("social", "Pide ayuda de Bienestar en la matrícula") in _activas()


def test_negar_el_consumo_no_apaga_la_discapacidad(periodo, tmp_path):
    """El mismo cruce en el otro orden: la negación del consumo va después de
    la discapacidad en las reglas, así que nada la vuelve a encender."""
    _cargar_fila(periodo, tmp_path, "2026-2", DISCAPACIDAD="Visual", DROGA_CONSUME="Sí")
    _cargar_fila(periodo, tmp_path, "2027-1", DISCAPACIDAD="Visual", DROGA_CONSUME="No")

    activas = _activas()
    assert ("riesgo", "Discapacidad declarada: Visual") in activas
    assert ("riesgo", "Consumo declarado en matrícula") not in activas


def test_la_salud_declarada_queda_en_el_expediente_y_un_vacio_no_la_borra(
    periodo, tmp_path, ejemplo
):
    _cargar(periodo, ejemplo)
    salud = Expediente.objects.get(persona__cedula=CEDULA).salud_declarada
    assert salud["estudiante_vacunas_covid"] == "2"
    assert salud["tiene_enfermedad_catastrofica"] == "No"

    _cargar_fila(periodo, tmp_path, "2027-1", ESTUDIANTE_VACUNAS_COVID="3")
    salud = Expediente.objects.get(persona__cedula=CEDULA).salud_declarada
    assert salud["estudiante_vacunas_covid"] == "3", "lo que cambia se actualiza"
    assert salud["estudiante_vacunas_tetanos"] == "1", "lo que viene vacío no se borra"


def test_la_salud_declarada_la_ven_salud_y_no_becas(periodo, ejemplo):
    from django.test import Client
    from django.urls import reverse

    from apps.core.models import Seccion, Servicio
    from apps.expediente.tests.factories import crear_estructura, crear_profesional

    _cargar(periodo, ejemplo)
    expediente = Expediente.objects.get(persona__cedula=CEDULA)
    expediente.salud_declarada = {"estudiante_salud_diagnostico": "Asma bronquial"}
    expediente.save()
    est = crear_estructura()
    becas = Servicio.objects.create(
        codigo="becas-y-ayudas-economicas",
        nombre="Becas",
        seccion=Seccion.objects.create(codigo="becas", nombre="Becas"),
    )
    vistas = {}
    for usuario, servicio in (("medica_sd", est["medicina"]), ("becas_sd", becas)):
        cuenta, _ = crear_profesional(usuario, servicio, servicio.seccion)
        cuenta.set_password("clave-larga-12345")
        cuenta.save()
        cliente = Client()
        cliente.login(username=usuario, password="clave-larga-12345")
        vistas[usuario] = cliente.get(
            reverse("expediente:detalle", args=[expediente.pk])
        ).content.decode()

    assert "Asma bronquial" in vistas["medica_sd"]
    assert "Asma bronquial" not in vistas["becas_sd"]
