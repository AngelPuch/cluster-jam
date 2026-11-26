# Cluster JAM Catalog Service

Spring Boot service for catalog and inventory. It provides health checks,
an OpenAPI contract, correlated JSON request logs and stateless authorization.
Flyway versions the PostgreSQL catalog schema and its reference data.
Catalog administrators can manage products, variants, prices and publication.
Spring Data JPA and Hibernate persist the catalog and enforce optimistic
revisions. The readiness check reads the Flyway history through JDBC.

## Build and run

Use JDK 21 and the included Maven Wrapper. For local PostgreSQL, start
Docker Desktop and run the following commands from this service directory
in PowerShell 7. Copy .env.example to .env and fill the three database
passwords with distinct local values. Use unquoted values, for example
random hexadecimal strings. Keep .env out of Git.

    docker compose --env-file .env -f ../../infra/catalog/compose.yaml up -d --wait
    foreach ($line in Get-Content -LiteralPath .env) {
        if ($line -match '^([A-Z][A-Z0-9_]*)=(.*)$') {
            [Environment]::SetEnvironmentVariable($Matches[1], $Matches[2], 'Process')
        }
    }

Apply the migrations explicitly as migrator_catalogo. The API runs as app_catalogo.

    $env:FLYWAY_URL = $env:CATALOG_DB_URL
    $env:FLYWAY_USER = 'migrator_catalogo'
    $env:FLYWAY_PASSWORD = $env:CATALOG_MIGRATION_PASSWORD
    try {
        .\mvnw.cmd -B flyway:migrate flyway:validate flyway:info
        if ($LASTEXITCODE -ne 0) { throw 'Catalog migrations failed.' }
    } finally {
        Remove-Item Env:FLYWAY_URL, Env:FLYWAY_USER, Env:FLYWAY_PASSWORD, Env:CATALOG_MIGRATION_PASSWORD, Env:CATALOG_POSTGRES_ADMIN_PASSWORD -ErrorAction SilentlyContinue
    }

    .\mvnw.cmd clean verify
    .\mvnw.cmd spring-boot:run

The default base URL is http://127.0.0.1:8083.

| Endpoint | Result |
| --- | --- |
| GET /health/live | 200 and status ok when the HTTP process responds |
| GET /health/ready | 200 when PostgreSQL and the expected Flyway history are available, otherwise 503 with Problem Details |
| GET /docs | Swagger UI when CATALOG_DOCS_ENABLED is true |
| GET /openapi.json | OpenAPI JSON when CATALOG_DOCS_ENABLED is true |

Set APP_ENV, HTTP_ADDRESS or HTTP_PORT to override the local defaults.
CATALOG_DB_URL, CATALOG_DB_USER and CATALOG_DB_PASSWORD configure the API
connection. The local database listens on 127.0.0.1:5436. Use a trusted
PostgreSQL server and certificate verification with sslmode=verify-full
outside local development.

The bootstrap script runs when the PostgreSQL volume is first initialized.
From this module, migrations live in
src/main/java/com/clusterjam/catalog/infrastructure/database/migrations.
Flyway resolves that directory from the module's pom.xml and runs from the
checkout before the application JAR is deployed. V1 creates the catalog
tables and indexes. V2 seeds reference data. V3 adds the local admin audit
and the initial write permissions. V4 grants Hibernate the insert columns
it needs for generated identifiers and revision values. Use new versioned
files for changes to deployed schemas.

Run Maven verify for the standard HTTP and contract checks. For the admin
integration tests, set CATALOG_VERIFY_POSTGRES=true and load the database
environment for a migrated development or test database. The tests send
requests through the API as app_catalogo and use CATALOG_MIGRATION_PASSWORD
with migrator_catalogo to inspect the inventory and audit rows. Hibernate
validates its mappings against that database during the integration run. The test
requests create sample records. Clear the test flag and migration password
before launching the API.

To stop the local database and preserve its data:

    docker compose --env-file .env -f ../../infra/catalog/compose.yaml stop db-catalogo

The API leaves its HTTP listener available while PostgreSQL is unavailable.
Readiness checks versions 1 through 10 on each request and recovers when the
database and history are accessible. Flyway validate verifies checksums.
The application starts with Hibernate DDL generation disabled and checks
database availability through readiness.
The connection pool allows up to eight connections and waits up to 1 s
for one. The API role has a 500 ms lock limit and 1.5 s statement limit.

The .env.example file documents the variables. Set them in the shell or the
IDE run configuration. Errors carry traceId when the request enters the HTTP
filter. Match it to X-Trace-Id and the trace_id in the request log. Use
X-Request-Id to locate one request within a trace.

## Authentication and authorization

Set SUPABASE_URL to the same project origin used by Auth. Catalog derives the
issuer and public JWKS URL. Use Auth's accessToken as a Bearer credential.
Catalog supports Supabase's asymmetric ES256 and RS256 keys. Human roles
come from app_metadata.app_role. Public health checks remain anonymous.

Set SERVICE_JWT_ISSUER when a dedicated service issuer is available.
It must publish public keys at its /.well-known/jwks.json. Internal requests
require audience catalog-service and a permitted subject and scope. Orders
uses catalog:read for internal reads. Reservation writes use AMQP. Personalization uses
catalog:compatibility. The same subject can receive multiple allowed scopes.
Catalog validates service credentials issued by that provider.

In local development, an unset issuer leaves that credential type unavailable.
Set SUPABASE_URL for staging and production. Docs are enabled locally with
CATALOG_DOCS_ENABLED=true. Set CATALOG_WRITES_PER_MINUTE or
CATALOG_MAX_JSON_BYTES to change the per-instance write quota or JSON limit.

## Manage products and variants

Use an administrator Bearer token with /api/v1/admin/products and its nested
/{productId}/variants resource. GET lists results with limit and after, POST
creates a draft, and PATCH on an item edits its fields or changes its status.
Read the item's ETag and send it verbatim as If-Match on PATCH.

Use DRAFT, PUBLISHED or RETIRED. Publication and retirement preserve the
resource IDs. A variant has a fixed SKU, size and color and an editable price
in MXN cents. Variant creation initializes the inventory and records the
admin audit in the same transaction.

## Product photos

Administrative photos use /api/v1/admin/products/{productId}/colors/{colorId}/photos/{side},
with FRONT or BACK. PUT accepts a single multipart file part. Use
If-None-Match: * for a new slot or the current If-Match ETag for replacement.
GET returns metadata. DELETE retires the slot with If-Match. POST /links
issues private read links for an active photo for 60 seconds.

Configure CATALOG_PHOTOS_BUCKET and CATALOG_STORAGE_KEY in the server
environment. Use a private catalog-only Supabase bucket limited to
10,000,000 bytes and image/png. Inputs may be PNG or JPEG. The API validates
image signatures and dimensions, re-encodes PNG and generates a thumbnail.
Inputs are limited to 8192 pixels per side and 16 million pixels in total.

Apply V5 before starting this binary. Photo metadata, audit and cleanup
tasks use PostgreSQL. A pending task is persisted before upload and is
locked during the upload and the final reference change. Failed uploads
are eligible for cleanup after one hour. Replaced or retired objects are
eligible after five minutes. The worker checks active references before
deleting a pair and retries failures in later cycles. Its delay defaults
to 60000 ms through CATALOG_PHOTO_CLEANUP_DELAY_MS.

The photo integration scenarios run with CATALOG_VERIFY_POSTGRES=true
against a migrated test database and a fake Storage provider. Manually
verify upload, signed links and retirement with a development bucket.

## Read catalog and compatibility

GET /api/v1/products lists published products using name, typeId, sizeId,
colorId, minPriceCents, maxPriceCents, limit and cursor. Variant filters
match one published variant. Prices use integer MXN cents. Lists use UUID
order and a signed cursor bound to the normalized filters and page size.
Set CATALOG_CURSOR_KEY to a stable random Base64 value of at least 32 bytes.

GET /api/v1/products/{productId} includes one page of published variants,
their available quantities and photo references for the colors on that
page. Photo links are issued on GET of the returned linksPath after checking
publication. Text reads are independent of Storage availability.
GET /api/v1/catalog/references returns the migration-maintained types,
sizes and colors.

Internal reads use /api/v1/internal/variants/{variantId} and
/api/v1/internal/products/{productId}/sizes/{sizeId}. A known but retired
reference returns its states with published/compatible=false. An unknown
association returns 404. Personalization requires catalog:compatibility;
Orders uses catalog:read and receives the commerce section with price and
availableQuantity. Catálogo verifies the service issuer and catalog-service
audience even when the request arrives through the gateway.

Apply V6 for the reference and inventory read permissions. The shared
gateway routes to the clusterjam-catalog:8083 alias on its backend network.
For direct local HTTP use 127.0.0.1:8083 and real user tokens from Auth.
The local Nginx configuration and CatalogDevIdentity described in the
branch-7 handoff are not tracked in the main revision used for branch 8.

The two catalog read integration tests run with CATALOG_VERIFY_POSTGRES=true.
Keep CATALOG_NGINX_EXE unset for this checkout's direct HTTP checks. The
tests verify signed JWTs, database queries and cursor behavior.

## Inventory adjustments

Apply V7 before starting this binary. Only human administrators may use
/api/v1/admin/variants/{variantId}/inventory. GET returns physicalQuantity,
reservedQuantity, availableQuantity and version. Available is physical
minus reserved, including for draft or retired variants.

POST /adjustments accepts an integer quantityDelta from -1000000 through
1000000, excluding zero, and a nonblank reason of at most 200 characters
without control or format characters. Leading and trailing whitespace in
reason is stripped. Actor identity comes from the validated user JWT.
Physical stock cannot fall below reserved stock. The request never changes
reserved stock, product publication or price.

Send one UUID Idempotency-Key per administrator action and keep it for all
retries. Keys are scoped to actor and ADJUST_INVENTORY_V1. The SHA-256 input
is variant UUID, newline, integer delta, newline, normalized reason in UTF-8.
A successful result is retained with its movement without automatic expiry.
Reusing the key with different content returns 409. Another administrator
has an independent namespace. Failed transactions do not consume a key.

The first request and identical retries return 201, the same Location and
historical movement. Idempotency-Replayed distinguishes a replay. Read GET
on the inventory resource for the current balance after later operations.
GET /movements lists immutable administrative movements by ascending
inventory version, with limit 1..100 and afterVersion (initially 0). Follow
nextAfterVersion when non-null. GET /movements/{movementId} scopes the
lookup to the variant.

InventoryService owns the transaction; InventoryJdbcStore uses the same
DataSource and Spring transaction as JPA with parameterized PostgreSQL
statements. INSERT ON CONFLICT serializes equal keys and SELECT FOR UPDATE
serializes inventory writes. Stock, movement and key commit together; the
deferred movement FK prevents committing an incomplete idempotency claim.
app_catalogo can append and read movements/keys. Adjustments change physical
stock and reservations change reserved stock, with the same inventory revision. It cannot edit or delete history.
Lock or database unavailability returns 503; retry with the same key.

InventoryAdminHttpTest adds three PostgreSQL HTTP tests for permissions,
validation, historical replay, key conflict, reserved stock and concurrency.
The decoder override exists only in test sources; Postman uses real Auth
credentials. The shared Nginx route also forwards /api/v1/admin/variants.

## Update the OpenAPI snapshot

Run from this service directory on Windows:

    .\mvnw.cmd "-Dtest=CatalogOpenApiContractTest" "-Dcatalog.openapi.write=true" test
    .\mvnw.cmd clean verify

Commit the generated contracts/openapi/catalog/v1/openapi.json from the
monorepo root. The standard verification detects drift against the snapshot.

## Reserve stock, complete its lifecycle and publish results (branches 9-11)

Apply V8, V9 and V10 and provision the existing local broker with
infra/rabbitmq/provision-catalog-local.py. The process uses the catalog-consumer
account; the local smoke test uses orders-test-publisher.
Set CATALOG_MESSAGING_ENABLED=true only after provisioning and migration.
The loopback development broker uses port 5672 and TLS=false.
Staging uses its existing AMQPS configuration and trusted certificates.

Catalog consumes reserve-stock, confirm-reservation, release-reservation and
consume-stock commands from catalog.commands.v1. Its type is the full
routing key; the common envelope has messageId, type, orderId, occurredAt and data.
See contracts/events/catalog-reservations.v1.md from the monorepo root.

ReservationService owns the local transaction. The inbox key deduplicates
messages and its operation/order unique constraint protects one purchase from
being executed again under another message ID. The consumer name identifies
the operation, not a shared queue. Rejected orders have inbox and outbox records
without a reservation row. Physical stock stays unchanged.
Product/variant share locks stabilize publication and price; ordered inventory
update locks protect availability. Database wall time is checked after locking.
The retained basket expires fifteen minutes after its creation.

The consumer uses manual acknowledgements after commit, prefetch 1 and up to
three technical attempts in memory. Invalid input or exhausted attempts are
rejected without requeue. RabbitMQ routes them through the native DLX/DLQ.
There are no message hashes, SQL quarantine, durable failure counters or
AMQP status queries. The runtime does not configure broker resources.
Readiness still checks database/migrations; check the queue consumer in RabbitMQ.

ReservationMessageReaderTest checks ordinary JSON/ISO-8601 and basic domain data.
ReservationCommandConsumerTest checks ACK order and the bounded rejection path.
ReservationStockTest has three PostgreSQL tests for order/message idempotency,
whole-basket rejection and competing buyers for the last unit.
ReservationRabbitTest adds one optional live-broker smoke test.
Set CATALOG_VERIFY_POSTGRES=true for database tests and
CATALOG_VERIFY_RABBITMQ=true for the loopback broker test.
Both require a migrated test/development database and fixture migrator password.
The broker test also needs CATALOG_TEST_ORDERS_PASSWORD.
Clear test flags and migration/admin credentials before launching the API.

Results are committed as PENDING in app.outbox_catalogo. The publisher marks them
PUBLISHED only after a positive broker confirm without a returned message.
Branch 10 supplies confirmation, release, production consumption and an expiration
worker with a 30-second delay and at most ten separate transactions per pass.
Branch 11 supplies the periodic outbox publisher with confirms/mandatory.
Orders/Payments must still be integrated to complete a checkout across services.

The pivot is ACTIVA -> CONFIRMADA under the reservation row lock and the
PostgreSQL wall clock. Confirmation keeps physical/reserved stock unchanged;
production consumption removes both quantities once. Release and expiration
remove only reserved stock. All inventory locks use variant order.

V9 adds payment_id and ultimo_evento_id to real reservations. The payment
reference is not a foreign key to another service. The last-event link lets a
late confirmation or release retain the already recorded terminal evidence,
without generating another event or fake success. Inbox and the last-event FK
are checked in the same commit as the state/stock/outbox changes.

Unknown/foreign reservations, contradictory payment identity and inadmissible
production/release states are invalid operations. They roll back and are
rejected without requeue to the native DLQ, rather than claiming that a
reservation was released. A message already handled by inbox has no new effect.

The expiration worker uses the existing scheduling configuration from the photo
feature. CATALOG_RESERVATION_EXPIRATION_ENABLED defaults to true; turn it off
only while running deterministic integration tests. It works independently of
RabbitMQ availability and leaves expiration results in outbox.
ReservationLifecycleReaderTest adds one DTO test.
ReservationLifecycleTest adds five PostgreSQL scenarios, including wall time
after waiting for a row lock. The existing live RabbitMQ smoke test now also
confirms and consumes with repeated deliveries.

## Publish the catalog outbox (branch 11)

Apply V10, provision RabbitMQ and set CATALOG_OUTBOX_PUBLISHER_ENABLED=true.
This flag is independent of CATALOG_MESSAGING_ENABLED and defaults to false.
The broker does not scan the database: CatalogOutboxWorker polls every five
seconds and processes up to ten rows. Only one service instance/publisher is
part of this project deployment.

Each publishNext call owns a separate technical SQL transaction. It selects the
oldest pending row with LIMIT 1 FOR NO KEY UPDATE SKIP LOCKED, publishes
persistent JSON, waits up to three seconds for a correlated publisher confirm,
checks that no mandatory return was received, then updates estado/publicado_en.
The row lock is retained until commit. This lock mode still excludes competing
writers while allowing the key-share reads used by the existing outbox FKs.
Only outbox rows are selected/updated by this transaction.

AMQP message_id stays equal to the outbox ID, correlation_id is orderId and
type is the routing key. The JSON body is read from the committed JSONB value.
CorrelationData belongs to Spring's per-publication confirmation mechanism;
it does not change the event ID or add a saga attempt.

A nack, missing route, unavailable connection or missing confirm leaves the
row pending. The worker stops that pass and retries in a later cycle.
Successful earlier rows in the pass have already committed.
If publication succeeds but the SQL commit fails, the same message may be
sent again. Consumers must retain their inbox idempotency.

PUBLISHED means routed and acknowledged by RabbitMQ. It does not mean that
Orders processed the event or that the purchase completed.
Publishing failures stay in outbox; the existing native DLQ is for rejected
consumer deliveries. Neither creates a SQL quarantine or error exchange.
Readiness still checks PostgreSQL and migrations, not broker delivery.

The local provisioning script also creates catalog-publisher-test. It can
create/read only temporary catalog.publisher.test.* queues and bind them to
catalog.events. It cannot publish catalog events or consume Orders' queue.
Set CATALOG_TEST_OUTBOX_PASSWORD only for the local broker integration tests.
Never run the application with a test/admin account.

RabbitMqCatalogEventPublisherTest adds two unit tests.
OutboxPublicationTest adds one PostgreSQL test for locking, rollback and retry.
OutboxRabbitTest adds two local broker tests for confirms/returns and recovery
after an unavailable connection. It uses exclusive temporary observer queues
and cleans up only the outbox fixtures it created.
The failure probe uses a closed loopback port; it does not stop the shared broker.
Existing reservation integration tests explicitly keep the publisher disabled.

Set CATALOG_VERIFY_POSTGRES=true and CATALOG_VERIFY_RABBITMQ=true for the
essential integration run. It needs the usual migration password plus
CATALOG_TEST_ORDERS_PASSWORD and CATALOG_TEST_OUTBOX_PASSWORD.
Turn scheduled expiration/publication off during deterministic tests; clear
test/admin/migration credentials before starting the application.
