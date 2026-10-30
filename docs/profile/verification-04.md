# Owner profile and onboarding verification

Run date: 29 October 2026, America/Mexico_City.
Branch: `feat/profile/add-onboarding-endpoints`.
Base: `e65035a97d39345e16d7bb2e441dee19d5510f6f`.

PR #49 was squash merged after explicit user authorization. Its head was
checked before merging; no remote check runs were associated with that head.
This branch was created from the subsequently updated main. The pre-existing
Auth lockfile change is preserved and excluded.

## Delivered behavior

GET and PATCH `/api/v1/profiles/me` derive the owner exclusively from the
verified JWT sub. The controller maps dedicated response DTOs and delegates
to application use cases behind a storage port. The TypeORM adapter maps SQL
name to fullName and never provisions on read/update. Missing profiles return
404 PROFILE_NOT_READY while registration processing catches up.

PATCH accepts partial fullName, phone and contactEmail updates, trims them,
rejects null/blank/unknown/privileged fields and derives onboarding state.
Only a valid name, phone and contact email produce COMPLETED; pickup does not
require an address. Contact email is independent of login credentials and
survives repeated registration events. Legacy null email remains readable;
updating it requires a genuine contact email, not an invented backfill.

The adopted phone-format recommendation is explicit in the README: 7–15
digits with limited presentation punctuation, within the existing SQL length.
This additional rule is not presented as a regional format mandated by the
source documents. Updates recompute status using the current validation rules,
including when editing historical records.

GET/PATCH expose a strong ETag derived from the stored snapshot. PATCH requires
one quoted If-Match; absence is 428, unsupported syntax 400, stale state 412.
The row lock, revision check, merge and status calculation share one PostgreSQL
transaction; a result is returned after commit. GET conditional reads return
304 only after authentication. No new database column/migration is introduced.

One global Problem Details boundary handles security, application, framework
and body-parser failures without serializing raw exceptions or submitted
values. Helmet, strict whitelist validation, `/api/v1`, safe JSON HTTP logs
and W3C trace propagation are configured by the shared HTTP setup. Health
routes remain public and unversioned. Completion callbacks retain trace context.

Swagger is available at `/docs/` and `/openapi.json`; the committed contract
is `contracts/openapi/profile/v1/openapi.json`. Its schemas, bearer security,
ETag conditions, stable codes and examples describe implemented operations only.
Offline export/check uses Nest preview mode to scan the actual AppModule
without constructing adapters/controllers or connecting/listening. There is
no runtime persistence-bypass switch or replacement persistence implementation.

## Executed checks

Commands run from `services/profileService` unless noted:

| Check | Observed result |
| --- | --- |
| `npm run build` (also run by OpenAPI commands) | Passed |
| `npm run typecheck` | Source and test types passed |
| `npm run lint` | Passed with zero warnings after corrections |
| `npm run format:check` | Passed |
| `npm test -- --runInBand` | 171 tests passed, 12 suites |
| `npm run test:e2e` | 23 tests passed, 2 suites |
| `npm run test:integration` | 48 tests passed, 3 suites |
| `npm run openapi:export` / `npm run openapi:check` | Exported and matched |
| Controlled OpenAPI drift probe | Equivalent CRLF passed; modified title caused exit 1; exact original bytes restored; recheck passed with test dependencies stopped |
| `git diff --check` | Passed |

The current suites contain 242 passing Jest tests. The final full integration
run contains 25 owner HTTP cases and the 23 existing PostgreSQL/RabbitMQ cases.
The JWT/health HTTP suite retains its 23 tests. The existing JSON-import
deprecation and Node experimental-VM-module notices remain visible during Jest
runs; the zero-warning statement above applies to ESLint, not those notices.
The intentional database outage case emits one sanitized HTTP 503 log.

## Real integration evidence

The owner suite runs the actual AppModule, controllers, security adapter,
guard, use cases, provisioning adapter and owner repository. Only the
DataSource binding selects a real, uniquely named disposable PostgreSQL
database created by that suite. Its schema is migrated from the first two
versions with a historical null-email record through the latest migration.
Tokens are cryptographically signed using ephemeral keys; an actual loopback
Node server supplies JWKS. No stub supplies successful persistence or identity.

| Boundary | Verified result |
| --- | --- |
| Owner isolation | JWT owner wins over query/header identity; another token sees its own data; arbitrary user route is absent |
| Read/provisioning separation | GET/PATCH missing owner return 404 and leave storage absent |
| Onboarding | Partial name remains PENDING; valid phone/name/email complete without address |
| Independent contact | Edited contact persists; a new registration event for that user does not overwrite it |
| Input protection | Null, whitespace, wrong format/length, control characters, IDs, roles, credentials and status are rejected with no stored changes |
| Conditional writes | Missing/unsupported preconditions fail; simultaneous writes with one ETag yield one 200 and one 412; stale retries fail |
| Legacy compatibility | Null contact reads; update without email rolls back; explicit contact repair persists and completes |
| Authentication | Missing/bad credentials cannot read/update; conditional reads still require authentication; only JWKS route is fetched |
| Error privacy | Malformed JSON and real missing-table failures become controlled 400/503; no query value, SQL or driver details escape |
| Observability | W3C parent matches problem/response trace ID; completion log context survives callbacks; private fields are excluded |
| Live API contract | Served OpenAPI exactly equals versioned JSON; docs are accessible; health paths remain unversioned |
| Regression | Existing migration/inbox, Auth-factory/publisher and real RabbitMQ retry/DLQ/shutdown cases pass |

The local PostgreSQL 18.6 instance and isolated RabbitMQ test project were used.
Tests create/drop only their own database names, vhosts and users. Infrastructure
Python code is unchanged and its tests were not rerun in this milestone.
After verification, the owned PostgreSQL instance was stopped and the named
RabbitMQ test project was removed. No existing service container was removed.

## Remaining work

Owned address CRUD, authorized Orders contact, the Profile Docker/Compose
deployment and CI remain in their planned branches. Production TLS and actual
Supabase signup/trigger acceptance are not claimed by these local signed-token
and broker tests. New Swagger/Helmet versions match the Auth service choices;
no Auth runtime, contract or lockfile change belongs to this PR.
