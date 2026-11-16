# Cluster JAM Catalog Service

Spring Boot service for catalog and inventory. This version exposes health
checks, an OpenAPI contract, correlated JSON request logs and stateless
authorization for future catalog routes.

## Build and run

Use JDK 21 and the included Maven Wrapper.

On Windows PowerShell:

    .\mvnw.cmd clean verify
    $env:CATALOG_DOCS_ENABLED = 'true'
    .\mvnw.cmd spring-boot:run

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
