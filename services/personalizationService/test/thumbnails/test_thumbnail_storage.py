"""Distinguish confirmed absence from failures during job recovery."""

import httpx
import pytest
from pydantic import SecretStr

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.infrastructure.storage.supabase_storage import (
    SupabaseStorage,
)
from test.files.fakes import BUCKET, PROJECT, TEST_KEY
from test.thumbnails.fakes import source_record


@pytest.mark.parametrize(
    "status,body,missing",
    [
        (404, {"code": "NoSuchKey"}, True),
        (400, {"statusCode": "404", "error": "not_found"}, True),
        (404, {"code": "NoSuchBucket"}, False),
        (404, {"code": "AccessDenied"}, False),
        (403, {"code": "NoSuchKey"}, False),
        (500, {"code": "NoSuchKey"}, False),
        (400, {"code": "InvalidRequest"}, False),
        (404, [], False),
    ],
)
def test_only_known_missing_objects_allow_retry(
    status: int,
    body: object,
    missing: bool,
) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json=body)

    storage = SupabaseStorage(
        PROJECT,
        BUCKET,
        SecretStr(TEST_KEY),
        transport=httpx.MockTransport(handle),
    )
    try:
        if missing:
            assert (
                storage.read_verified(source_record(), allow_missing=True)
                is None
            )
        else:
            with pytest.raises(FileError) as caught:
                storage.read_verified(source_record(), allow_missing=True)
            assert caught.value.failure is FileFailure.STORAGE_UNAVAILABLE
    finally:
        storage.close()


@pytest.mark.parametrize("content", [b"", b"x" * 10_001, b"wrong"])
def test_streamed_bytes_must_match_durable_metadata(content: bytes) -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=content)

    storage = SupabaseStorage(
        PROJECT,
        BUCKET,
        SecretStr(TEST_KEY),
        transport=httpx.MockTransport(handle),
    )
    try:
        with pytest.raises(FileError) as caught:
            storage.read_verified(source_record())
        assert caught.value.failure is FileFailure.FILE_INTEGRITY_MISMATCH
    finally:
        storage.close()


def test_untrusted_error_body_is_bounded() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, content=b"x" * 9000)

    storage = SupabaseStorage(
        PROJECT,
        BUCKET,
        SecretStr(TEST_KEY),
        transport=httpx.MockTransport(handle),
    )
    try:
        with pytest.raises(FileError) as caught:
            storage.read_verified(source_record(), allow_missing=True)
        assert caught.value.failure is FileFailure.STORAGE_UNAVAILABLE
    finally:
        storage.close()
