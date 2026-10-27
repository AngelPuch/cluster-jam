# Personalization Service

Backend de Cluster JAM con base HTTP FastAPI, configuración validada,
PostgreSQL aislado y observabilidad JSON. Los recursos de personalización
se incorporarán de forma incremental bajo `/api/v1`.

## Ejecutar en Docker para desarrollo

Desde la raíz del repositorio, con Docker en modo Linux:

```powershell
py -3.14 infra/personalization/provision_local.py
Copy-Item infra/personalization/.env.example infra/personalization/.env
# Editar las dos URLs públicas en infra/personalization/.env
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.dev.yaml up -d --build --wait personalization
```

El archivo base mantiene PostgreSQL y la API sin puertos publicados. El
archivo de desarrollo publica únicamente REST en `127.0.0.1:8082`, conectado
al puerto 8080 del contenedor. Para cambiar el puerto local, definir
`PERSONALIZATION_HTTP_PORT` antes de ejecutar Compose.

| Operación | URL local | Resultado |
| --- | --- | --- |
| Liveness | `http://127.0.0.1:8082/health/live` | 200 y `status=ok` |
| Readiness | `http://127.0.0.1:8082/health/ready` | 200 o 503 con Problem Details |
| Documentación | `http://127.0.0.1:8082/docs` | Swagger UI |
| Contrato | `http://127.0.0.1:8082/openapi.json` | OpenAPI |

Liveness no consulta dependencias. Readiness invoca un caso de uso mediante
un puerto e inspecciona su propia base de datos, con límites de conexión y
consulta. Si PostgreSQL cae, la API sigue viva y readiness devuelve 503.
Recuperar la base permite volver a responder 200 sin reiniciar la API.

La validación JWT y las políticas de acceso están implementadas y probadas.
Los endpoints técnicos actuales son públicos; las operaciones de negocio
se agregarán con sus políticas explícitas. El puerto 50051 queda reservado
para el servidor gRPC de un incremento posterior.
HTTPS y el proxy de despliegue se incorporarán en la fase de operación.

## Dependencias y configuración local

Desde `services/personalizationService`:

```powershell
py -3.14 -m pip install --user uv==0.13.5
py -3.14 -m uv sync --locked
```

Se requiere Python 3.14 de 64 bits. En Ubuntu usar `python3.14 -m uv` en
lugar de `py -3.14 -m uv`. `uv.lock` fija las dependencias transitivas; cada
comando usa `--locked` para evitar cambios implícitos en la resolución.

| Variable | Regla |
| --- | --- |
| `SUPABASE_ISSUER` | URL HTTPS del proyecto, terminada en `/auth/v1` |
| `SUPABASE_JWKS_URL` | Mismo origen, `/auth/v1/.well-known/jwks.json` |
| `APP_ENV` | Obligatoria: `development`, `test` o `production` |
| `HTTP_HOST` | `127.0.0.1` local o `0.0.0.0` dentro del contenedor |
| `HTTP_PORT` | Entero 1–65535; predeterminado 8080 |
| `GRPC_PORT` | Entero 1–65535; predeterminado 50051 |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARN` o `ERROR` |
| `DB_HOST` | Predeterminado `db-personalizacion` |
| `DB_PORT` | Entero 1–65535; predeterminado 5432 |
| `DB_NAME` | `personalizacion_db` |
| `DB_USER` | `app_personalizacion` |
| `DB_SCHEMA` | `app` |
| `DB_CONNECT_TIMEOUT_SECONDS` | Entre 1 y 30; predeterminado 5 |
| `DB_PASSWORD_FILE` | Archivo obligatorio, legible y no vacío |

Compose monta el secreto de aplicación y entrega las variables necesarias.
`.env.example` documenta rutas dentro de Docker; ese archivo de secreto no
existe en Windows fuera del contenedor. La API acepta un archivo local de
configuración, con prioridad para las variables del proceso, pero ningún
secreto se incorpora a Git ni a la imagen.

El punto de entrada es `python -m personalization.main`. Fuera de Docker
requiere un archivo de contraseña y una dirección de PostgreSQL accesibles
desde ese proceso. Dentro de Docker se usa el nombre `db-personalizacion`;
la base permanece sin publicar un puerto al host.

## Contratos y errores

Las respuestas JSON de DTO utilizan camelCase. Todo error HTTP se devuelve
con `application/problem+json` y los campos `type`, `title`, `status`,
`detail`, `instance`, `code` y `traceId`. `code` es estable y utiliza
SCREAMING_SNAKE_CASE. `instance` incluye la ruta sin su query string.

JSON mal formado produce 400; datos que incumplen el contrato producen 422.
Las rutas inexistentes, métodos no permitidos, dependencias no disponibles
y excepciones inesperadas también usan Problem Details. Se conservan
cabeceras de protocolo, como `Allow` y `WWW-Authenticate`, cuando procedan.
No se devuelven cuerpos rechazados, SQL, secretos ni stack traces.

OpenAPI se versiona en `contracts/openapi/personalization/v1/openapi.json`.
La exportación funciona sin configurar secretos ni conectarse a PostgreSQL.
Desde la carpeta del servicio:

```powershell
py -3.14 -m uv run --locked python -m personalization.interfaces.http.export_openapi --output ../../contracts/openapi/personalization/v1/openapi.json
py -3.14 -m uv run --locked python -m personalization.interfaces.http.export_openapi --check --output ../../contracts/openapi/personalization/v1/openapi.json
```

La CI compara el contrato versionado con la definición de las rutas. La
exportación no habilita endpoints auxiliares ni requiere datos ficticios.

## Logs y correlación

OpenTelemetry SDK crea un span por petición y valida el contexto W3C
entrante. La respuesta devuelve `traceparent` con un span nuevo y
`X-Request-ID` generado por el servidor. Un contexto ausente o inválido
produce una traza nueva. `traceId` del error coincide con el de los logs.

Los logs usan JSON de una línea en stdout, con identidad del servicio,
entorno, fecha UTC, evento, mensaje y correlación `trace_id`/`span_id`.
Se registra un resultado por petición y se omiten sondeos de salud exitosos.
Los eventos de arranque y cierre pueden tener correlación nula.

No se registran Authorization, JWT, cookies, cuerpos, query strings,
contraseñas, correos o URLs firmadas. La ruta del log usa la plantilla de
la operación; las rutas desconocidas usan `unmatched`. Los fallos inesperados
registran el tipo de excepción, sin su mensaje potencialmente sensible.

Este incremento crea contexto con OpenTelemetry, sin configurar un
exportador de trazas. La recolección de logs y el backend de observabilidad
se integrarán durante el despliegue.

## Verificaciones

Desde la carpeta del servicio:

```powershell
py -3.14 -m uv run --locked ruff check . ../../infra/personalization
py -3.14 -m uv run --locked ruff format --check . ../../infra/personalization
py -3.14 -m uv run --locked mypy
py -3.14 -m uv run --locked mypy ../../infra/personalization
py -3.14 -m uv run --locked pytest
py -3.14 -m uv build --no-sources
```

Desde la raíz para la prueba con contenedores reales:

```powershell
py -3.14 infra/personalization/provision_local.py
py -3.14 infra/personalization/verify_stack.py
```

La prueba usa un proyecto y volumen temporales. Comprueba HTTP, errores,
correlación, OpenAPI, caída y recuperación de PostgreSQL, permisos, red y
persistencia. Retira únicamente sus recursos temporales al terminar.

## Capas y evolución

`application/` contiene el caso de uso y puerto de readiness;
`infrastructure/` implementa configuración, conexiones y observabilidad;
`interfaces/http/` contiene rutas, DTO, errores y el límite ASGI.
`bootstrap.py` compone las dependencias y dispone conexiones al cerrar.
Los controladores no acceden al ORM ni a bases de otros servicios.

Las tablas de negocio se crearán con Alembic en su incremento. El arranque
HTTP no crea tablas ni ejecuta migraciones. La matriz requisito–operación–
prueba se completará con las funcionalidades, sin equiparar cobertura de
líneas con RNF09.

Rama: `feat/personalization/local-jwt-validation`.
Commit y título del PR:

```text
feat(personalization): validate JWTs locally
```


## Autenticación local y autorización

Se sigue `ClusterJAM_Guia_Autorizacion_Microservicios.md`, adaptada a las
capas del servicio y al contrato RFC 9457 completo. `application/` define
la identidad mínima, el puerto del verificador y la regla de propiedad;
`infrastructure/security/` verifica firmas y claims con PyJWT; las
dependencias de `interfaces/http/security.py` aplican las políticas HTTP.

Configurar únicamente las dos URLs públicas en el archivo ignorado
`infra/personalization/.env`. No se necesitan claves privadas, una clave
publicable de Supabase ni credenciales de la base de Auth. La configuración
rechaza URLs con credenciales, query o fragmento, HTTP, rutas distintas o
un origen diferente entre issuer y JWKS. Compose carga ese archivo desde
su directorio de proyecto; las variables del proceso tienen prioridad.
Al actualizar una instalación existente, conservar su `.env` y agregar las
dos variables; copiar el ejemplo solamente si el archivo todavía no existe.

Se crea un verificador por proceso durante el arranque, sin descargar
claves todavía. La primera petición protegida obtiene las claves públicas
por JWKS, con timeout de 5 segundos. `PyJWKClient` conserva el conjunto de
claves en memoria durante 600 segundos. La caché individual ilimitada por
tiempo está desactivada para respetar la retirada de claves. Las búsquedas
de un `kid` nuevo permiten refrescar tras un intervalo de 30 segundos,
evitando descargas repetidas por identificadores desconocidos. Una clave
recién publicada podría rechazarse durante ese intervalo. Las dependencias
sincrónicas se ejecutan en el pool de hilos de FastAPI.

Solo se permiten ES256 y RS256, con `kid` y firma válidos. Se exigen `sub`
UUID, `exp` numérico vigente, `iss` configurado y `aud` que contenga
`authenticated`. También se valida `role=authenticated`, se rechazan
usuarios anónimos y se respetan `nbf` e `iat` cuando están presentes.
El único rol de negocio aceptado procede de `app_metadata.app_role`:
`cliente` o `administrador`. `user_metadata`, cabeceras y cuerpos no
otorgan permisos. No se consulta Auth Service ni `/auth/v1/user` por petición.

Para cada futura ruta de negocio se usará `Depends(require_roles(...))`
con roles explícitos, además de `SECURITY_PROBLEM_RESPONSES` en su contrato.
Una lista vacía de roles deniega acceso. La regla `require_resource_owner`
recibe el propietario leído por el servidor; la excepción de administrador
requiere `allow_administrator=True` en el caso de uso que la autorice.
Esta regla no sustituye la consulta del recurso ni decide por sí sola qué
operaciones admiten esa excepción. No hay rutas de demostración en producción.

| Situación | HTTP | `code` |
| --- | --- | --- |
| Token ausente, inválido o expirado | 401 | `INVALID_ACCESS_TOKEN` |
| Rol protegido ausente o inválido | 403 | `INVALID_APP_ROLE` |
| Rol o propiedad insuficientes | 403 | `FORBIDDEN` |
| Claves necesarias no disponibles | 503 | `SERVICE_UNAVAILABLE` |

Los 401 incluyen `WWW-Authenticate: Bearer`. Todos conservan `detail` y
`traceId` y no exponen mensajes internos, tokens ni datos del proveedor.
Si JWKS falla, las claves conocidas siguen funcionando mientras su caché
sea válida; sin claves utilizables la petición protegida devuelve 503.
Los endpoints técnicos permanecen disponibles sin consultar JWKS.

La validación local no proporciona revocación inmediata de sesiones ni
actualiza roles de JWT ya emitidos: se aplican al renovar el token o al
expirar. La retirada de una clave puede tardar hasta el TTL de la caché.
No se promete una latencia fija para todas las peticiones.

Las pruebas usan firmas ES256/RS256 reales con claves efímeras y sustituyen
solo el transporte JWKS. Cubren claims, firmas alteradas, roles, propiedad,
caché concurrente, rotación, retirada de claves, fallos del proveedor,
contratos HTTP/OpenAPI y privacidad de logs. No necesitan usuarios ni
conectividad con Supabase. El verificador del stack Docker usa URLs de
prueba para comprobar el arranque sin depender del proveedor externo.

El contrato OpenAPI se regenera sin red y solo publica las rutas técnicas
existentes. Las rutas protegidas de prueba viven exclusivamente en `test/`.
Las tablas de negocio y sus migraciones Alembic pertenecen al siguiente
incremento; no se crean tablas al iniciar este servicio.
