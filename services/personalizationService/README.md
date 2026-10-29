# Personalization Service

Personalization microservice for Cluster JAM.

Manages private images, print versions, template drafts, design drafts,
and generated previews. Product compatibility, customer designs, and
checkout integration remain pending until Catalog and Orders are available.

## Technology Stack

- Python 3.14, FastAPI, Pydantic, and grpcio
- Pillow
- SQLAlchemy, Alembic, and PostgreSQL 17
- Supabase Storage
- Docker Compose and Nginx

## Requirements

- Python 3.14 for local development
- Docker with Linux containers and Compose
- Git
- A Supabase project with asymmetric JWT signing keys and a private bucket

## Project Setup

From `services/personalizationService`:

```bash
python -m pip install uv==0.13.5
python -m uv sync --locked
```

Use `py -3.14` instead of `python` on Windows. Dependencies are pinned in
`uv.lock`; use `--locked` when running project commands.

## Environment Configuration

Use `infra/personalization/.env.example` to prepare the local configuration.
Set `SUPABASE_ISSUER` and `SUPABASE_JWKS_URL` for the same Supabase project.
Prepare database and Storage secrets using the infrastructure tools.

Never commit `.env`, server keys, JWTs, certificates with private keys, or
backup data. JWT signatures and roles are verified locally using cached JWKS.

## Run the Service

From the repository root, after configuring the environment:

```bash
python infra/personalization/provision_local.py
docker compose -f infra/personalization/compose.yaml --profile tools build personalization-migrate
docker compose -f infra/personalization/compose.yaml up -d --wait db-personalizacion
docker compose -f infra/personalization/compose.yaml run --rm personalization-migrate
docker compose -f infra/personalization/compose.yaml -f infra/personalization/compose.dev.yaml up -d --wait personalization
```

The development API is available at `http://localhost:8082`.
Image uploads require the Storage overlay and a configured private bucket.
See the [infrastructure guide](../../infra/personalization/README.md) for
HTTPS, Storage, image workers, gRPC certificates, and deployment commands.

## Database Migrations

The service owns `personalizacion_db`, using the `app_personalizacion` role
and `app` schema. SQL identifiers are Spanish; Python attributes are English.

Schema changes use versioned Alembic migrations. Run migrations explicitly
before starting a release. The API and workers never create tables at startup.

## Health Checks

| Endpoint | Purpose |
| --- | --- |
| `GET /health/live` | Process liveness |
| `GET /health/ready` | Database access and migration readiness |
| `GET /docs` | Development Swagger UI |
| `GET /openapi.json` | REST contract |

Readiness returns 503 while the database is unavailable. The HTTPS gateway
uses `/health/personalization/live`, `/health/personalization/ready`, and
`/openapi/personalization.json`. The image worker has a progress heartbeat.

## Architecture

| Directory | Responsibility |
| --- | --- |
| `src/personalization/application/` | Use cases, rules, errors, and ports |
| `src/personalization/infrastructure/` | Configuration, persistence, security, and adapters |
| `src/personalization/interfaces/http/` | FastAPI routes, DTOs, and Problem Details |
| `src/personalization/interfaces/grpc/` | Internal TLS gRPC server |
| `src/personalization/interfaces/workers/` | Thumbnail and preview processing |
| `test/` | Unit, contract, HTTP, gRPC, and database tests |

REST uses `/api/v1`, camelCase DTOs, and RFC 9457 errors. Administrative
operations enforce role and ownership policies. Logs are structured JSON.

## Tests

From the service directory:

```bash
python -m uv run --locked ruff check . ../../infra/personalization
python -m uv run --locked ruff format --check . ../../infra/personalization
python -m uv run --locked mypy
python -m uv run --locked pytest --cov --cov-fail-under=70
```

Postman collections are in `contracts/postman/personalization`.
Database integration and recovery checks use disposable Docker resources;
their commands are documented in the infrastructure guide.

## Deployment and Operations

Deployment uses Docker Compose on Ubuntu with private database networks,
HTTPS through Nginx, and internal TLS gRPC. API and image workers run in
separate containers. Images are tagged with the service version and Git SHA.

Backup, restore rehearsal, and health inspection tools are described in the
[infrastructure guide](../../infra/personalization/README.md). Backups include
database metadata and the private image objects referenced by that snapshot.
Backup schedules, retention, and an off-host destination are pending team policy.

## Git Workflow

Use GitHub Flow with branches named `<type>/personalization/<description>`
and commits named `<type>(personalization): <imperative description>`.
Submit changes through a Pull Request and merge using squash merge.
