# Personalization Service

Backend de Cluster JAM para archivos, estampados, plantillas, zonas,
diseños y vistas previas. Este incremento incorpora empaquetado Docker y
PostgreSQL aislado, sobre la estructura Python del primer incremento.

## Estado

La imagen ejecuta una comprobación técnica de acceso a la base de datos.
Todavía no hay servidor HTTP/gRPC, endpoints, worker ni tablas de negocio.
Los siguientes incrementos incorporarán salud, OpenAPI, RFC 9457,
observabilidad HTTP y posteriormente migraciones Alembic.

## Requisitos e instalación local

- Python 3.14 de 64 bits.
- uv 0.13.5.
- Git; Docker con motor Linux para probar los contenedores.

Desde `services/personalizationService`, en PowerShell:

```powershell
py -3.14 -m pip install --user uv==0.13.5
py -3.14 -m uv sync --locked
```

`uv.lock` fija las dependencias transitivas. `--locked` impide modificar la
resolución al instalar. No es necesario activar `.venv` ni instalar estas
dependencias en el entorno de Auth/Profile. En Ubuntu, usar
`python3.14 -m uv` en lugar de `py -3.14 -m uv`.

## Configuración

| Variable | Regla |
| --- | --- |
| `APP_ENV` | Obligatoria: `development`, `test` o `production` |
| `HTTP_PORT` | Entero 1–65535; predeterminado 8080 |
| `GRPC_PORT` | Entero 1–65535; predeterminado 50051 |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARN` o `ERROR`; predeterminado `INFO` |
| `DB_HOST` | Predeterminado `db-personalizacion` |
| `DB_PORT` | Entero 1–65535; predeterminado 5432 |
| `DB_NAME` | `personalizacion_db` |
| `DB_USER` | `app_personalizacion` |
| `DB_SCHEMA` | `app` |
| `DB_CONNECT_TIMEOUT_SECONDS` | Entre 1 y 30; predeterminado 5 |
| `DB_PASSWORD_FILE` | Archivo obligatorio, legible y no vacío |

Las variables del proceso tienen prioridad sobre `.env`. No se acepta una
contraseña en `DB_PASSWORD`: se lee de un archivo secreto. Compose entrega
la configuración y monta ese archivo, por lo que no es necesario copiar
`.env.example` para ejecutar los contenedores.

`.env.example` documenta las rutas dentro de Docker. Su ruta de secreto no
existe en Windows fuera del contenedor. Una configuración local previa debe
incorporar `DB_PASSWORD_FILE` con una ruta válida si se instancia `Settings`
fuera de Docker. Los archivos `.env` y secretos no se incorporan a Git.

## Docker y PostgreSQL

Desde la raíz del repositorio:

```powershell
py -3.14 infra/personalization/provision_local.py
docker compose -f infra/personalization/compose.yaml --profile tools build personalization-check
docker compose -f infra/personalization/compose.yaml up -d --wait db-personalizacion
docker compose -f infra/personalization/compose.yaml run --rm --no-deps personalization-check
```

Resultado esperado: un evento JSON con `code=DATABASE_READY` y salida 0.
El contenedor de comprobación termina y la BD continúa ejecutándose. La
guía completa está en `infra/personalization/README.md`, relativa a la raíz
del repositorio.

El Dockerfile fija Python por versión y digest, construye y prueba en una
etapa independiente y copia solo la instalación de ejecución a la imagen
final. Usa un usuario sin privilegios y declara REST 8080 y gRPC 50051 para
los incrementos que abrirán esos servidores.

## Verificaciones locales

Desde `services/personalizationService`:

```powershell
py -3.14 -m uv run --locked ruff check . ../../infra/personalization
py -3.14 -m uv run --locked ruff format --check . ../../infra/personalization
py -3.14 -m uv run --locked mypy
py -3.14 -m uv run --locked mypy ../../infra/personalization
py -3.14 -m uv run --locked pytest
py -3.14 -m uv build --no-sources
```

Desde la raíz, para comprobar Docker, aislamiento y persistencia real:

```powershell
py -3.14 infra/personalization/provision_local.py
py -3.14 infra/personalization/verify_stack.py
```

La prueba usa un proyecto y volumen temporales independientes del entorno
de desarrollo. No requiere Supabase. La CI ejecuta controles Python y la
prueba Docker en Ubuntu.

Ruff aplica 79 caracteres de código y 72 de comentarios/docstrings. mypy
comprueba tipos en modo estricto. RNF09 se comprobará mediante la matriz
requisito–operación–prueba conforme se incorporen operaciones; la cobertura
de líneas no sustituye esa evidencia funcional.

## Capas y propiedad

```text
src/personalization/
├── application/       Casos de uso, reglas, errores y puertos
├── infrastructure/    Configuración, BD y adaptadores
└── interfaces/        Entradas HTTP, gRPC y workers
test/unit/             Configuración y diagnóstico técnico
```

Negocio define puertos y no importa ORM ni frameworks. Las interfaces
invocan casos de uso; no acceden directamente al ORM. Los identificadores
Python serán ingleses con PEP 8; las columnas SQL conservarán los nombres
españoles mediante mapeos explícitos. Los futuros DTO REST usarán camelCase.

Las migraciones mapearán `archivo`, `estampado`, `estampado_version`,
`plantilla_version`, `zona`, `tamano_zona`, `diseno`, `aplicacion` y
`auditoria_local`. No se crean tablas al arrancar. Catalog y Orders se
integrarán mediante puertos y contratos, sin acceso a sus bases de datos.

## GitHub Flow

Rama: `build/personalization/docker-database`.
Título del PR y commit de squash:

```text
build(personalization): add isolated database containers
```

Revisar imagen, secretos, red, volumen, usuario, migraciones pendientes y
resultados de pruebas. Fusionar con squash tras pasar controles y revisión.
