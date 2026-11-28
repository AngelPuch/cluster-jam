# Cluster JAM Payments Service

NestJS/TypeScript service for the financial participant in the Orders-orchestrated
purchase saga. This first increment provides HTTP health, PostgreSQL connectivity,
safe errors, correlated JSON logs and Swagger. Payment/refund and inbox/outbox
tables and command DTOs are implemented. AMQP handlers, Stripe and protected
payment access follow in separate increments.
There are no public payment operations yet.

## Run locally

Use Node 22+ and Docker Compose. From this service directory:

```powershell
npm ci --ignore-scripts --no-audit --no-fund
Copy-Item .env.example .env
# Set three distinct database passwords in the private .env.
docker compose --env-file .env -f ../../infra/payments/compose.yaml up -d --wait
npm run migration:run
npm run start:dev
```

| URL                                  | Purpose                                            |
| ------------------------------------ | -------------------------------------------------- |
| `http://localhost:8085/health/live`  | Process liveness, independent of PostgreSQL.       |
| `http://localhost:8085/health/ready` | Database and migration readiness; 503 until ready. |
| `http://localhost:8085/docs`         | Swagger UI.                                        |
| `http://localhost:8085/openapi.json` | Implemented HTTP contract.                         |

The local database uses loopback port 5437, database `payments_db` and runtime
role `app_pagos`. `migrator_pagos` owns schema `app` and applies versioned
migrations using `PAYMENTS_MIGRATION_PASSWORD`. The API has DML permissions only.
TypeORM never synchronizes the schema or runs migrations automatically.
Readiness checks database access and the required migration, not Stripe or AMQP.
The HTTP process stays live when PostgreSQL is unavailable.

The schema contains `pago`, `reembolso`, `inbox_pagos` and `outbox_pagos`.
It enforces one payment per order, one full refund per payment, MXN integer
cents and consumer/message deduplication. Stripe event IDs can use a separate
inbox consumer. No card data, client secrets or webhook payloads are stored.
See [the saga message contract](../../contracts/events/payments.v1.md).

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

CI also runs one PostgreSQL integration scenario on a disposable database.
To opt in locally, use an initialized local `payments_test_*` database and set
`PAYMENTS_VERIFY_POSTGRES=true`, its connection variables and migration password.
The integration fixture leaves records in that disposable database.

From the repository root, build the non-root runtime image with:

```powershell
docker build -f services/paymentsService/Dockerfile -t cluster-jam/payments:local .
```

The image listens on port 8080 by default. Supply database configuration at
runtime. PostgreSQL and the API remain separate processes; this increment
does not add gateway routes or configure a deployed Stripe webhook.
