"""Verify real JWT guards for asynchronous image-result endpoints."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from personalization.application.files.file_record import FileRecord, FileState
from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from test.files.fakes import MemoryFileRepository, StorageServer
from test.image_samples import make_image
from test.prints.fakes import MemoryPrintRepository
from test.security.test_print_http import Ready
from test.security.test_print_http import admin_headers as admin_headers
from test.thumbnails.fakes import MemoryThumbnailRepository, source_record
from test.thumbnails.test_thumbnail_worker import renderer


@dataclass
class HttpData:
    client: TestClient
    thumbnails: MemoryThumbnailRepository
    server: StorageServer
    path: str
    record: FileRecord
    original_path: str


@pytest.fixture
def thumbnail_http(tmp_path: Path) -> Iterator[HttpData]:
    password = tmp_path / "password"
    password.write_text("test-only-password", encoding="utf-8")
    settings = Settings.model_validate(
        {
            "APP_ENV": "test",
            "DB_PASSWORD_FILE": password,
            "SUPABASE_ISSUER": "https://supabase.example.test/auth/v1",
            "SUPABASE_JWKS_URL": "https://supabase.example.test/auth/v1/.well-known/jwks.json",
        }
    )
    source = source_record()
    prints = MemoryPrintRepository()
    created = prints.create(source.owner_id, "Logo", None, source.id, 0)
    thumbnails = MemoryThumbnailRepository()
    record = replace(
        renderer().render(source, make_image()).record(source),
        state=FileState.AVAILABLE,
    )
    thumbnails.records[record.id] = record
    files = MemoryFileRepository()
    files.records[record.id] = record
    server = StorageServer()
    storage = server.adapter()
    app = create_app(
        settings,
        Ready(),
        file_repository=files,
        storage=storage,
        print_repository=prints,
        thumbnail_repository=thumbnails,
    )
    try:
        with TestClient(app) as client:
            yield HttpData(
                client,
                thumbnails,
                server,
                f"/api/v1/admin/prints/{created.id}/versions/{created.latest_version.id}/thumbnail",
                record,
                f"/api/v1/files/{record.id}",
            )
    finally:
        storage.close()


def test_admin_can_read_metadata_and_create_private_download(
    thumbnail_http: HttpData,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    data = thumbnail_http
    response = data.client.get(data.path, headers=admin_headers)
    assert response.status_code == 200
    assert response.json()["id"] == str(data.record.id)
    assert response.json()["widthPx"] <= 320
    assert not data.server.requests  # Metadata does not contact Storage.
    download = data.client.post(
        data.path + "/download-urls", headers=admin_headers
    )
    assert download.status_code == 201
    assert download.json()["fileId"] == str(data.record.id)
    assert download.headers["Cache-Control"] == "no-store"
    assert len(data.server.requests) == 2
    assert (
        data.client.get(data.original_path, headers=admin_headers).status_code
        == 404
    )


@pytest.mark.parametrize(
    "method,suffix", [("get", ""), ("post", "/download-urls")]
)
@pytest.mark.parametrize("role,expected", [(None, 401), ("cliente", 403)])
def test_guard_runs_before_accessing_images(
    thumbnail_http: HttpData,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: object,
    method: str,
    suffix: str,
    role: str | None,
    expected: int,
) -> None:
    headers = (
        {}
        if role is None
        else {"Authorization": "Bearer " + sign_token(claims)}
    )
    response = thumbnail_http.client.request(
        method, thumbnail_http.path + suffix, headers=headers
    )
    assert response.status_code == expected
    assert response.headers["Content-Type"] == "application/problem+json"
    assert len(response.json()) == 7
    assert not thumbnail_http.server.requests


@pytest.mark.parametrize("pending", [False, True])
def test_missing_or_pending_derivation_returns_409_without_inline_work(
    thumbnail_http: HttpData,
    admin_headers: dict[str, str],
    jwks_transport: object,
    pending: bool,
) -> None:
    data = thumbnail_http
    data.thumbnails.records.clear()
    if pending:
        data.thumbnails.records[data.record.id] = replace(
            data.record, state=FileState.PENDING
        )
    response = data.client.get(data.path, headers=admin_headers)
    assert (
        response.status_code == 409
        and response.json()["code"] == "FILE_NOT_READY"
    )
    assert not data.server.requests


def test_unknown_version_returns_404(
    thumbnail_http: HttpData,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    response = thumbnail_http.client.get(
        f"/api/v1/admin/prints/{uuid4()}/versions/{uuid4()}/thumbnail",
        headers=admin_headers,
    )
    assert response.status_code == 404
