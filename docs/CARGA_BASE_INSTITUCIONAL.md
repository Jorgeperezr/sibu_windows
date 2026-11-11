# Carga de la base institucional

> Para el **procedimiento paso a paso**, ver `docs/COMO_CARGAR_LA_BASE.md`.
> Este documento es el diccionario: qué formato, qué encabezados y cuántas
> variables.

Cómo se entrega a SIBU la base de datos institucional, qué debe traer el
archivo y qué hace el sistema con él.

## Una base por estamento

Son cuatro y se cargan por separado: **estudiantes, docentes, administrativos y
trabajadores**. No traen la misma información —solo la de estudiantes tiene
`nivel`, `modalidad`, `ciclo`, `oferta_academica`, `paralelo` y `jornada`—, así
que la plantilla y el diccionario que se descargan son los del estamento
elegido; lo demás (identificación, procedencia, residencia, contacto,
situación laboral, salud y la ficha socioeconómica) es común a los cuatro.

El archivo no dice a quién describe. Lo declara quien carga, en el asistente, y
queda registrado en la bitácora de la carga junto al hash del archivo. Es lo que
decide con qué vínculo entra cada persona y, por tanto, cómo la cuenta después
el informe por estamento.

## En qué formato se entrega

**CSV separado por comas, codificado en UTF-8** (también se admite `.xlsx`, que
el lector abre con las mismas reglas). El CSV es preferible para volúmenes
grandes: pesa menos, no arrastra fórmulas ni formatos, y no impone el límite de
hojas de Excel.

Tres detalles que en la práctica son los que rompen una carga:

- **Guardar desde Excel como «CSV UTF-8 (delimitado por comas)»**, no como «CSV»
  a secas. El «CSV» de Excel en Windows guarda en Latin-1 y parte las tildes de
  los encabezados; entonces `parroquia_procedencia` deja de reconocerse.
- **La cédula es texto, no número.** Excel convierte `0912345678` en
  `912345678` y `1104567894` en `1,10457E+09`. Formatear la columna como texto
  antes de escribir. (El sistema repone el cero inicial perdido y limpia el
  `.0` que Excel añade, pero la notación científica ya no es recuperable.)
- **Fechas en `AAAA-MM-DD`.** También se aceptan `DD/MM/AAAA`, `DD-MM-AAAA`,
  `DD MM AAAA` (con espacios, como la base de estudiantes de la UNL),
  `DD.MM.AAAA`, `AAAA/MM/DD` y `MM/DD/AAAA`; cualquier otra cosa queda vacía
  sin avisar.

## Cuál es el encabezado de la tabla

La **primera fila son los encabezados**, con los nombres que espera el sistema.
Da igual que vengan en MAYÚSCULAS (`CEDULA`, `TIPO_SANGRE`), con tildes o con
espacios: se leen en minúsculas, sin tildes y con guion bajo. Cada fila
siguiente es una persona.

Al cargar también se limpia lo que la base escribe de varias maneras: un
teléfono `000000000` cuenta como sin teléfono, y el tipo de sangre `A Rh+`,
`ARH+` o `A positivo` se guarda como `A+`.

No hace falta escribirlos a mano. Desde
**Base institucional → Diccionario de columnas → Descargar plantilla CSV** se
obtiene el archivo ya con los encabezados correctos y una fila de ejemplo, que
se borra antes de entregar el archivo lleno. La plantilla se genera del mapeo
del sistema, así que no puede quedarse desactualizada.

Los primeros encabezados, para reconocer el formato de un vistazo:

```
tipo_documento,cedula,nombres,apellidos,fecha_nacimiento,sexo,genero,celular,
telefono,facultad,carrera,nivel,modalidad,ciclo,oferta_academica,estado,
paralelo,jornada,email_institucional,...
```

Si el archivo del período ya viene con otros nombres de encabezado, **no hay que
renombrar nada**: el asistente de carga permite mapear cada alias contra la
columna canónica y guarda ese mapeo junto con la carga, de modo que el archivo
original queda tal como lo entregó la institución.

## Cuántas variables debe proporcionar

**161 columnas en total, de las cuales solo 3 son obligatorias:** `cedula`,
`nombres` y `apellidos`. Una fila sin alguna de ellas se rechaza y queda anotada
en la bitácora de la carga, con su número de fila y el motivo; el resto del
archivo se procesa igual.

Las otras 158 son opcionales en el sentido estricto: una columna ausente
simplemente queda vacía y el profesional la completará al atender. Pero cuantas
más se entreguen, menos tiene que digitar el profesional y más completos salen
los informes.

| Grupo | Columnas | Va a |
|---|---:|---|
| Identificación | 9 | Persona |
| Datos académicos | 10 | Dato académico |
| Identidad (sensible) | 2 | No se guarda |
| Salud básica | 3 | Expediente |
| Procedencia | 6 | Persona (JSON) |
| Residencia actual | 10 | Persona (JSON) |
| Contacto de referencia | 5 | Persona (JSON) |
| Situación laboral | 11 | Ficha socioeconómica |
| Grupo familiar | 13 | Fila del período (padrón) |
| Convivencia | 7 | Ficha socioeconómica |
| Vivienda del estudiante | 10 | Ficha socioeconómica |
| Vivienda familiar | 10 | Ficha socioeconómica |
| Salud familiar | 6 | Ficha socioeconómica |
| Salud del estudiante | 17 | Expediente («salud declarada», solo para Medicina, Enfermería y Odontología) y alertas |
| Bienes y negocio | 7 | Fila del período (padrón) |
| Ingresos | 12 | Ficha socioeconómica |
| Egresos | 17 | Ficha socioeconómica |
| Situaciones sensibles | 3 | Solo genera la alerta; no se guarda |
| Datos bancarios de beca | 3 | No se guarda |
| Control del formulario | 3 | Solo fila cruda |

El detalle columna por columna está en la pantalla del diccionario, que es la
fuente única: esta tabla resume, no sustituye.

### El mínimo razonable

Si la institución solo puede entregar una parte, este es el conjunto que hace
que el sistema sea útil desde el primer día (19 columnas):

```
tipo_documento, cedula, nombres, apellidos, fecha_nacimiento, sexo, genero,
celular, email_institucional, facultad, carrera, nivel, modalidad, ciclo,
estado, paralelo, jornada, discapacidad, estudiante_necesidades_educativas_especiales
```

Las últimas dos no son de trámite: **`discapacidad` y
`estudiante_necesidades_educativas_especiales` son variables del informe
estadístico** y, además, generan alerta al cargarse. Sin ellas el informe dirá
«Sin dato», que es lo correcto —ausencia de dato no es prueba de ausencia— pero
no ayuda a nadie.

## Qué hace el sistema con cada fila

1. **Valida** la cédula con el módulo 10 ecuatoriano. Si no pasa, la fila se
   rechaza y se anota; la carga continúa.
2. **Crea o actualiza la persona** (`cedula` es la llave) y su fila académica del
   período.
3. **Abre el expediente** si no lo tenía, y completa grupo sanguíneo y
   discapacidad **solo si están vacíos**: lo que un profesional escribió en el
   expediente vale más que lo declarado en matrícula y no se pisa.
4. **Pre-puebla la ficha socioeconómica** con origen «matrícula», salvo que ya
   exista una vigente —posiblemente verificada por Trabajo Social—, que no se
   sobrescribe.
5. **Genera alertas** hacia el expediente y la bandeja del servicio que
   corresponda: violencia familiar y maltrato a Trabajo Social, necesidad
   educativa especial a Psicopedagogía, gestación, lactancia y discapacidad a
   Medicina, consumo declarado a Psicología.
6. **Conserva la fila cruda completa** en `ficha_raw`, con todas las columnas
   entregadas, aunque el sistema todavía no explote alguna de ellas.

La carga es idempotente: volver a subir el mismo archivo actualiza, no duplica.
Conviene **previsualizar antes de aplicar** —el asistente lo ofrece— porque la
previsualización no escribe nada y ya dice cuántas altas, cuántas
actualizaciones y cuántos errores saldrían.

## Después de cargar

- **Base institucional → Ver lo cargado** lista el padrón fila por fila, con
  buscador por cédula, nombre, apellido, facultad o carrera, y el historial de
  las últimas cargas con sus conteos.
- En la **búsqueda de expedientes**, el profesional escribe una cédula o un
  nombre y el sistema sugiere las coincidencias del padrón, con carrera, para no
  volver a digitar lo que la institución ya sabe. Buscar por cédula además
  precarga el alta de la persona.

El padrón y el diccionario son de quien administra. El autocompletado exige el
mismo permiso que la búsqueda de expedientes, y devuelve identificación y
matrícula: nunca contenido clínico, ni qué servicio atiende a la persona.

## Lo que esta carga todavía no hace

Tres grupos del archivo —`grupo_familiar`, `salud_estudiante` y
`bienes_negocio`— se conservan íntegros en la fila cruda pero aún no se
distribuyen a campos consultables de la ficha socioeconómica. El dato no se
pierde; simplemente todavía no se puede filtrar ni sumar por él. Queda anotado
como trabajo pendiente para no darlo por hecho.

## Las cuatro columnas que añadió la base de estudiantes

| Columna | Qué hace |
|---|---|
| `tiene_enfermedad_catastrofica` | Con «Sí» crea la alerta *Enfermedad catastrófica* (la que cuenta el informe estadístico) |
| `enfermedades_catastroficas` | El nombre de la enfermedad: va en la descripción de esa alerta. Escribirla basta aunque la casilla anterior venga vacía |
| `tiene_enfermedad_rara_huerfana` | Con «Sí» crea una alerta de riesgo para Medicina |
| `necesita_ayuda_bienestar` | Con «Sí» crea una alerta social para Trabajo Social: quien la marca está pidiendo ayuda |

Como las demás alertas de la matrícula, se apagan solo con una negación
expresa («No», «Ninguna», «No aplica», «0») y solo si las encendió una carga.
Cada columna apaga **sus** alertas: «discapacidad: No» ya no apaga la de
consumo, que comparte el tipo «riesgo».

