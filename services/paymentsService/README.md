# Cluster JAM Payments Service

NestJS/TypeScript service for the financial participant in the Orders-orchestrated
purchase saga. It provides HTTP health, PostgreSQL persistence, command validation,
safe logs/errors and the Stripe test-mode payment preparation core. The core
persists operation identity before calling Stripe, then saves the result with
inbox and a pending outbox event in one transaction. AMQP transport, signed
webhooks, cancellation/refunds and protected payment access follow separately.
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

`STRIPE_SECRET_KEY` accepts test keys only and is optional while transport is
not connected. No key means payment preparation fails safely; health still works.
Creation uses a stable order idempotency key and does not confirm or accredit
payment. An expired reservation is rejected only if no creation was attempted.
An uncertain creation older than 23 hours requires manual recovery instead of
reusing a potentially expired Stripe key. Client secrets are not persisted.

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

Tests use the real Stripe SDK against a local HTTP fixture, without credentials
or external Stripe calls. CI also runs a PostgreSQL scenario covering migrations,
financial constraints, lost responses, SQL rollback and duplicate delivery.
Live Stripe sandbox verification still requires a private test key.
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
