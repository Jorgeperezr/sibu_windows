# Qué falta para desplegar SIBU

Estado al 5 de noviembre de 2026 (`main` de `sibu_windows`). Lo que dice
«verificado» se comprobó ejecutándolo, no leyendo el código: 1532 pruebas, y un
recorrido completo con navegador real contra una portable —alta de cuentas,
triaje, consulta, receta, despacho, laboratorio, derivación a Psicología y el
sello—.

## La decisión que va primero

**Una instancia central con los datos, y las portables como clientes.** No es
una preferencia técnica: repartir una copia de `sibu.sqlite3` a cada
profesional rompe el sello de Psicología sin remedio, porque quien tenga el
archivo lo abre con cualquier visor de SQLite y lee el contenido clínico sin
pasar por el control de acceso. Detalle en `CONEXION_ENTRE_PORTABLES.md`.

Una portable **sola** (su propia base) sirve para una persona que trabaja
aislada. Para la Unidad, cliente de la central.

## Lo que está listo

| Pieza | Estado |
|---|---|
| Arranque desde una carpeta, sin instalar (`arrancar.py`, `SIBU.bat`) | Verificado en Linux |
| Modo cliente: `portable/servidor.txt` con la dirección de la central | Verificado; avisa si la red privada no responde |
| Primera cuenta (`crear_cuenta.py`) y el resto desde *Perfiles → Nueva cuenta* | Verificado; clave temporal obligada a cambiarse |
| Catálogos de Farmacia y Laboratorio desde sus pantallas | Verificado |
| Decimales con coma («36,8», «13,5») de punta a punta | Verificado con navegador real |
| Sello de Psicología: pantallas, API y los 62 modelos del panel de administración | Verificado sin fugas |
| Copia de seguridad diaria de la portable (`manage.py respaldar`) | Verificado; copia coherente y comprobada |
| Servidor Linux en Oracle Cloud con Docker | Documentado (`ORACLE_CLOUD.md`); ensayable con `manage.py ensayo_despliegue` |

## Lo que falta

### Decisiones de la Unidad (nadie puede tomarlas por ella)

1. **Dónde vive la instancia central.** Oracle Cloud (documentado) o un equipo
   de la Unidad encendido siempre. Ver «Técnico», punto 1: hoy un equipo
   Windows no puede hacer de central.
2. **Laboratorio con una sola persona.** Validar resultados exige a alguien
   distinto de quien los registró. Con una sola laboratorista, ningún
   resultado llega nunca a publicarse. Hay que decidir: una segunda persona
   que valide, o una excepción explícita y registrada.
3. **Correo institucional (SMTP).** Sin él, los resultados se entregan en
   ventanilla y la vinculación del portal se hace en persona. El sistema ya lo
   dice; falta decidir si se configura.
4. **Firma electrónica (FirmaEC).** Viene deshabilitada. Habilitarla requiere
   las credenciales del servicio institucional.
5. **Protección de datos.** SIBU trata datos de salud: la Ley Orgánica de
   Protección de Datos Personales (Ecuador, 2021) exige base legal, registro
   del tratamiento y medidas de seguridad. Es una tarea institucional, no del
   código.

### Técnico

1. **Que una portable pueda hacer de central en Windows.** Hoy escucha solo en
   `127.0.0.1`. Haría falta un «modo servidor»: escuchar en la red privada,
   aceptar esa dirección y servir con HTTPS. Con SQLite aguanta a un puñado de
   profesionales, pero sin bloqueos de fila (`select_for_update` no hace nada
   en SQLite): dos despachos simultáneos del mismo lote podrían no verse. Para
   la central, PostgreSQL es lo correcto.
2. **Probar la portable en Windows de verdad.** `preparar_windows.ps1` (Python
   3.11.9 embebido) nunca se ha ejecutado en un Windows: este entorno es Linux.
   Es lo primero que hay que hacer en un equipo de la Unidad.
3. **PDF en Windows.** WeasyPrint necesita GTK, que la carpeta no lleva. Sin
   él, los informes se ven en pantalla y se exportan a Excel; el sistema lo
   avisa. Para PDF hay que añadir GTK al paquete.
4. **CIE-10 completo.** Vienen 56 códigos curados. Medicina solo puede
   diagnosticar con esos. Hay que cargar el catálogo oficial completo
   (~14 000 códigos).
5. **Recordatorios de cita en el servidor.** Una línea de cron:
   `0 * * * * python manage.py recordatorios --silencioso`. En la portable ya
   se hacen al abrir.
6. **Copias fuera del equipo.** `respaldar` guarda en `datos/respaldos/`, en el
   mismo disco. Hay que llevarlas a otro sitio cifrado y bajo control de la
   Unidad: contienen la base entera, Psicología incluida. En el servidor,
   `pg_dump` (en `ORACLE_CLOUD.md`). Y probar restaurar: una copia que nunca
   se restauró no es una copia.

### Infraestructura

1. **Red privada (NetBird)**: el coordinador (su nube gratuita hasta 100
   equipos, o propio) y el cliente en cada computador.
2. **Cifrado de disco** (BitLocker) en cada equipo con una portable sola o con
   respaldos. En una memoria FAT32 no hay permisos: `datos/clave.txt` queda
   legible para cualquiera.
3. **Certificado HTTPS** en la central.

## Orden sugerido

1. Decidir dónde vive la central y preparar ese equipo (Oracle Cloud está
   documentado paso a paso).
2. Montar NetBird en la central y en un primer computador.
3. Probar `preparar_windows.ps1` en ese computador y dejarlo como cliente.
4. Crear la primera cuenta y dar de alta al equipo desde *Perfiles*.
5. Cargar el CIE-10 completo, los catálogos de Farmacia y Laboratorio y la base
   institucional de cada estamento.
6. Configurar copias fuera del equipo y **restaurar una** para comprobarla.
7. Una semana con un servicio antes de abrirlo a todos.

## Opciones para mejorar (vistas en clinube)

Funciones de clinube que encajan en SIBU y aún no se han traído, de más a
menos útiles para la Unidad:

1. **Consentimiento informado firmado en pantalla.** La persona firma con el
   dedo en una tableta; se guarda la imagen de la firma, el PDF, la hora, la IP
   y el equipo. Hoy SIBU tiene firma electrónica del profesional (FirmaEC), no
   de la persona atendida.
2. **Certificado de atención en Odontología** (en Medicina ya está), y que
   imprimir desde el navegador sustituya a WeasyPrint en los demás informes de
   la portable de Windows.
3. **Copia de seguridad cifrada con frase**, para la copia que va a un disco
   externo: hoy depende de cifrar ese disco (BitLocker).
4. **Vista previa de documentos en un modal**, sin salir de la consulta.
5. **Avisos del día**: quién llegó y espera, la próxima cita.
6. **Dictado en el propio equipo** (Whisper u otro motor local) para que el
   audio no salga hacia Google o Microsoft. Sería la condición para ofrecerlo
   alguna vez en Psicología, y aun así es una decisión del servicio.

