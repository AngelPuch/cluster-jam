# Personalization Service

Backend de Cluster JAM para archivos, estampados, plantillas, zonas,
diseños y vistas previas. Este incremento prepara el paquete Python,
sus dependencias, configuración y controles de calidad.

## Estado de este incremento

Todavía no hay servidor HTTP/gRPC, endpoints, worker ni tablas.
Docker y PostgreSQL se incorporan en el siguiente incremento; después
se implementarán salud, OpenAPI, errores RFC 9457 y observabilidad.
No se requieren credenciales de Supabase para estas verificaciones.

## Requisitos

- Python 3.14 de 64 bits.
- uv 0.13.5 como gestor de dependencias y entornos.
- Git.

En Windows, instalar uv sin modificar la instalación global:

```powershell
py -3.14 -m pip install --user uv==0.13.5
py -3.14 -m uv --version
```

Todos los comandos siguientes se ejecutan desde
`services/personalizationService`.

## Instalar el proyecto

```powershell
py -3.14 -m uv sync --locked
if (-not (Test-Path -LiteralPath .env)) {
    Copy-Item .env.example .env
}
```

Crear `.env` solo si todavía no existe. Contiene configuración local y
no se incorpora a Git. En Ubuntu, usar `python3.14 -m uv` en lugar de
`py -3.14 -m uv`; para crear el archivo local usar `cp -n`.

`uv.lock` fija las dependencias transitivas. `--locked` impide cambiar
la resolución durante la instalación. No es necesario activar `.venv`
ni instalar dependencias de este servicio en el entorno de Auth/Profile.

## Configuración

| Variable | Regla |
| --- | --- |
| `APP_ENV` | Obligatoria: `development`, `test` o `production` |
| `HTTP_PORT` | Entero 1–65535; predeterminado 8080 |
| `GRPC_PORT` | Entero 1–65535; predeterminado 50051 |
| `LOG_LEVEL` | `DEBUG`, `INFO`, `WARN` o `ERROR`; predeterminado `INFO` |

Las variables del proceso tienen prioridad sobre `.env`. La clase
`Settings` rechaza configuración inválida; se conectará al arranque
del servidor cuando se incorpore la base HTTP. Todavía no configura
manejadores de logs ni abre puertos.

Comprobar la configuración desde la raíz del servicio:

```powershell
py -3.14 -m uv run --locked python -c "from personalization.infrastructure.config.settings import Settings; Settings()"
```

Sin salida y con código 0 significa que la configuración es válida.
No ejecutar ese comando sin definir `APP_ENV` o crear el archivo local.

## Verificaciones

```powershell
py -3.14 -m uv run --locked ruff check .
py -3.14 -m uv run --locked ruff format --check .
py -3.14 -m uv run --locked mypy
py -3.14 -m uv run --locked pytest
py -3.14 -m uv build --no-sources
```

Ruff aplica nombres, imports, anotaciones y límites de 79 caracteres
para código y 72 para comentarios/docstrings. mypy comprueba tipos en
modo estricto. Las pruebas actuales verifican errores de configuración
y precedencia del entorno; no requieren red ni base de datos.

La CI ejecuta estos controles para cambios del servicio. Sus Actions
se fijan por SHA. El empaquetado genera wheel y sdist en `dist/`, que
permanece fuera de Git.

RNF09 se comprobará con una matriz requisito–operación–prueba conforme
se implementen operaciones. El porcentaje de líneas no sustituye la
cobertura funcional ni demuestra que el servicio ya esté terminado.

## Capas

```text
src/personalization/
├── application/       Casos de uso, reglas, errores y puertos
├── infrastructure/    Configuración y adaptadores
└── interfaces/        Entradas HTTP, gRPC y workers
test/unit/             Pruebas de configuración
```

Negocio define puertos y no importa FastAPI, SQLAlchemy ni adaptadores.
Infraestructura implementa esos puertos. Las interfaces invocan casos
de uso y no acceden directamente al ORM.

Los identificadores Python son ingleses y siguen PEP 8; las columnas
SQL conservarán los nombres españoles del modelo mediante mapeos
explícitos. Los futuros DTO REST usarán alias camelCase.

## Límites de datos e integración

PostgreSQL tendrá host `db-personalizacion`, base `personalizacion_db`,
usuario `app_personalizacion` y esquema `app`. SQLAlchemy y Alembic
administrarán `archivo`, `estampado`, `estampado_version`,
`plantilla_version`, `zona`, `tamano_zona`, `diseno`, `aplicacion` y
`auditoria_local`. No se crearán tablas al arrancar.

Auth conserva la identidad; Personalization validará JWT localmente y
comprobará rol y propiedad. Catalog y Orders aún no existen en este
repositorio: sus integraciones se desarrollarán mediante puertos y
contratos versionados, sin acceder a bases de otros servicios.

Los originales privados y previews se guardarán en Supabase Storage.
Los importes serán centavos enteros en MXN. Un diseño agregado al
carrito quedará congelado; editarlo creará otro ID.

## GitHub Flow

Rama de este incremento: `feat/personalization/project-scaffold`.
El PR incluye el servicio y su workflow de CI. Se fusiona a `main`
mediante squash después de pasar controles y recibir revisión.

Título del PR y commit de squash:

```text
feat(personalization): initialize service scaffold
```
