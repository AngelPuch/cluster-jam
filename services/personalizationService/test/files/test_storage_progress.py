"""Preserve Storage contracts while reporting worker activity."""

import httpx
import pytest
from pydantic import SecretStr

from personalization.application.files.file_record import FileRecord
from personalization.infrastructure.storage.supabase_storage import (
    SupabaseStorage,
)
from test.files.fakes import BUCKET, PROJECT, TEST_KEY, StorageServer
from test.files.test_supabase_storage import record as record
from test.image_samples import make_image


@pytest.mark.parametrize("action", ["upload", "read", "verify", "bucket"])
def test_storage_transfers_report_progress_without_changing_bytes(
    record: FileRecord,
    action: str,
) -> None:
    server = StorageServer()
    content = make_image()
    calls: list[bool] = []
    adapter = SupabaseStorage(
        PROJECT,
        BUCKET,
        SecretStr(TEST_KEY),
        transport=httpx.MockTransport(server.handle),
        on_progress=lambda: calls.append(True),
    )
    try:
        if action != "upload":
            server.objects[BUCKET + "/" + record.object_key] = content
        if action == "upload":
            adapter.upload(record, content)
            assert server.objects[BUCKET + "/" + record.object_key] == content
        elif action == "read":
            assert adapter.read_verified(record) == content
        elif action == "verify":
            adapter.verify_original(record)
        else:
            adapter.ensure_private()
        assert len(calls) >= 2
    finally:
        adapter.close()


def test_worker_heartbeat_failure_is_not_misreported_as_provider_failure() -> (
    None
):
    def fail() -> None:
        raise OSError("worker progress marker unavailable")

    server = StorageServer()
    adapter = SupabaseStorage(
        PROJECT,
        BUCKET,
        SecretStr(TEST_KEY),
        transport=httpx.MockTransport(server.handle),
        on_progress=fail,
    )
    try:
        with pytest.raises(OSError):
            adapter.ensure_private()
        assert not server.requests
    finally:
        adapter.close()
