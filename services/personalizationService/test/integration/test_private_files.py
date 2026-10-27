"""Check committed file transitions using PostgreSQL."""

import os
from collections.abc import Iterator
from io import BytesIO
from uuid import UUID, uuid4

import pytest
from sqlalchemy import Engine, delete
from sqlalchemy.orm import Session

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileState
from personalization.application.files.file_service import FileService
from personalization.application.images.image_policy import (
    ImageValidationPolicy,
)
from personalization.application.images.validate_image_service import (
    ValidateImageService,
)
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from personalization.infrastructure.database.file_repository import (
    SqlAlchemyFileRepository,
)
from personalization.infrastructure.database.models.image_file import FileModel
from personalization.infrastructure.images.pillow_image_inspector import (
    PillowImageInspector,
)
from test.files.fakes import BUCKET, StorageServer
from test.image_samples import make_image

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PERSONALIZATION_DATABASE_INTEGRATION") != "1",
        reason="Requires the disposable PostgreSQL integration database",
    ),
]


@pytest.fixture
def owner(engine: Engine) -> Iterator[VerifiedIdentity]:
    identity = VerifiedIdentity(uuid4(), AppRole.CLIENT)
    try:
        yield identity
    finally:
        with engine.begin() as connection:
            connection.execute(
                delete(FileModel).where(FileModel.owner_id == identity.user_id)
            )


def build_service(engine: Engine, server: StorageServer) -> FileService:
    return FileService(
        ValidateImageService(PillowImageInspector(), ImageValidationPolicy()),
        SqlAlchemyFileRepository(engine),
        server.adapter(),
        BUCKET,
        60,
    )


def test_upload_commits_metadata_and_acknowledged_object(
    engine: Engine,
    owner: VerifiedIdentity,
) -> None:
    server = StorageServer()
    record = build_service(engine, server).upload(
        owner, BytesIO(make_image()), "image/png"
    )
    with Session(engine) as session:
        row = session.get(FileModel, record.id)
        assert row is not None
        assert row.owner_id == owner.user_id
        assert row.state == FileState.AVAILABLE.value
        assert row.object_key == record.object_key
        assert row.sha256 == record.sha256
    assert server.objects[BUCKET + "/" + record.object_key] == make_image()


def test_postgres_intention_exists_before_remote_write(
    engine: Engine,
    owner: VerifiedIdentity,
) -> None:
    server = StorageServer()
    # An uncertain write must leave committed pending metadata.
    server.upload_failure = "after-write"
    service = build_service(engine, server)
    with pytest.raises(FileError):
        service.upload(owner, BytesIO(make_image()), "image/png")
    repository = SqlAlchemyFileRepository(engine)
    pending = [
        row
        for row in repository.list_pending(100)
        if row.owner_id == owner.user_id
    ]
    assert len(pending) == 1
    assert pending[0].state is FileState.PENDING
    assert len(server.objects) == 1
    server.upload_failure = None
    recovered = service.reconcile(pending[0].id)
    assert recovered.state is FileState.AVAILABLE
    assert repository.get(recovered.id) == recovered
    assert repository.make_available(recovered.id) == recovered


def test_missing_remote_object_keeps_local_intention(
    engine: Engine,
    owner: VerifiedIdentity,
) -> None:
    server = StorageServer()
    server.upload_failure = "before-write"
    service = build_service(engine, server)
    with pytest.raises(FileError):
        service.upload(owner, BytesIO(make_image()), "image/png")
    repository = SqlAlchemyFileRepository(engine)
    pending = [
        row
        for row in repository.list_pending(100)
        if row.owner_id == owner.user_id
    ]
    with pytest.raises(FileError) as missing:
        service.reconcile(pending[0].id)
    assert missing.value.failure is FileFailure.STORAGE_UNAVAILABLE
    assert repository.get(pending[0].id) == pending[0]


def test_duplicate_metadata_never_overwrites_the_first_intention(
    engine: Engine,
    owner: VerifiedIdentity,
) -> None:
    server = StorageServer()
    record = build_service(engine, server).upload(
        owner, BytesIO(make_image()), None
    )
    repository = SqlAlchemyFileRepository(engine)
    with pytest.raises(FileError) as duplicate:
        repository.create_pending(record)
    assert duplicate.value.failure is FileFailure.FILE_DATABASE_UNAVAILABLE
    assert repository.get(record.id) == record
    assert repository.get(uuid4()) is None
    with pytest.raises(FileError) as unknown:
        repository.make_available(UUID(int=0))
    assert unknown.value.failure is FileFailure.FILE_NOT_FOUND
