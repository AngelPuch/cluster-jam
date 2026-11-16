# Cluster JAM Catalog Service

Spring Boot service for catalog and inventory. It provides health checks,
an OpenAPI contract, correlated JSON request logs and stateless authorization.
Flyway versions the PostgreSQL catalog schema and its reference data.

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

    $env:CATALOG_VERIFY_POSTGRES = 'true'
    try {
        .\mvnw.cmd clean verify
        if ($LASTEXITCODE -ne 0) { throw 'Catalog verification failed.' }
    } finally {
        Remove-Item Env:CATALOG_VERIFY_POSTGRES -ErrorAction SilentlyContinue
    }
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
tables and indexes. V2 seeds reference data. Use new versioned files for
changes to deployed schemas. The optional local fixture lives in
src/test/resources/fixtures/catalog-demo.sql.

Run Maven verify alone for the HTTP and contract checks without a database.
The ready-success HTTP test is enabled by CATALOG_VERIFY_POSTGRES after
the migrations have run.

To stop the local database and preserve its data:

    docker compose --env-file .env -f ../../infra/catalog/compose.yaml stop db-catalogo

The API leaves its HTTP listener available while PostgreSQL is unavailable.
Readiness checks versions 1 and 2 on each request and recovers when the
database and history are accessible. Flyway validate verifies checksums.
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
uses catalog:read and catalog:reserve. Personalization uses
catalog:compatibility. The same subject can receive multiple allowed scopes.
Catalog validates service credentials issued by that provider.

In local development, an unset issuer leaves that credential type unavailable.
Set SUPABASE_URL for staging and production. Docs are enabled locally with
CATALOG_DOCS_ENABLED=true. Set CATALOG_WRITES_PER_MINUTE or
CATALOG_MAX_JSON_BYTES to change the per-instance write quota or JSON limit.

## Update the OpenAPI snapshot

Run from this service directory on Windows:

    .\mvnw.cmd "-Dtest=CatalogOpenApiContractTest" "-Dcatalog.openapi.write=true" test
    .\mvnw.cmd clean verify

Commit the generated contracts/openapi/catalog/v1/openapi.json from the
monorepo root. The standard verification detects drift against the snapshot.
