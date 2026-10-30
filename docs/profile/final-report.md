# Profile delivery report

Delivery prepared on 30 October 2026. Profile's agreed implementation is ready;
the final CI branch still requires PR checks/review and authorized squash merge.
Orders is deferred explicitly because that microservice does not exist yet.
There is no Orders route or service-authentication placeholder.

## Delivered behavior

- Registration provisioning through real Auth/Supabase outbox -> RabbitMQ ->
  Profile, with a local transactional inbox and minimum PENDING profile.
- Idempotent processing, three bounded attempts, confirmed retry/DLQ handoff,
  reconnection and graceful shutdown.
- Local asymmetric Supabase JWT/JWKS verification and protected roles. Owner
  identity always comes from signed `sub`, including administrator requests.
- Own contact read/partial update, derived onboarding and conditional writes.
  Contact email is separate from Supabase login email; Profile stores no tokens
  or credentials. Name, phone and valid contact email complete onboarding.
- Owned address CRUD with transactional default selection and owner isolation.
  Addresses are optional for the current pickup onboarding.
- Strict DTO validation, sanitized RFC 9457 errors, trace correlation, safe JSON
  logs, health/readiness and versioned Swagger/OpenAPI.
- Non-root Node 24 image, isolated persistent PostgreSQL, verified TLS/AMQPS,
  mounted secrets, separate migration/runtime roles and scoped deployment.
- Lean dedicated CI: source quality, one real registration scenario and contract
  drift. The complete image/TLS verifier is available through manual dispatch.

## Final structure and changes

`services/profileService/src/application` contains use cases and ports for
profiles, addresses and security. `infrastructure` contains TypeORM entities,
migrations/repositories, RabbitMQ, configuration, JWT and observability adapters.
`interfaces` contains HTTP controllers/DTOs/guards and registration consumption.
`commands` supplies compiled migrations/grants and offline OpenAPI export/check.

Service tests/configuration, package/lockfile, Docker build inputs, `.env.example`
and the service README are under `services/profileService`. Deployment/bootstrap/
verification files are under `infra/profile`; shared broker/gateway and scoped
deployment helpers are under `infra/shared` and `infra/deploy`. The API contract
is `contracts/openapi/profile/v1/openapi.json`; CI is
`.github/workflows/profile-ci.yml`. This report, the diagnosis, per-PR descriptions
and verification records are under `docs/profile`.

The pre-existing change to `services/authService/package-lock.json` was preserved
and excluded from all Profile commits. No Auth business behavior or
Personalization API was changed by the final acceptance/CI branch.

## Branches and integration history

| Branch | PR | Squash commit on main |
| --- | --- | --- |
| `feat/profile/add-transactional-provisioning` | [#47](https://github.com/AngelPuch/cluster-jam/pull/47) | `d3c788d` |
| `feat/profile/add-rabbitmq-consumer` | [#48](https://github.com/AngelPuch/cluster-jam/pull/48) | `0a07e76` |
| `feat/profile/add-jwt-authentication` | [#49](https://github.com/AngelPuch/cluster-jam/pull/49) | `e65035a` |
| `feat/profile/add-onboarding-endpoints` | [#50](https://github.com/AngelPuch/cluster-jam/pull/50) | `42f464c` |
| `feat/profile/add-owned-addresses` | [#51](https://github.com/AngelPuch/cluster-jam/pull/51) | `4053a1c` |
| `build/profile/add-deployment-support` | [#52](https://github.com/AngelPuch/cluster-jam/pull/52) | `781ed59` |
| `ci/profile/add-automated-checks` | Final reviewed milestone | Pending authorized squash merge |

Prior PRs were individually squash merged with user authorization. The final
branch starts from updated main at `781ed59c989c32cfa8341eb1cc899fa24907a527`.
See `pull-requests/` for each change description and `implementation-plan.md`
for architecture sources, discrepancies and adopted policies.

## Persistence and migrations

Profile owns schema `app` in its separate PostgreSQL database. There are no
cross-database foreign keys or writes to Supabase identities.

| Migration | Effect |
| --- | --- |
| `1789608835902-create-accounts` | Explicit uuid-ossp, profile/address tables, local FK and at-most-one-default index |
| `1789964255801-update-profile` | Contact email, optional initial name and onboarding, compatible with historical rows |
| `1793232000000-add-inbox-and-onboarding-status` | Inbox event-ID deduplication, constrained PENDING/COMPLETED state and nonempty contact for new/updated rows |

`synchronize` and automatic runtime migrations are disabled. Explicit one-shot
migrations precede the API and grant only the runtime operations it needs.
Legacy missing contact is retained and must be repaired explicitly on editing;
no email is invented from another database.

## Available endpoints

| Method | Direct service path | Behavior |
| --- | --- | --- |
| GET | `/api/v1/profiles/me` | Own profile and strong ETag |
| PATCH | `/api/v1/profiles/me` | Partial contact update/onboarding; If-Match required |
| GET / POST | `/api/v1/profiles/me/addresses` | Owned list/create; collection If-Match for creation |
| GET / PATCH / DELETE | `/api/v1/profiles/me/addresses/{addressId}` | Own item; item If-Match for mutations |
| GET | `/health/live`, `/health/ready` | Process and dependency readiness |
| GET | `/docs/`, `/openapi.json` | Swagger UI and versioned schema |

The shared HTTPS gateway also supplies `/docs/profile/`,
`/openapi/profile.json` and `/health/profile/live` / `ready`. The service README
details DTO fields, ETag refresh/retry behavior, error codes and authentication.

## Executed verification

Milestones 01–06 progressively verified migrations/legacy upgrades, persistence,
duplicate/rollback/retry behavior, signed JWT authorization, owner HTTP and
addresses. The last complete regression in milestone 06 passed 328 Jest cases
(228 unit, 23 HTTP, 77 real PostgreSQL/RabbitMQ) and two Python topology cases.
Docker successfully built its isolated 251 unit/HTTP cases and quality checks.
The disposable full TLS stack passed migrations/runtime grants, HTTPS/JWKS/
AMQPS, actual contact/address flows, outages/recovery, persistence, privacy and
graceful shutdown. These results are historical evidence, not new runs for CI.

Milestone 07 passed one real signup through the actual Auth API, Supabase trigger,
restricted publisher, RabbitMQ and Profile database. Both builds and basic
type/lint/format/OpenAPI checks passed. Routine CI was reduced per the user's
request; full test commands remain available when needed. See
`verification-01.md` through `verification-07.md` for exact scope and evidence.

## Execution and deployment

From the service directory, install/configure a dedicated local database and
the canonical broker topology using the README, then:

```sh
npm ci
# Copy .env.example to .env and supply local database/broker/Supabase settings.
npm run migration:run
npm run start:dev
```

From the repository root, build and optionally verify a disposable TLS stack:

```sh
docker build -f services/profileService/Dockerfile -t cluster-jam/profile:local .
python3 infra/profile/verify_stack.py --image cluster-jam/profile:local
```

For an Ubuntu staging host with the shared PKI/broker/network already prepared:

```sh
cp infra/profile/.env.example infra/profile/.env
# Supply the public Supabase/JWKS URLs; preserve existing shared credentials.
python3 infra/profile/prepare.py
bash infra/deploy/deploy.sh profile
```

Windows verification uses `python` instead of `python3`. See `infra/profile/README.md`
for secrets, readiness, diagnostics, migration commands and resource isolation.

## Remaining gates and limits

The final CI PR must pass its remote checks and be squash merged with explicit
authorization. There is no further implementation milestone in the agreed scope.
Actual staging/production installation, host DNS/PKI and operational deployment
are environment tasks; this delivery does not claim a production rollout.
Orders contact integration and its caller identity contract remain future work.
