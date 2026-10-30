# Owned address verification

Run date: 29 October 2026, America/Mexico_City.
Branch: `feat/profile/add-owned-addresses`.
Base: `42f464c3c317fc915f9b01fc4d7e0b6f4aa0f7b2`.

PR #50 was squash merged after the user's explicit authorization. Its exact
head, base and remote checks/statuses were checked first; that head had no
remote checks. This branch was then created from updated main. The existing
Auth lockfile change (60 deletions) is preserved and excluded.

## Requirement and implementation

RF-04, the Profile responsibility table and database PDF page 2 define owned
address creation, reading, editing, deletion and explicit default selection.
The schema permits 0..N addresses and **at most one** default. These addresses
are independent from pickup onboarding and are not shipping logic in this version.

Delivered paths under `/api/v1`:

| Operation | Behavior |
| --- | --- |
| GET `/profiles/me/addresses` | Own items, stable UUID ordering, empty list valid, collection ETag |
| GET `/profiles/me/addresses/{addressId}` | Own item and item ETag; followable POST Location |
| POST `/profiles/me/addresses` | Collection If-Match, 201 item, Location and item ETag |
| PATCH `/profiles/me/addresses/{addressId}` | Item If-Match, partial edit/default choice, 200 item/ETag |
| DELETE `/profiles/me/addresses/{addressId}` | Item If-Match, physical deletion after commit, 204 without a body |

The individual GET is a documented refinement of the planned CRUD to retrieve
the item revision and follow creation Location. Application use cases and a
storage port contain no TypeORM/broker types. The actual TypeORM adapter locks
the owner profile before reading/changing its address book; it never writes
profile contact fields or onboarding. Parent-null compatibility remains intact.

The existing AddressEntity, foreign key and partial unique default index are
unchanged. Setting a default demotes the previous default and persists the target
in the same transaction. Deleting/unsetting a default leaves none. No implicit
first/replacement default is invented. A failed later write restores the former
default through rollback. No new migration or dependency is required.

Collection validators hash the canonical current owner/book snapshot. Item
validators include that collection revision and the item ID. Every address-book
change invalidates prior item revisions, protecting default selection across
different addresses as one aggregate. Checks run inside the locked transaction;
responses follow commit. Missing/unsupported/stale If-Match yields 428/400/412.
GET conditional reads remain authenticated; successful responses are no-store.

Validation follows existing schema lengths. Text is trimmed and rejects blanks,
controls, wrong types, excess length and privileged/unknown fields. Only the
optional interiorNumber allows explicit null clearing. isDefault is a true JSON
boolean. Country validation adopts uppercase ISO alpha-2 as an additional,
documented policy; postalCode preserves text/leading zeroes within varchar(5)
without inventing regional shipping validation. JSON content guards run after
JWT authentication and before DTO validation, consistently returning 415 for
unsupported body formats, including required-field create DTOs.

## Executed checks

From `services/profileService`:

| Command | Observed result |
| --- | --- |
| `npm test -- --runInBand` | 213 tests passed, 14 suites |
| `npm run test:e2e` | 23 tests passed, 2 suites |
| `npm run test:integration` | 77 tests passed, 3 suites |
| `npm run test:integration -- profile-http` (after final Swagger refinement) | 54 HTTP/profile/address tests passed |
| `npm run typecheck` | Source and test types passed |
| `npm run lint` | Passed with zero ESLint warnings |
| `npm run format:check` | Passed |
| `npm run openapi:export` | Built service and updated the versioned actual-route contract |
| `npm run openapi:check` | Built service and matched the generated contract |
| `git diff --check` | Passed |

The current suites contain 313 passing Jest cases. The 54 profile HTTP cases
include 29 new address cases and the 25 existing profile cases. The other 23
integration cases cover real migrations/inbox and RabbitMQ/Auth publication.
The Node VM-module and JSON-import deprecation notices remain visible; zero
warnings above refers to ESLint. Two deliberate database-failure cases emit
sanitized 503 telemetry without SQL, address fields or driver details.

## Requirement–operation–test evidence

| Boundary | Executed evidence |
| --- | --- |
| RF-04 read/create | Empty owner list; real address insert; canonical followable Location; complete response DTO with nullable interior/default boolean |
| RF-04 update/delete | Partial preservation, trim, optional-null clear, default unset, 204 body absence, no automatic default replacement |
| Owner permissions | JWT sub wins over query/header identity; foreign and nonexistent IDs yield identical 404 codes for GET/PATCH/DELETE; administrator cannot cross ownership |
| Input protection | Required fields, every schema text limit, null/blank/control/type checks, country policy, string postal code, boolean default and protected fields |
| Default invariant | True replaces previous default atomically; another owner remains unchanged; actual conflicting SQL still fails the existing partial unique index |
| Aggregate concurrency | Concurrent creates from one collection revision yield 201/412; concurrent selections of distinct addresses yield 200/412 and exactly one stored default |
| Stale/replay requests | Changes to another address invalidate prior collection/item tags; stale creates/edits/deletes fail without lost writes or duplicate creation |
| Rollback | A real PostgreSQL trigger rejects insertion after default demotion; former default, collection and item ETag remain unchanged |
| Legacy/onboarding isolation | Real historical null-email PENDING owner creates an address without contact repair; address writes leave profile fields/timestamps/ETag unchanged |
| Provisioning separation | Every address operation for an unprovisioned owner returns PROFILE_NOT_READY without creating profile/address data |
| HTTP/security | All five routes require real signed JWTs; cached reads still authenticate; malformed UUIDs are 400; UUID case is normalized; body formats are 415 |
| Swagger contract | Live OpenAPI equals committed JSON; response-required fields and both collection/item paths are checked; strict input schemas are exposed |
| Regression | Existing profile onboarding, JWT/JWKS, health, migration/inbox, confirmed publication, retry/DLQ and shutdown suites pass |

The HTTP suite uses the actual AppModule, controllers, guards, use cases,
provisioning adapter and address repository with a real disposable PostgreSQL
18.6 database. Real loopback JWKS and ephemeral signed keys supply identity.
The failure trigger is test-only inside that owned database and is removed in
finally; it is not production schema or substitute persistence. Broker tests
use the named disposable RabbitMQ project. Tests clean only their own database
names, vhosts and users. Infrastructure Python code is unchanged and its tests
were not rerun here.
After checks, the owned PostgreSQL instance was stopped and the named RabbitMQ
test project was removed. Existing service containers and databases were untouched.

## Remaining scope

Authorized Orders contact requires an agreed service identity; the initial
plan identifies that documentation gap. Profile Docker/Compose/CI and full
Supabase signup/trigger acceptance remain planned. These local persistence,
signature and broker results do not claim production-stack/TLS validation.
