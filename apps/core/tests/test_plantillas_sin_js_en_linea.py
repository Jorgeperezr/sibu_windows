"""
Ninguna plantilla lleva JavaScript en línea.

La CSP de producción es `script-src 'self'`: el navegador ejecuta los
archivos de /static/ y NADA de lo escrito dentro de la página. En desarrollo
no hay CSP, así que todo parecía funcionar; en el servidor, las confirmaciones
(«¿Cerrar la atención?») no salían y la acción se ejecutaba sin preguntar, la
ventanilla no cargaba los turnos, el odontograma mandaba la pieza vacía y el
panel de firma no se enteraba de que el documento ya estaba firmado.

El comportamiento va en `static/js/` y se pide con atributos `data-*`
(`data-confirmar`, `data-enviar-al-cambiar`, `data-pedir`, `data-copiar-a`).
"""

import re
from pathlib import Path

from django.conf import settings

PLANTILLAS = Path(settings.BASE_DIR) / "templates"
SCRIPT_EN_LINEA = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>", re.IGNORECASE)
MANEJADOR_EN_LINEA = re.compile(r"\son[a-z]+\s*=\s*[\"']", re.IGNORECASE)
URL_JAVASCRIPT = re.compile(r"href\s*=\s*[\"']\s*javascript:", re.IGNORECASE)


def _plantillas():
    return sorted(PLANTILLAS.rglob("*.html"))


def test_hay_plantillas_que_revisar():
    assert len(_plantillas()) > 50


def test_ninguna_plantilla_lleva_script_en_linea():
    culpables = [
        f"{p.relative_to(PLANTILLAS)}: {m.group(0)}"
        for p in _plantillas()
        for m in SCRIPT_EN_LINEA.finditer(p.read_text(encoding="utf-8"))
    ]
    assert not culpables, culpables


def test_ninguna_plantilla_lleva_manejadores_en_linea():
    culpables = []
    for p in _plantillas():
        texto = p.read_text(encoding="utf-8")
        for patron in (MANEJADOR_EN_LINEA, URL_JAVASCRIPT):
            culpables += [
                f"{p.relative_to(PLANTILLAS)}: {m.group(0)}" for m in patron.finditer(texto)
            ]
    assert not culpables, culpables


def test_los_scripts_que_piden_las_plantillas_existen():
    pedidos = set()
    for p in _plantillas():
        pedidos |= set(re.findall(r"estatico '(js/[^']+)'", p.read_text(encoding="utf-8")))
    faltan = [r for r in pedidos if not (Path(settings.BASE_DIR) / "static" / r).exists()]
    assert pedidos and not faltan, faltan


# Lo que imprime WeasyPrint no pasa por la CSP del navegador; la página 500
# trae su estilo dentro porque, si falló el servidor, quizá fallen los estáticos.
A_PAPEL = {"informe_atencion.html", "base_pdf.html", "500.html"}


def test_ninguna_pantalla_lleva_estilos_en_linea():
    """`style-src 'self'` también descarta `style="..."`: el lienzo de marcar
    fotos perdía `touch-action:none` y en una tableta no se podía dibujar."""
    culpables = []
    for p in _plantillas():
        if p.name in A_PAPEL or p.name.endswith("_pdf.html"):
            continue
        texto = p.read_text(encoding="utf-8")
        culpables += [
            f"{p.relative_to(PLANTILLAS)}: {m.group(0)}"
            for m in re.finditer(r"\sstyle\s*=\s*[\"'][^\"']*[\"']|<style\b", texto)
        ]
    assert not culpables, culpables
