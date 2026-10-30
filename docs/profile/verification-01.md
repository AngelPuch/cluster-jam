# Transactional provisioning verification

Run date: 29 October 2026, America/Mexico_City.
Branch: `feat/profile/add-transactional-provisioning`.
Base: `406eb63ebfe1ed23038b17b30bdc61ae7024d1bf`.

This report covers the first incremental PR, not acceptance of the full
Profile Service. Commands run from `services/profileService`.

## Environment and executed checks

Windows, Node 22.20.0, npm 10.9.3, TypeORM 1.1.1, PostgreSQL 18.6. Installed
the existing lockfile with `npm ci --ignore-scripts --no-audit --no-fund`.
No dependency upgrades or Auth lockfile edits were made.

| Executed command/check | Observed result |
| --- | --- |
| `npm run build` | Pass |
| `npm run typecheck` | Pass, source and test configurations |
| `npm run lint` | Pass, zero warnings allowed |
| `npm run format:check` | Pass |
| `git diff --check` | Pass |
| `npm test -- --runInBand` | 2 suites, 15 tests pass |
| `npm run test:e2e -- --runInBand` | 1 suite, 4 tests pass |
| `npm run test:integration` | 1 suite, 12 tests pass against real PostgreSQL |
| `npm run migration:run` on a newly created test DB | All 3 migrations apply |
| Repeated `npm run migration:run` on that DB | No pending migrations |
| `npm run migration:run:prod` on that DB | Compiled configuration loads; no pending migrations |
| Compiled `node dist/main.js` using that DB | Starts; live and ready return `{ "status": "ok" }` |

Total automated tests: **31 passing**. Initial execution exposed ESM Jest
configuration and a configuration typing error; these were fixed before the
successful final checks. Restricted execution also blocked localhost sockets;
HTTP and real database tests were rerun with approved local network access.

PostgreSQL was initialized in a unique temporary directory, bound only to
127.0.0.1:55439, with test-only trust authentication. Integration tests created
and removed only uniquely named `profile_test_*` databases. The CLI/API smoke
check created and removed its own `profile_test_smoke_*` database. It started
the compiled API on localhost:18083 and stopped it after the check. Existing
application databases were not used.

## Requirement to operation to test matrix

| Requirement | Operation | Automated evidence |
| --- | --- | --- |
| Minimum profile, design 2.2 | Transactional provision | Null name/phone, initial email, PENDING, no address and timestamped inbox |
| Idempotence by eventId, design 4.1 | Provision same event twice | Duplicate result; same profile including unchanged timestamps; one inbox entry |
| Idempotence by userId, design 3.2 | Distinct event for same user | No overwrite of edited contact, name, phone or COMPLETED |
| Commit before successful completion, design 4.1 | Await use case then query separately | Committed inbox is visible after successful return |
| Atomic rollback, design 4.1 | Profile insert fails after inbox insert | Neither profile nor inbox persists; corrected redelivery succeeds |
| Concurrent same event | Eight simultaneous provisions | One processed event, seven duplicates, one profile and inbox |
| Concurrent same user | Eight distinct simultaneous events | One profile created; all eight events recorded |
| Migrations from empty | `runMigrations` twice | Correct varchar type/length; subsequent run no-op |
| Legacy rows before contact email | Upgrade populated first-migration DB | Existing name/phone preserved, no invented email; PENDING |
| Legacy completed/onboarding data | Upgrade populated second-migration DB | COMPLETED preserved; complete PENDING row promoted; down/up retains completion |
| Integrity | Direct invalid SQL inserts | Invalid status and missing contact email rejected |
| Dependency injection | Real ProfileModule | Injected use case reaches real TypeORM adapter and PostgreSQL |
| Startup configuration | Environment validator | Required values, port range, environment names, TLS booleans and production TLS checked |
| Error propagation | Application use case | Persistence rejection propagates to caller; no false successful completion |
| Technical health | HTTP health routes | Liveness independent of DB, successful readiness, 503 for uninitialized/failing DB, no private error leak |

`src/application/profile/create-minimum-profile.service.spec.ts` supplies
application delegation/error tests. Configuration tests live beside their
validator. Real persistence and migration tests are in
`test/profile-provisioning.integration-spec.ts`. Health HTTP tests use a database
test double; the persistence suite uses the real database and actual migrations.

## Not verified or not implemented in this PR

RabbitMQ consumption, retry/DLQ delivery, actual Auth-to-Profile publication,
signed JWT validation, owner profile/address HTTP, Orders service authorization,
Swagger/OpenAPI, Docker image/Compose execution and Profile CI are future PRs.
No pass is claimed for them. Existing Auth and Personalization suites were not
rerun in this branch; their code and contracts were not changed.

Docker Desktop's Linux engine was unavailable (`dockerDesktopLinuxEngine`
named pipe absent), so Docker execution is not reported as passing. No line
coverage percentage or full RNF09 exposed-functionality acceptance is claimed;
that matrix must expand as the remaining endpoints and messaging are delivered.

The pre-existing uncommitted change to
`services/authService/package-lock.json` remains outside this PR.
