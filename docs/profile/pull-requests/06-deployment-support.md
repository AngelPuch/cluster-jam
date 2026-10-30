Profile's implemented API/consumer lacked a reproducible image and deployment.
Add an allowlisted multi-stage Node 24 build with quality/unit/HTTP/OpenAPI
checks, pruned dependencies, non-root runtime and liveness healthcheck. Add
isolated PostgreSQL storage/network, separate migration/runtime credentials,
one-shot compiled migrations/grants, mounted secrets and verified PostgreSQL/
RabbitMQ TLS. Runtime has no DDL, migration-history access, destructive profile/
inbox grants or access to another database.

Add Profile-only staging preparation and deployment helpers, preserving existing
shared credentials. Expose owner API, Profile Swagger and health aliases through
shared HTTPS Nginx while retaining Auth/Personalization routes and safe trace
correlation. Keep graceful consumer/database shutdown and dependency recovery.
Orders is excluded at the user's request; no internal endpoint or mTLS is added.

Validation: source types, zero-warning lint, formatting and OpenAPI pass; all
328 Jest cases pass (228 unit, 23 HTTP, 77 real PostgreSQL/RabbitMQ). Docker
executes its 251 isolated unit/HTTP cases and quality checks successfully.
Infrastructure Ruff, 2 broker-contract tests and Bash syntax checks pass. The
disposable full TLS stack verifies actual migration/grant, HTTPS/JWKS/AMQPS,
profile/address, isolation, persistence/outage recovery, privacy and graceful
shutdown behavior. See `docs/profile/verification-06.md` for commands/evidence.

No new domain migration/dependency upgrade. The existing Auth lockfile change
is excluded. Dedicated Profile CI and full live Supabase signup/outbox
acceptance remain the next reviewed milestone; local signed fixtures do not
claim that acceptance or a production deployment.
