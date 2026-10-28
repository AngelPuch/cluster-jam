# Docker y PostgreSQL de Personalization

Este incremento construye la imagen del servicio y una base PostgreSQL
aislada. La imagen inicia la API REST. El servicio de herramientas
`personalization-check` conserva la comprobación técnica de configuración,
conexión, esquema y permisos. No se crean tablas de negocio al arrancar.

## Requisitos

- Docker Desktop con el motor de contenedores Linux iniciado, o Docker
  Engine con Compose en Ubuntu.
- Python 3.14 para las herramientas del proyecto en Windows.
- Ejecutar los siguientes comandos desde la raíz del repositorio.

## Preparar secretos locales

```powershell
py -3.14 infra/personalization/provision_local.py
# Solo si todavía no existe .env:
Copy-Item infra/personalization/.env.example infra/personalization/.env
# Editar las dos URLs públicas del proyecto Supabase en ese archivo
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
replicar ni omitir RLS. Es dueño del esquema `app`, donde se ejecutan
las migraciones Alembic versionadas. El rol administrativo no se utiliza para
la conexión del servicio.

`postgres/001-bootstrap.sql` prepara el rol y el esquema solamente cuando
el volumen está vacío. No crea tablas de negocio ni sustituye migraciones.
Editar ese archivo o un secreto no modifica automáticamente un volumen ya
inicializado. Las rotaciones requieren actualizar el rol de PostgreSQL y el
secreto de forma coordinada, conservando los datos.

La comprobación usa SQLAlchemy y psycopg con tiempos límite. Consulta la
base, usuario, propietario del esquema y privilegios. No realiza DDL ni
registra contraseñas, cadenas completas de conexión o errores SQL internos.

La API se conecta a las redes `backend` y `personalization-db` del
proyecto Compose; PostgreSQL permanece exclusivamente en la segunda.
La orquestación conjunta de otros servicios se incorporará al despliegue.
RabbitMQ mantiene su configuración independiente.

## Prueba automatizada del incremento

```powershell
py -3.14 infra/personalization/provision_local.py
py -3.14 infra/personalization/verify_stack.py
```

La prueba construye la imagen y crea un proyecto Compose temporal con un
UUID. Comprueba acceso real, usuario sin privilegios, red interna, puerto no
publicado y ausencia de tablas antes de migrar. Instala y prueba las
migraciones y restricciones con PostgreSQL real. Después recrea el contenedor de
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


## API REST y publicación local

```powershell
docker compose -f infra/personalization/compose.yaml --profile tools build personalization-migrate
docker compose -f infra/personalization/compose.yaml up -d --wait db-personalizacion
docker compose -f infra/personalization/compose.yaml run --rm personalization-migrate
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.dev.yaml up -d --wait personalization
```

La API estará en `http://127.0.0.1:8082`, con salud en `/health/live` y
`/health/ready`, Swagger UI en `/docs` y contrato en `/openapi.json`.
`compose.dev.yaml` publica únicamente el puerto REST en loopback; el archivo
base no publica puertos. gRPC se implementará en un incremento posterior.

La prueba automatizada también detiene PostgreSQL, comprueba liveness 200
y readiness 503, vuelve a iniciarlo y exige recuperación a readiness 200.
Los logs deben ser JSON y no contener los tokens ni query strings de prueba.

Para detener el entorno de desarrollo conservando sus datos:

```powershell
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.dev.yaml down
```


## Configuración pública de autenticación

Compose requiere `SUPABASE_ISSUER` y `SUPABASE_JWKS_URL`, documentadas en
`.env.example`. El archivo local `.env` está ignorado. Conservarlo si ya
existe y agregar solamente esas dos variables; no copiar credenciales de
Auth ni sobrescribir otros valores. Ambas URLs deben usar HTTPS y el mismo
origen. La API valida los JWT localmente con claves públicas en caché.

`verify_stack.py` proporciona URLs de prueba al entorno de sus procesos
Docker, con prioridad sobre `.env`. La prueba de infraestructura puede
ejecutarse sin acceso a Supabase ni credenciales de usuarios. El arranque
y los endpoints técnicos no descargan JWKS. Las pruebas criptográficas
de autenticación y autorización se ejecutan durante la construcción de
la imagen, con claves generadas únicamente para las pruebas.


## Migraciones y pruebas de PostgreSQL

`personalization-migrate` ejecuta Alembic mediante el paquete instalado y
utiliza únicamente el secreto de aplicación. Ejecutarlo antes de iniciar
réplicas; la API no aplica migraciones. Readiness exige la revisión vigente.
Repetir `upgrade` mantiene los datos existentes. Se pueden comprobar
consistencia y revisión con las acciones `check` y `current`.

La imagen `personalization-tests` usa la etapa Docker `integration`; no se
despliega como API. `verify_stack.py` la ejecuta con una base temporal vacía
y comprueba restricciones, instalación, reversión y reaplicación. Rechaza
esquemas previamente poblados. Usar ese verificador para QA y reservar
`personalization-migrate` para preparar la base de desarrollo.

El modelo, decisiones de tipos, comandos y reversión están en
[la guía de persistencia](../../services/personalizationService/docs/database.md).


## Límites de validación de imágenes

Compose transmite `IMAGE_MAX_WIDTH_PX`, `IMAGE_MAX_HEIGHT_PX` y
`IMAGE_MAX_PIXELS`; sus valores iniciales son 8192, 8192 y 16000000.
Se pueden restringir en `.env` o en el entorno. Settings comprueba rangos
antes del arranque; ampliar los techos exige revisar la política y recursos.
El máximo de archivo permanece fijo en 10 000 000 bytes.

Las comprobaciones y pruebas con Pillow se ejecutan al construir la imagen.
El contrato HTTP actual sigue exponiendo las rutas técnicas; el endpoint
de carga persistente se incorporará junto con Supabase Storage.


## Habilitar Storage privado

Preparar la clave de servidor con `py -3.14 infra/personalization/set_storage_key.py`.
El script usa entrada oculta y conserva el secreto en `.secrets/`, fuera de Git.
Añadir `compose.storage.yaml` a los comandos de Compose para montar la clave
y habilitar las cargas reales. El servicio de herramientas
`personalization-storage` permite `create`, `check`, `pending` y `reconcile`.

La API utiliza un tmpfs de 32 MiB en `/tmp` para el spool multipart, con una
subida activa por proceso. Las demás rutas y la raíz de ejecución mantienen
su configuración anterior. No hay migraciones SQL nuevas: se usa `archivo`.

La configuración completa y pruebas con Postman se describen en
[archivos privados](../../services/personalizationService/docs/private-files.md).


## Worker de imágenes

El perfil `images` añade `personalization-worker`, con la misma imagen del
servicio y un comando independiente. Usar `compose.storage.yaml` para su
red externa y secreto de Storage; no publica puertos. Procesa secuencialmente
con 1 CPU, 512 MiB, raíz de solo lectura y cierre con gracia de 120 segundos.
Los límites `WORKER_BATCH_SIZE` y `WORKER_POLL_SECONDS` están en .env.example.
No agrega tablas ni ejecuta migraciones al arrancar.

El arranque, diagnóstico con `--once` y cierre sin eliminar datos están en
[miniaturas](../../services/personalizationService/docs/print-thumbnails.md).


## Umbral de resolución de impresión

`MIN_PRINT_DPI` se pasa a los procesos del servicio. Omitido o vacío deja
la evaluación pendiente; no hay un mínimo implícito. Configurar un entero
de 1 a 2400 solo cuando el equipo acuerde el valor y recrear la API. El
análisis usa este valor para un aviso, no para rechazar la imagen.
Consultar [reglas de diseño](../../services/personalizationService/docs/design-rules.md).
