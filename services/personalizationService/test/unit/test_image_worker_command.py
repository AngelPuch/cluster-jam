"""Verify independent queues, shutdown and sanitized worker logs."""

import json
import sys
from collections.abc import Callable

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.storage.supabase_storage import (
    SupabaseStorage,
)
from personalization.interfaces.workers import images as entrypoint
from test.designs.draft_fakes import MemoryDesignRepository
from test.files.fakes import TEST_KEY, StorageServer
from test.previews.fakes import MemoryPreviewRepository
from test.thumbnails.fakes import MemoryThumbnailRepository
from test.unit.test_storage_commands import settings as settings


@pytest.mark.parametrize(
    "ready,thumbnail_failure", [(True, False), (True, True), (False, False)]
)
def test_once_runs_both_queues_even_if_thumbnail_batch_fails(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    ready: bool,
    thumbnail_failure: bool,
) -> None:
    repository = MemoryThumbnailRepository()
    previews = MemoryPreviewRepository(MemoryDesignRepository())
    server = StorageServer()

    class Readiness:
        def __init__(self, engine: Engine, settings: Settings) -> None:
            pass

        def is_ready(self) -> bool:
            return ready

    def storage(
        project_url: str,
        bucket: str,
        key: SecretStr,
        *,
        on_progress: Callable[[], None] | None = None,
    ) -> SupabaseStorage:
        return server.adapter()

    def thumbnails(engine: Engine, bucket: str) -> MemoryThumbnailRepository:
        return repository

    def preview_repository(
        engine: Engine, bucket: str
    ) -> MemoryPreviewRepository:
        return previews

    def fail_candidates(after: object, limit: int) -> list[object]:
        raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE)

    monkeypatch.setattr(entrypoint, "Settings", lambda: settings)
    monkeypatch.setattr(entrypoint, "SupabaseStorage", storage)
    monkeypatch.setattr(
        entrypoint, "SqlAlchemyThumbnailRepository", thumbnails
    )
    monkeypatch.setattr(
        entrypoint, "SqlAlchemyPreviewRepository", preview_repository
    )
    monkeypatch.setattr(entrypoint, "SqlAlchemyReadinessAdapter", Readiness)
    if thumbnail_failure:
        monkeypatch.setattr(repository, "candidates", fail_candidates)
    monkeypatch.setattr(sys, "argv", ["images", "--once"])
    assert entrypoint.main() == (0 if ready and not thumbnail_failure else 1)
    output = capsys.readouterr()
    events = [json.loads(line) for line in output.out.splitlines()]
    assert events[0]["event"] == "worker.started"
    assert events[-1]["event"] == "worker.stopped"
    assert len(events) == 4
    assert events[2]["event"] == (
        "preview.batch.completed" if ready else "preview.batch.failed"
    )
    for event in events[1:3]:
        assert event["trace_id"] and event["span_id"]
    assert TEST_KEY not in output.out + output.err


def test_invalid_image_worker_config_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def invalid() -> Settings:
        return Settings.model_validate({"APP_ENV": "private-input"})

    monkeypatch.setattr(entrypoint, "Settings", invalid)
    monkeypatch.setattr(sys, "argv", ["images", "--once"])
    assert entrypoint.main() == 2
    output = capsys.readouterr()
    assert json.loads(output.out)["code"] == "CONFIGURATION_INVALID"
    assert "private-input" not in output.out + output.err
