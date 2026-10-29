"""Exercise stale worker detection without dependency-based restarts."""

import json
import time
from pathlib import Path

import pytest

from personalization.interfaces.workers import health
from personalization.interfaces.workers.heartbeat import (
    WorkerHeartbeat,
    heartbeat_is_healthy,
)


def test_worker_heartbeat_is_atomic_throttled_and_removed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "health.json"
    heartbeat = WorkerHeartbeat(marker)
    monkeypatch.setattr(time, "monotonic", lambda: 100.0)
    monkeypatch.setattr(time, "time", lambda: 1000.0)
    heartbeat.pulse()
    assert heartbeat_is_healthy(marker, 180)
    original = marker.read_bytes()
    monkeypatch.setattr(time, "time", lambda: 1010.0)
    heartbeat.pulse()
    assert marker.read_bytes() == original
    heartbeat.pulse(force=True)
    assert marker.read_bytes() != original
    assert list(tmp_path.iterdir()) == [marker]
    heartbeat.close()
    assert not heartbeat_is_healthy(marker, 180)


@pytest.mark.parametrize(
    "payload",
    [
        b"not json",
        b"x" * 1025,
        b"[]",
        b"{}",
        b'{"status":"stopped","updated_at":1000}',
        b'{"status":"running","updated_at":true}',
        b'{"status":"running","updated_at":"1000"}',
        b'{"status":"running","updated_at":NaN}',
        b'{"status":"running","updated_at":Infinity}',
    ],
)
def test_corrupt_heartbeat_never_reports_healthy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    payload: bytes,
) -> None:
    monkeypatch.setattr(time, "time", lambda: 1000.0)
    marker = tmp_path / "health.json"
    marker.write_bytes(payload)
    assert not heartbeat_is_healthy(marker, 180)


@pytest.mark.parametrize(
    "timestamp,expected",
    [
        (1000, True),
        (820, True),
        (819, False),
        (1005, True),
        (1006, False),
    ],
)
def test_worker_heartbeat_detects_stalls_and_clock_skew(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    timestamp: int,
    expected: bool,
) -> None:
    monkeypatch.setattr(time, "time", lambda: 1000.0)
    marker = tmp_path / "health.json"
    marker.write_text(
        json.dumps({"status": "running", "updated_at": timestamp})
    )
    assert heartbeat_is_healthy(marker, 180) is expected


def test_worker_health_checks_allow_long_polling_without_database_calls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = tmp_path / "health.json"
    monkeypatch.setattr(time, "time", lambda: 1000.0)
    marker.write_text('{"status":"running","updated_at":200}')
    monkeypatch.setenv("WORKER_HEARTBEAT_FILE", str(marker))
    monkeypatch.setenv("WORKER_POLL_SECONDS", "300")
    monkeypatch.setenv("WORKER_HEARTBEAT_MAX_AGE_SECONDS", "180")
    assert health.main() == 0
    monkeypatch.setenv("WORKER_POLL_SECONDS", "10")
    assert health.main() == 1


@pytest.mark.parametrize(
    "name,value",
    [
        ("WORKER_POLL_SECONDS", "0"),
        ("WORKER_POLL_SECONDS", "301"),
        ("WORKER_POLL_SECONDS", "invalid"),
        ("WORKER_HEARTBEAT_MAX_AGE_SECONDS", "29"),
        ("WORKER_HEARTBEAT_MAX_AGE_SECONDS", "3601"),
    ],
)
def test_invalid_worker_health_configuration_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    name: str,
    value: str,
) -> None:
    monkeypatch.setenv(name, value)
    assert health.main() == 1
