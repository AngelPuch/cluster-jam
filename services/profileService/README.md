# Cluster JAM Profile Service

Profile owns customer names, phone numbers, contact emails, onboarding and
addresses. Supabase Auth owns identity and credentials. Auth's registration
event is the source of the minimum profile; neither Auth nor Supabase writes
to the Profile database.

## Current implementation

The service consumes Auth registration events through RabbitMQ and provisions
minimum profiles using a transactional PostgreSQL inbox. It handles duplicates,
bounded retries, DLQ delivery, reconnection and graceful consumer shutdown.

Local Supabase JWT verification and owner profile read/update are implemented,
with transactional onboarding, strong conditional updates, sanitized Problem
Details, HTTP trace correlation and Swagger/OpenAPI. Owned address CRUD and
transactional default selection and Docker/Compose deployment support are
implemented. Dedicated CI and complete Supabase signup acceptance remain.
Orders integration is deferred at the user's request.
No public endpoint invokes provisioning. The runnable API exposes:

- `GET /health/live`: process liveness, independent of PostgreSQL.
- `GET /health/ready`: database query and consumer connection; 503 when unavailable.
- `GET /api/v1/profiles/me`: authenticated owner's profile and current ETag.
- `PATCH /api/v1/profiles/me`: conditional partial update and derived onboarding state.
- `GET/POST /api/v1/profiles/me/addresses`: list/create owned addresses.
- `GET/PATCH/DELETE /api/v1/profiles/me/addresses/{addressId}`: read/edit/delete an owned address.
- `GET /docs/` and `GET /openapi.json`: public interactive and machine-readable API documentation.

See [the diagnosis and implementation plan](../../docs/profile/implementation-plan.md)
and verification results for [persistence](../../docs/profile/verification-01.md)
and [messaging](../../docs/profile/verification-02.md), plus
[JWT verification](../../docs/profile/verification-03.md) and
[owner HTTP/onboarding](../../docs/profile/verification-04.md) and
[owned addresses](../../docs/profile/verification-05.md) and
[TLS deployment](../../docs/profile/verification-06.md).

## Architecture and technologies

NestJS 12, TypeScript in strict mode, TypeORM 1.1.1 and PostgreSQL. Dependency
versions are fixed by `package-lock.json`; use `npm ci`. Node 22.20 was used
for local checks; the existing Auth production image uses Node 24 LTS.

```text
src/
    application/
        ports/profile-provisioning.port.ts
        ports/access-token-verifier.port.ts
        ports/profile-repository.port.ts
        ports/address-book-repository.port.ts
        profile/            # minimum provisioning, read mine, update/onboarding rules
        addresses/          # owner reads, create/update/delete, validation and safe failures
        security/           # verified identity, protected roles and safe failures
    infrastructure/
        config/environment.validation.ts
        database/
            entities/       # profile, address and inbox
            migrations/     # schema changes, no synchronize
            repositories/   # provisioning, owner profile and transactional address book
            typeorm.options.ts
            typeorm.config.ts
            typeorm.module.ts
        messaging/          # canonical topology, confirmed handoff and reconnecting listener
        observability/      # JSON allowlist logger and OpenTelemetry HTTP/consumer spans
        security/           # jose/JWKS adapter and Nest module
    interfaces/http/health/
    interfaces/http/profiles/ # owner controller, DTOs, JWT guard and identity decorator
    interfaces/http/addresses/ # owned address controller and input/response DTOs
    interfaces/http/common/errors/ # centralized sanitized Problem Details
    interfaces/http/openapi/ # Swagger schema and examples
    interfaces/messaging/   # validated registration DTO and manual ACK consumer
    profile.module.ts
    commands/               # metadata-only OpenAPI export/check
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
# Set the public SUPABASE_URL and matching SUPABASE_JWKS_URL before starting.
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
| `DB_PASSWORD_FILE` | Mounted alternative; cannot accompany a direct value |
| `DB_RUNTIME_ROLE` | Optional safe role identifier for compiled migration grants |
| `DB_SSL` | true/false; false locally, required true in staging/production |
| `DB_CA_PATH` | Optional PEM CA for verified database TLS |
| `SUPABASE_URL` | Required public Supabase project origin, HTTPS outside local development |
| `SUPABASE_JWKS_URL` | Required matching /auth/v1/.well-known/jwks.json URL |
| `SUPABASE_ISSUER` | Optional; must equal SUPABASE_URL + /auth/v1, otherwise derived |
| `SUPABASE_AUDIENCE` | Optional; fixed authenticated user audience |
| `LOG_LEVEL` | DEBUG, INFO, WARN or ERROR; INFO |
| `RABBITMQ_CONSUMER_ENABLED` | true by default; explicit false for database-only tooling |
| `RABBITMQ_URI` | Required when consuming; amqps in staging/production |
| `RABBITMQ_URL` | Compatibility alias; conflicting values are rejected |
| `RABBITMQ_URI_FILE` / `RABBITMQ_URL_FILE` | Mounted secret alternatives, without a direct value |
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

Adding JWT support changes the application startup configuration: existing
private `.env` or deployment settings must supply both public Supabase URLs.
No publishable key, service-role key, shared signing secret, password or token
is required by the JWT verifier. Migration commands validate only database
settings and remain independent of broker/identity configuration.

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

JWT unit tests use real cryptographic signatures and a controlled JWKS
transport. HTTP tests start a real loopback JWKS server and Nest routes defined
only inside the test suite. They exercise the actual exported SecurityModule,
guard, decorator and error filter; no probe route is built into production.
The local HTTP test command requires loopback socket access but no Supabase
account or database. `jose` is pinned to Auth's existing 6.2.12 version.

The health-only HTTP suite uses a controlled database test double. The JWT
HTTP suite uses real signed tokens and a loopback JWKS server. The owner HTTP
integration suite runs the actual AppModule, controller, guard, use cases and
TypeORM adapters against PostgreSQL and a loopback JWKS server. The integration suite
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

## Docker and deployment

Profile supplies a non-root read-only image, isolated PostgreSQL database/network/
volume, separate migration/runtime credentials, compiled one-shot migration job,
verified database/broker TLS, mounted secrets and HTTPS gateway routes. The
compiled migration command logs sanitized results and optionally applies explicit
runtime grants; it never starts HTTP or the consumer. No new domain migration is
required. See [deployment commands and trust boundaries](../../infra/profile/README.md).

From the repository root:

```powershell
docker build -f services/profileService/Dockerfile -t cluster-jam/profile:local .
python infra/profile/verify_stack.py --image cluster-jam/profile:local
```

The verifier uses disposable owned containers and real TLS, PostgreSQL, RabbitMQ,
ES256/JWKS and HTTPS requests. The earlier test-broker Compose remains a focused
regression fixture. Dedicated CI and live Supabase signup/outbox acceptance are
pending. Orders is outside current scope.

## Local JWT authentication contract

`SecurityModule` exports `JwtAuthGuard` and the application token-verifier port.
Owner controllers import this module, apply the guard and read
`CurrentIdentity`. The verified result contains only an immutable `userId`
and `appRole`. The user ID is taken from the signed UUID `sub`; roles are
`cliente` or `administrador` from signed `app_metadata.app_role`. Body/query
user IDs, `x-user-id`, cookies, URL tokens and `user_metadata` do not supply
identity or elevate permissions. Administrator identity alone grants no access
to another customer's profile or to the future Orders-only internal route.

The adapter verifies ES256/RS256 signatures, exact issuer, audience
`authenticated`, required sub/exp/iss/aud, expiration and not-before. It requires
the Supabase claim `role=authenticated` and rejects anonymous/service-role
credentials, unsupported algorithms, unsigned tokens, unknown keys and forged
signatures. JWT input is bounded to 16 KiB. Duplicate Authorization fields or
an invalid Bearer header are rejected before key retrieval.

Configure an asymmetric Supabase signing key published through the project's
JWKS before using this service. Profile follows Personalization's local
asymmetric verification. Auth retains its own legacy HS256/live-session
behavior; Profile makes no user/session lookup and stores no credentials.
Local JWT validation observes signed claims until token expiry; session/role
changes are reflected in newly issued tokens. Auth's local configuration sets
access-token expiry to 900 seconds.

One reusable JWKS resolver caches public keys for 10 minutes, coalesces
concurrent downloads and limits unknown-key refresh to a 30-second cooldown.
Each fetch has a 5-second timeout and does not follow redirects. Keys come
only from the configured project URL; token-provided key URLs are ignored.
Fresh cached keys can validate during an outage. Once the cache expires,
unavailable/malformed/empty/ambiguous JWKS fails closed. No identity-provider
request occurs at startup or on a normal verification using cached keys.

The project origin and JWKS must match, with no credentials, custom paths,
query strings or fragments. Staging/production require HTTPS. HTTP is allowed
only for loopback origins in development/test, enabling the isolated tests.
Health routes remain public and their probes do not fetch JWKS.

| Status | Stable code | Meaning |
| --- | --- | --- |
| 401 | INVALID_ACCESS_TOKEN | Missing, malformed, expired or unverifiable user credential |
| 403 | INVALID_APP_ROLE | Signed identity lacks an allowed protected application role |
| 503 | SERVICE_UNAVAILABLE | Required signing keys cannot currently be obtained or used |

These errors use `application/problem+json`, `Cache-Control: no-store`, a path
without its query and a traceId. A 401 includes `WWW-Authenticate: Bearer`.
Responses contain no presented token, provider diagnostics, SQL or raw error.
Owner endpoints use this boundary for every read and update.

## Owner profile and onboarding HTTP contract

`GET /api/v1/profiles/me` returns only `userId`, `fullName`, `phone`,
`contactEmail`, `onboardingStatus`, `createdAt` and `updatedAt`. `fullName`
maps to the existing SQL `name` column; timestamps are ISO 8601 UTC strings.
Name and phone start null. Historical profiles can also have null contactEmail.
If asynchronous provisioning has not arrived, GET and PATCH return
`404 PROFILE_NOT_READY`; neither creates a profile.

PATCH accepts at least one of `fullName` (120 characters), `phone` (30) and
`contactEmail` (254, valid email). Surrounding whitespace is trimmed. Missing
fields are preserved; null, blanks, control characters and unknown properties
are rejected with 422. Clients cannot supply userId, timestamps, roles,
credentials or onboardingStatus. A historical profile without a valid contact
email must explicitly provide one or receives `422 PROFILE_CONTACT_EMAIL_REQUIRED`.
Contact email evolves independently of the Supabase login email; registration
redelivery never overwrites it. There is no identity-provider update call.

Additional validation recommendation adopted here: phones contain 7–15 digits,
with an optional leading `+` and spaces, parentheses, dots or hyphens, within
the existing 30-character SQL limit. The source documents do not prescribe a
regional phone format. Names are nonblank within the existing 120-character
limit. `COMPLETED` is derived only when name, phone and contact email satisfy
these rules. Other profiles remain `PENDING`. Pickup onboarding requires no address.

GET and successful PATCH return a strong quoted `ETag` and `Cache-Control:
no-store`. A GET with matching `If-None-Match` returns 304 after authentication.
Send that ETag in `If-Match` on PATCH: absent headers return
`428 PRECONDITION_REQUIRED`; unsupported weak/wildcard/list/malformed tags
return 400; a stale revision returns `412 PRECONDITION_FAILED`. Read again
and reconcile changes before retrying. The repository takes a PostgreSQL row
lock, checks the revision and recomputes onboarding in the same transaction.
Responses are returned only after commit. No new migration is needed: the
revision hashes the stored profile snapshot and timestamps.

Example from `services/profileService`, using a privately supplied valid token:

```powershell
$headers = @{ Authorization = "Bearer $env:PROFILE_ACCESS_TOKEN" }
$profile = Invoke-WebRequest http://localhost:8080/api/v1/profiles/me -Headers $headers
$headers['If-Match'] = [string]$profile.Headers.ETag
$body = @{ fullName = 'María López'; phone = '+52 55 1234 5678' } | ConvertTo-Json
Invoke-WebRequest http://localhost:8080/api/v1/profiles/me -Method Patch -Headers $headers -ContentType 'application/json' -Body $body
```

All failures use RFC 9457 `application/problem+json` and stable codes. Invalid
input is 422, syntax is 400, unsupported content type is 415, oversized JSON is
413, authentication is 401/403 and unavailable persistence/JWKS is 503. Raw
exceptions, SQL, tokens and submitted values are not exposed. HTTP logs record
status, duration and W3C trace/span identifiers without bodies, contact fields,
headers or query strings. Responses include `X-Trace-Id`; problems include traceId.

## Swagger and contract checks

Start the service normally, then open `http://localhost:8080/docs/` or download
`http://localhost:8080/openapi.json`. Authorize with an asymmetric Supabase user
JWT. The UI does not persist authorization. Owner profile/address operations document the
bearer boundary, DTOs, ETag/If-Match, responses and Problem Details examples.
Health routes remain outside `/api/v1` and require no authentication.

```powershell
npm run openapi:export  # build and write contracts/openapi/profile/v1/openapi.json
npm run openapi:check   # build and fail if generated JSON differs
```

These commands scan the actual AppModule using Nest preview mode. They do not
instantiate providers, connect PostgreSQL/RabbitMQ/JWKS, initialize or listen.
This is an offline metadata tool, not a runtime persistence bypass. The
check compares normalized JSON, so key ordering, formatting and Windows CRLF
do not create false drift. The versioned contract contains only implemented routes. To run owner HTTP tests
alone with the local PostgreSQL environment documented above:

```powershell
npm run test:integration -- profile-http
```

## Owned address contract

RF-04 and the database model define 0..N owned addresses and at most one
default. These addresses are independent of pickup onboarding. A provisioned
PENDING owner, including a legacy owner with null contactEmail, can manage
addresses. No address operation creates a profile or changes contact/onboarding.

| Method and path (under `/api/v1`) | Result and conditional revision |
| --- | --- |
| GET `/profiles/me/addresses` | 200 `{ "items": [...] }`, sorted by UUID; collection ETag; empty collection is valid |
| GET `/profiles/me/addresses/{addressId}` | 200 address DTO and item ETag; follows POST Location and supplies revision for edit/delete |
| POST `/profiles/me/addresses` | Requires collection If-Match; 201 address DTO, item ETag and canonical Location |
| PATCH `/profiles/me/addresses/{addressId}` | Requires item If-Match; 200 updated DTO and current item ETag |
| DELETE `/profiles/me/addresses/{addressId}` | Requires item If-Match; 204 with no body; refresh the list afterward |

Both reads support authenticated `If-None-Match`/304 and all responses use
`Cache-Control: no-store`. The individual GET refines the original CRUD plan
so clients can follow Location and retrieve the correct item validator.
Collection and item tags are distinct and cannot be substituted. Every tag
covers the current owned address book; changing any address invalidates older
item tags too. Read the list before creating, or read the target address before
editing/deleting. Missing If-Match is 428, unsupported syntax is 400 and stale
state is 412. Re-read and reconcile before retrying; POST retries with a stale
collection tag do not create another address.

Create requires label, recipient, street, exteriorNumber, neighborhood,
municipality, state, postalCode and country. Input lengths follow the existing
columns: label 40, recipient/neighborhood/municipality/state 120, street 160,
exteriorNumber/interiorNumber 20, postalCode 5 and country 2. Text is trimmed;
blank/control-containing or oversized values and unknown fields are rejected
with 422. Postal code remains text, preserving leading zeroes. The adopted
country-validation policy is ISO 3166-1 alpha-2, normalized to uppercase; the
source documents specify the two-character column, not a country-code registry.
Postal formatting uses the documented column length rather than a new regional rule.

Only interiorNumber accepts null. Omit it on create for null, or send null on
PATCH to clear it. All other null values are invalid. PATCH preserves omitted
fields and requires at least one allowed field. isDefault must be a JSON boolean
and defaults to false on create; no first address is automatically selected.

Setting isDefault=true demotes the previous default and writes the target in
one transaction. false or deletion can leave no default; no replacement is
chosen automatically. This implements the documented **at most one** rule.
Reads take a shared parent-profile lock; writes take its exclusive lock,
recheck revisions inside that transaction and return only after commit. The
existing partial unique index remains the database backstop. A failure after
demotion rolls back the entire change. No new migration or dependency is needed.

Owner scope comes only from JWT sub, including for administrators. userId/id/
roles/revisions supplied in JSON cannot reassign ownership. Every query/mutation
is scoped to the owner; foreign and missing address UUIDs both return
`404 ADDRESS_NOT_FOUND`. UUID paths are case-insensitive. Missing owner profiles
return `404 PROFILE_NOT_READY`. Persistence failures are sanitized 503 problems.
POST/PATCH require JSON after authentication and before DTO validation, returning
415 for unsupported types. Logs retain status/duration/trace fields only.

Example, continuing with the privately supplied bearer header above:

```powershell
$addressHeaders = @{ Authorization = "Bearer $env:PROFILE_ACCESS_TOKEN" }
$list = Invoke-WebRequest http://localhost:8080/api/v1/profiles/me/addresses -Headers $addressHeaders
$addressHeaders['If-Match'] = [string]$list.Headers.ETag
$addressJson = @{
    label = 'Casa'; recipient = 'María López'; street = 'Avenida Reforma'; exteriorNumber = '123'
    neighborhood = 'Centro'; municipality = 'Cuauhtémoc'; state = 'Ciudad de México'
    postalCode = '06000'; country = 'MX'; isDefault = $true
} | ConvertTo-Json
$created = Invoke-WebRequest http://localhost:8080/api/v1/profiles/me/addresses -Method Post -Headers $addressHeaders -ContentType 'application/json' -Body $addressJson
$addressHeaders['If-Match'] = [string]$created.Headers.ETag
$itemUrl = 'http://localhost:8080' + [string]$created.Headers.Location
Invoke-WebRequest $itemUrl -Method Patch -Headers $addressHeaders -ContentType 'application/json' -Body '{"interiorNumber":"4B"}'
# Refresh this item's ETag before the next edit/delete.
```
