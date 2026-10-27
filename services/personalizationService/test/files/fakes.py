"""Keep test doubles out of the installed service package."""

import json
from dataclasses import replace
from uuid import UUID

import httpx
from pydantic import SecretStr

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileRecord, FileState
from personalization.infrastructure.storage.supabase_storage import (
    SupabaseStorage,
)

PROJECT = "https://supabase.example.test"
BUCKET = "personalization-originals"
TEST_KEY = "sb_secret_" + "test-only-key-material" * 2


class MemoryFileRepository:
    """Model committed transitions and injectable database outages."""

    def __init__(self) -> None:
        self.records: dict[UUID, FileRecord] = {}
        self.fail_create = False
        self.fail_publish = False

    def create_pending(self, record: FileRecord) -> None:
        if self.fail_create:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE)
        self.records[record.id] = record

    def get(self, file_id: UUID) -> FileRecord | None:
        return self.records.get(file_id)

    def make_available(self, file_id: UUID) -> FileRecord:
        if self.fail_publish:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE)
        record = replace(self.records[file_id], state=FileState.AVAILABLE)
        self.records[file_id] = record
        return record

    def list_pending(self, limit: int) -> list[FileRecord]:
        return [
            row
            for row in self.records.values()
            if row.state is FileState.PENDING
        ][:limit]


class StorageServer:
    """Emulate only the published Supabase HTTP API, without sockets."""

    def __init__(self) -> None:
        self.objects: dict[str, bytes] = {}
        self.requests: list[httpx.Request] = []
        self.exists = True
        self.public = False
        self.limit = 10_000_000
        self.mime_types = ["image/png", "image/jpeg"]
        self.upload_failure: str | None = None
        self.signed_response: str | None = None
        self.status_override: int | None = None
        self.body_override: bytes | None = None

    def adapter(self) -> SupabaseStorage:
        return SupabaseStorage(
            PROJECT,
            BUCKET,
            SecretStr(TEST_KEY),
            transport=httpx.MockTransport(self.handle),
        )

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        assert request.url.host == "supabase.example.test"
        assert request.headers["apikey"] == TEST_KEY
        assert "Authorization" not in request.headers
        if self.status_override is not None:
            return httpx.Response(
                self.status_override, content=b"private-provider-detail"
            )
        if self.body_override is not None:
            return httpx.Response(200, content=self.body_override)
        path = request.url.path.removeprefix("/storage/v1/")
        if path == "bucket/" + BUCKET:
            if not self.exists:
                return httpx.Response(404)
            return httpx.Response(
                200,
                json={
                    "id": BUCKET,
                    "public": self.public,
                    "file_size_limit": self.limit,
                    "allowed_mime_types": self.mime_types,
                },
            )
        if path == "bucket" and request.method == "POST":
            body = json.loads(request.content)
            assert body["public"] is False
            assert body["file_size_limit"] == 10_000_000
            self.exists = True
            return httpx.Response(200, json={"name": BUCKET})
        if path.startswith("object/sign/"):
            target = path.removeprefix("object/sign/")
            signed = self.signed_response or (
                "/object/sign/" + target + "?token=private-signed-token"
            )
            return httpx.Response(200, json={"signedURL": signed})
        if path.startswith("object/authenticated/"):
            target = path.removeprefix("object/authenticated/")
            if target not in self.objects:
                return httpx.Response(404)
            return httpx.Response(200, content=self.objects[target])
        if path.startswith("object/") and request.method == "POST":
            target = path.removeprefix("object/")
            assert request.headers["x-upsert"] == "false"
            if target in self.objects:
                return httpx.Response(409)
            if self.upload_failure == "before-write":
                raise httpx.ConnectError(
                    "private-provider-detail", request=request
                )
            self.objects[target] = request.content
            if self.upload_failure == "after-write":
                raise httpx.ReadTimeout(
                    "private-provider-detail", request=request
                )
            return httpx.Response(200, json={"Key": target})
        raise AssertionError("Unexpected provider endpoint")
