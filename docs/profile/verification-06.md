# Profile image and TLS deployment verification

Run date: 29 October 2026, America/Mexico_City.
Branch: `build/profile/add-deployment-support`.
Base: `4053a1cae91b819efe48e9d5aadb42901f5d60d6`.

PR #51 was squash merged after explicit authorization, head/base checks and
verification that no remote checks/statuses were attached. Main was updated
before creating the next branch. The user then explicitly excluded Orders,
which does not exist yet. The unchanged tentative Orders branch was renamed
to deployment; no internal endpoint/mTLS implementation was created. The
pre-existing Auth lockfile change remains preserved and excluded.

## Deployment delivered

The allowlisted multi-stage image uses Auth's pinned Node 24 base, executes
quality/unit/HTTP/contract checks, prunes development dependencies and runs as
`node`. It includes only Profile production artifacts/dependencies and a
liveness healthcheck. Secrets/other services are excluded from its build context.
Cross-service integration source files remain outside this isolated image
build; full host regression still includes them and Auth's actual test publisher.

Compose supplies a separate PostgreSQL database/internal network/persistent
volume, migration/admin/runtime credentials, TLS-only database network access,
verified AMQPS, mounted secret files, one-shot migration job and hardened API.
The API has no published port, filesystem writes or capabilities. Runtime
permissions exclude DDL, migration metadata, destructive profile/inbox operations
and access to other databases. Admin/migration secrets never mount into runtime.

The compiled migration command is independent of identity/broker startup and
logs only safe results. It applies pending versioned migrations and explicit
runtime grants. No new domain migration is introduced. Bootstrap configures
database identities, while all application schema/tables remain versioned.

Shared Nginx adds Profile owner routes, Swagger assets/schema and health aliases
without replacing Auth/Personalization routes. Existing W3C or valid Profile
response trace identifiers correlate gateway/application logs. Profile-only
staging preparation preserves shared credentials/PKI. Deployment builds a
commit-tagged release, runs migrations before the API and recreates only the
gateway; it does not restart the other service/broker containers.

## Executed source and build checks

| Check | Observed result |
| --- | --- |
| Source/test types, ESLint and Prettier | Passed; zero ESLint warnings |
| `npm test -- --runInBand` | 228 unit tests, 15 suites passed |
| `npm run test:e2e` | 23 JWT/health HTTP tests, 2 suites passed |
| `npm run test:integration` | 77 PostgreSQL/RabbitMQ tests, 3 suites passed |
| `npm run openapi:check` | Compilation and committed-contract check passed |
| Docker build | Final `cluster-jam/profile:deployment-check` image built; 228 unit + 23 HTTP cases and all isolated checks passed inside Node 24 |
| Infrastructure Python | Ruff 0.17.2 format/check passed; 2 topology/permission tests passed |
| Bash syntax | `compose.sh`, `deploy.sh`, `deploy-profile.sh` passed `bash -n` |

Current source regression contains 328 passing Jest cases. The new 15 mounted-
secret/role-validation cases cover ambiguous/missing/empty/multiline/oversized
files, password preservation, migration independence, AMQPS enforcement and
unsafe grant identifiers. Source integration uses the existing disposable
PostgreSQL 18.6 and RabbitMQ fixture. The image uses Node 24; its deployment
verification uses the existing pinned PostgreSQL 17.11/RabbitMQ 4.4.0/Nginx
1.30.6 choices from the monorepository. No dependencies were upgraded.

Jest's existing JSON-import and Node VM-module notices remain; the zero-warning
statement applies to ESLint. Deliberate database-failure cases emit sanitized
503 telemetry. Docker packaging changes only Profile's scripts/runtime; the
unrelated Auth lockfile is not staged.

## Actual container evidence

Run from the repository root:

```sh
docker build -f services/profileService/Dockerfile -t cluster-jam/profile:deployment-check .
python3 infra/profile/verify_stack.py --image cluster-jam/profile:deployment-check
```

The verifier runs the actual image and Compose stack in unique private
`profile-verify-<random>` networks/volumes with fresh local certificates. There
are no host-published dependency/API ports or changes to the shared backend.

| Boundary | Verified behavior |
| --- | --- |
| Migration startup | Fresh migration job succeeds; immediate rerun succeeds without replaying existing versions; API waits for successful job |
| Image isolation | Runtime user is node, root filesystem is read-only, capabilities are dropped, passwords/URI are mounted rather than literal environment values |
| Database boundary | Only private DB network; TLS session verified; plaintext rejected; cross-database login rejected; DDL/history access and profile/inbox deletion denied |
| Registration | Confirmed persistent canonical events traverse AMQPS; duplicate event produces one inbox result; another event for an existing owner preserves edited contact |
| HTTP contact | Real ES256/JWKS over HTTPS, 401 boundary, pending provisioning and completed onboarding through Nginx |
| Addresses | Real create/read/update/delete, Location, owner isolation, default replacement/deletion and stale ETag rejection through HTTPS |
| Swagger | Profile schema and UI assets served through the shared gateway |
| Trust | Untrusted HTTPS CA rejected; database and broker verify certificates/hostnames using mounted CAs |
| Availability | Separately stopped RabbitMQ/PostgreSQL cause readiness 503 while liveness remains 200; both recover without API restart and retain profile/address data |
| Shutdown | SIGTERM completes within grace period, logs consumer shutdown and leaves zero app SQL connections and zero broker consumers; Nest's post-cleanup exit 143 is accepted, SIGKILL is not |
| Privacy | Application logs contain no generated credentials, contact email/name or street; no raw captured configuration is printed |

Both the complete candidate-stack run and final-image stack run passed. The
final run additionally verified cross-gateway trace correlation after the Nginx
mapping refinement and actual linked Swagger assets. Only test-owned databases, vhosts/users,
containers/networks/volumes and validated fixture directories are cleaned.
The final local image inspection returned
`sha256:be5eefdecd9ef5dedc26019ffaa8a79603ac07ad3185068b99ee633ab50d3809`.
The temporary native PostgreSQL instance was stopped, the regression broker
project was removed and no test containers remained. Built images remain for review.
The production Ubuntu helper is syntax-checked and its underlying Compose/PKI/
migration/runtime components are exercised locally; no actual staging/production
deployment or certificate installation is claimed.

## Remaining agreed scope

Dedicated Profile CI, integration of this reviewed deployment PR and full
Supabase signup/trigger/outbox acceptance remain. The stack's ephemeral signed
identity/event fixtures prove the real protocol/persistence boundaries but do
not claim a live Supabase signup. Orders remains explicitly deferred.
