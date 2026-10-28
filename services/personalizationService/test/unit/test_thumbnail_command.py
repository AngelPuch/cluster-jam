"""Verify worker lifecycle, trace context, and sanitized failures."""

import json
import sys

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine

from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.storage.supabase_storage import (
    SupabaseStorage,
)
from personalization.interfaces.workers import thumbnails as entrypoint
from test.files.fakes import TEST_KEY, StorageServer
from test.thumbnails.fakes import MemoryThumbnailRepository
from test.unit.test_storage_commands import settings as settings


@pytest.mark.parametrize("ready", [True, False])
def test_once_mode_has_trace_context_and_safe_logs(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ready: bool,
) -> None:
    repository = MemoryThumbnailRepository()
    server = StorageServer()

    class Readiness:
        def __init__(self, engine: Engine, settings: Settings) -> None:
            pass

        def is_ready(self) -> bool:
            return ready

    def storage(
        project_url: str, bucket: str, key: SecretStr
    ) -> SupabaseStorage:
        return server.adapter()

    def thumbnail_repository(
        engine: Engine, bucket: str
    ) -> MemoryThumbnailRepository:
        return repository

    monkeypatch.setattr(entrypoint, "Settings", lambda: settings)
    monkeypatch.setattr(entrypoint, "SupabaseStorage", storage)
    monkeypatch.setattr(
        entrypoint, "SqlAlchemyThumbnailRepository", thumbnail_repository
    )
    monkeypatch.setattr(entrypoint, "SqlAlchemyReadinessAdapter", Readiness)
    monkeypatch.setattr(sys, "argv", ["thumbnails", "--once"])
    assert entrypoint.main() == (0 if ready else 1)
    output = capsys.readouterr()
    events = [json.loads(line) for line in output.out.splitlines()]
    assert events[0]["event"] == "worker.started"
    assert events[-1]["event"] == "worker.stopped"
    batch = events[1]
    assert batch["trace_id"] and batch["span_id"]
    if ready:
        assert batch["completed"] == batch["failures"] == 0
    else:
        assert batch["code"] == "FILE_DATABASE_UNAVAILABLE"
    assert TEST_KEY not in output.out + output.err


def test_invalid_configuration_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def invalid() -> Settings:
        return Settings.model_validate({"APP_ENV": "private-input"})

    monkeypatch.setattr(entrypoint, "Settings", invalid)
    monkeypatch.setattr(sys, "argv", ["thumbnails", "--once"])
    assert entrypoint.main() == 2
    output = capsys.readouterr()
    assert json.loads(output.out)["code"] == "CONFIGURATION_INVALID"
    assert "private-input" not in output.out + output.err
