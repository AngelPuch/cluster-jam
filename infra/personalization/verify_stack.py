"""Verify Docker packaging, isolation, and a disposable data volume."""

import json
import os
import subprocess
import textwrap
from pathlib import Path
from uuid import uuid4


def run_command(arguments: list[str], *, capture: bool = False) -> str:
    """Run a bounded command without printing credential contents."""
    environment = dict(os.environ)
    environment["SUPABASE_ISSUER"] = "https://supabase.example.test/auth/v1"
    environment["SUPABASE_JWKS_URL"] = (
        "https://supabase.example.test/auth/v1/.well-known/jwks.json"
    )
    result = subprocess.run(
        arguments,
        check=True,
        text=True,
        capture_output=capture,
        timeout=900,
        env=environment,
    )
    return result.stdout.strip() if capture else ""


def request_http(compose: list[str], path: str) -> dict[str, object]:
    """Probe HTTP inside the container without publishing ports."""
    script = textwrap.dedent("""
        import json
        import sys
        import httpx
        response = httpx.get(
            'http://127.0.0.1:8080' + sys.argv[1],
            timeout=10, trust_env=False,
            headers={
                'traceparent':
                '00-4bf92f3577b34da6a3ce929d0e0e4736-00f067aa0ba902b7-01',
                'Authorization': 'Bearer private-test-token',
            },
        )
        print(json.dumps({
            'status': response.status_code,
            'headers': dict(response.headers),
            'body': response.json(),
        }))
    """)
    payload = json.loads(
        run_command(
            [
                *compose,
                "exec",
                "--no-TTY",
                "personalization",
                "python",
                "-c",
                script,
                path,
            ],
            capture=True,
        )
    )
    if not isinstance(payload, dict):
        raise RuntimeError("The HTTP probe must return a JSON object")
    return payload


def verify_http(compose: list[str]) -> None:
    """Check HTTP contracts, outage recovery, and log privacy."""
    if request_http(compose, "/health/live")["status"] != 200:
        raise RuntimeError("The HTTP process is not live")
    if request_http(compose, "/health/ready")["status"] != 200:
        raise RuntimeError("The HTTP process cannot access its database")
    problem = request_http(compose, "/api/v1/missing?token=private-query")
    body = problem["body"]
    headers = problem["headers"]
    if not isinstance(body, dict) or not isinstance(headers, dict):
        raise RuntimeError("The problem contract has an invalid shape")
    if problem["status"] != 404 or body["code"] != "NOT_FOUND":
        raise RuntimeError("Unknown resources must return a problem response")
    if headers["content-type"] != "application/problem+json":
        raise RuntimeError("The problem response has an incorrect media type")
    if body["traceId"] != "4bf92f3577b34da6a3ce929d0e0e4736":
        raise RuntimeError("The incoming trace was not propagated")
    contract = request_http(compose, "/openapi.json")
    document = contract["body"]
    if (
        not isinstance(document, dict)
        or "/health/live" not in document["paths"]
    ):
        raise RuntimeError("The real API must expose its OpenAPI contract")
    run_command([*compose, "stop", "db-personalizacion"])
    if request_http(compose, "/health/live")["status"] != 200:
        raise RuntimeError("A database outage must not fail liveness")
    if request_http(compose, "/health/ready")["status"] != 503:
        raise RuntimeError("A database outage must fail readiness")
    run_command(
        [
            *compose,
            "up",
            "--detach",
            "--wait",
            "--wait-timeout",
            "120",
            "db-personalizacion",
        ]
    )
    if request_http(compose, "/health/ready")["status"] != 200:
        raise RuntimeError("Readiness must recover after the database returns")
    logs = run_command(
        [
            *compose,
            "logs",
            "--no-color",
            "--no-log-prefix",
            "personalization",
        ],
        capture=True,
    )
    if "private-query" in logs or "private-test-token" in logs:
        raise RuntimeError("Request credentials appeared in application logs")
    events = [json.loads(line) for line in logs.splitlines() if line.strip()]
    for event in events:
        for field in (
            "timestamp",
            "level",
            "service_name",
            "service_version",
            "environment",
            "instance_id",
            "event",
            "message",
            "trace_id",
            "span_id",
        ):
            if field not in event:
                raise RuntimeError("An application log field is missing")
    print("HTTP, OpenAPI, readiness recovery, and JSON log checks passed")


def verify_rpc_configuration(compose: list[str]) -> None:
    """Keep the RPC backend reachable without exposing its database."""
    configuration = json.loads(
        run_command(
            [*compose, "--profile", "rpc", "config", "--format", "json"],
            capture=True,
        )
    )
    rpc = configuration["services"]["personalization-grpc"]
    if set(rpc["networks"]) != {"personalization-db", "backend"}:
        raise RuntimeError("RPC needs private database and backend networks")
    if rpc.get("ports"):
        raise RuntimeError("Base RPC must not publish a host port")
    sources = {item["source"] for item in rpc["secrets"]}
    if sources != {
        "personalization_db_password",
        "grpc_server_certificate",
        "grpc_server_key",
        "grpc_trusted_ca",
    }:
        raise RuntimeError("RPC must mount only its own required secrets")
    print("RPC networks, unpublished base port, and scoped secrets verified")


def verify_stack() -> None:
    """Delete only the temporary Compose project's test resources."""
    directory = Path(__file__).resolve().parent
    project_name = f"personalization-verify-{uuid4().hex[:12]}"
    compose = [
        "docker",
        "compose",
        "--project-name",
        project_name,
        "--file",
        str(directory / "compose.yaml"),
    ]
    run_command([*compose, "config", "--quiet"])
    verify_rpc_configuration(compose)
    run_command(
        [
            *compose,
            "--profile",
            "tools",
            "build",
            "personalization-check",
            "personalization-db-test",
        ]
    )
    try:
        run_command(
            [
                *compose,
                "up",
                "--detach",
                "--wait",
                "--wait-timeout",
                "120",
                "db-personalizacion",
                "personalization",
            ]
        )
        run_command(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "personalization-check",
            ]
        )
        if request_http(compose, "/health/live")["status"] != 200:
            raise RuntimeError("Fresh API must start without migrations")
        if request_http(compose, "/health/ready")["status"] != 503:
            raise RuntimeError("Unmigrated schema must not be ready")
        run_command(
            [*compose, "run", "--rm", "--no-deps", "personalization-db-test"]
        )
        run_command(
            [*compose, "run", "--rm", "--no-deps", "personalization-migrate"]
        )
        run_command(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "personalization-migrate",
                "python",
                "-m",
                "personalization.infrastructure.database.migrate",
                "check",
            ]
        )
        verify_http(compose)
        user_id = run_command(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "personalization-check",
                "python",
                "-c",
                "import os; print(os.getuid())",
            ],
            capture=True,
        )
        if user_id != "10001":
            raise RuntimeError("The runtime user must not be root")
        container_id = run_command(
            [
                *compose,
                "ps",
                "--quiet",
                "db-personalizacion",
            ],
            capture=True,
        )
        ports = json.loads(
            run_command(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{json .NetworkSettings.Ports}}",
                    container_id,
                ],
                capture=True,
            )
        )
        if ports.get("5432/tcp"):
            raise RuntimeError("PostgreSQL must not publish host ports")
        networks = json.loads(
            run_command(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{json .NetworkSettings.Networks}}",
                    container_id,
                ],
                capture=True,
            )
        )
        if len(networks) != 1:
            raise RuntimeError("The database needs one private network")
        network = next(iter(networks))
        internal = run_command(
            [
                "docker",
                "network",
                "inspect",
                "--format",
                "{{.Internal}}",
                network,
            ],
            capture=True,
        )
        if internal != "true":
            raise RuntimeError("The database network must be internal")
        sql_command = [
            *compose,
            "exec",
            "--no-TTY",
            "db-personalizacion",
            "psql",
            "-U",
            "postgres",
            "-d",
            "personalizacion_db",
            "--tuples-only",
            "--no-align",
            "--command",
        ]
        system_id_sql = "SELECT system_identifier FROM pg_control_system()"
        original_id = run_command([*sql_command, system_id_sql], capture=True)
        table_count = run_command(
            [
                *sql_command,
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'app'",
            ],
            capture=True,
        )
        if table_count != "10":
            raise RuntimeError("Expected nine tables and Alembic history")
        marker_id = str(uuid4())
        run_command(
            [
                *sql_command,
                "INSERT INTO app.auditoria_local "
                "(id, accion, recurso, recurso_id) VALUES "
                f"('{marker_id}', 'PERSISTENCE_TEST', "
                f"'diseno', '{marker_id}')",
            ]
        )
        run_command(
            [
                *compose,
                "up",
                "--detach",
                "--wait",
                "--wait-timeout",
                "120",
                "--force-recreate",
                "db-personalizacion",
            ]
        )
        restored_id = run_command([*sql_command, system_id_sql], capture=True)
        if not original_id or restored_id != original_id:
            raise RuntimeError("Recreation did not preserve PostgreSQL")
        marker_count = run_command(
            [
                *sql_command,
                "SELECT count(*) FROM app.auditoria_local "
                f"WHERE id = '{marker_id}'",
            ],
            capture=True,
        )
        if marker_count != "1":
            raise RuntimeError("Recreation lost migrated application data")
        if request_http(compose, "/health/ready")["status"] != 200:
            raise RuntimeError("Migrated API must recover after recreation")
        run_command(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "personalization-check",
            ]
        )
        run_command(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "personalization-migrate",
                "python",
                "-m",
                "personalization.infrastructure.database.migrate",
                "current",
            ]
        )
        print(
            "Docker checks passed: runtime user, DB access, private "
            "network, unpublished port, and volume persistence"
        )
    finally:
        # This UUID project owns only disposable test resources.
        run_command(
            [
                *compose,
                "--profile",
                "tools",
                "down",
                "--volumes",
                "--remove-orphans",
            ]
        )


if __name__ == "__main__":
    verify_stack()
