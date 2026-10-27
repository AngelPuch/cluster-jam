"""Verify durable ordering, recovery, and ownership policy."""

from dataclasses import replace
from io import BytesIO
from uuid import UUID, uuid4

import pytest

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.errors.security_error import SecurityError
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
from personalization.infrastructure.images.pillow_image_inspector import (
    PillowImageInspector,
)
from test.files.fakes import BUCKET, MemoryFileRepository, StorageServer
from test.image_samples import make_image

OWNER = VerifiedIdentity(UUID(int=1), AppRole.CLIENT)


@pytest.fixture
def repository() -> MemoryFileRepository:
    return MemoryFileRepository()


@pytest.fixture
def server() -> StorageServer:
    return StorageServer()


@pytest.fixture
def service(
    repository: MemoryFileRepository, server: StorageServer
) -> FileService:
    return FileService(
        ValidateImageService(PillowImageInspector(), ImageValidationPolicy()),
        repository,
        server.adapter(),
        BUCKET,
        60,
    )


def test_original_publishes_after_object_acknowledgement(
    service: FileService,
    repository: MemoryFileRepository,
    server: StorageServer,
) -> None:
    image = make_image()
    result = service.upload(OWNER, BytesIO(image), "image/png")
    assert result.owner_id == OWNER.user_id
    assert result.state is FileState.AVAILABLE
    assert repository.records[result.id] == result
    assert server.objects[BUCKET + "/" + result.object_key] == image


def test_database_intention_failure_never_creates_an_object(
    service: FileService,
    repository: MemoryFileRepository,
    server: StorageServer,
) -> None:
    repository.fail_create = True
    with pytest.raises(FileError):
        service.upload(OWNER, BytesIO(make_image()), "image/png")
    assert not server.objects


@pytest.mark.parametrize("failure", ["before-write", "after-write"])
def test_uncertain_upload_keeps_durable_pending_metadata(
    service: FileService,
    repository: MemoryFileRepository,
    server: StorageServer,
    failure: str,
) -> None:
    server.upload_failure = failure
    with pytest.raises(FileError) as caught:
        service.upload(OWNER, BytesIO(make_image()), "image/png")
    assert caught.value.failure is FileFailure.STORAGE_UNAVAILABLE
    row = next(iter(repository.records.values()))
    assert row.state is FileState.PENDING
    assert service.get(OWNER, row.id) == row
    with pytest.raises(FileError) as not_ready:
        service.create_download(OWNER, row.id)
    assert not_ready.value.failure is FileFailure.FILE_NOT_READY
    assert not any("/object/sign/" in str(r.url) for r in server.requests)
    if failure == "after-write":
        server.upload_failure = None
        assert service.reconcile(row.id).state is FileState.AVAILABLE
        assert len(server.objects) == 1


def test_failed_publication_can_be_reconciled_without_reupload(
    service: FileService,
    repository: MemoryFileRepository,
    server: StorageServer,
) -> None:
    repository.fail_publish = True
    with pytest.raises(FileError):
        service.upload(OWNER, BytesIO(make_image()), "image/png")
    row = next(iter(repository.records.values()))
    assert row.state is FileState.PENDING
    assert len(server.objects) == 1
    repository.fail_publish = False
    published = service.reconcile(row.id)
    assert service.reconcile(row.id) == published
    assert published.state is FileState.AVAILABLE


def test_recovery_rejects_modified_remote_bytes(
    service: FileService,
    repository: MemoryFileRepository,
    server: StorageServer,
) -> None:
    repository.fail_publish = True
    with pytest.raises(FileError):
        service.upload(OWNER, BytesIO(make_image()), "image/png")
    row = next(iter(repository.records.values()))
    server.objects[BUCKET + "/" + row.object_key] = b"modified"
    repository.fail_publish = False
    with pytest.raises(FileError) as caught:
        service.reconcile(row.id)
    assert caught.value.failure is FileFailure.FILE_INTEGRITY_MISMATCH
    assert repository.records[row.id].state is FileState.PENDING


def test_non_owner_cannot_read_or_request_storage_links(
    service: FileService,
    server: StorageServer,
) -> None:
    row = service.upload(OWNER, BytesIO(make_image()), None)
    calls = len(server.requests)
    stranger = VerifiedIdentity(UUID(int=2), AppRole.CLIENT)
    for operation in (service.get, service.create_download):
        with pytest.raises(SecurityError):
            operation(stranger, row.id)
    assert len(server.requests) == calls
    admin = VerifiedIdentity(UUID(int=3), AppRole.ADMINISTRATOR)
    assert service.get(admin, row.id) == row
    result = service.create_download(admin, row.id)
    assert result.file_id == row.id
    assert "private-signed-token" not in repr(result)


def test_unknown_files_and_non_originals_are_not_resources(
    service: FileService,
    repository: MemoryFileRepository,
) -> None:
    with pytest.raises(FileError) as unknown:
        service.get(OWNER, uuid4())
    assert unknown.value.failure is FileFailure.FILE_NOT_FOUND
    row = service.upload(OWNER, BytesIO(make_image()), None)
    repository.records[row.id] = replace(row, usage="PREVIEW")
    with pytest.raises(FileError) as preview:
        service.get(OWNER, row.id)
    assert preview.value.failure is FileFailure.FILE_NOT_FOUND
