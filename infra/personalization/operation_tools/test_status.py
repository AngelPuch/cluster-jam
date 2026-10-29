"""Check operational failures without restarts or cascading actions."""

from typing import Any

import pytest

from . import status
from .runtime import ComposeContext, OperationError, revision


class FakeContext(ComposeContext):
    def __init__(self) -> None:
        self.command = ["personalization-compose"]
        self.gateway = ["gateway-compose"]
        self.deployment = False

    def database_id(self) -> str:
        return "fixture-database"


class PrivateStorage:
    def __init__(self, available: bool) -> None:
        self.available = available

    def ensure_private(self) -> None:
        if not self.available:
            raise OperationError("STORAGE_UNAVAILABLE")


@pytest.mark.parametrize(
    "failed", [None, "database", "storage", "worker", "rpc", "https"]
)
def test_operational_health_detects_component_failures_without_mutation(
    monkeypatch: pytest.MonkeyPatch,
    failed: str | None,
) -> None:
    commands: list[list[str]] = []

    def read_database(container: str, sql: str) -> dict[str, Any]:
        assert container == "fixture-database"
        if failed == "database":
            raise OperationError("COMMAND_FAILED")
        return {"revision": revision(), "pending_files": 2}

    def command(arguments: list[str], *, timeout: int) -> bytes:
        commands.append(arguments)
        assert "exec" in arguments
        assert not any(
            value in {"up", "stop", "down", "restart"} for value in arguments
        )
        if (
            (failed == "worker" and "personalization-worker" in arguments)
            or (failed == "rpc" and "personalization-grpc" in arguments)
            or (failed == "https" and "nginx" in arguments)
        ):
            raise OperationError("COMMAND_FAILED")
        return b""

    monkeypatch.setattr(
        status,
        "http_ready",
        lambda context, endpoint: failed != "database" or endpoint == "live",
    )
    monkeypatch.setattr(status, "psql", read_database)
    monkeypatch.setattr(
        status,
        "storage_client",
        lambda context: PrivateStorage(failed != "storage"),
    )
    monkeypatch.setattr(status, "service_running", lambda command, name: True)
    monkeypatch.setattr(status, "run", command)
    healthy, checks = status.inspect_status(
        FakeContext(),
        require_worker=True,
        require_rpc=True,
        require_https=True,
    )
    assert healthy is (failed is None)
    assert checks["rest_liveness"] == "ok"
    assert commands
    if failed is None:
        assert checks["pending_files"] == "2"


@pytest.mark.parametrize("required", [False, True])
def test_optional_services_are_reported_and_require_flags_are_enforced(
    monkeypatch: pytest.MonkeyPatch,
    required: bool,
) -> None:
    monkeypatch.setattr(status, "http_ready", lambda context, endpoint: True)
    monkeypatch.setattr(
        status,
        "psql",
        lambda container, sql: {"revision": revision(), "pending_files": 0},
    )
    monkeypatch.setattr(
        status, "storage_client", lambda context: PrivateStorage(True)
    )
    monkeypatch.setattr(
        status, "service_running", lambda command, service: False
    )
    healthy, checks = status.inspect_status(
        FakeContext(),
        require_worker=required,
        require_rpc=required,
        require_https=required,
    )
    assert healthy is not required
    assert checks["personalization-worker"] == (
        "failed" if required else "not_running_optional"
    )
