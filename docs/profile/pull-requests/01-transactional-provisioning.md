Profile had database entities but no idempotent way to provision a customer
from a registration event. Its migration also failed when profiles already
existed because it added a required email without a legitimate backfill.

Add a provisioning port/use case and TypeORM adapter that insert the inbox
event and minimum PENDING profile in one transaction. Deduplicate by eventId
and userId without overwriting edited or completed profiles. Successful
completion is returned after commit. Keep the documented `app` schema and
existing table names; create no cross-service database dependency.

Add the forward inbox/onboarding migration, preserve completed legacy profiles,
and make fresh/populated schema upgrades reproducible. Correct the two
historical prerequisites explicitly: declare uuid-ossp in the initial migration
and allow legacy contact emails to be collected without inventing values.
Already applied migrations are not replayed. New/updated rows must have a
contact email; the compatibility CHECK is NOT VALID for historical rows.

Validation: build, source/test type checking, zero-warning lint and format
checks pass. All 31 automated tests pass, including 12 real PostgreSQL tests
covering concurrency, deduplication, rollback and legacy migration upgrades.
Actual source/compiled migration commands and compiled API health were also
verified on a disposable PostgreSQL 18.6 database. See the versioned verification
report for the requirement matrix and exact commands.

This is the first incremental Profile PR. RabbitMQ consumption, JWT/business
HTTP, owned addresses, Orders authorization, Swagger, Docker and CI follow in
separate branches after review and squash merge. Docker execution is not
claimed because the local engine was unavailable. The unrelated existing Auth
lockfile change is excluded. No production data migration was executed.
