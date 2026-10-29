"""Verify real HTTPS routing using only disposable Docker resources."""

import http.client
import json
import os
import secrets
import shutil
import ssl
import subprocess
import tempfile
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]
DIRECTORY = ROOT / "infra" / "personalization"
TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
TRACEPARENT = f"00-{TRACE_ID}-00f067aa0ba902b7-01"


def run(
    arguments: list[str], environment: dict[str, str], *, capture: bool = False
) -> str:
    result = subprocess.run(
        arguments,
        env=environment,
        check=True,
        text=True,
        capture_output=capture,
        timeout=900,
    )
    return result.stdout.strip() if capture else ""


def compose_model(
    files: list[str], environment: dict[str, str], empty_env: Path
) -> dict[str, Any]:
    arguments = ["docker", "compose", "--env-file", str(empty_env)]
    for name in files:
        arguments.extend(["-f", str(DIRECTORY / name)])
    value = json.loads(
        run(
            [
                *arguments,
                "--profile",
                "tools",
                "--profile",
                "rpc",
                "--profile",
                "images",
                "config",
                "--format",
                "json",
            ],
            environment,
            capture=True,
        )
    )
    if not isinstance(value, dict):
        raise TypeError("Compose must produce a JSON object")
    return value


def verify_deployment_model(model: dict[str, Any]) -> None:
    services = model["services"]
    for name, service in services.items():
        if service.get("ports"):
            raise RuntimeError("Deployment must not publish service ports")
        if name not in {"db-personalizacion", "personalization-db-test"}:
            if service["environment"]["APP_ENV"] != "production":
                raise RuntimeError("Deployment must use production settings")
            if service.get("pull_policy") != "never":
                raise RuntimeError("Deployment must use the built release")
    backend = model["networks"]["backend"]
    if not backend["external"] or backend["name"] != "cluster-jam-backend":
        raise RuntimeError("Deployment must join the shared backend")
    private = model["networks"]["personalization-db"]
    if not private["internal"]:
        raise RuntimeError("The database network must stay private")
    rpc_secrets = {
        value["source"]
        for value in services["personalization-grpc"]["secrets"]
    }
    if "supabase_storage_key" in rpc_secrets:
        raise RuntimeError("RPC must not receive the Storage backend key")
    if (
        not model["secrets"]["grpc_trusted_ca"]["file"]
        .replace("\\", "/")
        .endswith("/shared/.pki/ca.crt")
    ):
        raise RuntimeError("Deployment RPC must trust the staging CA")
    print("Deployment model: production, release, private DB and RPC TLS OK")


def certificate_fixture(directory: Path, environment: dict[str, str]) -> None:
    executable = shutil.which("openssl")
    if executable is None:
        raise RuntimeError("OpenSSL is required for the HTTPS verification")
    arguments = [
        executable,
        "req",
        "-x509",
        "-newkey",
        "rsa:2048",
        "-nodes",
        "-days",
        "1",
        "-subj",
        "/CN=localhost",
        "-addext",
        "subjectAltName=DNS:localhost,IP:127.0.0.1",
        "-keyout",
        str(directory / "https.key"),
        "-out",
        str(directory / "https.crt"),
    ]
    # Generate only temporary test certificates and keys.
    run(arguments, environment, capture=True)
    for name in ("https.key", "https.crt"):
        (directory / name).chmod(0o444)


def request(
    port: int,
    trust: Path,
    path: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: bytes | None = None,
) -> tuple[int, dict[str, str], object]:
    context = ssl.create_default_context(cafile=str(trust))
    connection = http.client.HTTPSConnection(
        "127.0.0.1", port, context=context, timeout=20
    )
    try:
        connection.request(method, path, body=body, headers=headers or {})
        response = connection.getresponse()
        payload = response.read()
        return (
            response.status,
            {name.lower(): value for name, value in response.getheaders()},
            json.loads(payload),
        )
    finally:
        connection.close()


def expect_problem(
    response: tuple[int, dict[str, str], object], status: int, code: str
) -> None:
    actual, headers, payload = response
    if actual != status or not isinstance(payload, dict):
        raise RuntimeError("Unexpected HTTPS error status or body")
    if headers["content-type"] != "application/problem+json":
        raise RuntimeError("HTTPS errors must retain Problem Details")
    if (
        set(payload)
        != {"type", "title", "status", "detail", "instance", "code", "traceId"}
        or payload["code"] != code
    ):
        raise RuntimeError("HTTPS error contract differs from its source")


def verify_requests(
    compose: list[str], environment: dict[str, str], port: int, trust: Path
) -> None:
    def command(*arguments: str, capture: bool = False) -> str:
        return run([*compose, *arguments], environment, capture=capture)

    for path in (
        "/health/personalization/live",
        "/health/personalization/ready",
    ):
        if request(port, trust, path)[0] != 200:
            raise RuntimeError("HTTPS must route service health checks")
    contract = request(port, trust, "/openapi/personalization.json")
    if contract[0] != 200 or not isinstance(contract[2], dict):
        raise RuntimeError("HTTPS must route the Personalization contract")
    if "/api/v1/admin/design-drafts" not in contract[2]["paths"]:
        raise RuntimeError("The proxy returned a different service contract")
    for path in (
        "/api/v1/prints",
        "/api/v1/files/00000000-0000-4000-8000-000000000099",
        "/api/v1/admin/prints",
        "/api/v1/admin/template-versions",
        "/api/v1/admin/design-drafts",
    ):
        result = request(
            port,
            trust,
            path + "?token=private-test-query",
            headers={"traceparent": TRACEPARENT},
        )
        expect_problem(result, 401, "INVALID_ACCESS_TOKEN")
        if not isinstance(result[2], dict) or result[2]["traceId"] != TRACE_ID:
            raise RuntimeError("The proxy must preserve trace correlation")
        if result[1].get("www-authenticate") != "Bearer":
            raise RuntimeError(
                "The proxy must preserve authentication headers"
            )
    result = request(
        port,
        trust,
        "/api/v1/admin/template-versions/"
        "00000000-0000-4000-8000-000000000099/design-analyses",
        method="POST",
        headers={"Content-Type": "application/json"},
        body=b"{}",
    )
    expect_problem(result, 401, "INVALID_ACCESS_TOKEN")
    # The former 64 KB gateway limit must not block multipart uploads.
    result = request(
        port,
        trust,
        "/api/v1/files",
        method="POST",
        headers={"Content-Type": "multipart/form-data; boundary=test"},
        body=b"x" * 70_000,
    )
    expect_problem(result, 401, "INVALID_ACCESS_TOKEN")
    # Verify the framing limit without sending an oversized body.
    result = request(
        port,
        trust,
        "/api/v1/files",
        method="POST",
        headers={"Content-Length": "10131073"},
    )
    expect_problem(result, 413, "REQUEST_BODY_TOO_LARGE")
    expect_problem(
        request(port, trust, "/personalization-no-such-route"),
        404,
        "ROUTE_NOT_FOUND",
    )
    # The Auth fixture tests routing with no real credentials.
    auth = request(port, trust, "/api/v1/sessions", method="POST", body=b"{}")
    if auth[0] != 200 or auth[2] != {"service": "auth-route-fixture"}:
        raise RuntimeError("The existing Auth route was changed")

    def limited_request(_index: int) -> int:
        return request(port, trust, "/api/v1/prints")[0]

    with ThreadPoolExecutor(max_workers=12) as executor:
        statuses = list(executor.map(limited_request, range(120)))
    if 429 not in statuses or any(code not in {401, 429} for code in statuses):
        raise RuntimeError("Personalization request limits must be bounded")
    command("stop", "db-personalizacion")
    if request(port, trust, "/health/personalization/live")[0] != 200:
        raise RuntimeError("Database outages must not fail liveness")
    expect_problem(
        request(port, trust, "/health/personalization/ready"),
        503,
        "SERVICE_NOT_READY",
    )
    command(
        "up", "-d", "--wait", "--wait-timeout", "120", "db-personalizacion"
    )
    if request(port, trust, "/health/personalization/ready")[0] != 200:
        raise RuntimeError("Readiness must recover after database recovery")
    command("stop", "personalization")
    expect_problem(
        request(port, trust, "/health/personalization/live"),
        503,
        "SERVICE_UNAVAILABLE",
    )
    logs = command(
        "logs", "--no-color", "--no-log-prefix", "nginx", capture=True
    )
    if "private-test-query" in logs:
        raise RuntimeError("The gateway logged private query data")
    events = [
        json.loads(line) for line in logs.splitlines() if line.startswith("{")
    ]
    if not any(event.get("trace_id") == TRACE_ID for event in events):
        raise RuntimeError("The gateway did not correlate the service trace")
    print(
        "HTTPS OK: verified TLS, health, routing, trace, JWT, 70 KB upload, "
        "413, 404, 429, Auth route, outages and log privacy"
    )


def verify_https() -> None:
    environment = dict(os.environ)
    # Isolate verification from operator overrides and .env.
    for name in tuple(environment):
        if name.startswith(("PERSONALIZATION_", "COMPOSE_", "SUPABASE_")):
            environment.pop(name)
    environment.update(
        SUPABASE_ISSUER="https://supabase.example.test/auth/v1",
        SUPABASE_JWKS_URL=(
            "https://supabase.example.test/auth/v1/.well-known/jwks.json"
        ),
        PERSONALIZATION_IMAGE_TAG=os.environ.get(
            "PERSONALIZATION_IMAGE_TAG", "0.1.0-local"
        ),
    )
    project = "personalization-https-verify-" + uuid4().hex[:12]
    with tempfile.TemporaryDirectory(prefix=project) as temporary:
        directory = Path(temporary)
        empty_env = directory / "empty.env"
        empty_env.touch()
        staging = compose_model(
            ["compose.yaml", "compose.storage.yaml", "compose.deploy.yaml"],
            environment,
            empty_env,
        )
        verify_deployment_model(staging)
        model = compose_model(
            ["compose.yaml", "compose.https.dev.yaml"], environment, empty_env
        )
        certificate_fixture(directory, environment)
        for name in ("postgres_admin_password", "personalization_db_password"):
            path = directory / name
            path.write_text(secrets.token_urlsafe(32), encoding="utf-8")
            path.chmod(0o444)
        model["services"] = {
            name: service
            for name, service in model["services"].items()
            if name
            in {
                "db-personalizacion",
                "personalization",
                "personalization-migrate",
                "nginx",
            }
        }
        model["name"] = project
        for network in model["networks"].values():
            network.pop("external", None)
            network.pop("name", None)
        model["volumes"]["personalization-data"].pop("name", None)
        model["secrets"]["personalization_db_admin_password"]["file"] = str(
            directory / "postgres_admin_password"
        )
        model["secrets"]["personalization_db_password"]["file"] = str(
            directory / "personalization_db_password"
        )
        model["secrets"]["https_key"]["file"] = str(directory / "https.key")
        model["configs"]["personalization_https_certificate"]["file"] = str(
            directory / "https.crt"
        )
        model["configs"]["personalization_https_ca"]["file"] = str(
            directory / "https.crt"
        )
        model["services"]["nginx"]["ports"] = [
            {"target": 8443, "published": "0", "host_ip": "127.0.0.1"}
        ]
        for name in ("personalization", "personalization-migrate"):
            model["services"][name]["environment"]["APP_ENV"] = "production"
        stub = (
            "from http.server import BaseHTTPRequestHandler, HTTPServer\n"
            "class Handler(BaseHTTPRequestHandler):\n"
            " def do_POST(self):\n"
            '  data=b\'{"service":"auth-route-fixture"}\'\n'
            "  self.send_response(200)\n"
            "  self.send_header('Content-Type','application/json')\n"
            "  self.send_header('Content-Length',str(len(data)))\n"
            "  self.end_headers(); self.wfile.write(data)\n"
            " def log_message(self, *args): pass\n"
            "HTTPServer(('0.0.0.0',8080),Handler).serve_forever()\n"
        )
        model["services"]["auth-route-fixture"] = {
            "image": model["services"]["personalization"]["image"],
            "command": ["python", "-c", stub],
            "networks": {"backend": {"aliases": ["clusterjam-auth"]}},
            "read_only": True,
            "cap_drop": ["ALL"],
        }
        path = directory / "compose.json"
        path.write_text(json.dumps(model), encoding="utf-8")
        compose = ["docker", "compose", "-p", project, "-f", str(path)]
        try:
            run(
                [
                    *compose,
                    "up",
                    "-d",
                    "--no-build",
                    "--wait",
                    "--wait-timeout",
                    "120",
                    "db-personalizacion",
                    "personalization",
                    "nginx",
                    "auth-route-fixture",
                ],
                environment,
            )
            run([*compose, "exec", "-T", "nginx", "nginx", "-t"], environment)
            address = run(
                [*compose, "port", "nginx", "8443"], environment, capture=True
            )
            port = int(address.rsplit(":", 1)[1])
            trust = directory / "https.crt"
            expect_problem(
                request(port, trust, "/health/personalization/ready"),
                503,
                "SERVICE_NOT_READY",
            )
            run(
                [
                    *compose,
                    "run",
                    "--rm",
                    "--no-deps",
                    "personalization-migrate",
                ],
                environment,
            )
            untrusted = http.client.HTTPSConnection(
                "127.0.0.1",
                port,
                context=ssl.create_default_context(),
                timeout=5,
            )
            try:
                untrusted.connect()
            except ssl.SSLCertVerificationError:
                pass
            else:
                raise RuntimeError("An untrusted certificate was accepted")
            finally:
                untrusted.close()
            verify_requests(compose, environment, port, trust)
        finally:
            # This UUID project owns only these disposable resources.
            run(
                [
                    *compose,
                    "--profile",
                    "tools",
                    "down",
                    "--volumes",
                    "--remove-orphans",
                ],
                environment,
            )


if __name__ == "__main__":
    verify_https()
