"""Verify durable discovery and recovery against PostgreSQL."""

import os
from dataclasses import replace
from uuid import uuid4

import pytest
from sqlalchemy import Engine
from sqlalchemy.orm import Session

from personalization.application.errors.file_error import FileError
from personalization.application.files.file_record import FileState
from personalization.application.thumbnails.thumbnail_worker import (
    ThumbnailWorker,
)
from personalization.infrastructure.database.file_repository import (
    SqlAlchemyFileRepository,
)
from personalization.infrastructure.database.models.image_file import FileModel
from personalization.infrastructure.database.print_repository import (
    SqlAlchemyPrintRepository,
)
from personalization.infrastructure.database.thumbnail_repository import (
    SqlAlchemyThumbnailRepository,
)
from test.files.fakes import BUCKET, StorageServer
from test.image_samples import make_image
from test.integration.test_print_versioning import Seed
from test.integration.test_print_versioning import seed as seed
from test.thumbnails.test_thumbnail_worker import renderer

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PERSONALIZATION_DATABASE_INTEGRATION") != "1",
        reason="Requires the disposable PostgreSQL integration database",
    ),
]


def test_discovery_is_durable_unique_and_includes_retired_history(
    engine: Engine,
    seed: Seed,
) -> None:
    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    repository = SqlAlchemyThumbnailRepository(engine, BUCKET)
    assert repository.candidates(None, 100) == []
    created = prints.create(seed.actor, seed.name, None, seed.file_id, 0)
    prints.create_version(seed.actor, created.id, 1, seed.file_id, 100)
    with Session(engine) as session, session.begin():
        from personalization.infrastructure.database.models.print import (
            PrintModel,
        )

        row = session.get(PrintModel, created.id)
        assert row is not None
        row.active = False
    candidates = repository.candidates(None, 100)
    assert len(candidates) == 1 and candidates[0].id == seed.file_id
    assert repository.candidates(seed.file_id, 100) == []
    record = (
        renderer().render(candidates[0], make_image()).record(candidates[0])
    )
    assert repository.reserve(record) == record
    assert repository.get(seed.file_id) == record
    assert len(repository.candidates(None, 1)) == 1
    assert repository.reserve(record) == record
    published = repository.publish(record)
    assert published.state is FileState.AVAILABLE
    assert repository.publish(record) == published
    assert repository.candidates(None, 100) == []
    assert (
        prints.get_version(created.id, created.latest_version.id).file_id
        == seed.file_id
    )


def test_claims_exclude_other_connections_and_release_on_exception(
    engine: Engine,
    seed: Seed,
) -> None:
    first = SqlAlchemyThumbnailRepository(engine, BUCKET)
    second = SqlAlchemyThumbnailRepository(engine, BUCKET)
    with pytest.raises(RuntimeError, match="simulated crash"):
        with first.lock(seed.file_id) as acquired:
            assert acquired
            with second.lock(seed.file_id) as competing:
                assert competing is False
            with second.lock(uuid4()) as other:
                assert other is True
            raise RuntimeError("simulated crash")
    with second.lock(seed.file_id) as recovered:
        assert recovered is True


@pytest.mark.parametrize(
    "failure", [None, "before-write", "after-write", "publish"]
)
def test_restart_recovers_a_committed_intention_against_real_database(
    engine: Engine,
    seed: Seed,
    failure: str | None,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    created = prints.create(seed.actor, seed.name, None, seed.file_id, 0)
    repository = SqlAlchemyThumbnailRepository(engine, BUCKET)
    source = SqlAlchemyFileRepository(engine).get(seed.file_id)
    assert source is not None
    server = StorageServer()
    server.objects[f"{BUCKET}/{source.object_key}"] = make_image()
    storage = server.adapter()
    worker = ThumbnailWorker(repository, storage, renderer())
    real_publish = repository.publish

    def fail_publish(record: object) -> None:
        from personalization.application.errors.file_error import FileFailure

        raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE)

    try:
        if failure == "publish":
            monkeypatch.setattr(repository, "publish", fail_publish)
        else:
            server.upload_failure = failure
        if failure:
            with pytest.raises(FileError):
                worker.process(source)
            pending = repository.get(source.id)
            assert pending is not None and pending.state is FileState.PENDING
        server.upload_failure = None
        monkeypatch.setattr(repository, "publish", real_publish)
        # A fresh adapter represents the restarted worker.
        restarted = SqlAlchemyThumbnailRepository(engine, BUCKET)
        assert ThumbnailWorker(restarted, storage, renderer()).process(source)
        result = restarted.get(source.id)
        assert result is not None and result.state is FileState.AVAILABLE
        assert result.owner_id == seed.actor
        assert restarted.candidates(None, 100) == []
        assert len(server.objects) == 2
        assert SqlAlchemyFileRepository(engine).get(seed.file_id) == source
        assert prints.get(created.id).latest_version == created.latest_version
        assert worker.process(source)
    finally:
        storage.close()


def test_publication_rejects_changed_intention(
    engine: Engine, seed: Seed
) -> None:
    source = SqlAlchemyFileRepository(engine).get(seed.file_id)
    assert source is not None
    repository = SqlAlchemyThumbnailRepository(engine, BUCKET)
    record = renderer().render(source, make_image()).record(source)
    repository.reserve(record)
    with pytest.raises(FileError):
        repository.publish(replace(record, sha256="0" * 64))
    assert repository.get(seed.file_id) == record


def test_unavailable_original_is_never_discovered(
    engine: Engine, seed: Seed
) -> None:
    prints = SqlAlchemyPrintRepository(engine, BUCKET)
    prints.create(seed.actor, seed.name, None, seed.file_id, 0)
    with Session(engine) as session, session.begin():
        row = session.get(FileModel, seed.file_id)
        assert row is not None
        row.state = FileState.PENDING.value
    assert (
        SqlAlchemyThumbnailRepository(engine, BUCKET).candidates(None, 100)
        == []
    )
