# Cómo cargar la base de datos, paso a paso

Guía de uso. El detalle de las 161 columnas está en
`docs/CARGA_BASE_INSTITUCIONAL.md`; esto es el procedimiento.

## Antes de empezar

Entre con la cuenta de administración:

| | |
|---|---|
| Usuario | `1104346091` |
| Contraseña | `1104346091` |

Si el menú de la izquierda no muestra **Base institucional** bajo *Gestión*,
esa cuenta no tiene el permiso de carga. Compruébelo con `make cuentas` y
recréela con `make preparar`.

## Paso 1 — Elegir el estamento

Hay cuatro bases, una por estamento: **estudiantes, docentes, administrativos y
trabajadores**. No traen las mismas columnas —solo la de estudiantes tiene
nivel, modalidad, ciclo, oferta académica, paralelo y jornada— y se cargan por
separado.

El archivo no dice a quién describe, así que lo declara usted en el asistente.
Es lo que decide con qué vínculo entra cada persona: cargar la base de docentes
sin elegir «Docente» daría de alta al claustro como estudiantes, y el informe
por estamento contaría cero docentes.

## Paso 2 — Descargar la plantilla

**Base institucional → Diccionario de columnas → Descargar plantilla CSV**

Baja un archivo con los encabezados exactos y una fila de ejemplo. Es la forma
de no equivocarse escribiéndolos a mano. La plantilla y el diccionario son los
del estamento seleccionado arriba: el archivo se llama
`plantilla-base-institucional-docente.csv`, y por eso las cuatro descargas no
se confunden entre sí.

## Paso 3 — Llenar el archivo

Borre la fila de ejemplo y ponga una fila por persona.

Solo tres columnas son obligatorias: **`cedula`, `nombres`, `apellidos`**. El
resto puede ir vacío; cuantas más traiga, menos tendrá que digitar el
profesional después.

Tres cosas que rompen una carga, por orden de frecuencia:

1. **Guardar como «CSV UTF-8 (delimitado por comas)»**, no como «CSV» a secas.
   El «CSV» de Excel en Windows guarda en Latin-1 y parte las tildes de los
   encabezados; entonces `parroquia_procedencia` deja de reconocerse.
2. **Formatear la columna de la cédula como TEXTO antes de escribir.** Excel la
   trata como número: convierte `0912345678` en `912345678` y `1104567894` en
   `1,10457E+09`. El sistema repone el cero perdido; la notación científica ya
   no se puede recuperar.
3. **Fechas en `AAAA-MM-DD`.** También se aceptan `DD/MM/AAAA`, `DD-MM-AAAA`
   y `DD MM AAAA`; cualquier otra cosa queda vacía sin avisar. Los encabezados
   pueden venir en MAYÚSCULAS.

**Los montos se escriben como se escriben aquí**: `450,50` con coma decimal, o
`450.50` con punto; los dos entran por lo mismo. Con separador de miles escriba
también los decimales (`1.234,00`): `1.234` a secas admite dos lecturas que se
diferencian en mil veces, y aunque el sistema lo lee como decimal, lo anota
como aviso en el resumen de la carga para que usted lo revise. Lo que no sea un
número —«no aplica», o un `45O,50` con la letra O— se suma como cero y también
queda anotado.

## Paso 4 — Previsualizar

**Base institucional → Cargar archivo**, elija el período y el estamento,
adjunte el archivo y pulse **Previsualizar**.

No escribe nada en la base. Dice cuántas altas, cuántas actualizaciones y
cuántos errores saldrían, con el número de fila y el motivo de cada error.
Corrija el archivo y repita hasta que los errores sean los que espera.

## Paso 5 — Aplicar

El mismo formulario, botón **Aplicar carga**. Ahora sí escribe.

Es idempotente: volver a subir el mismo archivo actualiza, no duplica. Si se
equivocó en una columna, corrija el archivo y vuelva a aplicarlo.

Por cada fila válida el sistema crea o actualiza la persona, abre su expediente
si no lo tenía, pre-puebla la ficha socioeconómica y genera las alertas que
correspondan (violencia familiar a Trabajo Social, necesidad educativa especial
a Psicopedagogía, gestación y lactancia a Medicina, consumo declarado a
Psicología).

## Paso 6 — Verificar que quedó cargado

**Base institucional → Ver lo cargado**

Lista fila por fila. Busque por cédula, nombre, facultad o carrera, y ordene por
cualquier columna pulsando su cabecera (otra vez, para invertir el sentido). El
panel de filtros incluye **Estamento**: es la forma de comprobar que la base de
docentes entró como docentes y no como estudiantes.

Abajo, el historial de cargas con sus conteos: fecha, archivo, período, filas,
altas, actualizaciones y errores.

## Paso 7 — Comprobar el autocompletado

Es lo que la carga viene a alimentar, y conviene verificarlo con una cuenta de
profesional, no con la de administración.

1. Entre con un profesional, por ejemplo `jhoely.lalangui` / `jhoely.lalangui`.
2. **Expedientes** → escriba tres letras de un apellido que acabe de cargar en
   la casilla *Por nombre o apellido*. Deben aparecer sugerencias con la cédula
   y la carrera.
3. Escriba una cédula cargada en *Por cédula* y pulse **Buscar**: sale la
   tarjeta con facultad, carrera, ciclo y estado de matrícula, y el botón para
   abrir el expediente.

Si las sugerencias no salen, la carga no llegó: vuelva al paso 5.

## Registrar a varias personas de una vez

Distinto de la carga: **Expedientes → Varias cédulas** abre el expediente de una
lista de cédulas pegadas en fila, resolviéndolas contra lo que ya está cargado.
Sirve para preparar una jornada, no para alimentar el padrón.

## Preguntas que se repiten

**¿Puedo cargar sin ser administrador?** No. La pantalla exige el permiso
`academico.add_cargainstitucional`. La cuenta `1104346091` lo tiene; un
profesional corriente, no.

**¿Qué pasa con una cédula que no pasa el módulo 10?** La fila se rechaza y
queda anotada en la bitácora con su número de línea. El resto del archivo se
procesa igual.

**¿Y si el archivo trae otros nombres de encabezado?** No hay que renombrar
nada: el asistente permite mapear cada alias contra la columna canónica y
guarda ese mapeo con la carga.

**¿Se puede deshacer una carga?** No hay un botón para eso. Como es idempotente,
la vía es corregir el archivo y volver a aplicarlo. Por eso conviene
previsualizar siempre.
