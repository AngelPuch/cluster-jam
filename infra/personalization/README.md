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
contenedor conserva el volumen, pero no reemplaza un respaldo. Las herramientas de respaldo y restauración se describen en Operación y recuperación.


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
base no publica puertos. El perfil rpc ejecuta el servidor TLS en 50051.

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

Los modelos y migraciones están en el paquete database del servicio.
No ejecutar downgrade sobre la base local poblada; usar la base desechable
de verify_stack.py para comprobar reversión y reaplicación.


## Límites de validación de imágenes

Compose transmite `IMAGE_MAX_WIDTH_PX`, `IMAGE_MAX_HEIGHT_PX` y
`IMAGE_MAX_PIXELS`; sus valores iniciales son 8192, 8192 y 16000000.
Se pueden restringir en `.env` o en el entorno. Settings comprueba rangos
antes del arranque; ampliar los techos exige revisar la política y recursos.
El máximo de archivo permanece fijo en 10 000 000 bytes.

Las comprobaciones y pruebas con Pillow se ejecutan al construir la imagen.
La carga persistente usa POST /api/v1/files y las validaciones del
servicio; sus contratos y errores están en OpenAPI.


## Habilitar Storage privado

Preparar la clave de servidor con `py -3.14 infra/personalization/set_storage_key.py`.
El script usa entrada oculta y conserva el secreto en `.secrets/`, fuera de Git.
Añadir `compose.storage.yaml` a los comandos de Compose para montar la clave
y habilitar las cargas reales. El servicio de herramientas
`personalization-storage` permite `create`, `check`, `pending` y `reconcile`.

La API utiliza un tmpfs de 32 MiB en `/tmp` para el spool multipart, con una
subida activa por proceso. Las demás rutas y la raíz de ejecución mantienen
su configuración anterior. No hay migraciones SQL nuevas: se usa `archivo`.

Usar la colección files.postman_collection.json de
contracts/postman/personalization para comprobar cargas y descargas.


## Worker de imágenes

El perfil `images` añade `personalization-worker`, con la misma imagen del
servicio y un comando independiente. Usar `compose.storage.yaml` para su
red externa y secreto de Storage; no publica puertos. Procesa secuencialmente
con 1 CPU, 512 MiB, raíz de solo lectura y cierre con gracia de 120 segundos.
Los límites `WORKER_BATCH_SIZE` y `WORKER_POLL_SECONDS` están en .env.example.
No agrega tablas ni ejecuta migraciones al arrancar.

El comando actual del worker es personalization.interfaces.workers.images;
procesa miniaturas y previews de diseños. Desde la raíz:

```powershell
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml --profile images up -d --build personalization-worker
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml --profile images run --rm --no-deps personalization-worker python -m personalization.interfaces.workers.images --once
```

--once procesa un lote por cola. Las intenciones duraderas permiten recuperar
cargas; una revisión obsoleta no se asocia al diseño vigente. Los originales
y derivados históricos permanecen privados.


## Umbral de resolución de impresión

`MIN_PRINT_DPI` se pasa a los procesos del servicio. Omitido o vacío deja
la evaluación pendiente; no hay un mínimo implícito. Configurar un entero
de 1 a 2400 solo cuando el equipo acuerde el valor y recrear la API. El
análisis usa este valor para un aviso, no para rechazar la imagen.
La colección de prueba es design-rules.postman_collection.json.


## gRPC con TLS

El perfil rpc ejecuta PersonalizationDrafts/GetDesignDraft en un proceso
separado, con JWT local y propiedad del borrador. Es de solo lectura:
CATALOG_VALIDATION_PENDING, CHECKOUT_BLOCKED y diagnostic_only=true. No
congela ni cotiza sin la integración real de Catalog.

Preparar certificados de desarrollo e iniciar desde la raíz:

```powershell
py -3.14 -m uv run --locked --project services/personalizationService python infra/personalization/provision_grpc_tls.py
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.dev.yaml -f infra/personalization/compose.storage.yaml --profile rpc up -d --build --wait personalization personalization-grpc
```

El provisionador preserva los archivos existentes en .secrets. El certificado
de desarrollo dura 30 días; la clave privada de CA no se guarda. Producción
requiere sus propios certificados y rotación. Los secretos no entran a Git.
RPC monta clave/certificado TLS, CA y contraseña de su BD; no monta la clave
de Storage. Usa las redes backend y personalization-db. La configuración
base no publica 50051; el overlay dev lo expone solo en 127.0.0.1:50051.
El healthcheck verifica TLS/h2, no readiness de PostgreSQL.

En Postman:

1. Ejecutar las dos solicitudes HTTP de grpc-preparation.postman_collection.json
   con adminAccessToken vigente: ambas 200 y Tests aprobados.
2. Settings → Certificates → CA Certificates: importar .secrets/grpc_ca.crt.
3. New → gRPC, localhost:50051, TLS y verificación de certificado activados.
4. Service definition: importar contracts/proto/personalization/v1/personalization.proto
   y seleccionar PersonalizationDrafts/GetDesignDraft. No hay reflexión.
5. Connection Timeout = 8000 ms. Authorization = No Auth; en Metadata añadir
   solo authorization = Bearer {{adminAccessToken}}.
6. Message: {"design_id":"{{rpcDesignId}}"}. El campo se llama design_id
   en el proto; Use Example Message genera su estructura.

| Caso | Resultado esperado |
| --- | --- |
| Administrador y diseño propio válido | 0 OK |
| Sin metadata authorization | 16 UNAUTHENTICATED |
| JWT cliente vigente o distinto propietario | 7 PERMISSION_DENIED |
| UUID válido inexistente | 5 NOT_FOUND |
| design_id=not-a-uuid | 3 INVALID_ARGUMENT, INVALID_DESIGN_ID |
| Timeout 15000 con administrador y UUID válido | 3 INVALID_ARGUMENT, INVALID_RPC_DEADLINE |

Al terminar, restaurar timeout 8000, JWT administrador e ID válido y repetir
0 OK. La respuesta conserva el snapshot/ETag de REST; campos opcionales
ausentes pueden omitirse. Trailers incluyen error-code y trace-id. gRPC usa
sus estados propios; los errores HTTP mantienen RFC 9457.

La lectura limita mensajes a 65 536 bytes y exige deadline de hasta 10 s.
El contrato .proto y sus bindings se comprueban en CI. Para regenerar,
desde services/personalizationService:

```powershell
py -3.14 -m uv run --locked python -m personalization.interfaces.grpc.codegen --proto ../../contracts/proto/personalization/v1/personalization.proto --output src/personalization/interfaces/grpc/generated
```

Añadir --check verifica que las bindings coincidan. No editar los archivos
generados manualmente.

Para detener los procesos Docker conservando el volumen y los archivos:

```powershell
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml --profile rpc --profile images stop personalization-worker personalization-grpc personalization db-personalizacion
```


## HTTPS local y despliegue Ubuntu

El gateway usa `infra/shared/nginx.conf` y conserva las rutas de Auth. Los
datos siguen en el volumen `cluster-jam-personalization_personalization-data`.
No se necesita una migración nueva: la revisión es `0001_personalization`.

### Preparación local en Windows

Conservar `.env`, contraseñas, clave de Storage y certificados ya preparados.
Para una instalación nueva, provision_local.py y set_storage_key.py preparan
los archivos; el bucket privado debe existir. Desde la raíz del repositorio:

```powershell
py -3.14 -m uv run --locked --project services/personalizationService python infra/personalization/provision_grpc_tls.py
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml -f infra/personalization/compose.https.dev.yaml --profile images build personalization
docker compose -f infra/personalization/compose.yaml up -d --wait db-personalizacion
docker compose -f infra/personalization/compose.yaml run --rm --no-deps personalization-migrate
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml -f infra/personalization/compose.https.dev.yaml --profile images up -d --wait personalization personalization-worker nginx
```

Este overlay publica solo `127.0.0.1:8443`; no combinarlo con compose.dev.yaml
si se quiere probar únicamente a través de HTTPS. Se reutiliza exclusivamente
en desarrollo el certificado local válido para localhost/127.0.0.1. No se
reemplaza ni cambia su CA: `.secrets/grpc_ca.crt` sigue siendo la CA pública
que se importa en Postman. Nunca importar o compartir grpc_server_key.pem.
El overlay de Ubuntu usa una PKI distinta, no estos certificados locales.

En Postman, mantener SSL certificate verification activada. En Settings →
Certificates → CA Certificates, importar `infra/personalization/.secrets/grpc_ca.crt`
si aún no está registrada. Importar la nueva colección y actualizar en el
entorno local `httpsBaseUrl=https://localhost:8443`, `accessToken` y
`adminAccessToken` con JWT vigentes. Conservar baseUrl/authBaseUrl para las colecciones anteriores. La nueva
colección usa únicamente httpsBaseUrl; Auth local sigue en su puerto habitual.

| Petición | HTTP esperado |
| --- | --- |
| 01 Liveness HTTPS | 200 |
| 02 Readiness HTTPS | 200 |
| 03 OpenAPI Personalization | 200 |
| 04 Print catalog as client | 200 |
| 05 Print administration | 200 |
| 06 No JWT | 401, INVALID_ACCESS_TOKEN |
| 07 Client without admin permission | 403, FORBIDDEN |
| 08 Missing route | 404, ROUTE_NOT_FOUND |
| 09 Draft administration | 200 |

Las nueve peticiones son lecturas y no necesitan archivos. Para comprobar
también la subida por HTTPS, duplicar la solicitud POST de archivos ya usada,
cambiar solo su URL a `{{httpsBaseUrl}}/api/v1/files`, usar el JWT cliente y
adjuntar de nuevo un PNG/JPEG válido en `file` (multipart/form-data). Se espera
201; no escribir Content-Type manualmente, Postman añade el boundary.
Una imagen de más de 64 KiB comprueba que ya no aplica el límite de Auth.

Detener después de las pruebas, conservando datos y secretos:

```powershell
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.storage.yaml -f infra/personalization/compose.https.dev.yaml --profile images --profile rpc stop nginx personalization-worker personalization-grpc personalization db-personalizacion
```

### Integración Ubuntu de staging

El equipo debe haber preparado el despliegue compartido con `prepare.py`,
incluyendo `.pki/ca.crt`, `.pki/https.crt` y `.pki/personalization-grpc.crt/key`.
Volver a ejecutar la preparación compartida después de actualizar el código
crea únicamente el certificado RPC ausente y conserva los existentes. No usar
`--renew-certificates` salvo que se quiera renovar la PKI deliberadamente.
El certificado RPC incluye los SAN internos personalization-grpc y
clusterjam-personalization-grpc. El propio servidor y su healthcheck usan TLS.

Desde la copia del repositorio en Ubuntu:

```bash
if [ ! -f infra/personalization/deployment.env ]; then
    cp infra/personalization/deployment.env.example infra/personalization/deployment.env
fi
# Editar solo las URLs públicas y opciones del proyecto en deployment.env.
python3 infra/personalization/provision_local.py
# Solo si falta la clave de servidor, introducirla en el prompt oculto:
if [ ! -f infra/personalization/.secrets/supabase_storage_key ]; then
    python3 infra/personalization/set_storage_key.py
fi
# Conservar el bucket privado existente, sin recrear ni borrar objetos.
bash infra/deploy/deploy.sh personalization
```

Copiar el ejemplo únicamente si deployment.env todavía no existe. No copiar
contraseñas de Auth ni credenciales de su base; Personalization usa su propia
BD. La clave backend de Storage queda solo en `.secrets`. El helper
set_storage_key.py usa la biblioteca estándar y un prompt oculto; funciona
con python3 en Ubuntu y no requiere instalar el servicio en el host.

El target personalization es explícito; `deploy.sh all` conserva el alcance
previo de Auth/shared. Requiere Git limpio y crea una imagen con versión y SHA
de commit. No publicar ni ejecutar un despliegue real antes del PR revisado.
La secuencia es: construir, preparar contraseña si falta, iniciar BD, aplicar
Alembic, verificar bucket, iniciar REST/worker/RPC, comprobar readiness/TLS y
recrear Nginx y verificar readiness a través de HTTPS con su CA. Si migración
o Storage falla, no inicia la nueva versión.
En una actualización los contenedores de la versión anterior pueden seguir
atendiendo; este script no proporciona reversión automática de migraciones.

`compose.sh personalization` usa deployment.env y release.env de forma explícita,
neutraliza overrides del entorno de desarrollo y nunca añade compose.dev.yaml.
APP_ENV=production es el modo validado de Personalization dentro de staging;
Auth conserva su APP_ENV=staging. No hay puertos de BD, REST ni RPC publicados.
La única entrada HTTP externa es el HTTPS 443 de Nginx. En Vagrant, el puerto
reenviado ya definido permite `https://localhost:8443`, con la CA de staging.

Para revisar estado o logs sin mostrar secretos:

```bash
bash infra/deploy/compose.sh personalization --profile images --profile rpc ps
bash infra/deploy/compose.sh personalization logs --tail 50 personalization
```

Las rutas públicas son `/api/v1/files`, `/api/v1/prints`, las rutas administrativas
de Personalization, `/health/personalization/live`, `/health/personalization/ready`
y `/openapi/personalization.json`. `/docs`, `/openapi.json` y las rutas de Auth
mantienen su destino previo. No se publica el RPC administrativo en Nginx;
permanece interno, con TLS y su JWT obligatorio.

### Verificación automatizada

```powershell
py -3.14 infra/personalization/verify_https.py
py -3.14 infra/personalization/verify_deploy_commands.py
```

Requiere Docker Linux, OpenSSL y la imagen runtime construida. Usa un proyecto
UUID, contraseñas nuevas, certificados efímeros y volumen temporal. No monta los
secretos reales de Storage ni modifica la PKI del equipo. Comprueba TLS con CA
verificada, rechazo sin confianza, rutas, JWT, cuerpo mayor de 64 KiB, límites,
correlación, errores RFC 9457, la ruta Auth mediante un upstream de prueba y
caída/recuperación de BD/API. No valida un despliegue en una VM Ubuntu real.
Al terminar retira únicamente sus contenedores, red y volumen temporales.
verify_deploy_commands.py ejecuta los scripts Bash reales con procesos externos
simulados en contenedores Linux sin red. Verifica orden de arranque, rechazo de
Git sucio, aislamiento de variables y parada ante fallos de migración o Storage.

Referencias de configuración: [límites Nginx](https://nginx.org/en/docs/http/ngx_http_core_module.html#client_max_body_size),
[proxy Nginx](https://nginx.org/en/docs/http/ngx_http_proxy_module.html#proxy_pass)
y [combinación de archivos Compose](https://docs.docker.com/reference/compose-file/merge/).

La configuración HTTPS local no inicia Auth. Para renovar tokens se usa el
Auth local habitual; en Ubuntu las rutas Auth requieren su contenedor desplegado
en la red compartida con el alias clusterjam-auth.

Si se renuevan los certificados de staging con prepare.py --renew-certificates,
ejecutar primero deploy.sh all y despues deploy.sh personalization. El segundo
recrea RPC para cargar su certificado nuevo; all conserva su alcance Auth/shared.


## Operación y recuperación

Ejecutar desde la raíz del repositorio con Python 3.12 o posterior y Docker.
En Windows usar `py -3.14`; en Ubuntu usar `python3`. Estas herramientas usan
la biblioteca estándar del host. El microservicio conserva Python 3.14.

### Diagnóstico

```powershell
py -3.14 infra/personalization/operations.py status --require-worker --require-rpc --require-https
```

Comprueba liveness/readiness REST, revisión Alembic, bucket privado, avance del
worker, TLS gRPC y readiness a través de HTTPS. Devuelve un evento JSON con
`OPERATIONS_HEALTHY` y salida 0, o `OPERATIONS_UNHEALTHY` y salida 1. Muestra
cargas pendientes como conteo; no considera un pendiente un error por sí solo.
Los componentes opcionales apagados se informan como `not_running_optional`;
las opciones `--require-*` hacen que su ausencia sea un fallo.

En Ubuntu desplegado:

```bash
python3 infra/personalization/operations.py --deployment status --require-worker --require-rpc --require-https
```

El diagnóstico no inicia, detiene ni reinicia servicios. El worker escribe un
heartbeat privado y atómico en su tmpfs; lo actualiza por lote, por trabajo y
durante transferencias de Storage. Docker comprueba su edad sin consultar BD ni
Storage. Así una dependencia caída no provoca una falsa muerte del proceso.
`WORKER_HEARTBEAT_MAX_AGE_SECONDS` tiene valor inicial 180, configurable entre
30 y 3600; el límite efectivo permite al menos tres intervalos de polling.
La supervisión de progreso no sustituye la revisión de fallos de negocio en
los logs JSON. Los logs de despliegue conservan rotación de 10 MB × 3 archivos.

### Crear un respaldo completo

La BD debe estar iniciada y migrada. Storage debe estar configurado con su clave
de servidor y bucket privado existentes. La API y el worker pueden seguir
atendiendo; el respaldo SQL usa el snapshot consistente de pg_dump.

```powershell
py -3.14 infra/personalization/operations.py backup --output "C:/Users/zenbook i5/Sistemas_en_red/Proyecto/personalization-backups"
```

El destino es obligatorio, externo al repositorio y distinto del volumen de BD.
En Ubuntu, usar una ruta privada persistente elegida por el operador y añadir
`--deployment` antes de `backup` para usar deployment.env/release.env.

Cada ejecución crea `personalization-<backup_id>` con:

- `database.dump`: las nueve tablas y la revisión Alembic, en formato custom.
- `objects/`: bytes de todos los archivos DISPONIBLE, incluidos originales,
  miniaturas y previews históricos, con nombres UUID.
- `manifest.json`: revisión, imagen PostgreSQL fijada, conteos e integridad SHA-256.

Antes de copiar imágenes, la herramienta restaura el dump en un PostgreSQL
temporal y obtiene de esa copia el inventario exacto. Así no mezcla metadata
posterior con un dump anterior. Los objetos son inmutables y se validan por
tamaño y SHA-256. Una imagen ausente o alterada impide publicar la copia.
Las filas PENDIENTE_CARGA quedan en la BD y el manifiesto, pero sus objetos aún
no publicados no se consideran archivos disponibles para recuperar.

La publicación del directorio es atómica y no reemplaza copias existentes.
No se incluyen contraseñas, claves, JWT ni certificados privados. En Linux, el
directorio privado queda en modo 0700; Windows usa los permisos del perfil.
El respaldo contiene datos privados y no se cifra automáticamente. Se debe
guardar bajo acceso restringido y trasladar a un destino cifrado externo cuando
el equipo lo defina. Una copia en el mismo servidor no cubre la pérdida del host.
No se ha instalado un temporizador ni una regla de borrado o retención: el
equipo todavía debe definir frecuencia, retención, destino, RPO y RTO.

### Verificar y ensayar restauración

Sustituir la ruta por el directorio concreto del respaldo creado:

```powershell
py -3.14 infra/personalization/operations.py verify --backup "<backup-directory>"
py -3.14 infra/personalization/operations.py restore-check --backup "<backup-directory>"
```

`verify` funciona sin conexión a Docker o Storage y comprueba archivos, hashes,
rutas UUID y compatibilidad de formato/esquema. SHA-256 detecta corrupción; el
manifiesto no es una firma de autenticidad. Restaurar solo copias confiables.
`restore-check` usa un clúster nuevo sin puertos publicados, restaura en una sola
transacción, compara conteos e inventario y retira sus propios recursos al final.
Nunca ejecuta restauraciones sobre la BD activa. Los recursos temporales usan
el prefijo `personalization-recovery-` y contraseñas nuevas, no las originales.

### Preparar un candidato recuperado

```powershell
py -3.14 infra/personalization/operations.py restore --backup "<backup-directory>" --workspace "<new-external-workspace>"
```

El workspace debe ser nuevo y externo al repositorio. La herramienta valida la
restauración y conserva el candidato **detenido**, su volumen, `compose.json`,
dos secretos nuevos y `recovery.override.yaml`. No modifica la BD activa.
Ese workspace contiene credenciales de recuperación y debe quedar privado.

Para inspeccionarlo sin reemplazar la instancia activa:

```bash
docker compose -f /path/to/recovery/compose.json up -d --wait
docker compose -f /path/to/recovery/compose.json exec -T db-personalizacion psql -U app_personalizacion -d personalizacion_db -c 'SELECT version_num FROM app.alembic_version'
docker compose -f /path/to/recovery/compose.json stop
```

Un cambio real de volumen requiere una ventana revisada: detener entradas,
API, worker, RPC y BD actuales, mantener el candidato detenido y añadir el
`recovery.override.yaml` al final de los archivos de Compose usados normalmente.
Ese overlay selecciona el volumen recuperado y sus credenciales nuevas; conserva
el volumen y los secretos originales para una reversión. Validar configuración,
revisión Alembic, permisos, TLS, Storage y lecturas antes de reabrir el tráfico.
No ejecutar dos instancias PostgreSQL sobre el mismo volumen.
Esta rama prueba la recuperación aislada; no hace un cambio de volumen real.

Si faltan imágenes en el bucket original, con el bucket privado ya preparado:

```powershell
py -3.14 infra/personalization/operations.py restore-objects --backup "<backup-directory>"
```

Exige el mismo proyecto de Storage, verifica primero la copia local y usa
creación sin upsert. Un objeto existente con SHA/tamaño correctos se conserva;
si difiere, la recuperación se detiene sin sobrescribirlo. La repetición es
segura y confirma escrituras ambiguas mediante lectura verificada. No restaura
otros proyectos ni administra usuarios de Auth. Las credenciales de servidor
se vuelven a preparar fuera del respaldo; no se recuperan desde el dump.

La edad del respaldo puede inspeccionarse sin imponer una política por defecto:

```powershell
py -3.14 infra/personalization/operations.py status --backup "<backup-directory>"
# Añadir --max-backup-age-seconds solo con un umbral definido por el equipo.
```

### Pruebas automatizadas de operación

```powershell
py -3.14 -m uv run --locked --project services/personalizationService pytest infra/personalization/operation_tools --import-mode=prepend
py -3.14 infra/personalization/verify_operations.py
```

La prueba integral utiliza exclusivamente PostgreSQL, claves e imágenes de
prueba y un servidor HTTPS efímero. Comprueba todas las tablas, auditoría,
consistencia frente a escrituras concurrentes, bytes de originales/previews,
pendientes, corrupción, conflictos, rechazos de redirección, recuperación
idempotente, cierre del worker y liveness durante una caída de su BD temporal.
La CI repite estas pruebas en Ubuntu y compila las herramientas con Python 3.12.
No se crean tablas de negocio al arrancar servicios; una restauración explícita
reconstruye el esquema versionado del dump, con su historial de Alembic.

Referencias: [pg_dump](https://www.postgresql.org/docs/17/app-pgdump.html),
[pg_restore](https://www.postgresql.org/docs/17/app-pgrestore.html) y
[alcance de los respaldos de Supabase](https://supabase.com/docs/guides/platform/backups).

Los límites iniciales de las herramientas son 10 000 registros archivo y 10 GB
por respaldo. No son una política de retención. No se admiten respaldos anidados
ni workspaces de recuperación dentro de un respaldo ya publicado.
