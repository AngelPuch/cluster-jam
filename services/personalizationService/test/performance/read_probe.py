"""Measure real catalog reads with local signed JWTs and PostgreSQL.

Only the opt-in infrastructure wrapper starts this fixture. It contains
no production authentication override and uses throwaway signing keys.
"""

import argparse
import http.client
import json
import logging
import math
import os
import platform
import ssl
import threading
import time
from array import array
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from uuid import UUID

import jwt
import uvicorn
from cryptography.hazmat.primitives.asymmetric import ec

from personalization.infrastructure.security.development_tls import (
    create_development_tls,
)

ISSUER = "https://localhost:8443/auth/v1"
PRINT_ID = "00000000-0000-4000-9000-000000000001"
PATHS = ("/api/v1/prints?limit=20", f"/api/v1/prints/{PRINT_ID}")


def prepare(directory: Path) -> None:
    key = ec.generate_private_key(ec.SECP256R1())
    jwk = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(key.public_key()))
    jwk.update(kid="load-fixture", alg="ES256", use="sig")
    tls = create_development_tls()
    tokens = [
        jwt.encode(
            {
                "sub": str(UUID(int=index + 1)),
                "iss": ISSUER,
                "aud": "authenticated",
                "exp": int(time.time()) + 7200,
                "role": "authenticated",
                "is_anonymous": False,
                "app_metadata": {"app_role": "cliente"},
            },
            key,
            algorithm="ES256",
            headers={"kid": "load-fixture"},
        )
        for index in range(100)
    ]
    contents = {
        "jwks.json": json.dumps({"keys": [jwk]}).encode(),
        "tokens.json": json.dumps(tokens).encode(),
        "ca.crt": tls.root_certificate,
        "server.crt": tls.server.certificate,
        "server.key": tls.server.private_key,
    }
    for name, content in contents.items():
        target = directory / name
        target.write_bytes(content)
        target.chmod(0o444)


class KeyServer(ThreadingHTTPServer):
    calls: int = 0


class KeyHandler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:
        if self.path == "/auth/v1/.well-known/jwks.json":
            KeyServer.calls += 1
            body = Path("/qa/jwks.json").read_bytes()
        elif self.path == "/fixture-count":
            body = json.dumps({"jwks_requests": KeyServer.calls}).encode()
        else:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def serve() -> None:
    server = KeyServer(("127.0.0.1", 8443), KeyHandler)
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain("/qa/server.crt", "/qa/server.key")
    server.socket = context.wrap_socket(server.socket, server_side=True)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        uvicorn.run(
            "personalization.bootstrap:create_app",
            factory=True,
            host="0.0.0.0",
            port=8080,
            workers=int(os.environ.get("HTTP_WORKERS", "1")),
            timeout_graceful_shutdown=15,
            access_log=False,
            log_config=None,
            server_header=False,
            proxy_headers=False,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def percentiles(values: array[float]) -> dict[str, float | int]:
    ordered = sorted(values)
    if not ordered:
        return {"count": 0, "p50_ms": 0.0, "p95_ms": 0.0, "max_ms": 0.0}
    return {
        "count": len(ordered),
        "p50_ms": round(ordered[math.ceil(len(ordered) * 0.50) - 1], 3),
        "p95_ms": round(ordered[math.ceil(len(ordered) * 0.95) - 1], 3),
        "max_ms": round(ordered[-1], 3),
    }


def checked_read(
    connection: http.client.HTTPConnection, path: str, token: str
) -> None:
    connection.request(
        "GET", path, headers={"Authorization": "Bearer " + token}
    )
    response = connection.getresponse()
    content = response.read(256_001)
    if response.status != 200 or len(content) > 256_000:
        raise ValueError("READ_FAILED")
    body = json.loads(content)
    if path == PATHS[0]:
        if len(body["items"]) != 20 or not body["nextCursor"]:
            raise ValueError("INVALID_CATALOG_PAGE")
        items = body["items"]
    else:
        if body["id"] != PRINT_ID:
            raise ValueError("INVALID_CATALOG_DETAIL")
        items = [body]
    if any(
        item["version"]["number"] != 3
        or item["version"]["currency"] != "MXN"
        or item["version"]["surchargeCents"] != 1237
        or item["thumbnail"]["mimeType"] != "image/png"
        for item in items
    ):
        raise ValueError("INVALID_CATALOG_DATA")


def load(
    host: str, users: int, duration: int, limit_ms: float
) -> dict[str, Any]:
    tokens: list[str] = json.loads(Path("/qa/tokens.json").read_bytes())
    warmup = http.client.HTTPConnection(host, 8080, timeout=10)
    try:
        for index in range(40):
            checked_read(warmup, PATHS[index % 2], tokens[index % users])
    finally:
        warmup.close()
    ready = threading.Barrier(users + 1)
    start = threading.Event()
    deadline = 0.0

    def actor(index: int) -> tuple[list[array[float]], int]:
        connection = http.client.HTTPConnection(host, 8080, timeout=10)
        samples = [array("d"), array("d")]
        failures = 0
        ready.wait(timeout=30)
        start.wait(timeout=30)
        turn = index % 2
        try:
            while time.perf_counter() < deadline:
                before = time.perf_counter()
                try:
                    checked_read(connection, PATHS[turn], tokens[index])
                except (
                    OSError,
                    ValueError,
                    KeyError,
                    TypeError,
                    http.client.HTTPException,
                ):
                    failures += 1
                    connection.close()
                    connection = http.client.HTTPConnection(
                        host, 8080, timeout=10
                    )
                samples[turn].append((time.perf_counter() - before) * 1000)
                turn = 1 - turn
        finally:
            connection.close()
        return samples, failures

    with ThreadPoolExecutor(max_workers=users) as executor:
        futures = [executor.submit(actor, index) for index in range(users)]
        ready.wait(timeout=30)
        started = time.perf_counter()
        deadline = started + duration
        start.set()
        results = [future.result(timeout=duration + 30) for future in futures]
    elapsed = time.perf_counter() - started
    combined = [array("d"), array("d")]
    failures = 0
    for samples, failed in results:
        failures += failed
        for index in range(2):
            combined[index].extend(samples[index])
    by_operation = {
        path: percentiles(values)
        for path, values in zip(PATHS, combined, strict=True)
    }
    total = percentiles(combined[0] + combined[1])
    passed = failures == 0 and all(
        value["count"] > 0 and value["p95_ms"] < limit_ms
        for value in by_operation.values()
    )
    return {
        "event": "qa.read_performance.completed",
        "timestamp": datetime.now(UTC).isoformat(),
        "passed": passed,
        "users": users,
        "full_rnf05_load_window": users >= 30 and duration >= 300,
        "requested_duration_seconds": duration,
        "elapsed_seconds": round(elapsed, 3),
        "think_time_seconds": 0,
        "warmup_requests_excluded": 40,
        "failure_count": failures,
        "target_p95_ms_strictly_below": limit_ms,
        "overall": total,
        "by_operation": by_operation,
        "requests_per_second": round(total["count"] / elapsed, 3),
        "scope": "Internal HTTP backend; gateway TLS/rate limits excluded",
        "identity": (
            "Distinct ES256 clients; HTTPS JWKS fixture cached locally"
        ),
        "providers": "No uploads, signed downloads, or external providers",
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("prepare", "serve", "load"))
    parser.add_argument("--directory", type=Path, default=Path("/qa"))
    parser.add_argument("--host", default="read-api")
    parser.add_argument("--users", type=int, default=30, choices=range(1, 101))
    parser.add_argument(
        "--seconds", type=int, default=300, choices=range(1, 1801)
    )
    parser.add_argument("--limit-ms", type=float, default=500)
    arguments = parser.parse_args()
    if arguments.mode == "prepare":
        prepare(arguments.directory)
    elif arguments.mode == "serve":
        serve()
    else:
        logging.disable(logging.CRITICAL)
        result = load(
            arguments.host,
            arguments.users,
            arguments.seconds,
            arguments.limit_ms,
        )
        result["generator"] = {
            "python": platform.python_version(),
            "system": platform.system(),
            "machine": platform.machine(),
            "logical_cpus": os.cpu_count(),
        }
        print(json.dumps(result))


if __name__ == "__main__":
    main()
