"""
Documentos del expediente: subir, escanear, ver, marcar y retirar.

Traído de clinube. Lo que no se negocia, y es lo primero que se prueba: un
documento de Psicología no sale de Psicología. Ni el archivo, ni su nombre en
la lista, ni en el panel de administración.
"""

import io

import pytest
from django.urls import reverse
from PIL import Image

from apps.auditoria.models import LogAuditoria
from apps.documentos import services
from apps.documentos.models import DocumentoAnexo
from apps.expediente.tests.factories import crear_estructura, crear_expediente, crear_profesional
from apps.usuarios.models import Rol, Usuario

CLAVE = "clave-larga-12345"


def _foto(color=(200, 200, 200), tamano=(400, 300), formato="JPEG"):
    buf = io.BytesIO()
    Image.new("RGB", tamano, color).save(buf, formato)
    return buf.getvalue()


PDF = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"


@pytest.fixture
def escenario(db, settings, tmp_path):
    settings.SIBU_DOCUMENTOS_ROOT = str(tmp_path / "privado")
    est = crear_estructura()
    medica, _ = crear_profesional("medica_d", est["medicina"], est["salud"])
    psicologa, _ = crear_profesional("psico_d", est["psicologia"], est["psico"])
    for u in (medica, psicologa):
        u.set_password(CLAVE)
        u.save()
    return {
        "est": est,
        "medica": medica,
        "psicologa": psicologa,
        "exp": crear_expediente(cedula="1104346091"),
    }


def _subir(e, usuario, servicio, contenido=PDF, nombre="informe.pdf", **extra):
    return services.subir_documento(
        expediente=e["exp"],
        servicio=servicio,
        usuario=usuario,
        nombre=nombre,
        contenido=contenido,
        **extra,
    )


# --------------------------------------------------------------------- el sello


@pytest.mark.django_db
def test_un_documento_de_psicologia_no_lo_ve_medicina(escenario, client):
    e = escenario
    doc = _subir(e, e["psicologa"], e["est"]["psicologia"], descripcion="Valoración por ideación")
    client.login(username="medica_d", password=CLAVE)

    lista = client.get(reverse("documentos:lista", args=[e["exp"].pk])).content.decode()
    assert "informe.pdf" not in lista and "ideación" not in lista, "ni el nombre sale del sello"
    assert client.get(reverse("documentos:archivo", args=[doc.pk])).status_code == 404


@pytest.mark.django_db
@pytest.mark.parametrize("rol", [Rol.DIRECTOR, Rol.ADMIN_GENERAL, Rol.COORDINADOR])
def test_ni_direccion_ni_administracion_ni_coordinacion(escenario, client, rol):
    e = escenario
    doc = _subir(e, e["psicologa"], e["est"]["psicologia"])
    otro = Usuario.objects.create_user(username=f"u_{rol}", password=CLAVE, rol_principal=rol)
    if rol == Rol.COORDINADOR:
        from apps.usuarios.models import PerfilProfesional

        PerfilProfesional.objects.create(usuario=otro, seccion=e["est"]["psico"])
    client.login(username=f"u_{rol}", password=CLAVE)

    assert client.get(reverse("documentos:archivo", args=[doc.pk])).status_code == 404
    assert not services.puede_ver_documento(otro, doc)


@pytest.mark.django_db
def test_la_psicologa_si_lo_ve(escenario, client):
    e = escenario
    doc = _subir(e, e["psicologa"], e["est"]["psicologia"])
    client.login(username="psico_d", password=CLAVE)

    respuesta = client.get(reverse("documentos:archivo", args=[doc.pk]))
    assert respuesta.status_code == 200
    assert respuesta.content == PDF


@pytest.mark.django_db
def test_no_se_adjunta_en_un_servicio_ajeno(escenario, client):
    """Elegir Psicología en el formulario no mete nada en su sello."""
    e = escenario
    client.login(username="medica_d", password=CLAVE)

    client.post(
        reverse("documentos:lista", args=[e["exp"].pk]),
        {
            "accion": "subir",
            "servicio": e["est"]["psicologia"].pk,
            "archivo": _archivo(PDF, "x.pdf"),
        },
    )
    assert not DocumentoAnexo.objects.filter(expediente=e["exp"]).exists()


@pytest.mark.django_db
def test_el_panel_de_administracion_no_ensena_documentos_del_expediente(escenario, client):
    e = escenario
    _subir(e, e["psicologa"], e["est"]["psicologia"], descripcion="Valoración por ideación")
    Usuario.objects.create_superuser(
        username="adm_d", password=CLAVE, rol_principal=Rol.ADMIN_GENERAL
    )
    client.login(username="adm_d", password=CLAVE)

    contenido = client.get(reverse("admin:documentos_documentoanexo_changelist")).content.decode()
    assert "informe.pdf" not in contenido and "ideación" not in contenido


@pytest.mark.django_db
def test_el_archivo_no_esta_bajo_media(escenario, settings):
    """`/media/` se sirve sin preguntar; los documentos, por fuera."""
    e = escenario
    doc = _subir(e, e["medica"], e["est"]["medicina"])
    from pathlib import Path

    en_disco = Path(settings.SIBU_DOCUMENTOS_ROOT) / doc.ruta
    assert en_disco.exists()
    assert Path(settings.MEDIA_ROOT).resolve() not in en_disco.resolve().parents
    assert "informe" not in en_disco.name, "el nombre en disco no dice nada"


# ---------------------------------------------------------------------- subir


def _archivo(contenido, nombre):
    from django.core.files.uploadedfile import SimpleUploadedFile

    return SimpleUploadedFile(nombre, contenido)


@pytest.mark.django_db
def test_subir_desde_la_pantalla_y_aparece(escenario, client):
    e = escenario
    client.login(username="medica_d", password=CLAVE)

    respuesta = client.post(
        reverse("documentos:lista", args=[e["exp"].pk]),
        {
            "accion": "subir",
            "servicio": e["est"]["medicina"].pk,
            "tipo_documento": "examen",
            "descripcion": "Biometría de fuera",
            "archivo": _archivo(PDF, "lab.pdf"),
        },
        follow=True,
    )
    contenido = respuesta.content.decode()
    assert "lab.pdf" in contenido and "Biometría de fuera" in contenido
    assert LogAuditoria.objects.filter(entidad="DocumentoAnexo", accion="create").exists()


@pytest.mark.django_db
def test_un_html_disfrazado_de_pdf_no_entra(escenario):
    """Servido en línea, su JavaScript correría con la sesión de quien lo abre."""
    e = escenario
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError, match="Solo se admiten"):
        _subir(
            e,
            e["medica"],
            e["est"]["medicina"],
            contenido=b"<html><script>alert(1)</script>",
            nombre="x.pdf",
        )


@pytest.mark.django_db
def test_un_nombre_con_ruta_no_escribe_fuera(escenario, settings):
    e = escenario
    doc = _subir(e, e["medica"], e["est"]["medicina"], nombre="../../../etc/passwd.pdf")
    assert ".." not in doc.ruta
    assert doc.nombre_archivo == "passwd.pdf"


@pytest.mark.django_db
def test_leer_deja_constancia(escenario, client):
    e = escenario
    doc = _subir(e, e["medica"], e["est"]["medicina"])
    client.login(username="medica_d", password=CLAVE)
    client.get(reverse("documentos:archivo", args=[doc.pk]))

    assert LogAuditoria.objects.filter(entidad_id=str(doc.pk), accion="read").exists()


@pytest.mark.django_db
def test_un_archivo_alterado_en_disco_se_detecta(escenario, settings):
    from pathlib import Path

    from django.core.exceptions import ValidationError

    e = escenario
    doc = _subir(e, e["medica"], e["est"]["medicina"])
    (Path(settings.SIBU_DOCUMENTOS_ROOT) / doc.ruta).write_bytes(PDF + b"cambiado")
    with pytest.raises(ValidationError, match="no coincide"):
        services.leer_documento(e["medica"], doc)


# -------------------------------------------------------------------- escanear


def test_el_realce_deja_el_papel_blanco_y_la_tinta_negra():
    """Una foto gris y apagada sale con niveles completos."""
    gris = Image.new("L", (100, 100), 120)
    for x in range(30, 70):
        for y in range(45, 55):
            gris.putpixel((x, y), 80)
    hoja = services.realzar(gris.convert("RGB"), "documento")
    minimo, maximo = hoja.getextrema()
    assert minimo < 20 and maximo > 235


def test_una_pagina_en_blanco_no_se_estira():
    """Amplificaría el ruido hasta dejar una mancha."""
    assert services.niveles(Image.new("L", (50, 50), 200)) == (0, 255)


@pytest.mark.django_db
def test_escanear_varias_fotos_da_un_solo_pdf(escenario, client):
    e = escenario
    client.login(username="medica_d", password=CLAVE)

    client.post(
        reverse("documentos:lista", args=[e["exp"].pk]),
        {
            "accion": "escanear",
            "servicio": e["est"]["medicina"].pk,
            "modo": "documento",
            "descripcion": "Consentimiento firmado",
            "tipo_documento": "consentimiento",
            "fotos": [_archivo(_foto(), "p1.jpg"), _archivo(_foto((180, 180, 180)), "p2.jpg")],
        },
    )
    doc = DocumentoAnexo.objects.get(expediente=e["exp"])
    assert doc.mime == "application/pdf"
    assert doc.nombre_archivo == "Consentimiento firmado.pdf"
    contenido = services.leer_documento(e["medica"], doc)
    assert (
        contenido.count(b"/Type /Page\n")
        + contenido.count(b"/Type /Page ")
        + contenido.count(b"/Type/Page")
        >= 2
    )


@pytest.mark.django_db
def test_una_foto_rota_se_dice_cual(escenario):
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError, match="foto 2"):
        services.armar_pdf([_foto(), b"\xff\xd8\xffbasura"], "documento")


# ---------------------------------------------------------------------- marcar


@pytest.mark.django_db
def test_marcar_guarda_una_version_nueva_y_no_toca_la_original(escenario, client):
    e = escenario
    original = _subir(
        e,
        e["medica"],
        e["est"]["medicina"],
        contenido=_foto(),
        nombre="lesion.jpg",
        tipo_documento="foto",
    )
    hash_original = original.hash_sha256
    client.login(username="medica_d", password=CLAVE)

    client.post(
        reverse("documentos:marcar", args=[original.pk]),
        {
            "descripcion": "Lesión señalada",
            "imagen": _archivo(_foto((255, 0, 0), formato="PNG"), "m.png"),
        },
    )

    nueva = DocumentoAnexo.objects.get(original=original)
    original.refresh_from_db()
    assert original.hash_sha256 == hash_original
    assert nueva.mime == "image/png" and nueva.servicio == original.servicio
    assert nueva.nombre_archivo == "lesion (marcada).png"


@pytest.mark.django_db
def test_un_pdf_no_se_marca(escenario, client):
    e = escenario
    doc = _subir(e, e["medica"], e["est"]["medicina"])
    client.login(username="medica_d", password=CLAVE)
    assert client.get(reverse("documentos:marcar", args=[doc.pk])).status_code == 404


# --------------------------------------------------------------------- retirar


@pytest.mark.django_db
def test_retirar_lo_quita_de_la_lista_sin_borrar_el_archivo(escenario, client, settings):
    from pathlib import Path

    e = escenario
    doc = _subir(e, e["medica"], e["est"]["medicina"])
    client.login(username="medica_d", password=CLAVE)
    client.post(reverse("documentos:retirar", args=[doc.pk]))

    lista = client.get(reverse("documentos:lista", args=[e["exp"].pk])).content.decode()
    assert reverse("documentos:archivo", args=[doc.pk]) not in lista
    assert (Path(settings.SIBU_DOCUMENTOS_ROOT) / doc.ruta).exists()
    assert DocumentoAnexo.objects.todos().get(pk=doc.pk).eliminado_por == e["medica"]


@pytest.mark.django_db
def test_retirar_responde_solo_a_post(escenario, client):
    e = escenario
    doc = _subir(e, e["medica"], e["est"]["medicina"])
    client.login(username="medica_d", password=CLAVE)
    assert client.get(reverse("documentos:retirar", args=[doc.pk])).status_code == 405
