# Cluster JAM Catalog Service

Spring Boot service for catalog and inventory. This version exposes health
checks, an OpenAPI contract and correlated JSON request logs.

## Build and run

Use JDK 21 and the included Maven Wrapper.

On Windows PowerShell:

    .\mvnw.cmd clean verify
    $env:CATALOG_DOCS_ENABLED = 'true'
    .\mvnw.cmd spring-boot:run

On Linux or macOS:

    ./mvnw clean verify
    CATALOG_DOCS_ENABLED=true ./mvnw spring-boot:run

The default base URL is http://127.0.0.1:8083.

| Endpoint | Result |
| --- | --- |
| GET /health/live | 200 and status ok when the HTTP process responds |
| GET /health/ready | 200 and status ok, or 503 with Problem Details |
| GET /docs | Swagger UI when CATALOG_DOCS_ENABLED is true |
| GET /openapi.json | OpenAPI JSON when CATALOG_DOCS_ENABLED is true |

Set APP_ENV, HTTP_ADDRESS or HTTP_PORT to override the local defaults.
Set CATALOG_READINESS_AVAILABLE=false and restart to simulate a dependency
failure. The initial probe reads this setting. A later branch will connect
it to PostgreSQL and schema checks.

The .env.example file documents the variables. Set them in the shell or the
IDE run configuration. Errors carry traceId when the request enters the HTTP
filter. Match it to X-Trace-Id and the trace_id in the request log. Use
X-Request-Id to locate one request within a trace.

## Update the OpenAPI snapshot

Run from this service directory on Windows:

    .\mvnw.cmd "-Dtest=CatalogOpenApiContractTest" "-Dcatalog.openapi.write=true" test
    .\mvnw.cmd clean verify

On Linux or macOS:

    ./mvnw -Dtest=CatalogOpenApiContractTest -Dcatalog.openapi.write=true test
    ./mvnw clean verify

Commit the generated contracts/openapi/catalog/v1/openapi.json from the
monorepo root. The standard verification detects drift against the snapshot.
