"""
Motor de carga de la ficha socioeconómica (asistente de 6 pasos, sección 7.2).

Flujo público:
    lector = LectorFicha(ruta, formato)
    columnas = lector.columnas()                 # paso 2: para el mapeo
    resultado = ProcesadorCarga(carga, mapeo).procesar(lector, aplicar=False)  # 3-4 (preview)
    ProcesadorCarga(carga, mapeo).procesar(lector, aplicar=True)               # 5 (aplicar)

Cada fila válida hace upsert de Persona + DatoAcademico, pre-puebla la
FichaSocioeconomica (origen=matrícula) y genera alertas hacia las bandejas de
Trabajo Social / Psicopedagogía / Psicología / Medicina (sección 12.7).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction

from apps.core.models import Servicio
from apps.expediente.models import AlertaClinica, Expediente, Persona

from . import mapping, validators


# --------------------------------------------------------------------------
# Lectura del archivo
# --------------------------------------------------------------------------
class LectorFicha:
    """Lee un Excel/CSV y entrega filas como diccionarios normalizados."""

    def __init__(self, ruta: str, formato: str):
        self.ruta = ruta
        self.formato = formato
        self._df = None

    def _cargar(self):
        import pandas as pd  # import diferido: pandas es pesado

        if self._df is None:
            if self.formato == "csv":
                self._df = pd.read_csv(self.ruta, dtype=str, keep_default_na=False)
            else:
                self._df = pd.read_excel(self.ruta, dtype=str, keep_default_na=False)
            self._df.columns = [validators.normalizar_encabezado(c) for c in self._df.columns]
        return self._df

    def columnas(self) -> list[str]:
        return list(self._cargar().columns)

    def filas(self):
        df = self._cargar()
        for _, fila in df.iterrows():
            yield {k: (v if v != "" else None) for k, v in fila.to_dict().items()}

    def total(self) -> int:
        return len(self._cargar())


def hash_archivo(ruta: str) -> str:
    h = hashlib.sha256()
    with open(ruta, "rb") as f:
        for bloque in iter(lambda: f.read(8192), b""):
            h.update(bloque)
    return h.hexdigest()


# --------------------------------------------------------------------------
# Resultado del procesamiento
# --------------------------------------------------------------------------
@dataclass
class ResultadoCarga:
    total: int = 0
    altas: int = 0
    actualizaciones: int = 0
    errores: int = 0
    alertas_generadas: int = 0
    detalle_errores: list = field(default_factory=list)

    def as_dict(self):
        return {
            "total": self.total,
            "altas": self.altas,
            "actualizaciones": self.actualizaciones,
            "errores": self.errores,
            "alertas_generadas": self.alertas_generadas,
            "detalle_errores": self.detalle_errores[:200],  # cota para la bitácora
        }


# --------------------------------------------------------------------------
# Procesador
# --------------------------------------------------------------------------
class ProcesadorCarga:
    """Aplica el mapeo, valida y hace upsert. `aplicar=False` = solo previsualiza."""

    def __init__(self, carga, mapeo: dict | None = None, estamento: str = ""):
        self.carga = carga
        self.periodo = carga.periodo
        # A quién describe el archivo. Se toma de la carga —que es donde queda
        # registrado— y el parámetro solo sirve para forzarlo en pruebas; antes
        # esto era la constante ESTUDIANTE escrita en el upsert, y cargar la
        # base de docentes daba de alta a todo el claustro como estudiantes.
        self.estamento = estamento or carga.estamento
        # mapeo: alias_en_archivo -> columna_canonica. Por defecto, identidad.
        self.mapeo = mapeo or {}
        self.dominio = settings.SIBU["DOMINIO_CORREO_INSTITUCIONAL"]

    # -- utilidades de acceso a la fila usando el mapeo de alias --
    def _alias(self, col_canonica: str) -> str:
        # El alias se normaliza igual que los encabezados del archivo: el mapeo
        # guardado puede venir escrito como en el archivo original.
        return validators.normalizar_encabezado(self.mapeo.get(col_canonica, col_canonica))

    def _get(self, fila: dict, col_canonica: str):
        return fila.get(self._alias(col_canonica))

    def _fila_conservable(self, fila: dict) -> dict:
        """
        La fila cruda sin lo que SIBU decidió no guardar (`mapping.NO_SE_CONSERVAN`).

        Se quitan por su nombre canónico y por el alias que traiga el archivo:
        si la columna se llama distinto en la base de un estamento, quitarla solo
        por el canónico la dejaría pasar con su otro nombre.
        """
        fuera = set(mapping.NO_SE_CONSERVAN)
        fuera |= {self._alias(c) for c in mapping.NO_SE_CONSERVAN}
        return {k: v for k, v in fila.items() if v is not None and k not in fuera}

    def _subdict(self, fila: dict, columnas: list[str]) -> dict:
        return {c: self._get(fila, c) for c in columnas if self._get(fila, c) is not None}

    def procesar(self, lector: LectorFicha, aplicar: bool = False) -> ResultadoCarga:
        r = ResultadoCarga(total=lector.total())
        for indice, fila in enumerate(lector.filas(), start=2):  # fila 1 = encabezados
            try:
                self._procesar_fila(fila, r, aplicar)
            except Exception as exc:  # noqa: BLE001 - se reporta, no se aborta la carga
                r.errores += 1
                r.detalle_errores.append({"fila": indice, "error": str(exc)})
        return r

    def _procesar_fila(self, fila: dict, r: ResultadoCarga, aplicar: bool):
        cedula = validators.normalizar_cedula(self._get(fila, "cedula"))
        nombres = self._get(fila, "nombres")
        apellidos = self._get(fila, "apellidos")

        # Validaciones mínimas
        faltantes = [
            c
            for c in mapping.COLUMNAS_OBLIGATORIAS
            if not (self._get(fila, c) or (c == "cedula" and cedula))
        ]
        if faltantes:
            raise ValueError(f"Columnas obligatorias vacías: {', '.join(faltantes)}")
        if not validators.validar_cedula_ecuatoriana(cedula):
            raise ValueError(f"Cédula inválida: {cedula}")

        correo = self._get(fila, "email_institucional") or ""
        if correo and not validators.validar_correo_institucional(correo, self.dominio):
            # No es error bloqueante: se registra pero se continúa
            r.detalle_errores.append(
                {"cedula": cedula, "aviso": f"Correo no institucional: {correo}"}
            )

        self._revisar_montos(fila, cedula, r)

        if not aplicar:
            # Modo previsualización: solo cuenta alta/actualización sin escribir
            existe = Persona.objects.filter(cedula=cedula).exists()
            r.actualizaciones += 1 if existe else 0
            r.altas += 0 if existe else 1
            return

        with transaction.atomic():
            persona, creada = self._upsert_persona(fila, cedula, nombres, apellidos)
            self._upsert_dato_academico(fila, persona)
            expediente = self._asegurar_expediente(fila, persona)
            self._prepoblar_ficha(fila, expediente)
            r.alertas_generadas += self._generar_alertas(fila, expediente)
            r.altas += 1 if creada else 0
            r.actualizaciones += 0 if creada else 1

    # Columnas del archivo que son montos: lo que se escriba ahí se suma, y
    # lo que no se pueda leer se suma como cero sin que nadie lo note.
    COLUMNAS_DE_MONTO = tuple(mapping.FICHA_JSONB["ingresos"]) + tuple(
        mapping.FICHA_JSONB["egresos"]
    )

    def _revisar_montos(self, fila, cedula, r: ResultadoCarga) -> None:
        """
        Anota los montos que no se pueden leer, o que admiten dos lecturas.

        No bloquea la fila: una celda con «no aplica» en una columna de monto es
        corriente y no puede tumbar una carga de miles de filas. Pero tampoco se
        calla, que es lo que hacía antes: estos números alimentan el puntaje
        socioeconómico que orienta una beca, y `1.234` leído como uno coma
        doscientos treinta y cuatro en vez de mil doscientos treinta y cuatro
        cambia el estrato de una familia sin dejar rastro.
        """
        from apps.core import numeros

        for columna in self.COLUMNAS_DE_MONTO:
            valor = self._get(fila, columna)
            if valor in (None, ""):
                continue
            if numeros.es_ambiguo(valor):
                r.detalle_errores.append(
                    {
                        "cedula": cedula,
                        "aviso": f"{columna}=«{valor}» admite dos lecturas y se "
                        f"leyó como {numeros.a_decimal(valor)}. Con separador de "
                        "miles escriba también los decimales (1.234,00).",
                    }
                )
                continue
            try:
                numeros.a_decimal(valor, campo=columna)
            except ValidationError as exc:
                r.detalle_errores.append(
                    {"cedula": cedula, "aviso": f"{columna}: {' '.join(exc.messages)} Se suma 0."}
                )

    # -- upserts --
    #
    # Qué se actualiza al RECARGAR a alguien que ya está, y qué no. La base se
    # entrega cada período académico, y el archivo del período nuevo trae lo
    # que cambia: ciclo, estado de matrícula, gestación… El resto viene vacío.
    #
    # Con `update_or_create` y un `defaults` completo, esos huecos se escribían:
    # una recarga borraba la fecha de nacimiento, el sexo, el celular y el
    # correo de quien ya estaba registrado. Sin fecha de nacimiento no hay edad;
    # sin sexo el informe pierde una variable; sin celular no se puede llamar al
    # paciente. Nadie veía un error: la carga decía «1 actualización».

    # Lo que identifica a la persona y no cambia con el período. Se rellena si
    # falta; si ya hay valor, NO se pisa. Es el mismo criterio que ya seguía
    # `_asegurar_expediente`: la matrícula es una foto del día en que se llenó
    # la ficha, y lo que el sistema ya sabe de alguien no se reescribe con ella.
    # Una corrección de verdad —un apellido mal escrito— se hace donde se
    # corrige, no colándola en la carga del semestre siguiente.
    ESTABLES = ("nombres", "apellidos", "tipo_documento", "fecha_nacimiento", "sexo", "genero")

    # Datos de contacto: cambian de verdad entre períodos y la institución es la
    # fuente. Se actualizan cuando el archivo trae algo; un vacío nunca borra.
    DE_CONTACTO = ("celular", "telefono", "correo_institucional")

    def _upsert_persona(self, fila, cedula, nombres, apellidos):
        leidos = {
            "nombres": nombres,
            "apellidos": apellidos,
            "tipo_documento": self._get(fila, "tipo_documento") or "cedula",
            "sexo": self._get(fila, "sexo") or "",
            "genero": self._get(fila, "genero") or "",
            "celular": validators.telefono_o_vacio(self._get(fila, "celular")),
            "telefono": validators.telefono_o_vacio(self._get(fila, "telefono")),
            "correo_institucional": self._get(fila, "email_institucional") or "",
            "fecha_nacimiento": validators.a_fecha(self._get(fila, "fecha_nacimiento")),
        }
        jsonb = {
            campo: self._subdict(fila, columnas)
            for campo, columnas in mapping.PERSONA_JSONB.items()
        }

        persona = Persona.objects.filter(cedula=cedula).first()
        if persona is None:
            return Persona.objects.create(
                cedula=cedula, tipo_vinculo=self.estamento, **leidos, **jsonb
            ), True

        # El estamento sí se declara en cada carga: es lo que dice a qué base
        # pertenece este archivo, y quien lo carga acaba de afirmarlo.
        cambios = ["tipo_vinculo"]
        persona.tipo_vinculo = self.estamento

        for campo in self.ESTABLES:
            valor = leidos[campo]
            if valor and not getattr(persona, campo):
                setattr(persona, campo, valor)
                cambios.append(campo)

        for campo in self.DE_CONTACTO:
            valor = leidos[campo]
            if valor and valor != getattr(persona, campo):
                setattr(persona, campo, valor)
                cambios.append(campo)

        # Los JSON se FUSIONAN, no se reemplazan: un archivo que solo trae la
        # provincia no puede vaciar la parroquia y el cantón que ya estaban.
        for campo, nuevos in jsonb.items():
            if not nuevos:
                continue
            fusionado = {**(getattr(persona, campo) or {}), **nuevos}
            if fusionado != getattr(persona, campo):
                setattr(persona, campo, fusionado)
                cambios.append(campo)

        persona.save(update_fields=[*dict.fromkeys(cambios), "actualizado_en"])
        return persona, False

    def _upsert_dato_academico(self, fila, persona):
        from .models import DatoAcademico

        defaults = {campo: (self._get(fila, col) or "") for col, campo in mapping.ACADEMICO.items()}
        defaults["carga"] = self.carga
        defaults["ficha_raw"] = self._fila_conservable(fila)
        DatoAcademico.objects.update_or_create(
            persona=persona, periodo=self.periodo, defaults=defaults
        )

    def _asegurar_expediente(self, fila, persona):
        """
        El expediente de la persona, creándolo si la carga es lo primero que la
        registra.

        Los datos de `defaults` solo se aplican al crear, y eso dejaba un hueco:
        si el expediente ya existía —lo abre también la búsqueda por cédula—, el
        grupo sanguíneo y la discapacidad de la ficha no entraban nunca, y la
        discapacidad es una de las variables del informe estadístico. Se rellenan
        después, pero SOLO si están vacíos: lo que un profesional haya escrito en
        el expediente vale más que lo declarado en matrícula y no se pisa.
        """
        expediente, _ = Expediente.objects.get_or_create(
            persona=persona,
            defaults={
                "numero_expediente": f"EXP-{persona.cedula}",
                "grupo_sanguineo": validators.normalizar_grupo_sanguineo(
                    self._get(fila, "tipo_sangre")
                )
                or "",
                "discapacidad_tipo": self._get(fila, "discapacidad_tipo") or "",
            },
        )
        completados = []
        for columna, campo in mapping.SALUD_EXPEDIENTE.items():
            valor = self._get(fila, columna)
            if not valor or getattr(expediente, campo, None):
                continue
            valor = self._valor_para_expediente(campo, valor)
            if valor is None:
                continue
            setattr(expediente, campo, valor)
            completados.append(campo)
        # La salud declarada se FUSIONA: el archivo del período nuevo trae lo
        # que cambia y el resto vacío, y ese vacío no borra lo que ya estaba.
        declarada = {
            c: str(v).strip()
            for c, v in self._subdict(fila, mapping.FICHA_JSONB["salud_estudiante"]).items()
            if str(v).strip()
        }
        fusionada = {**(expediente.salud_declarada or {}), **declarada}
        if fusionada != (expediente.salud_declarada or {}):
            expediente.salud_declarada = fusionada
            completados.append("salud_declarada")
        if completados:
            expediente.save(update_fields=completados)
        return expediente

    @staticmethod
    def _valor_para_expediente(campo: str, valor):
        """
        Ajusta el valor de la ficha al campo del expediente, o None si no cabe.

        La ficha llega como texto libre desde un Excel: un porcentaje escrito
        "50%" o "no aplica" reventaría un `PositiveSmallIntegerField`, y un tipo
        de discapacidad más largo que el campo abortaría la fila entera. Nada de
        eso debe tumbar una carga de miles de filas por un dato accesorio: lo que
        no encaja se descarta y la fila cruda lo conserva igual en `ficha_raw`.
        """
        if campo == "discapacidad_porcentaje":
            digitos = "".join(c for c in str(valor) if c.isdigit())
            if not digitos:
                return None
            numero = int(digitos)
            return numero if 0 <= numero <= 100 else None
        if campo == "grupo_sanguineo":
            return validators.normalizar_grupo_sanguineo(valor)
        limites = {"discapacidad_tipo": 60}
        return str(valor).strip()[: limites.get(campo, 255)]

    def _prepoblar_ficha(self, fila, expediente):
        """Crea la FichaSocioeconomica (origen=matrícula) si no existe una vigente."""
        from apps.trabajo_social.models import FichaSocioeconomica

        if FichaSocioeconomica.objects.filter(expediente=expediente, vigente=True).exists():
            return  # ya existe (posiblemente verificada por Trabajo Social): no se sobrescribe

        ingresos = self._subdict(fila, mapping.FICHA_JSONB["ingresos"])
        egresos = self._subdict(fila, mapping.FICHA_JSONB["egresos"])
        FichaSocioeconomica.objects.create(
            expediente=expediente,
            origen=FichaSocioeconomica.Origen.MATRICULA,
            ingresos=ingresos,
            egresos=egresos,
            ingresos_totales=validators.a_decimal(self._get(fila, "ingreso_mensual")),
            egresos_totales=validators.a_decimal(self._get(fila, "gastos_mensual_familia")),
            vivienda_estudiante=self._subdict(fila, mapping.FICHA_JSONB["vivienda_estudiante"]),
            vivienda_familiar=self._subdict(fila, mapping.FICHA_JSONB["vivienda_familiar"]),
            convivencia=self._subdict(fila, mapping.FICHA_JSONB["convivencia"]),
            situacion_laboral=self._subdict(fila, mapping.FICHA_JSONB["situacion_laboral"]),
            salud_familiar=self._subdict(fila, mapping.FICHA_JSONB["salud_familiar"]),
        )

    # Lo que en el archivo significa «no». Se compara en minúsculas y sin
    # espacios: las cuatro bases institucionales escriben la negación a su
    # manera y ninguna vale más que otra.
    NEGACIONES = {
        "no",
        "0",
        "ninguno",
        "n/a",
        "ninguna",
        "false",
        "-",
        "no aplica",
        "na",
        "nada",
    }

    def _generar_alertas(self, fila, expediente) -> int:
        """
        Enciende y APAGA las alertas que declara la ficha de matrícula.

        Apagar es la mitad que faltaba. La gestación y la lactancia cambian de
        un período al siguiente y esto solo sabía encenderlas: un embarazo
        declarado en 2026-1 seguía activo en 2027 y el informe estadístico lo
        seguía contando como una gestación en curso.

        Solo se apaga lo que la propia matrícula encendió (`origen=matricula`) y
        solo cuando el archivo lo NIEGA expresamente: una columna vacía es
        ausencia de dato, no un «ya no». Lo que registró un profesional en
        consulta no se toca —él lo comprobó, la ficha no—, y por eso la alerta
        lleva su origen.
        """
        generadas = 0
        for columna, regla in mapping.REGLAS_ALERTA.items():
            tipo, _servicio, plantilla = regla[:3]
            columna_detalle = regla[3] if len(regla) > 3 else None
            detalle = self._get(fila, columna_detalle) if columna_detalle else None
            if detalle is not None and self._es_negacion(detalle):
                detalle = None

            valor = self._get(fila, columna)
            if (valor is None or str(valor).strip() == "") and detalle:
                # Nombrar la enfermedad ya es declararla, aunque la casilla
                # del «sí» venga vacía.
                valor = "Sí"
            if valor is None or str(valor).strip() == "":
                continue  # sin dato: ni se enciende ni se apaga

            # Solo las de ESTA regla: varias comparten tipo.
            propias = AlertaClinica.objects.filter(
                expediente=expediente,
                tipo=tipo,
                origen=AlertaClinica.Origen.MATRICULA,
                descripcion__startswith=plantilla.split("{")[0],
            )
            if self._es_negacion(valor):
                propias.filter(activa=True).update(activa=False)
                continue

            descripcion = plantilla.format(
                valor=valor, detalle=f": {str(detalle).strip()}" if detalle else ""
            )
            alerta, creada = AlertaClinica.objects.get_or_create(
                expediente=expediente,
                tipo=tipo,
                descripcion=descripcion,
                defaults={"activa": True, "origen": AlertaClinica.Origen.MATRICULA},
            )
            if creada:
                generadas += 1
            elif not alerta.activa and alerta.origen == AlertaClinica.Origen.MATRICULA:
                # Negada en un período y declarada de nuevo en el siguiente:
                # antes `get_or_create` encontraba la apagada y la dejaba así.
                alerta.activa = True
                alerta.save(update_fields=["activa"])
                generadas += 1
        return generadas

    def _es_negacion(self, valor) -> bool:
        return " ".join(str(valor).split()).lower() in self.NEGACIONES


def servicios_por_codigo():
    """Cache simple de servicios por código para el ruteo de alertas."""
    return {s.codigo: s for s in Servicio.objects.all()}
