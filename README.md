# SIBU portable

Sistema Integral de Bienestar Universitario de la **Universidad Nacional de
Loja**, en versión **portable**: corre desde una carpeta, sin instalar nada.
El profesional pulsa un icono, se abre su navegador en la pantalla de
credenciales, entra y trabaja. Al cerrar, la carpeta se guarda en una memoria
o se copia a otro computador y sigue funcionando igual.

Nueve servicios: Medicina, Enfermería, Odontología, Laboratorio Clínico,
Farmacia, Psicología, Psicopedagogía, Trabajo Social y Becas. Más citas,
expediente único, derivaciones, firma electrónica, talleres, portal del
estudiante y tablero de gestión.

> El repositorio original —`Jorgeperezr/sibu`— queda **archivado** con el
> despliegue de servidor (Oracle Cloud, PostgreSQL, nginx). Aquí continúa el
> desarrollo de la versión portable.

## Arrancar en Windows, sin instalar nada

1. Descargue **`SIBU-portable-windows.zip`**: en GitHub, pestaña *Actions* →
   *Portable Windows* → la última ejecución en verde → *Artifacts* (o, si hay
   versiones publicadas, desde *Releases*). Trae Python y todas las
   dependencias dentro.
2. Antes de descomprimir: clic derecho en el zip → *Propiedades* → marque
   **Desbloquear** → *Aceptar*. Si no, Windows marca cada archivo como
   descargado de internet y pide confirmación al abrirlos.
3. Descomprímalo donde quiera: el escritorio, *Documentos* o una memoria.
4. Doble clic en **`Abrir SIBU`**. La primera vez tarda un minuto: prepara la
   base. Se abre el navegador.
5. La primera vez, el navegador pide crear la cuenta de **Administración
   General**. Desde ella se da de alta al resto en *Perfiles → Nueva cuenta*.

Desde el primer arranque aparece en la carpeta un acceso directo **`SIBU`**
con el escudo de la UNL; se puede llevar al escritorio (clic derecho →
*Enviar a* → *Escritorio*). Cerrar la ventana negra cierra SIBU.

Esa carpeta la construye y la **prueba en un Windows real** GitHub Actions en
cada cambio (`.github/workflows/portable-windows.yml`): arma la carpeta, la
arranca, crea la primera cuenta por la pantalla y hace una copia de
seguridad. Si eso falla, no se publica el zip.

**En Linux o macOS**, con Python instalado: `portable/sibu.sh`, o
`python portable/arrancar.py`.

`arrancar.py` busca un puerto libre, aplica las migraciones que falten,
levanta el servidor, hace la copia de seguridad del día y abre el navegador
**cuando el servidor ya responde**.

### Trabajar entre varios por la WiFi de la oficina

Cada carpeta, sola, es un SIBU aislado: lo que registra una compañera no lo
ve nadie más. Para trabajar juntos, **un computador guarda los datos** y los
demás entran desde los suyos por la misma red WiFi. No hace falta servidor ni
instalar nada.

**En el computador que guardará los datos** (uno que esté encendido mientras
se trabaja):

1. Doble clic en **`Compartir SIBU en la red`**. Queda guardado: desde
   entonces su icono «SIBU» arranca siempre así.
2. La primera vez Windows pregunta si deja a Python usar la red: marque
   **Redes privadas** y pulse *Permitir acceso*. Si la WiFi está marcada como
   *Pública*, cámbiela a *Privada* (*Configuración → Red e Internet*).
3. La ventana muestra la dirección que hay que dictar a los compañeros, por
   ejemplo `http://RECEPCION:8000`. **No cierre esa ventana ni apague o
   suspenda el equipo** mientras los demás trabajen: los datos están ahí.

**En el computador de cada compañero:**

1. Doble clic en **`Conectar al SIBU de la oficina`** y escriba esa dirección.
   Queda guardada: desde entonces su icono «SIBU» abre el de la oficina.
2. Entra con la cuenta que le dio Administración General.

Para volver a usar SIBU solo en un equipo: en el servidor, borre
`portable\compartir_en_red.txt`; en un compañero, abra *Conectar…* y escriba
`NINGUNO`.

> **Solo en la WiFi propia de la oficina, con contraseña.** El tráfico va sin
> cifrar: en una red compartida —la WiFi de la universidad, con estudiantes
> conectados— alguien podría ver contraseñas y datos clínicos, incluida la
> contraseña de Psicología. Para trabajar desde fuera de la oficina, o en una
> red que no es solo de la Unidad, está la red privada cifrada de
> [`docs/CONEXION_ENTRE_PORTABLES.md`](docs/CONEXION_ENTRE_PORTABLES.md).

**Nunca** copie ni sincronice `datos\sibu.sqlite3` entre computadores para
«compartir»: rompe el sello de Psicología —el archivo se abre con cualquier
visor— y las copias acaban diciendo cosas distintas sobre la misma persona.

### La primera cuenta, y las demás

La primera vez el navegador se abre en *Bienvenido a SIBU*. **La primera
cuenta nace con Administración General**, porque si no, nadie podría conceder
servicios a nadie. Esa pantalla solo existe en la portable, solo desde el
propio computador y solo mientras no hay ninguna cuenta.

Desde ahí se da de alta al resto en *Perfiles → Nueva cuenta*:

1. Administración General crea la cuenta con la cédula y una **clave
   temporal**, que le dice a su dueño.
2. La misma pantalla lleva a asignar sección y servicios.
3. Su dueño entra y **el sistema le obliga a cambiar la clave** antes de ver
   nada: si la cuenta es de Psicología, una clave que conocen dos personas
   sería una puerta al contenido sellado.

Luego cada profesional declara su horario en *Mi horario*; Farmacia da de alta
sus medicamentos en *Inventario* y Laboratorio sus exámenes en *Catálogo de
exámenes*.

## La carpeta de datos

Todo lo que la portable escribe vive junto a ella, en `datos/`:

```
datos/
  sibu.sqlite3        la base entera
  media/              evidencias de talleres, documentos, adjuntos
  correo/             los correos que el sistema habría enviado
  clave.txt           la SECRET_KEY de ESTA carpeta
  sibu.log            el registro, que aquí no hay journalctl
```

Copiar la carpeta es copiar el sistema con sus datos dentro. Borrar `datos/`
es volver a empezar.

`clave.txt` se genera sola la primera vez y **no se comparte**: firma las
sesiones de esta carpeta.

## Dos modos: sola o conectada

Cada portable decide al arrancar, mirando si existe `portable/servidor.txt`:

| `portable/servidor.txt` | Qué hace | Para qué |
|---|---|---|
| No existe | Levanta su propio servidor contra su `datos/sibu.sqlite3` | Un profesional, su computador, sus datos |
| Contiene una URL | No levanta nada: abre el navegador en ese SIBU central | Varios profesionales sobre un mismo expediente |

Hay plantilla en `portable/servidor.txt.example`.

**El modo conectado es el que el servicio necesita, y no es opcional cuál se
elige.** Repartir una copia de `sibu.sqlite3` a cada profesional rompe el sello
de Psicología de forma irreparable: quien tenga el archivo lo abre con
cualquier visor de SQLite y lee el contenido clínico sin pasar por el RBAC. Una
instancia central y las portables como clientes mantiene el sello; copias
sincronizadas, no.

**Cómo se conectan entre sí** —qué red superpuesta de código abierto usar,
comparadas por licencia y por lo que cuesta montarlas—:
[`docs/CONEXION_ENTRE_PORTABLES.md`](docs/CONEXION_ENTRE_PORTABLES.md).

## Tres cosas que saber antes de usarla en serio

1. **No hay correo.** La portable escribe los correos en `datos/correo/` en vez
   de enviarlos. El sistema lo sabe y lo dice: los resultados de laboratorio
   dejan una notificación que pide entregarlos en ventanilla, y el portal del
   estudiante rechaza la vinculación explicando que este SIBU no tiene correo
   configurado, en vez de dejar a alguien esperando un código que no va a
   llegar.
2. **No hay PDF si no hay WeasyPrint.** Necesita librerías del sistema (GTK en
   Windows) que una carpeta portable no lleva. Cuando faltan, la pantalla lo
   dice y ofrece la alternativa —ver en pantalla, exportar a Excel—; no
   devuelve un 500.
3. **Los adjuntos los sirve Django.** En un servidor es trabajo de nginx; aquí
   no hay nginx, así que la portable sirve `/media/` ella misma. Sin eso se
   sube una evidencia a un taller y luego no se puede abrir: 404 sobre un
   archivo que está en el propio disco.

Y una cuarta, por si pasa: tras **5 intentos fallidos** el acceso se bloquea
15 minutos. La pantalla está en español, dice cuánto falta, aclara que no se ha
perdido nada e indica `python manage.py changepassword SU_USUARIO` para cuando
no hay nadie a quien llamar.

## Documentación

| | |
|---|---|
| [`docs/QUE_FALTA_PARA_DESPLEGAR.md`](docs/QUE_FALTA_PARA_DESPLEGAR.md) | **Lo que está listo, lo que falta y en qué orden.** |
| [`docs/PORTABLE.md`](docs/PORTABLE.md) | Armar la carpeta, repartirla y qué saber antes de usarla en serio. |
| [`docs/CONEXION_ENTRE_PORTABLES.md`](docs/CONEXION_ENTRE_PORTABLES.md) | Cómo se conectan los profesionales entre sí. |
| [`docs/OPERACION.md`](docs/OPERACION.md) | Qué se ejecuta cada día y qué significa lo que responde. |
| [`docs/SEGURIDAD.md`](docs/SEGURIDAD.md) | El control de acceso tal como está montado, y qué hacer al añadir un endpoint o una pantalla. |
| [`docs/COMO_CARGAR_LA_BASE.md`](docs/COMO_CARGAR_LA_BASE.md) | La carga de la base institucional, paso a paso. |
| [`docs/CARGA_BASE_INSTITUCIONAL.md`](docs/CARGA_BASE_INSTITUCIONAL.md) | El diccionario de las 157 columnas. |
| [`docs/Informe_Tecnico_SIBU_UNL.md`](docs/Informe_Tecnico_SIBU_UNL.md) | Alcance, modelo de datos, requerimientos, flujos. |
| [`docs/DESPLIEGUE.md`](docs/DESPLIEGUE.md) · [`docs/ORACLE_CLOUD.md`](docs/ORACLE_CLOUD.md) | El despliegue de servidor, para el SIBU central. |

## Reglas del dominio que no se negocian

- **El sello de Psicología es absoluto.** Su contenido clínico no es accesible
  fuera del servicio: ni Dirección, ni administración, ni break-glass.
- **Los tableros muestran gestión, no contenido.** En servicios
  confidenciales, un conteo de pacientes distintos menor que 5 se reporta como
  `<5`: un conteo pequeño identifica.
- **Un taller no es una atención clínica**, y los talleres no se publican al
  estudiante: los ve el personal del servicio que los organiza.
- **Verificar matrícula no suspende una beca.** El sistema informa; la decisión
  es de Trabajo Social, con causal escrita.
- **El portal aísla por identidad, no por rol.**
- **La edad se calcula, nunca se guarda.** Sale de la fecha de nacimiento.
- **El horario lo pone quien atiende**, y de ahí sale el agendamiento: sus
  días, sus horas y cuánto dura su consulta (`citas:mi_horario`).
- **Asignar un servicio es conceder acceso**, y lo hace Administración General
  (`usuarios:gestion_perfiles`), no Dirección ni Coordinación.

Las demás, y las trampas técnicas que ya costaron caro, en `CLAUDE.md`.

## Desarrollo

Para trabajar en el código hace falta el entorno completo —PostgreSQL— porque
es contra el que corren las pruebas y es el que usa el SIBU central:

```bash
make up         # prepara la base si hace falta y sirve
make cuentas    # recordar con qué usuario entrar
make perfil     # dar a una cuenta todos los servicios (solo DEBUG=True)
make test       # pytest con cobertura
make lint       # ruff check, ruff format --check y bandit (separados)
```

El `&&` entre `ruff check` y `ruff format --check` oculta el fallo de formato y
tumba el CI: van separados.

### Estructura

```
config/settings/   base · dev · prod · test · portable
portable/          launcher, creación de cuenta, scripts e icono
apps/              core, usuarios, academico, expediente, los nueve
                   servicios, becas, talleres, citas, portal, reportes
api/v1/            capa REST
templates/ static/ Bootstrap 5
docs/              documentación
```

Cada app sigue la misma división: `models`, `services` (lógica), `selectors`
(consultas), `api`, `serializers`, `views`, `urls`, `tests`.

### Antes de dar por terminado un cambio

Los cinco, por separado, y las pruebas tienen que pasar **todas**:

```bash
ruff check .
ruff format --check .
pytest apps -q
python manage.py check
python manage.py makemigrations --check --dry-run
```
