# Personalization Service

Backend de Cluster JAM con base HTTP FastAPI, configuración validada,
PostgreSQL aislado y observabilidad JSON. Los recursos de personalización
se incorporarán de forma incremental bajo `/api/v1`.

## Ejecutar en Docker para desarrollo

Desde la raíz del repositorio, con Docker en modo Linux:

```powershell
py -3.14 infra/personalization/provision_local.py
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

Todavía no hay operaciones de negocio, validación JWT ni servidor gRPC. El
esquema de seguridad de OpenAPI identifica el contrato futuro; los endpoints
técnicos actuales son públicos. El puerto 50051 queda reservado para gRPC.
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

Rama: `feat/personalization/http-foundation`.
Commit y título del PR:

```text
feat(personalization): add HTTP service foundation
```
