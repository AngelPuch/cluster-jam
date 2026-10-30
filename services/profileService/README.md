# Cluster JAM Profile Service

Profile owns customer names, phone numbers, contact emails, onboarding and
addresses. Supabase Auth owns identity and credentials. Auth's registration
event is the source of the minimum profile; neither Auth nor Supabase writes
to the Profile database.

## Current implementation

This first incremental PR supplies PostgreSQL migrations, a transactional inbox
and a provisioner wired through a Nest application port. Provisioning is tested
against real PostgreSQL, including concurrent deliveries and transaction failures.

RabbitMQ consumption, JWT guards, profile/address HTTP routes, Orders contact,
Swagger/OpenAPI, Docker deployment and CI are subsequent PRs. No public
endpoint currently invokes provisioning. The runnable API exposes only:

- `GET /health/live`: process liveness, independent of PostgreSQL.
- `GET /health/ready`: database query, 503 when unavailable.

See [the diagnosis and implementation plan](../../docs/profile/implementation-plan.md)
and [verification results](../../docs/profile/verification-01.md).

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
    interfaces/http/health/
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
3. Resolve only after COMMIT; a failure rolls back both inserts. The future
   consumer must await this result before ACKing RabbitMQ.

The inbox stores no event payload, passwords or tokens. The event contract is
[`identity.user.registered.v1`](../../contracts/events/identity.user.registered.v1.schema.json).
Input contract validation belongs to the future messaging interface. This
branch adds no dependency on Auth's or Personalization's code or database.

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
npm run test:integration
pg_ctl -D $testData -m fast -w stop
```

Use the trust-authenticated server only for disposable, loopback-bound local
tests. No real data or service credentials belong there. The integration
command fails without explicit local test configuration; it never silently
skips real database verification.

## Deployment status

The first PR provides source and compiled migration commands, not a deployed
Profile stack. Dockerfile, Compose database provisioning, migration job,
service secrets, broker TLS/permissions and CI arrive in their planned branches.
Swagger and business routes are not yet available. Do not deploy this branch
as though it were the completed Profile Service.
