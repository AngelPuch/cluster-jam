# Profile deployment

This deploys Profile's owner profile/onboarding/address API and registration
consumer. Orders integration is deferred at the user's request; no internal
Orders route or service-authentication setting is added.

## Build and verify

From the repository root, with Docker/Compose v2, Python 3.12+ and OpenSSL on PATH:

```sh
docker build -f services/profileService/Dockerfile -t cluster-jam/profile:local .
python3 infra/profile/verify_stack.py --image cluster-jam/profile:local
```

On Windows use `python` instead of `python3`. The image uses Auth's pinned Node
24 base, runs non-root with production dependencies and includes a liveness
healthcheck. Its allowlisted build context excludes secrets, environment files,
other services and installed dependencies. Build checks include source/isolated
test types, ESLint, formatting, unit/HTTP tests and OpenAPI drift. Cross-service
database/broker integration files run separately with Auth's test dependencies;
they are not copied into the isolated image build.

The verifier creates a private staging-like PKI and disposable PostgreSQL,
RabbitMQ, HTTPS JWKS fixture and Nginx containers using the actual Compose model
and runtime image. It checks migrations/grants, verified TLS, confirmed events,
inbox deduplication, JWT-protected HTTP/address flows, owner isolation, default
selection, preconditions, log privacy/correlation, outages/recovery, persistence
and graceful shutdown. It publishes no ports and removes only its own
`profile-verify-<random>` containers/networks/volumes and validated `.verify`
directory. Existing shared services and volumes are untouched.

The identity/event fixture uses real ES256 signatures and TLS. A separate,
single real signup scenario verifies Auth and local Supabase without replacing
them with identity fixtures:

```sh
npm --prefix services/profileService ci --ignore-scripts --no-audit --no-fund
npm --prefix services/authService ci --ignore-scripts --no-audit --no-fund
python3 infra/profile/verify_registration.py
```

It uses Auth's locked Supabase CLI, configuration, migrations and email templates,
starts only database/Auth/gateway/mail services, and calls the real compiled Auth
API. Its actual outbox worker publishes through RabbitMQ into Profile's separate
database. One minimum profile, inbox record and protected role are asserted.
Only its uniquely named Supabase/Compose project is removed; the helper refuses
occupied ports 54321, 54322, 54324, 55439 and 5679. Supabase CLI output/keys are
captured privately. The fictitious credentials in `compose.registration.yaml`
belong only to these disposable loopback dependencies.

Normal Profile CI runs this one scenario, source quality and OpenAPI drift. The
full image/TLS verifier above is available through manual `extended_checks`;
routine PRs do not repeat the earlier complete battery.

## Trust boundaries

- `profile`: read-only filesystem, dropped capabilities, bounded resources/logs,
  private HTTP listener, mounted runtime password and AMQPS consumer URI.
- `db-profile`: isolated internal network and persistent volume, no host port,
  password authentication and TLS-only network access with hostname verification.
- `profile-migrate`: explicit one-shot compiled job using a separate login.
  Compose requires it to succeed before API startup; runtime performs no DDL.
- Existing shared RabbitMQ: canonical topology and narrowly scoped
  `profile-consumer`, using verified AMQPS.
- Existing shared Nginx: HTTPS owner routes, `/docs/profile/`,
  `/openapi/profile.json` and `/health/profile/live` / `ready`. Auth and
  Personalization routes remain. W3C/upstream trace IDs correlate safe JSON logs.

Bootstrap establishes database/logins only. Versioned TypeORM migrations create
the schema/tables. Runtime receives SELECT/INSERT/UPDATE on profiles,
SELECT/INSERT/UPDATE/DELETE on addresses and SELECT/INSERT on inbox. It has no
DDL, migration-history access, profile/inbox DELETE permission or access to
another database. Migration/admin credentials never reach the API container.

## Ubuntu staging preparation and deployment

Provision the shared PKI, backend network and broker first with the existing
monorepository deployment. Its definitions already include Profile permissions.

```sh
cp infra/profile/.env.example infra/profile/.env
# Replace the public Supabase/JWKS URLs.
python3 infra/profile/prepare.py
bash infra/deploy/deploy.sh profile
```

The Profile-only preparer uses the existing shared CA/consumer credential,
preserves existing passwords, creates missing database credentials and
issues/preserves a `db-profile` server certificate. It does not request Supabase
keys or change Auth secrets. Private directories are ignored by Git. Certificate
renewal follows the shared PKI procedure; recreate the affected database
container to load its renewed key. Bootstrap runs only on a new volume: changing
a password file does not rotate an existing SQL login.

The deployment helper builds a commit-tagged image, records `release.env` and
its previous value, validates Compose, starts PostgreSQL, runs migrations,
starts Profile and checks readiness. It recreates only the shared gateway and
checks HTTPS readiness; Auth, Personalization and RabbitMQ are not restarted.
Pending shared certificate renewal must be completed first. Source-change checks
are scoped to Profile deployment paths, preserving unrelated Auth changes.

| Mounted file | Consumer |
| --- | --- |
| `.secrets/postgres_admin_password` | Database bootstrap |
| `.secrets/profile_db_migration_password` | Bootstrap and migration job |
| `.secrets/profile_db_password` | Bootstrap and runtime |
| `.secrets/profile_rabbitmq_uri` | Runtime only |
| `.secrets/profile-db.key` | Database TLS; copied to postgres-owned mode 0600 |
| `.certificates/profile-db.crt` / `profile-db-ca.crt` | Database public certificate / trust |
| `infra/shared/.pki/ca.crt` | Broker/JWKS trust, additive to Node's public roots |

Use `DB_PASSWORD_FILE`, `RABBITMQ_URI_FILE` or alias `RABBITMQ_URL_FILE` instead
of its direct value, never alongside it. Empty, multiline, oversized and
unreadable secrets fail with sanitized messages. Migration validation resolves
only database settings. `DB_RUNTIME_ROLE=app_profile` enables the explicit
grants on the migration job; it is not set on runtime.

```sh
bash infra/deploy/compose.sh profile ps
bash infra/deploy/compose.sh profile logs --tail 100 profile
bash infra/deploy/compose.sh profile run --rm --no-deps profile-migrate
# Stop only the API, retaining data and shared services.
bash infra/deploy/compose.sh profile stop profile
```

Liveness remains independent of dependencies; readiness returns controlled 503
during database/broker outages and recovers afterward. SIGTERM cancels/drains
consumption, closes AMQP and closes the database pool. Nest may re-emit SIGTERM
after cleanup, giving exit 143; SIGKILL is not a successful graceful stop.
