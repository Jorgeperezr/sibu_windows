"""Validaciones de datos institucionales (cédula ecuatoriana, correo, números)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from apps.core import numeros


def validar_cedula_ecuatoriana(cedula: str) -> bool:
    """
    Valida una cédula ecuatoriana (10 dígitos) con el algoritmo módulo 10.

    Reglas: los dos primeros dígitos son la provincia (01-24 o 30 para
    extranjeros), el tercero < 6 para personas naturales, y el último es el
    dígito verificador calculado sobre los 9 anteriores.
    """
    if cedula is None:
        return False
    cedula = str(cedula).strip()
    if len(cedula) != 10 or not cedula.isdigit():
        return False

    provincia = int(cedula[:2])
    if not (1 <= provincia <= 24 or provincia == 30):
        return False
    if int(cedula[2]) >= 6:
        return False

    coeficientes = [2, 1, 2, 1, 2, 1, 2, 1, 2]
    total = 0
    for coef, digito in zip(coeficientes, cedula[:9], strict=False):
        producto = coef * int(digito)
        total += producto - 9 if producto > 9 else producto
    verificador = (10 - (total % 10)) % 10
    return verificador == int(cedula[9])


def normalizar_cedula(cedula) -> str:
    """
    Limpia una cédula: elimina espacios y rellena con ceros a la izquierda
    si perdió el 0 inicial (Excel suele convertirla a número).
    """
    if cedula is None:
        return ""
    texto = str(cedula).strip().replace("-", "").replace(" ", "")
    # Excel suele eliminar el 0 inicial y convertir a número: 12345678.0
    if texto.endswith(".0"):
        texto = texto[:-2]
    if texto.isdigit() and len(texto) == 9:
        texto = "0" + texto
    return texto


def validar_correo_institucional(correo: str, dominio: str) -> bool:
    """Verifica que el correo pertenezca al dominio institucional (p. ej. unl.edu.ec)."""
    if not correo:
        return False
    correo = str(correo).strip().lower()
    return "@" in correo and correo.endswith("@" + dominio.lower())


def a_decimal(valor) -> Decimal:
    """
    Un monto de la ficha, o 0 si la celda trae texto descriptivo.

    Borraba la coma antes de leer —`.replace(",", "")`—, tratándola como
    separador de miles. Aquí la coma es el separador DECIMAL, así que
    «450,50» entraba como 45050: cien veces el ingreso declarado, en silencio,
    alimentando el puntaje que orienta una beca. La lectura vive ahora en
    `core.numeros`, una sola para todo el sistema.

    Se conserva el 0 por defecto —y no `None`— porque estas celdas se suman y
    porque una fila no puede abortar la carga entera por traer «no aplica» en
    una columna de monto. Lo que sí cambia es que el motor de carga ANOTA lo
    que no pudo leer y lo que admite dos lecturas, en vez de tragárselo.
    """
    return numeros.a_decimal_o(valor, Decimal("0"))


def a_fecha(valor):
    """Normaliza fechas de nacimiento en varios formatos comunes; None si falla."""
    if valor in (None, ""):
        return None
    if isinstance(valor, date | datetime):
        return valor.date() if isinstance(valor, datetime) else valor
    # Espacios repetidos fuera: «14  04 2001» es la misma fecha.
    texto = " ".join(str(valor).split())
    # «14 04 2001» y «14.04.2001» son como la base de estudiantes de la UNL
    # escribe la fecha de nacimiento: sin ellos, cada fecha quedaba vacía sin
    # aviso y la edad no se podía calcular.
    for fmt in (
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d %m %Y",
        "%d.%m.%Y",
        "%Y/%m/%d",
        "%m/%d/%Y",
    ):
        try:
            return datetime.strptime(texto, fmt).date()
        except ValueError:
            continue
    return None


def normalizar_encabezado(nombre) -> str:
    """
    El encabezado de una columna como lo espera el mapeo: minúsculas, sin
    tildes y con guion bajo en lugar de espacios.

    La base de estudiantes de la UNL llega con los encabezados en MAYÚSCULAS
    (`CEDULA`, `NOMBRES`): sin esto, cada fila salía rechazada por «cédula,
    nombres y apellidos vacíos» aunque estuvieran escritos. El guion se
    conserva: `trabajo_telefono-2` es un nombre canónico.
    """
    import unicodedata

    texto = unicodedata.normalize("NFD", str(nombre or "").strip().lower())
    texto = "".join(c for c in texto if unicodedata.category(c) != "Mn")
    return "_".join(texto.split())


def telefono_o_vacio(valor) -> str:
    """
    El teléfono, o cadena vacía si no hay ninguno de verdad.

    «000000000» es lo que se escribe en la ficha cuando no hay teléfono: como
    dato parece un número y no se puede llamar a él. Un vacío nunca borra el que
    ya estaba (ver `ProcesadorCarga.DE_CONTACTO`).
    """
    texto = str(valor or "").strip()
    digitos = "".join(c for c in texto if c.isdigit())
    if not digitos or set(digitos) == {"0"}:
        return ""
    return texto


GRUPOS_SANGUINEOS = ("A+", "A-", "B+", "B-", "AB+", "AB-", "O+", "O-")


def normalizar_grupo_sanguineo(valor) -> str | None:
    """
    «A Rh+», «ARH+», «A positivo», «0+» → «A+», «O+»; None si no se reconoce.

    El campo del expediente admite 5 caracteres y la base escribe el tipo de
    sangre de muchas maneras: «A Rh+» cabía justo y entraba tal cual, «O RH +»
    se cortaba y quedaba «O RH », y el mismo grupo salía en varias filas al
    contarlo. Lo que no se reconoce no se adivina: la fila cruda lo conserva.
    """
    import re

    texto = str(valor or "").upper().replace("POSITIVO", "+").replace("NEGATIVO", "-")
    texto = re.sub(r"FACTOR|RH|[\s.()]", "", texto)
    texto = re.sub(r"^0", "O", texto)
    return texto if texto in GRUPOS_SANGUINEOS else None
