# Cluster JAM Payments Service

NestJS/TypeScript service for the financial participant in the Orders-orchestrated
purchase saga. This first increment provides HTTP health, PostgreSQL connectivity,
safe errors, correlated JSON logs and Swagger. Payment tables, AMQP handlers,
Stripe, JWT-protected payment access and refunds follow in separate increments.
There are no public payment operations yet.

## Run locally

Use Node 22+ and Docker Compose. From this service directory:

```powershell
npm ci --ignore-scripts --no-audit --no-fund
Copy-Item .env.example .env
# Set three distinct database passwords in the private .env.
docker compose --env-file .env -f ../../infra/payments/compose.yaml up -d --wait
npm run start:dev
```

| URL | Purpose |
| --- | --- |
| `http://localhost:8085/health/live` | Process liveness, independent of PostgreSQL. |
| `http://localhost:8085/health/ready` | Database query; 503 during an outage and recovery on a later request. |
| `http://localhost:8085/docs` | Swagger UI. |
| `http://localhost:8085/openapi.json` | Implemented HTTP contract. |

The local database uses loopback port 5437, database `payments_db` and runtime
role `app_pagos`. `migrator_pagos` owns schema `app`; no business tables exist yet.
TypeORM never synchronizes the schema or runs migrations automatically.
Readiness currently checks database access, not payment or broker availability.
The HTTP process stays live when PostgreSQL is unavailable.

Use `.env.example` for configuration. Staging/production require `DB_SSL=true`
and a trusted PostgreSQL certificate; `DB_CA_PATH` supplies a private CA when
needed. Keep credentials out of Git and leave the local Compose on development.

## Checks and image

```powershell
npm run build
npm run typecheck
npm run lint
npm run format:check
npm test
```

From the repository root, build the non-root runtime image with:

```powershell
docker build -f services/paymentsService/Dockerfile -t cluster-jam/payments:local .
```

The image listens on port 8080 by default. Supply database configuration at
runtime. PostgreSQL and the API remain separate processes; this increment
does not add gateway routes or configure a deployed Stripe webhook.
