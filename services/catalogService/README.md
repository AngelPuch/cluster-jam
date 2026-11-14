# Cluster JAM Catalog Service

Spring Boot service for catalog and inventory. The bootstrap exposes process
liveness and configurable readiness.

## Build and run

Use JDK 21 and the included Maven Wrapper.

On Windows PowerShell:

    .\mvnw.cmd clean verify
    .\mvnw.cmd spring-boot:run

On Linux or macOS:

    ./mvnw clean verify
    ./mvnw spring-boot:run

The default base URL is http://127.0.0.1:8083.

| Endpoint | Result |
| --- | --- |
| GET /health/live | 200 with status ok when the HTTP process responds |
| GET /health/ready | 200 with status ok or 503 with status unavailable |

Set APP_ENV, HTTP_ADDRESS or HTTP_PORT to override the local defaults.
Set CATALOG_READINESS_AVAILABLE=false before starting the application to
simulate a dependency failure. Restart after a change. The initial probe uses
this setting. A later branch will connect it to PostgreSQL and schema checks.

The .env.example file documents the variables. Set them in the shell or the
IDE run configuration.
