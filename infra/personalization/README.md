# Docker y PostgreSQL de Personalization

Este incremento construye la imagen del servicio y una base PostgreSQL
aislada. El comando de la imagen comprueba configuración, conexión, esquema
y permisos; termina con código 0 si todo es correcto. Todavía no inicia un
servidor REST/gRPC ni crea tablas de negocio.

## Requisitos

- Docker Desktop con el motor de contenedores Linux iniciado, o Docker
  Engine con Compose en Ubuntu.
- Python 3.14 para las herramientas del proyecto en Windows.
- Ejecutar los siguientes comandos desde la raíz del repositorio.

## Preparar secretos locales

```powershell
py -3.14 infra/personalization/provision_local.py
docker compose -f infra/personalization/compose.yaml config --quiet
```

El script crea dos contraseñas aleatorias en `.secrets/` y no imprime sus
valores. Conserva los archivos existentes para no desincronizar credenciales
de un volumen ya inicializado. La carpeta queda fuera de Git.

En Linux se limita el directorio a modo 0700 y los archivos a 0444: el
directorio protege su lectura en el host y los montajes permiten leerlos al
usuario sin privilegios dentro de cada contenedor. En Windows se utilizan
los permisos de la carpeta del usuario. Docker monta solamente los secretos
declarados para cada servicio. Estos archivos locales no sustituyen una
gestión de secretos de producción.

El contenedor PostgreSQL recibe la contraseña de administración y la de la
aplicación. La comprobación del servicio recibe únicamente la segunda.

## Construir y comprobar

```powershell
$env:PERSONALIZATION_GIT_SHA = (git rev-parse HEAD).Trim()
$env:PERSONALIZATION_IMAGE_TAG = "0.1.0-$env:PERSONALIZATION_GIT_SHA"

docker compose -f infra/personalization/compose.yaml --profile tools build personalization-check
docker compose -f infra/personalization/compose.yaml up -d --wait db-personalizacion
docker compose -f infra/personalization/compose.yaml run --rm --no-deps personalization-check
```

La última operación debe devolver un evento JSON con `DATABASE_READY` y
código de salida 0. El comando es una herramienta de diagnóstico que termina
al completar la comprobación. La base de datos continúa ejecutándose.

En Ubuntu, utilizar `python3` en lugar de `py -3.14` y `export` para las
variables de imagen. Las dos variables son metadatos, no secretos. Sin ellas
se utiliza la etiqueta de desarrollo `0.1.0-local` y revisión `local`.

La construcción ejecuta lint, formato, tipos, pruebas y empaquetado. La
imagen final contiene dependencias de ejecución y el paquete instalado sin
modo editable. No incluye pruebas, herramientas de desarrollo ni archivos
locales de configuración. Se ejecuta como UID/GID 10001, con raíz de solo
lectura y capacidades retiradas en Compose.

## Base de datos y aislamiento

| Elemento | Configuración |
| --- | --- |
| Servicio y host | `db-personalizacion` |
| Puerto dentro de la red privada | `5432` |
| Base | `personalizacion_db` |
| Usuario de aplicación | `app_personalizacion` |
| Esquema propio | `app` |
| Volumen | `personalization-data`, aislado por proyecto Compose |
| Red | `personalization-db`, interna y sin puertos publicados |

El usuario de aplicación no es superusuario, no puede crear bases o roles,
replicar ni omitir RLS. Es dueño del esquema `app`, donde posteriormente
ejecutaremos migraciones Alembic. El rol administrativo no se utiliza para
la conexión del servicio.

`postgres/001-bootstrap.sql` prepara el rol y el esquema solamente cuando
el volumen está vacío. No crea tablas de negocio ni sustituye migraciones.
Editar ese archivo o un secreto no modifica automáticamente un volumen ya
inicializado. Las rotaciones requieren actualizar el rol de PostgreSQL y el
secreto de forma coordinada, conservando los datos.

La comprobación usa SQLAlchemy y psycopg con tiempos límite. Consulta la
base, usuario, propietario del esquema y privilegios. No realiza DDL ni
registra contraseñas, cadenas completas de conexión o errores SQL internos.

La red compartida del backend se añadirá al incorporar la API; PostgreSQL
permanecerá conectado exclusivamente a su red privada. RabbitMQ conserva
su configuración independiente y no es necesario para esta comprobación.

## Prueba automatizada del incremento

```powershell
py -3.14 infra/personalization/provision_local.py
py -3.14 infra/personalization/verify_stack.py
```

La prueba construye la imagen y crea un proyecto Compose temporal con un
UUID. Comprueba acceso real, usuario sin privilegios, red interna, puerto no
publicado y ausencia de tablas de negocio. Después recrea el contenedor de
PostgreSQL y verifica que conserva el identificador del clúster y el acceso
al esquema. Elimina solamente contenedores, red y volumen de ese proyecto
temporal al terminar; el proyecto de desarrollo queda intacto.

La CI ejecuta la misma prueba en Ubuntu. Los límites de CPU y memoria son
valores iniciales para desarrollo; no representan mediciones de rendimiento.

## Detener y conservar datos

```powershell
docker compose -f infra/personalization/compose.yaml down
```

Este comando conserva el volumen. No añadir `--volumes` al proyecto de
desarrollo si contiene datos que deban conservarse. La recreación de un
contenedor conserva el volumen, pero no reemplaza un respaldo. El ejercicio
de respaldo y restauración forma parte del incremento de operación.


## Docker Desktop no inicia en Windows

Si WSL devuelve `HCS_E_HYPERV_NOT_INSTALLED`, comprobar virtualización del
procesador, Plataforma de máquina virtual y arranque del hipervisor. Con
virtualización y plataforma habilitadas, Docker recomienda ejecutar en
PowerShell como administrador:

```powershell
bcdedit /set hypervisorlaunchtype auto
```

Guardar el trabajo y reiniciar Windows manualmente. Después abrir Docker
Desktop y verificar que `docker info --format '{{.OSType}}'` devuelve `linux`
antes de ejecutar la prueba del incremento. Por defecto no se necesita
iniciar sesión en Docker para trabajar con estos contenedores locales.

Referencia: https://docs.docker.com/desktop/troubleshoot-and-support/troubleshoot/topics/
