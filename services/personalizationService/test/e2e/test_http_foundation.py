"""Exercise HTTP readiness, errors, and trace correlation."""

import json
from concurrent.futures import ThreadPoolExecutor
from io import StringIO
from typing import Protocol, cast

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from personalization.interfaces.http.dto.health_response import HealthResponse
from personalization.interfaces.http.dto.rest_model import RestModel

TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736"
PARENT_SPAN_ID = "00f067aa0ba902b7"
TRACEPARENT = f"00-{TRACE_ID}-{PARENT_SPAN_ID}-01"


class ReadinessControl(Protocol):
    ready: bool
    calls: int


@pytest.mark.e2e
def test_health_and_contract(client: TestClient) -> None:
    assert client.get("/health/live").json() == {"status": "ok"}
    assert client.get("/health/ready").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    document = client.get("/openapi.json").json()
    assert "/api/v1/health/live" not in document["paths"]
    problem = document["components"]["schemas"]["ProblemDetails"]
    assert "traceId" in problem["required"]
    assert "trace_id" not in problem["properties"]
    content = document["paths"]["/health/ready"]["get"]["responses"]["503"]
    assert set(content["content"]) == {"application/problem+json"}


@pytest.mark.e2e
def test_liveness_is_independent_and_readiness_recovers(
    client: TestClient, readiness_port: ReadinessControl
) -> None:
    readiness_port.ready = False
    assert client.get("/health/live").status_code == 200
    assert readiness_port.calls == 0
    response = client.get("/health/ready")
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_NOT_READY"
    assert readiness_port.calls == 1
    readiness_port.ready = True
    assert client.get("/health/ready").status_code == 200


@pytest.mark.e2e
def test_valid_parent_correlates_response_and_log(
    client: TestClient, http_logs: StringIO
) -> None:
    http_logs.seek(0)
    http_logs.truncate(0)
    response = client.get(
        "/api/v1/missing?token=private-query",
        headers={
            "traceparent": TRACEPARENT,
            "Authorization": "Bearer private",
        },
    )
    problem = response.json()
    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert problem["traceId"] == TRACE_ID
    assert problem["instance"] == "/api/v1/missing"
    parent = response.headers["traceparent"].split("-")
    assert parent[1] == TRACE_ID
    assert parent[2] != PARENT_SPAN_ID
    output = http_logs.getvalue()
    events = [json.loads(line) for line in output.splitlines()]
    assert len(events) == 1
    assert events[0]["trace_id"] == TRACE_ID
    assert events[0]["span_id"] == parent[2]
    assert events[0]["http_route"] == "unmatched"
    assert "private" not in output


@pytest.mark.e2e
@pytest.mark.parametrize(
    "traceparent",
    [
        "invalid",
        "00-" + "0" * 32 + "-" + PARENT_SPAN_ID + "-01",
        "00-" + TRACE_ID + "-" + "0" * 16 + "-01",
    ],
)
def test_invalid_trace_context_creates_a_valid_trace(
    client: TestClient, traceparent: str
) -> None:
    response = client.get(
        "/api/v1/missing", headers={"traceparent": traceparent}
    )
    trace_id = response.json()["traceId"]
    assert len(trace_id) == 32
    assert int(trace_id, 16) > 0
    assert response.headers["traceparent"].split("-")[1] == trace_id


@pytest.mark.e2e
def test_requests_have_independent_contexts(client: TestClient) -> None:
    def request_trace(index: int) -> str:
        return str(client.get(f"/api/v1/missing-{index}").json()["traceId"])

    with ThreadPoolExecutor(max_workers=2) as pool:
        traces = list(pool.map(request_trace, range(2)))
    assert len(set(traces)) == 2


@pytest.mark.e2e
def test_method_errors_preserve_allow_header(client: TestClient) -> None:
    response = client.post("/health/live")
    assert response.status_code == 405
    assert "GET" in response.headers["allow"]
    assert response.json()["code"] == "METHOD_NOT_ALLOWED"


@pytest.mark.e2e
def test_protocol_errors_preserve_authentication_headers(
    client: TestClient,
) -> None:
    app = cast(FastAPI, client.app)

    @app.get("/api/v1/test-auth")
    def reject_request() -> None:
        raise HTTPException(401, headers={"WWW-Authenticate": "Bearer"})

    response = client.get("/api/v1/test-auth")
    assert response.status_code == 401
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["code"] == "UNAUTHORIZED"


@pytest.mark.e2e
def test_validation_errors_never_echo_input(
    client: TestClient, http_logs: StringIO
) -> None:
    class TestInput(RestModel):
        image_width: int

    app = cast(FastAPI, client.app)

    @app.post("/api/v1/test-input")
    def validate_input(payload: TestInput) -> TestInput:
        return payload

    http_logs.seek(0)
    http_logs.truncate(0)
    invalid = client.post(
        "/api/v1/test-input", json={"imageWidth": "private-input"}
    )
    assert invalid.status_code == 422
    assert invalid.json()["code"] == "VALIDATION_ERROR"
    malformed = client.post(
        "/api/v1/test-input",
        content="{private-invalid-json",
        headers={"Content-Type": "application/json"},
    )
    assert malformed.status_code == 400
    assert malformed.json()["code"] == "BAD_REQUEST"
    assert "private" not in invalid.text + malformed.text
    assert "private" not in http_logs.getvalue()
    valid = client.post("/api/v1/test-input", json={"imageWidth": 100})
    assert valid.json() == {"imageWidth": 100}


@pytest.mark.e2e
def test_unexpected_exception_is_sanitized_and_logged_once(
    client: TestClient, http_logs: StringIO
) -> None:
    app = cast(FastAPI, client.app)

    @app.get("/api/v1/test-failure")
    def fail_request() -> None:
        raise RuntimeError("SELECT password FROM private-database")

    http_logs.seek(0)
    http_logs.truncate(0)
    response = client.get("/api/v1/test-failure")
    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_SERVER_ERROR"
    output = http_logs.getvalue()
    events = [json.loads(line) for line in output.splitlines()]
    assert len(events) == 1
    assert events[0]["level"] == "ERROR"
    assert events[0]["error_type"] == "RuntimeError"
    assert "private-database" not in output + response.text
    assert "SELECT" not in output + response.text


@pytest.mark.e2e
def test_invalid_response_becomes_a_safe_server_error(
    client: TestClient,
) -> None:
    app = cast(FastAPI, client.app)

    @app.get("/api/v1/test-response", response_model=HealthResponse)
    def invalid_response() -> dict[str, str]:
        return {"status": "private-response"}

    response = client.get("/api/v1/test-response")
    assert response.status_code == 500
    assert "private-response" not in response.text


@pytest.mark.e2e
def test_successful_health_probes_do_not_generate_request_logs(
    client: TestClient, http_logs: StringIO
) -> None:
    http_logs.seek(0)
    http_logs.truncate(0)
    client.get("/health/live")
    client.get("/health/ready")
    assert http_logs.getvalue() == ""
