# Cluster JAM Profile Service

Profile owns customer names, phone numbers, contact emails, onboarding and
addresses. Supabase Auth owns identity and credentials. Auth's registration
event is the source of the minimum profile; neither Auth nor Supabase writes
to the Profile database.

## Current implementation

The service consumes Auth registration events through RabbitMQ and provisions
minimum profiles using a transactional PostgreSQL inbox. It handles duplicates,
bounded retries, DLQ delivery, reconnection and graceful consumer shutdown.

JWT guards, profile/address HTTP routes, Orders contact, Swagger/OpenAPI,
the Profile Docker deployment and CI are subsequent PRs. No public
endpoint currently invokes provisioning. The runnable API exposes only:

- `GET /health/live`: process liveness, independent of PostgreSQL.
- `GET /health/ready`: database query and consumer connection; 503 when unavailable.

See [the diagnosis and implementation plan](../../docs/profile/implementation-plan.md)
and verification results for [persistence](../../docs/profile/verification-01.md)
and [messaging](../../docs/profile/verification-02.md).

## Architecture and technologies

NestJS 12, TypeScript in strict mode, TypeORM 1.1.1 and PostgreSQL. Dependency
versions are fixed by `package-lock.json`; use `npm ci`. Node 22.20 was used
for local checks; the existing Auth production image uses Node 24 LTS.

```text
src/
    application/
        ports/profile-provisioning.port.ts
        profile/create-minimum-profile.service.ts
    infrastructure/
        config/environment.validation.ts
        database/
            entities/       # profile, address and inbox
            migrations/     # schema changes, no synchronize
            repositories/   # TypeORM provisioning adapter
            typeorm.options.ts
            typeorm.config.ts
            typeorm.module.ts
        messaging/          # canonical topology, confirmed handoff and reconnecting listener
        observability/      # JSON allowlist logger and OpenTelemetry consumer spans
    interfaces/http/health/
    interfaces/messaging/   # validated registration DTO and manual ACK consumer
    profile.module.ts
```

The application port has no ORM or broker types. `CreateMinimumProfileService`
delegates to the port, and the TypeORM adapter owns its local transaction.

## Configuration and local execution

Run commands from `services/profileService`. Start an independently provisioned
PostgreSQL instance and create its database and application/migration role
through your local PostgreSQL administration tooling. Creating a PostgreSQL
database is infrastructure provisioning; the versioned migrations below create
all application tables, schema and the required `uuid-ossp` extension.

Start and provision the existing local development broker from the repository
root before launching Profile. This uses only fictitious local credentials:

```powershell
docker compose -f infra/rabbitmq/compose.yaml up -d --wait
python infra/rabbitmq/provision-local.py
cd services/profileService
```

```powershell
npm ci --ignore-scripts --no-audit --no-fund
Copy-Item .env.example .env
# Set DB_HOST, DB_NAME, DB_USER and DB_PASSWORD in the private .env.
npm run migration:run
npm run start:dev
```

| Variable | Purpose / local default |
| --- | --- |
| `APP_ENV` | development, test, staging or production; development |
| `HTTP_PORT` | HTTP listener port; 8080 |
| `DB_HOST` | Required database hostname; localhost in example |
| `DB_PORT` | PostgreSQL port; 5432 |
| `DB_NAME` | Required isolated Profile database name |
| `DB_USER` | Required PostgreSQL role |
| `DB_PASSWORD` | Required role password; example value must be replaced |
| `DB_SSL` | true/false; false locally, required true in staging/production |
| `DB_CA_PATH` | Optional PEM CA for verified database TLS |
| `LOG_LEVEL` | DEBUG, INFO, WARN or ERROR; INFO |
| `RABBITMQ_CONSUMER_ENABLED` | true by default; explicit false for database-only tooling |
| `RABBITMQ_URI` | Required when consuming; amqps in staging/production |
| `RABBITMQ_URL` | Compatibility alias; conflicting values are rejected |
| `RABBITMQ_CA_PATH` | Optional PEM CA for broker TLS; server identity always verified |
| `RABBITMQ_EXCHANGE` / `RABBITMQ_QUEUE` | identity.events / profile.identity.user-registered.v1 |
| `RABBITMQ_RETRY_EXCHANGE` | profile.identity.user-registered.retry |
| `RABBITMQ_RETRY_QUEUE_1` / `_2` | profile.identity.user-registered.retry.1 / .2 |
| `RABBITMQ_RETRY_DELAY_1_MS` / `_2_MS` | 5000 / 30000; shortened values allowed only with APP_ENV=test |
| `RABBITMQ_DLX` / `RABBITMQ_DLQ` | profile.identity.user-registered.dead-letter / .dlq |
| `RABBITMQ_MAX_ATTEMPTS` | Must be 3, including the first processing attempt |
| `SERVICE_VERSION` / `INSTANCE_ID` | Optional structured-log deployment identifiers |

Configuration fails before database use when required values or ports are
invalid. TLS always verifies the server certificate when enabled. Connection
timeout is 3 seconds, statement timeout 8 seconds and idle transaction timeout
10 seconds. The pool limit is 10. Migration and runtime use the same options.
No credentials are committed in this service.

```powershell
Invoke-RestMethod http://localhost:8080/health/live
Invoke-RestMethod http://localhost:8080/health/ready
```

## Migrations and compatibility

```powershell
npm run migration:run             # apply pending migrations
npm run migration:run             # no-op if already applied
npm run build
npm run migration:run:prod        # compiled migration CLI, run once before API replicas
npm run migration:generate -- src/infrastructure/database/migrations/change-name
# Review generated SQL and register the migration in typeorm.options.ts.
npm run migration:revert          # revert the latest migration, after backup/review
```

`synchronize`, automatic migration execution and automatic extension
installation are disabled. All migrations run in one transaction. A migration
role needs DDL/extension permissions on this service's own database; runtime
must use a least-privilege role. The application never creates a database.

Migration history:

1. `1789608835902`: schema `app`, profile, addresses, local FK and the partial
   unique default-address index. It now explicitly creates `uuid-ossp`; this
   prerequisite was previously installed implicitly by TypeORM initialization.
2. `1789964255801`: contact email, onboarding state and optional name. The
   historical email addition is corrected to permit existing rows without
   inventing a contact email. An already applied migration is not replayed.
3. `1793232000000`: varchar(20) onboarding state with two-value constraint,
   default PENDING, compatibility backfill, required-contact CHECK for all new
   and updated rows, and `app.inbox_messages` with event_id primary key.

**Legacy data:** existing COMPLETED values are preserved. Complete PENDING
legacy rows become COMPLETED only when name and phone are nonblank and email
has a nonblank local/domain form with dotted domain. Legacy records lacking a
contact email remain readable with null contactEmail and PENDING; do not copy
credentials or manufacture an address. The application model represents this
legacy nullability. A NOT VALID CHECK permits those historical rows but rejects
new rows or updates without a nonempty email. Existing installations that
already have NOT NULL retain that stronger column restriction. Before validating
the CHECK for every old row, collect a legitimate contact email from its owner.

**Rollback:** stop consumers and back up the service database first.
`migration:revert` for the latest migration drops inbox deduplication records
and its constraints, and restores onboarding to text. It deliberately retains
profile data and COMPLETED values. Reapply with `migration:run`; existing
user_id uniqueness prevents overwriting profiles on event replay. Do not revert
the older name-NOT-NULL migration while minimum profiles have null names.
No production rollback or destructive database operation is run automatically.

## Transactional provisioning contract

`CreateMinimumProfileService.execute({ eventId, userId, initialContactEmail })`
returns either `{ status: 'processed', profileCreated: boolean }` or
`{ status: 'duplicate' }`.

In one `DataSource.transaction`:

1. Insert event_id and event_type into the inbox with ON CONFLICT DO NOTHING
   RETURNING. A duplicate returns successfully without touching the profile.
2. Insert the minimum profile with null name/phone and PENDING, using
   ON CONFLICT(user_id) DO NOTHING. Distinct events for an existing user never
   overwrite contact information, timestamps or onboarding.
3. Resolve only after COMMIT; a failure rolls back both inserts. The consumer
   awaits this result before ACKing RabbitMQ, including duplicate outcomes.

The inbox stores no event payload, passwords or tokens. The event contract is
[`identity.user.registered.v1`](../../contracts/events/identity.user.registered.v1.schema.json).
The messaging interface validates all required event fields, nested data,
schema/aggregate version, timestamp, extra properties and matching aggregate
identity. Supplied AMQP metadata must agree with the body. This
branch adds no dependency on Auth's or Personalization's code or database.

## RabbitMQ topology and recovery

`src/infrastructure/messaging/profile-topology.json` is the canonical resource
and permission definition. Both the listener and `infra/deploy/prepare.py` use
it. The identity exchange belongs to Auth/infrastructure; Profile checks it
passively and cannot configure or publish to it. The existing durable main
queue and its identity binding remain compatible; no queue is deleted to
change its type or arguments.

The consumer uses `noAck: false` and prefetch 1. Two new quorum retry queues
have progressive TTLs and dead-letter back to the main queue through a private
direct exchange. `x-dead-letter-strategy=at-least-once`, `x-overflow=reject-publish`
and a bounded queue size keep expired retries until their destination confirms.
The durable quorum DLQ has no TTL; capacity exhaustion rejects a publication
rather than dropping an older message.

The maximum is **three scheduled processing attempts total**, separated by
5 and 30 seconds. Invalid contracts and deterministic database rejection go
directly to DLQ. Recognized connection/transaction failures and uncoded Error
failures are retried finitely. The unchanged body, identifiers and trace
headers are transferred with persistent, mandatory publication and publisher
confirmation. The original is ACKed only after that transfer is confirmed.
An incoming expiration is not copied, so it cannot silently expire the handoff.

If a confirmation is missing, returned, NACKed or interrupted, the channel is
closed without ACK. The broker redelivers the original; Inbox handles a commit
whose ACK was lost. Transport redeliveries can repeat the same scheduled
attempt and are not a fourth configured retry. Reconnection backs off from
1 to 30 seconds. Shutdown cancels consumption, waits for work and closes AMQP
before the database is destroyed. Readiness is false while disconnected;
liveness does not query dependencies.

Logs use the project's JSON fields and OpenTelemetry/W3C correlation. Payloads,
emails, credentials, raw exceptions and SQL are excluded by an allowlist.
Retry/DLQ bodies remain private broker data for authorized operators.

If a TTL return route is absent, RabbitMQ retains the message. Its internal
dead-letter confirm retry can delay delivery after a route is repaired (the
tested 4.3.6 default is 180 seconds). Do not delete the retry queue to accelerate
recovery. The isolated test broker shortens that timer to one second only for
testing. See [RabbitMQ quorum queue guarantees](https://www.rabbitmq.com/docs/quorum-queues)
and [resource permissions](https://www.rabbitmq.com/docs/access-control).

For an existing staging broker, regenerate definitions using the existing
`infra/deploy/prepare.py` procedure, then apply the shared deployment with its
broker revision mechanism. This branch adds the Profile queues/permissions
without changing Auth's publisher credentials or event. Incorrect existing
queue arguments cause a visible startup/readiness failure rather than deletion.
DLQ replay is an operator action after diagnosis; preserve the eventId and
reset `x-profile-attempt` to 1 for an approved new cycle.

## Tests and quality checks

```powershell
npm run build
npm run typecheck
npm run format:check
npm run lint
npm test -- --runInBand
npm run test:e2e -- --runInBand
```

The HTTP suite verifies technical health routes using a controlled database
test double; it does not claim JWT/onboarding coverage. The integration suite
uses a real local PostgreSQL server and creates uniquely named disposable
databases. It requires a local role with CREATEDB and extension permissions.
It drops only the databases created by that test run, never a supplied database.

For an isolated native PostgreSQL test instance on Windows (PostgreSQL tools
must be on PATH):

```powershell
$testData = Join-Path $env:TEMP ('cluster-jam-profile-' + [guid]::NewGuid().ToString('N'))
initdb -D $testData -U profile_test --auth=trust --encoding=UTF8 --no-locale
pg_ctl -D $testData -l (Join-Path $testData 'server.log') -o '-h 127.0.0.1 -p 55439' -w start
$env:PROFILE_INTEGRATION_LOCAL = 'true'
$env:PROFILE_TEST_DATABASE_URL = 'postgresql://profile_test@127.0.0.1:55439/postgres'
npm run test:database
pg_ctl -D $testData -m fast -w stop
```

Use the trust-authenticated server only for disposable, loopback-bound local
tests. No real data or service credentials belong there. The integration
command fails without explicit local test configuration; it never silently
skips real database verification.

The full messaging suite additionally needs the isolated broker. From the
repository root:

```powershell
docker compose -p cluster-jam-profile-test -f infra/profile/compose.test.yaml up -d --wait
npm --prefix services/authService ci --ignore-scripts --no-audit --no-fund
cd services/profileService
# Start the disposable PostgreSQL instance above and keep it running.
$env:PROFILE_INTEGRATION_LOCAL = 'true'
$env:PROFILE_TEST_DATABASE_URL = 'postgresql://profile_test@127.0.0.1:55439/postgres'
$env:PROFILE_TEST_RABBITMQ_URI = 'amqp://profile-test-admin:local-broker-test-only@127.0.0.1:5679/profile-tests'
$env:PROFILE_TEST_RABBITMQ_MANAGEMENT_URL = 'http://127.0.0.1:15679'
npm run test:integration
# Or npm run test:messaging for the messaging suite alone.
python -m unittest discover -s ../../infra/profile -p 'test_*.py' -v
cd ../..
docker compose -p cluster-jam-profile-test -f infra/profile/compose.test.yaml down --volumes
```

This removes only the explicitly named disposable test project. Each broker
test uses a unique vhost and service users, with the production permission
patterns; those are removed afterward. The contract test executes Auth's real
event factory and RabbitMQ publisher. It requires Auth's dependencies for that
test only; Profile runtime imports no other service. Actual Supabase signup
and trigger publication still need the wider registration acceptance stack.

## Deployment status

The service supplies source/compiled migration commands and a working broker
consumer. Dockerfile, Compose database provisioning, migration job, mounted
service secrets and CI arrive in their planned branches. Shared broker
topology and permissions are included here because the consumer requires them.
Swagger and business routes are not yet available. The test broker Compose
does not constitute a complete production Profile deployment.
