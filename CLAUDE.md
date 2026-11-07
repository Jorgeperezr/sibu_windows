# SIBU portable — Sistema Integral de Bienestar Universitario (UNL)

**Este repositorio es la versión PORTABLE de SIBU.** El mismo sistema, pensado
para correr desde una carpeta sin instalar: el profesional pulsa un icono y se
abre el navegador en la pantalla de credenciales. El repositorio original
—`Jorgeperezr/sibu`— queda archivado; aquí continúa el desarrollo.

Lo propio de la portable está en `docs/PORTABLE.md`, y la arquitectura de
conexión entre los profesionales en `docs/CONEXION_ENTRE_PORTABLES.md`.

Django 5.1 + DRF + Bootstrap 5. PostgreSQL 16 en el servidor central, SQLite en
la portable. Nueve servicios: Medicina,
Enfermería, Odontología, Laboratorio, Farmacia, Psicología, Psicopedagogía,
Trabajo Social y Becas. Más citas, expediente único, derivaciones, firma,
talleres, portal del estudiante y tablero de gestión.

## Reglas del dominio que no se negocian

- **El sello de Psicología es absoluto.** El contenido clínico de Psicología no
  es accesible fuera del servicio: ni Dirección, ni administración, ni
  break-glass. Sin excepciones. Antes de tocar RBAC, derivaciones, firma,
  portal o reportes, comprobar que no se abre una rendija.
- **Los tableros muestran gestión, no contenido.** En servicios confidenciales,
  un conteo de pacientes distintos < 5 se reporta como `<5` (K_MINIMO): un
  conteo pequeño identifica.
- **Un taller no es una atención clínica.** Registrar a alguien en un taller no
  le abre expediente.
- **Verificar matrícula no suspende una beca.** El sistema informa; la decisión
  es de Trabajo Social. Suspender exige causal escrita.
- **El portal aísla por identidad, no por rol.** Toda consulta parte del
  expediente vinculado; ningún recurso se busca por id de URL sin filtrar.
- **Ausencia de dato no es prueba de ausencia.** Sin datos académicos cargados
  no se concluye "no matriculado".
- **Una recarga de otro período no rescribe a la persona.** El archivo nuevo
  trae lo que cambia y el resto vacío: con un `defaults` completo esos huecos
  borraban la fecha de nacimiento, el sexo y el contacto. Lo estable se rellena
  si falta y no se pisa; el contacto se actualiza pero un vacío no borra; los
  JSON se fusionan; lo del período vive en `DatoAcademico`.
- **La edad se calcula, nunca se guarda.** Una edad almacenada queda congelada
  en la carga que la escribió. `Persona.edad` sale de la fecha de nacimiento.
- **La carga apaga lo que la carga encendió, y nada más.** Gestación y
  lactancia cambian de período: solo se desactivan con una negación EXPRESA del
  archivo y solo si `origen=matricula`. Lo que registró un profesional no lo
  toca una recarga: él lo comprobó, la ficha no.
- **Lo que un servicio comprueba se anota como suyo, no en la base.**
  `AjusteDeServicio` desde el detalle del expediente; la matrícula queda
  intacta y se puede volver a ella. Género e identidad no son ajustables.
- **Los talleres no se publican al estudiante.** Los ve el personal del
  servicio que los organiza.
- **El estamento es `Persona.tipo_vinculo`, no un campo nuevo.** Cuatro
  estamentos (estudiante, docente, administrativo, trabajador) más «externo»,
  que no lo es. Cada estamento tiene su propia base con columnas distintas y se
  declara al cargar; sin declararlo no se escribe.
- **El horario lo pone quien atiende, y de ahí sale el agendamiento.** Cada
  profesional declara sus días, sus horas y cuánto dura su consulta
  (`citas:mi_horario`, sobre `Agenda`). De esas franjas salen los turnos que ve
  ventanilla Y la duración que se graba en cada cita: no hay un número por
  omisión que decida por él. Solo en servicios propios, sin franjas que se
  pisen —la persona es una— y la consulta tiene que caber en la franja.
  Estrechar el horario **no cancela** citas ya reservadas: el sistema avisa de
  las que quedan fuera y la decisión es del profesional.
- **Asignar un servicio es conceder acceso, y lo hace Administración General.**
  `usuarios:gestion_perfiles` es la única pantalla que toca servicios, sección,
  rol y firma —`mi_perfil` sigue sin aceptarlos, que sería ampliarse el acceso a
  uno mismo—. Ni Dirección ni Coordinación: uno de los servicios abre contenido
  sellado. Cada cambio deja en la bitácora QUÉ entró y QUÉ salió, servicio por
  servicio. Y nadie se quita a sí mismo la Administración General: si el único
  administrador se degrada, no queda quien pueda devolvérsela.
- **La portable no reparte la base.** Una copia de `sibu.sqlite3` en el disco
  de cada profesional pone las sesiones de Psicología en el computador de
  Farmacia: quien tiene el archivo lo abre con cualquier visor de SQLite y se
  salta el RBAC entero. Los datos viven en UNA instancia y la portable es el
  cliente que llega a ella (`portable/servidor.txt`). Sincronizar el archivo
  de la base por Syncthing, Drive o una carpeta de red no es una alternativa:
  es la misma fuga, más corrupción.
- **En SQLite `select_for_update()` no bloquea.** El backend de Django declara
  `has_select_for_update = False` y la llamada es un no-op, así que las
  protecciones de concurrencia de farmacia y de la ficha socioeconómica quedan
  sin efecto en modo portable. Con una sola persona escribiendo en su propia
  carpeta da igual; compartir el archivo entre varios NO es una opción.
- **Un anexo nombra a personas.** La nómina y las evidencias del informe
  estadístico llevan la identidad protegida por omisión (sin cédula, teléfono,
  correo ni número de expediente —que es `EXP-<cédula>`—) y no existen para los
  servicios confidenciales.

## Trampas técnicas que ya nos costaron caro

- **Insertar una función encima de otra decorada le roba el decorador.** Meter
  un `def` nuevo entre `@transaction.atomic` y la función que decoraba deja a
  la original sin transacción y a la nueva envuelta en una. No lo ve ninguna
  prueba de comportamiento normal: lo ve una que compruebe que un fallo a mitad
  no deja el dato partido.
- **Auditar y abortar no caben en la misma transacción.** Registrar un rechazo
  dentro de `@transaction.atomic` y luego lanzar ValidationError revierte el
  propio log. Pasó dos veces (firma, portal).
- **Ejecutar `ruff check .` y `ruff format --check .` por separado, sin `&&`.**
  El `&&` oculta el fallo de formato y tumba el CI.
- **Las pruebas de configuración deben FIJAR lo que afirman, no heredarlo del
  entorno.** Una prueba que lee `DATABASES` o `BASE_DIR` del entorno pasa en una
  máquina y falla en otra.
- **Cédulas de prueba deben pasar el módulo 10 ecuatoriano**: `1100000007`,
  `1700000001` son válidas; `1104567890` NO.
- **Zona horaria America/Guayaquil**: usar `timezone.localtime()`, no comparar
  UTC contra `localdate()`.
- **Un decimal con coma es un decimal: `apps/core/numeros.py` es la única
  lectura.** Aquí se escribe 450,50. El sistema lo leía de cuatro maneras
  —×100 al cargar, cero al sumar, vacío en signos vitales, bien solo en
  Laboratorio—, todas silenciosas y todas alimentando el estrato que orienta
  una beca. No escribir otra conversión: `a_decimal` (lanza), `a_decimal_o`
  (indulgente, para lo YA guardado), `a_entero`, `es_ambiguo`. Y `Decimal("8,5")`
  lanza `InvalidOperation`, que NO es `ValidationError`: un `except
  (ValidationError, KeyError)` no lo atrapa.
- **Guardar lo leído, no lo tecleado.** Validar «8,5» y luego guardar la cadena
  en un campo decimal vuelve a romper al escribir, donde ya no hay a quién
  avisar.
- **Indulgente con lo guardado, estricto con lo tecleado.** Un cálculo sobre
  fichas viejas no puede reventar por un «no aplica»; un formulario que acaba
  de recibir «450,5O» tiene que devolverlo, porque si lo ignora ese ingreso
  desaparece del hogar.
- **Un cero es falsy: `{% if valor %}` lo esconde.** Escondía el puntaje 0,00
  SBU —que es «extrema vulnerabilidad»— y el rango de laboratorio que empieza
  en 0. Usar `{% if valor is not None %}`; distinguir el cero de la ausencia es
  el objetivo, no borrar la ausencia.
- **Un color semántico de Bootstrap no vale para un mapa clínico.** La línea
  gráfica tiñe `primary` con el verde de la UNL, así que el diente obturado
  (`btn-primary`) salió del mismo verde que el sano (`btn-success`): 1,14:1 de
  contraste. Paleta propia, y el color nunca decide solo —cada pieza lleva su
  inicial, porque el 8 % de los hombres no distingue rojo de verde—.
- **Un atributo que no existe no da error en una plantilla: da un hueco.**
  `{{ receta.codigo }}` sobre un modelo cuyo campo es `numero` responde 200 y
  pinta vacío. Ninguna prueba de estado ni de contexto lo ve; lo ve una que
  compruebe que lo propio APARECE (`assert receta.numero in contenido`).
- **Un `<a href>` es un GET: no vale para una vista de solo POST.** Django 5
  retiró el GET de `LogoutView`, así que el icono de cerrar sesión devolvía
  405. Se arregla en la PLANTILLA —formulario POST con su `csrf_token`—, nunca
  aflojando la vista: el GET es lo que permitiría cerrar la sesión ajena con un
  `<img src="/cuentas/logout/">`. Un barrido comprueba que todo `{% url %}`
  dentro de un `href` responda a GET.
- **Comentarios de plantilla `{# #}` solo funcionan en una línea.** Para varias,
  `{% comment %}`.
- **`pluralize` no sirve para una palabra con tilde en la última sílaba.**
  «atención» → `atencion{{ n|pluralize:"es" }}` imprime «1 atencion», sin
  tilde. Usar `{{ n|plural:"atención,atenciones" }}` (`apps/core/templatetags/
  textos.py`); una prueba barre las plantillas buscando la recaída.
- **El mismo valor llega escrito de varias maneras.** Cuatro bases
  institucionales, cuatro escrituras: «F», «f», «Femenino», «Mujer». El informe
  daba cuatro filas para dos grupos. Se agrupa al CONTAR en
  `core.vocabulario.normalizar`, nunca al guardar, y solo hay sinónimos donde
  el vocabulario es oficial y cerrado: género e identidad son libres a
  propósito y ahí solo se unifica la capitalización.
- **Un formulario no envía las casillas desmarcadas.** «Quité todas las
  variables» y «acabo de abrir la pantalla» llegan idénticos al servidor: hace
  falta un testigo oculto (`elegir=1`) para distinguirlos, o el informe sale con
  todo justo cuando se pidió que no.
- **Una cifra y su evidencia no pueden calcularse dos veces.** El informe y sus
  anexos comparten `reportes.services.etiquetar`; dos consultas parecidas se
  separan y el anexo acaba desmintiendo lo que respalda.
- **El almacenamiento con manifiesto sigue las referencias internas.**
  `CompressedManifestStaticFilesStorage` lee los `url()` de un CSS y el
  `sourceMappingURL` de un JS: si apuntan a algo que no se vendorizó,
  `collectstatic` aborta. Y el `|| true` del Dockerfile convertía ese fallo de
  construcción visible en uno de producción invisible —el sitio arrancaba sin
  estáticos, cada página con un ValueError—.
- **Una dependencia de producción que solo está en `prod.txt` no se prueba.**
  El CI instala `dev.txt`. La prueba que ejercita el almacenamiento de
  producción fallaba allí por no encontrar WhiteNoise, no por lo que comprueba,
  y en local pasaba porque el entorno se había separado del de integración.
- **`docker compose` no lee `.env.prod` para sus propios `${...}`.** `env_file:`
  alimenta al CONTENEDOR; la interpolación la resuelve el CLI mirando el shell
  y un `.env` del directorio. Sin `--env-file`, el arranque aborta diciendo que
  falta una variable que está escrita delante.
- **`createsuperuser` no daba una cuenta que pudiera gobernar el sistema.**
  `rol_principal` sale por omisión como «consulta»: la primera cuenta del
  despliegue veía seis módulos de diecisiete. Lo arregla el gestor del modelo,
  no un paso manual del manual de instalación.
- **Una redirección que pierde el parámetro de contexto miente.** Anotar desde
  Medicina y volver a otro servicio enseña el valor sin tocar bajo un aviso que
  dice «Anotado»: parece que no guardó. La redirección conserva el `?servicio=`.
- **Una hora que compone el navegador sale en la zona del equipo.** El
  desplegable de turnos usaba `toLocaleString`: en un equipo mal configurado
  ofrecía «02:00 p. m.» para el turno de las 09:00 y el aviso de guardado
  confirmaba «09:00» —la misma cita con dos horas en la misma pantalla—. La
  agenda se define en hora de Loja y el servidor ya la conoce: la etiqueta
  viaja escrita desde el servidor, no se recalcula en el cliente.
- **Un valor por omisión que nadie sobrescribe es una mentira con vida propia.**
  `reservar_cita` llevaba `duracion_min=20` y ninguna pantalla lo pasaba: con
  consultas de 40 min configuradas, la pantalla ofrecía turnos cada 40 y
  grababa citas de 20, así que SIBU daba por libre la segunda mitad de cada
  consulta. La duración la pone la agenda.
- **Ocupado es solapar, no empezar en el mismo minuto.** Comparar la igualdad
  exacta de `fecha_hora` basta mientras todas las citas duran lo mismo; en
  cuanto el profesional cambia su duración, deja de bastar.
- **Una prueba que ejercita justo el valor por omisión no falsifica nada.** La
  del retorno al servicio anotaba desde Enfermería, que era el servicio al que
  se caía por omisión: pasaba con el defecto puesto. Al falsificar, si la
  prueba NO falla, el fallo está en la prueba.
- **`AnonymousUser` no es una persona.** django-guardian crea esa fila por
  migración para colgar los permisos por objeto del usuario anónimo. Aparecía
  en la lista de cuentas sin ficha con un botón de «dar ficha» al lado. Se
  esconde de la lista Y se niega en el servicio: un `pk` en el POST no es un
  permiso.
- **`Usuario.objects.exists()` siempre es cierto.** La migración de
  django-guardian deja su fila `AnonymousUser`, así que «¿hay alguna cuenta
  todavía?» no se puede preguntar así. El creador de cuentas de la portable lo
  preguntaba de esa forma y nunca reconocía la primera cuenta como primera: la
  creaba con «Consulta Restringida» y quien acababa de instalar el sistema
  entraba y no podía hacer nada. Se pregunta con
  `selectors.cuentas_de_persona()`.
- `auto_now_add` sobre tabla existente falla sin default.

## Convenciones

- Todo en español: código, comentarios, commits (Conventional Commits), UI.
- Estructura por app: `models`, `services` (lógica), `selectors` (consultas),
  `api`, `serializers`, `views`, `urls`, `tests`.
- Las integraciones externas van tras un **provider** intercambiable
  (`AcademicoProvider`, `FirmadorProvider`, `AlmacenEvidenciasProvider`): el
  sistema debe funcionar sin ellas. Firma y Google Drive vienen deshabilitados
  por defecto.
- La navegación se deriva del RBAC (`apps/core/navegacion.py`), nunca de listas
  fijas paralelas.
- Prosa concisa, sin redundancia. Citas APA 7 en docs cuando aplique.

## Comandos

    make up        # levanta la web (deriva variables de Codespaces)
    make perfil    # perfil de dev con todos los servicios (solo DEBUG=True)
    make setup     # migraciones + datos base + RBAC
    make test      # pytest con cobertura
    make lint      # ruff check, ruff format --check y bandit (separados)

Entorno docker-compose: PostgreSQL en el contenedor `db`, Redis en `redis`. No
existen `service postgresql` ni `redis-server` dentro del contenedor `web`.

Portable:

    python portable/arrancar.py        # levanta SIBU local y abre el navegador
    python portable/crear_cuenta.py    # la primera cuenta
    powershell -ExecutionPolicy Bypass -File portable\preparar_windows.ps1

Despliegue del servidor central (Oracle Cloud, capa gratuita) en
`docs/ORACLE_CLOUD.md`. El `--env-file` no es opcional:

    docker compose --env-file .env.prod -f docker-compose.prod.yml up -d --build
    ... exec web python manage.py createsuperuser
    ... exec web python manage.py ensayo_despliegue --usuario X --clave Y

## Antes de dar por terminado un cambio

    ruff check .
    ruff format --check .
    pytest apps -q          # deben pasar TODAS (1607 al día de hoy)
    python manage.py check
    python manage.py makemigrations --check --dry-run
