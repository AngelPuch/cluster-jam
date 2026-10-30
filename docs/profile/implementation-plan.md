# Profile Service diagnosis and implementation plan

Analysis performed on 29 October 2026 against `main` at
`406eb63ebfe1ed23038b17b30bdc61ae7024d1bf`.

This document records the analysis required before implementation. The first PR
implements only transactional provisioning and its database foundation. Later
steps require their preceding PR to be reviewed and squash merged into `main`.
No merge is authorized automatically by this plan.

Progress: PRs #47–49 were squash merged after explicit user authorization.
PR #48's Python and Docker CI checks both passed before merge. The current
branch, `feat/profile/add-onboarding-endpoints`, starts from updated main at
`e65035a97d39345e16d7bb2e441dee19d5510f6f`. Milestone reports 01–04 record
persistence, messaging, JWT and owner HTTP verification. Owned addresses are
the next step after the current branch is reviewed and squash merged.

## Sources and precedence

The supplied documentation lives in
`C:\Users\migue\Downloads\ProyectoJ\Proyecto`:

- `Proyecto-Cluster-JAM.docx`: RF-04 (own profile and addresses), RNF02–03,
  RNF07–11, technologies, ORM selection and service responsibility tables.
- `Decisiones-diseño-Cluster-JAM.docx`, version 1.0, 18 September 2026:
  sections 2.2, 2.3, 2.4, 3.2, 3.3, 4.1, 4.2 and 5.3; normative decisions D01–D07.
- `Estandar-codificacion.docx`, version 1.1, 18 September 2026:
  sections 1, 2, 4–8 (layers, strict types, REST, errors, events, logs,
  Docker and GitHub Flow).
- `BD-Cluster-JAM.pdf`, version 1.1: page 2 (profile, addresses and inbox),
  page 9 (technical integration tables), pages 10–11 (schema and isolation).

Project decisions are authoritative; the supplementary implementation request
specifies concrete inbox fields and paths. Existing code supplies the actual
integration contract and naming. Recommendations below are identified explicitly.

## Existing architecture

The monorepo contains independent projects under `services/`, versioned REST,
protobuf and event contracts under `contracts/`, and infrastructure under `infra/`.
There is no root Node workspace or shared business model package.

Auth uses Nest modules with `interfaces/http`, `interfaces/workers`,
`application` use cases and ports, and `infrastructure` adapters. Controllers
delegate to use cases. Supabase owns identities, sessions, credentials and roles.
`integration.auth_outbox` lives in Supabase; its trigger is atomic with identity
creation. Auth's publisher reads it, publishes persistent messages with mandatory
routing and publisher confirms, then marks publication after confirmation.

Relevant files:

- `services/authService/src/app.module.ts`, `src/application/ports/`,
  `src/infrastructure/supabase/`, `src/infrastructure/outbox/`.
- `services/authService/src/application/events/registration-event.ts` and
  `src/infrastructure/messaging/rabbitmq-registration-event.publisher.ts`.
- `services/authService/supabase/migrations/` and `supabase/tests/database/`.
- `services/authService/src/interfaces/http/http.setup.ts`: Helmet,
  whitelist validation, forbidden unknown properties, 422 and `/api/v1`.
- `services/authService/src/interfaces/http/common/errors/`: sanitized
  RFC 9457 Problem Details with stable codes and trace identifiers.
- `services/authService/src/interfaces/http/openapi/openapi.setup.ts` and
  `src/commands/auth-openapi.command.ts`: `/docs`, `/openapi.json`, export/check.
- `services/authService/src/infrastructure/observability/`: structured JSON
  logging and OpenTelemetry/W3C trace context.
- Auth tests use Jest in ESM mode, Supertest, adapter unit tests and explicit
  local integration suites with Supabase/PostgreSQL/RabbitMQ.

Personalization follows equivalent boundaries using FastAPI/Pydantic,
SQLAlchemy/Alembic and ports. It has local JWT/JWKS verification, private object
storage, workers, REST and TLS gRPC. Its security verifier checks issuer,
`authenticated` audience, signature, expiration, UUID subject and trusted
`app_metadata.app_role`. It has no profile integration and needs none for the
documented responsibilities.

Profile initially contained entities, two migrations, database wiring and
health routes. Its README and root HTTP test were unmodified Nest starter
content; the test expected a nonexistent `Hello World!` route. There were no
profile use cases, controllers, messaging, JWT guard, Swagger, Dockerfile or CI.

Existing tooling is npm/lockfiles, Nest CLI, TypeScript, ESLint and Prettier.
The only checked-in workflow is `.github/workflows/personalization-ci.yml`.
Auth's Docker build also executes its checks. Shared deployment uses Compose,
Nginx TLS, RabbitMQ TLS and a `cluster-jam-backend` network. Personalization
adds its own database network and migration job.

## Technologies and versions

Profile's lockfile was installed without upgrading dependencies:

| Component | Installed version |
| --- | --- |
| Node on this workstation | 22.20.0 |
| Reference production Node image in Auth | 24, pinned digest |
| Nest common/core/platform-express | 12.0.3 |
| Nest config / TypeORM integration | 12.0.0 / 12.0.1 |
| TypeORM / pg | 1.1.1 / 8.23.0 |
| TypeScript | 5.9.3 |
| Jest / ts-jest | 30.5.1 / 29.4.12 |
| ESLint / Prettier | 9.39.5 / 3.9.7 |
| PostgreSQL used for integration verification | 18.6 |

Auth additionally locks `amqplib` 0.10.9 and uses `jose`, class-validator,
class-transformer, Joi, Swagger and Helmet. Reuse those choices when their
corresponding Profile branch needs them. Personalization declares Python 3.14,
FastAPI 0.162.0, SQLAlchemy 2.1.6, Alembic 1.20.1 and grpcio 1.84.1.

## Exact profile responsibilities

Documented: asynchronously create the minimum profile; read and edit the
authenticated owner's name, phone and contact email; complete onboarding;
manage owned addresses and one default address; return verified contact data
to authorized Orders during checkout. No password/session storage, credential
changes, public arbitrary-user lookup or profile deletion is required.

The contact email starts from registration and then evolves independently of
the login email. Duplicate registration deliveries never update existing data.
The minimum profile has null name/phone, initial contact email and PENDING.
Name, phone and valid contact email are required for COMPLETED; an address is
not an onboarding requirement in the current pickup version.

## Discrepancies and resolutions

1. **`accounts.profiles/full_name` versus `app.profile/name`.** The database PDF
   requires schema `app`; existing migrations/entities use singular English
   names. Keep these SQL identifiers. Expose `fullName` through the future DTO
   and map to entity `name`. No table rename or cross-database FK is needed.
2. **Onboarding already exists.** Add a forward migration converting text to
   varchar(20), preserving the default and adding the two-value constraint;
   do not add a duplicate column. The explicit supplementary enum spelling
   takes precedence over the general PascalCase-member recommendation.
3. **Populated legacy schema cannot run migration 1789964255801.** Its original
   addition of a NOT NULL contact email has no legitimate backfill source.
   Make that addition nullable for historical rows. A later NOT VALID CHECK
   requires nonempty contact email for every new or updated row while retaining
   legacy rows. The ORM explicitly represents this compatibility nullability.
   No fabricated addresses, email lookup in Supabase or profile deletion occurs.
   TypeORM has no checksum replay: databases which already applied that
   migration do not rerun it, and their stricter existing NOT NULL is retained.
4. **Completed legacy profiles.** Preserve existing COMPLETED states. Promote
   PENDING legacy rows only if name and phone are nonblank and the stored email
   has a nonblank local/domain form with a dotted domain. Rows with missing
   required data remain PENDING; no old completion state is blindly reset.
   Future HTTP DTO validation must validate email before persisting user input.
5. **UUID dependency outside migrations.** The initial migration now declares
   `uuid-ossp` explicitly; disable TypeORM's automatic extension installation.
   The migration role needs CREATE on its own database. Runtime does not perform
   DDL or automatically run migrations.
6. **Broad PDF inbox versus minimal inbox request.** Use a dedicated
   `app.inbox_messages(event_id PK, event_type, processed_at)` for this consumer.
   It stores processed identifiers and no contact payload. Composite consumer
   keys and payload retention are not necessary for a dedicated registration
   inbox. Broker retry metadata supplies attempts; no generic projection inbox
   is introduced.
7. **Three attempts.** Both design section 4.1 and the coding standard say a
   maximum of three automatic attempts per cycle. Interpret this as one initial
   attempt plus two retries. This is an explicit implementation interpretation;
   no fourth automatic processing attempt is planned.
8. **Address required at checkout.** The PDF page 2 and RF-04 explicitly say
   addresses are separate from the current pickup order. Orders contact must
   not require an arbitrary shipping address. An explicitly requested address
   must belong to the requested user; selection and optional response need an
   OpenAPI contract in the Orders-contact PR.
9. **Internal authentication unspecified.** Documentation requires authorized
   internal services but specifies no HTTP service credential/issuer/scope.
   Existing gRPC TLS authenticates the server, not an Orders HTTP caller.
   Recommendation: define a service identity mechanism (for example mTLS with
   an Orders identity) before implementing this endpoint. A user JWT, a caller
   header or network membership is insufficient. Do not implement an allow-all
   endpoint or guess a production secret.
10. **Broker permissions insufficient.** `infra/deploy/prepare.py` predeclares
    only the main queue and gives `profile-consumer` no write permissions.
    The consumer PR must add narrowly scoped retry/DLQ permissions and
    provisioning; a retry implementation alone would fail in deployment.
11. **Variable naming.** Auth uses `RABBITMQ_URL`; the supplementary request
    requires `RABBITMQ_URI` validation for Profile. Accept a documented alias or
    consistently use URI in Profile without changing Auth's environment contract.

## Proposed structure

```text
services/profileService/src/
    application/
        ports/              # provisioning, profile/address storage, token verification
        profile/            # create minimum, get mine, update onboarding, order contact
    infrastructure/
        config/             # environment validation and secret loading
        database/           # TypeORM entities, migrations, repository adapters
        messaging/          # amqplib connection, topology, confirmed delivery
        security/           # local Supabase JWT verification
    interfaces/
        http/
            common/         # Problem Details, validation, observability
            health/
            profiles/       # DTOs, guards, thin owner/internal controllers
            openapi/
        messaging/          # validated event DTO and consumer
    commands/               # OpenAPI export/check
```

Application contracts must not import TypeORM or RabbitMQ. Nest modules wire
the implementations. Persistence entities are never HTTP response DTOs.

## Model and proposed API

`app.profile` owns user_id PK (Supabase sub REF, no external FK), nullable
name/phone, contact email, onboarding status, created_at and updated_at.
The compatibility exception for legacy contact email is described above.
`app.address` has its existing address fields and FK to profile; the partial
unique index permits at most one default per user. `app.inbox_messages` has
event_id PK, event_type varchar(100) and processed_at timestamptz.

All business HTTP routes use `/api/v1` per the coding standard:

| Method and path | Requirement and behavior |
| --- | --- |
| GET `/profiles/me` | Owner profile and onboarding state; 404 PROFILE_NOT_READY before provisioning |
| PATCH `/profiles/me` | Partial allowed fields fullName, phone, contactEmail; atomically recompute onboarding |
| GET `/profiles/me/addresses` | List own addresses, including default |
| POST `/profiles/me/addresses` | Create own address; 201 and Location |
| PATCH `/profiles/me/addresses/{addressId}` | Edit own address / choose default transactionally |
| DELETE `/profiles/me/addresses/{addressId}` | Delete own address, no business history deletion |
| GET `/internal/profiles/{userId}/order-contact` | Authorized Orders only; reject incomplete contact; optional owned address under an agreed contract |
| GET `/health/live`, `/health/ready` | Process liveness and bounded local dependency readiness |

Use JWT sub exclusively for owner routes. For validation use 422; credentials
401; authorization 403; missing/not-visible resources 404; incomplete checkout
contact 422 PROFILE_INCOMPLETE; transient dependencies 503. Document Problem
Details, examples, bearer/service security and all implemented codes in Swagger.

## Event contract and delivery plan

`contracts/events/identity.user.registered.v1.schema.json` matches Auth's actual
publisher: eventId UUID, eventType `identity.user.registered`, schemaVersion 1,
aggregateId UUID equal to data.userId, aggregateVersion 1, occurredAt date-time,
data.userId UUID and data.initialContactEmail (email, maximum 254 characters).
The JSON schema prohibits extra properties. AMQP messageId is eventId, type is
eventType, schemaVersion and traceparent are headers. Payload data is never logged.

Keep `identity.events` topic/durable, routing key `identity.user.registered.v1`
and durable main queue `profile.identity.user-registered.v1`. Add two staged
retry queues under `profile.identity.user-registered.retry.*` with progressive
TTL and dead-letter delivery back to the main route; the maximum is 3 attempts
including the original. Invalid contracts and exhausted/permanent failures go
to `profile.identity.user-registered.dlq`.

Before ACKing the original on failure, publish the unchanged body with bounded
attempt metadata to a guaranteed route, require publisher confirm and detect
mandatory returns. If handoff is uncertain, close the channel and let the broker
redeliver the unacknowledged original. Reconnection must use backoff; no infinite
`nack(requeue=true)` processing loop. Evaluate quorum queues with at-least-once
dead lettering so the TTL return leg is also durable, rather than silently
assuming classic queue dead lettering cannot lose messages.

The implemented persistence transaction first inserts eventId with ON CONFLICT
DO NOTHING RETURNING. An absent returned row means successful duplication. A
new event then inserts the minimum profile with ON CONFLICT(user_id) DO NOTHING.
Errors roll back both writes; the Promise resolves only after COMMIT. The future
consumer can ACK successful results of either kind.

## Incremental GitHub Flow

Every branch starts from current main after its prerequisite PR is squash
merged. Do not create stacked branches or locally simulate merges to bypass
this requirement. Every PR carries its own tests, documentation and config.

| Order | Branch | Verifiable scope and dependency |
| --- | --- | --- |
| 1 | `feat/profile/add-transactional-provisioning` | Migration compatibility, inbox, provisioning port/use case/adapter, real PostgreSQL tests; merged PR #47 |
| 2 | `feat/profile/add-rabbitmq-consumer` | Contract DTO, topology, bounded attempts, confirms, reconnection, broker permissions; depends on 1 |
| 3 | `feat/profile/add-jwt-authentication` | Local JWKS verifier, trusted claims, owner guard, signed-token tests; depends on 1 |
| 4 | `feat/profile/add-onboarding-endpoints` | GET/PATCH, domain rules, Problem Details, Swagger export/check and authorization tests; depends on 2–3 |
| 5 | `feat/profile/add-owned-addresses` | Owned CRUD and transactional default selection, constraints and API tests; depends on 4 |
| 6 | `feat/profile/add-order-contact-endpoint` | Agreed service identity and pickup/address contract, complete-only response and access tests; depends on 4–5 and security decision |
| 7 | `build/profile/add-deployment-support` | Docker image, isolated DB/volume, migration job, network/TLS/secrets, graceful shutdown and actual stack verification; depends on 2–6 |
| 8 | `ci/profile/add-automated-checks` | Per-service checks, real DB/broker and Auth publication integration, Docker/OpenAPI drift checks; depends on 7 |

Docs and tests are included with features rather than deferred to a final giant
test branch. The final matrix must demonstrate all critical permissions,
idempotency and failure scenarios and at least 70% of exposed functionality
(RNF09); line coverage alone is not the acceptance measure.

## Verification and remaining work

Milestones 1–3 are squash merged as PRs #47, #48 and #49 after user approval.
Milestone 4 now implements owner GET/PATCH, conditional transactional updates,
derived onboarding, HTTP telemetry, sanitized errors and versioned Swagger.
Its executed checks and scope are recorded in `verification-04.md`; owned
addresses, Orders service authentication/contact, deployment and CI remain.
The phone validation recommendation and ETag/If-Match contract are explicit in
the service README. No address requirement was added to pickup onboarding.

Initial checks and commands are in the service README and milestone reports.
Docker's Linux engine became available for the RabbitMQ test fixture in
milestone 2. The test broker Compose and temporary native PostgreSQL instance
support real integration checks without existing data; they are not a complete
Profile image/deployment verification.

The full service is not complete at milestone 4. Addresses, Orders authorization,
deployment and CI remain planned. No critical-path stub substitutes for them.

The pre-existing modification to `services/authService/package-lock.json` is
unrelated, preserved and excluded from Profile commits.
