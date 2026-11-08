"""
Al recetar, cruzar el medicamento con las alertas clínicas del expediente.

Traído de clinube (`apps/clinical/alertas.py`) y adaptado: allí las alertas
salían de los antecedentes escritos; en SIBU ya existen como `AlertaClinica`
(«Alergia: penicilina», la gestación, un riesgo), visibles en todo el
expediente. Lo que faltaba es que la consulta las mirara al recetar:
amoxicilina a una persona alérgica a la penicilina pasaba sin aviso.

Principios, porque esto es seguridad del paciente:

1. **Avisa, no decide.** La regla no conoce el caso: el profesional puede
   recetar igual, confirmándolo, y cada aviso dice de qué alerta salió.
2. **Sin IA ni servicios externos.** Reglas explícitas sobre texto
   normalizado (minúsculas, sin tildes), escritas aquí y probadas.
3. **Las negaciones no disparan.** «Niega alergias» o «sin alergia a la
   penicilina» no avisan de lo contrario: se descarta la frase que empieza
   negando.
4. **Se calcula una vez, en el servidor.** La pantalla recibe el aviso ya
   escrito en cada opción del desplegable; no repite las reglas en JavaScript.

Es una ayuda, no una guía clínica: cubre las interacciones más comunes y
debe revisarla el criterio del servicio.
"""

from __future__ import annotations

import re
import unicodedata

ALTO, MEDIO = "alto", "medio"


def normalizar(texto: str) -> str:
    t = unicodedata.normalize("NFD", (texto or "").lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


_NEGACION = re.compile(r"^\s*(niega|no\b|sin\b|ningun|ninguna|descarta|negativo|nada)")


def _fragmentos(texto: str):
    for trozo in re.split(r"[.;,\n]+", texto or ""):
        if trozo.strip() and not _NEGACION.match(normalizar(trozo)):
            yield trozo.strip()


def _buscar(texto: str, raices) -> str | None:
    for frase in _fragmentos(texto):
        n = normalizar(frase)
        if any(re.search(r"\b" + re.escape(r), n) for r in raices):
            return frase
    return None


PENICILINAS = ["penicilin", "amoxicilin", "ampicilin", "augmentin", "betalactam", "dicloxacilin"]
CEFALOSPORINAS = ["cefalexin", "cefadroxil", "cefuroxim", "ceftriaxon", "cefazolin", "cefalosporin"]
OTROS_ANTIBIOTICOS = [
    "clindamicin",
    "azitromicin",
    "eritromicin",
    "claritromicin",
    "metronidazol",
    "doxiciclin",
    "tetraciclin",
    "minociclin",
    "ciprofloxacin",
    "levofloxacin",
]
TETRACICLINAS = ["doxiciclin", "tetraciclin", "minociclin"]
AINE = [
    "ibuprofen",
    "naproxen",
    "diclofenac",
    "ketorolac",
    "aspirin",
    "acido acetilsalicilico",
    "ketoprofen",
    "dexketoprofen",
    "meloxicam",
    "celecoxib",
    "etoricoxib",
    "nimesulid",
    "piroxicam",
    "aine",
    "antiinflamatori",
]
ANTICOAGULANTES = [
    "warfarin",
    "acenocumarol",
    "sintrom",
    "rivaroxaban",
    "xarelto",
    "apixaban",
    "eliquis",
    "dabigatran",
    "pradaxa",
    "edoxaban",
    "heparin",
    "enoxaparin",
    "clopidogrel",
    "plavix",
    "ticagrelor",
    "prasugrel",
    "anticoagul",
    "antiagreg",
]
HEMORRAGICOS = ["hemofilia", "hemorrag", "coagulopat", "von willebrand", "trombocitopen"]
ANTIBIOTICO = ["antibiotic"]


def alertas_del_expediente(alertas) -> list[dict]:
    """
    Las alertas que importan al recetar, a partir de las `AlertaClinica`
    activas. Cada una: clave, titulo y fuente (la alerta tal como se escribió).
    """
    from apps.expediente.models import AlertaClinica

    salida: list[dict] = []
    claves: set[str] = set()

    def agregar(clave, titulo, fuente):
        if clave not in claves:
            claves.add(clave)
            salida.append({"clave": clave, "titulo": titulo, "fuente": fuente})

    for alerta in alertas:
        texto = alerta.descripcion or ""
        fuente = f"{alerta.get_tipo_display()}: «{texto}»"
        if alerta.tipo == AlertaClinica.Tipo.ALERGIA:
            if _buscar(texto, PENICILINAS):
                agregar("alergia_penicilina", "Alergia a penicilinas", fuente)
            elif _buscar(texto, ANTIBIOTICO):
                agregar("alergia_antibiotico", "Alergia a antibióticos sin especificar", fuente)
            if _buscar(texto, AINE):
                agregar("alergia_aine", "Alergia a antiinflamatorios (AINE)", fuente)
        elif alerta.tipo == AlertaClinica.Tipo.GESTACION:
            agregar("embarazo", "Gestación", fuente)
        elif alerta.tipo == AlertaClinica.Tipo.RIESGO:
            if _buscar(texto, ANTICOAGULANTES):
                agregar("anticoagulado", "Toma anticoagulantes o antiagregantes", fuente)
            elif _buscar(texto, HEMORRAGICOS):
                agregar("hemorragico", "Trastorno de la coagulación", fuente)
    return salida


REGLAS = [
    ("alergia_penicilina", PENICILINAS, ALTO, "es una penicilina y hay alergia a penicilinas"),
    (
        "alergia_penicilina",
        CEFALOSPORINAS,
        MEDIO,
        "es una cefalosporina: posible reacción cruzada con la alergia a penicilinas",
    ),
    (
        "alergia_antibiotico",
        PENICILINAS + CEFALOSPORINAS + OTROS_ANTIBIOTICOS,
        ALTO,
        "es un antibiótico y hay una alergia a antibióticos sin especificar cuál",
    ),
    ("alergia_aine", AINE, ALTO, "es un AINE y hay alergia a los AINE"),
    (
        "anticoagulado",
        AINE,
        ALTO,
        "es un AINE y la persona toma anticoagulante o antiagregante: riesgo de sangrado",
    ),
    ("hemorragico", AINE, MEDIO, "es un AINE y hay un trastorno de la coagulación"),
    ("embarazo", TETRACICLINAS, ALTO, "es una tetraciclina: contraindicada en la gestación"),
    ("embarazo", AINE, MEDIO, "es un AINE: evitarlo en la gestación, sobre todo al final"),
]


def choques(medicamento, alertas_receta: list[dict]) -> list[dict]:
    """Los choques de un medicamento con las alertas: nivel, texto y fuente."""
    presentes = {a["clave"]: a for a in alertas_receta}
    if not presentes:
        return []
    nombre = " ".join(
        filter(
            None, [getattr(medicamento, "dci", ""), getattr(medicamento, "nombre_comercial", "")]
        )
    )
    n = normalizar(nombre)
    salida, vistos = [], set()
    for clave, raices, nivel, mensaje in REGLAS:
        if clave in presentes and clave not in vistos:
            if any(re.search(r"\b" + re.escape(r), n) for r in raices):
                vistos.add(clave)
                salida.append(
                    {
                        "nivel": nivel,
                        "texto": f"{nombre.strip()} {mensaje}.",
                        "fuente": presentes[clave]["fuente"],
                    }
                )
    return salida


def aviso(choques_: list[dict]) -> str:
    """Los choques en una frase, para el desplegable y para el mensaje."""
    return " ".join(f"{c['texto']} ({c['fuente']})" for c in choques_)
