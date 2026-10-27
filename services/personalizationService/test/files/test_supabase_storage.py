"""Verify the actual HTTP adapter against provider-shaped responses."""

from dataclasses import replace
from hashlib import sha256
from uuid import uuid4

import pytest

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileRecord, FileState
from test.files.fakes import (
    BUCKET,
    TEST_KEY,
    StorageServer,
)
from test.image_samples import make_image


@pytest.fixture
def record() -> FileRecord:
    file_id = uuid4()
    content = make_image()
    return FileRecord(
        id=file_id,
        owner_id=uuid4(),
        bucket=BUCKET,
        object_key=f"{file_id}.png",
        mime_type="image/png",
        size_bytes=len(content),
        width_px=12,
        height_px=8,
        sha256=sha256(content).hexdigest(),
        state=FileState.PENDING,
    )


@pytest.mark.parametrize("attribute", ["public", "limit", "mime_types"])
def test_bucket_configuration_is_checked_before_use(attribute: str) -> None:
    server = StorageServer()
    setattr(
        server,
        attribute,
        {
            "public": True,
            "limit": 50_000_000,
            "mime_types": ["image/png"],
        }[attribute],
    )
    adapter = server.adapter()
    try:
        with pytest.raises(FileError) as caught:
            adapter.ensure_private()
        assert caught.value.failure is FileFailure.STORAGE_BUCKET_UNSAFE
    finally:
        adapter.close()


@pytest.mark.parametrize("status", [301, 401, 403, 429, 500])
def test_provider_errors_are_sanitized_and_redirects_are_not_followed(
    status: int,
) -> None:
    server = StorageServer()
    server.status_override = status
    adapter = server.adapter()
    try:
        with pytest.raises(FileError) as caught:
            adapter.ensure_private()
        assert caught.value.failure is FileFailure.STORAGE_UNAVAILABLE
        assert "private-provider-detail" not in str(caught.value)
        assert TEST_KEY not in str(caught.value)
        assert len(server.requests) == 1
    finally:
        adapter.close()


@pytest.mark.parametrize("body", [b"not-json", b"[]", b"null"])
def test_malformed_bucket_responses_are_unavailable(body: bytes) -> None:
    server = StorageServer()
    server.body_override = body
    adapter = server.adapter()
    try:
        with pytest.raises(FileError) as caught:
            adapter.ensure_private()
        assert caught.value.failure is FileFailure.STORAGE_UNAVAILABLE
    finally:
        adapter.close()


def test_bucket_creation_is_private_and_repeatable() -> None:
    server = StorageServer()
    server.exists = False
    adapter = server.adapter()
    try:
        adapter.create_bucket()
        adapter.create_bucket()
        assert sum(r.method == "POST" for r in server.requests) == 1
    finally:
        adapter.close()


def test_create_never_changes_an_existing_public_bucket() -> None:
    server = StorageServer()
    server.public = True
    adapter = server.adapter()
    try:
        with pytest.raises(FileError):
            adapter.create_bucket()
        assert all(r.method == "GET" for r in server.requests)
    finally:
        adapter.close()


@pytest.mark.parametrize(
    "signed",
    [
        "https://evil.example/object?token=x",
        "//evil.example/object?token=x",
        "/object/sign/wrong?token=x",
        "/object/sign/wrong",
        "/object/sign/wrong?token=x&token=y",
    ],
)
def test_malformed_signed_urls_are_rejected(
    record: FileRecord, signed: str
) -> None:
    server = StorageServer()
    server.signed_response = signed
    adapter = server.adapter()
    try:
        with pytest.raises(FileError) as caught:
            adapter.sign_download(record, 60)
        assert caught.value.failure is FileFailure.STORAGE_UNAVAILABLE
    finally:
        adapter.close()


def test_upload_is_create_only_and_integrity_checked(
    record: FileRecord,
) -> None:
    server = StorageServer()
    adapter = server.adapter()
    try:
        adapter.upload(record, make_image())
        with pytest.raises(FileError):
            adapter.upload(record, make_image())
        count = len(server.requests)
        with pytest.raises(FileError) as wrong_data:
            adapter.upload(record, b"bad")
        assert wrong_data.value.failure is FileFailure.FILE_INTEGRITY_MISMATCH
        with pytest.raises(FileError):
            adapter.upload(
                replace(record, object_key="../another-file"), make_image()
            )
        assert len(server.requests) == count
    finally:
        adapter.close()
