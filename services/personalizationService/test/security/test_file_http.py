"""Exercise production file routes with real locally signed JWTs."""

import asyncio
import logging
from collections.abc import AsyncIterator, Callable, Iterator
from io import StringIO
from pathlib import Path
from tempfile import SpooledTemporaryFile
from typing import cast
from uuid import UUID

import httpx
import pytest
import starlette.formparsers as formparsers
from fastapi import FastAPI
from fastapi.testclient import TestClient

import personalization.bootstrap as bootstrap
import personalization.interfaces.http.files.routes as file_routes
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.observability.logging_config import (
    configure_logging,
)
from personalization.interfaces.http.files.upload_limits import (
    MAX_MULTIPART_BYTES,
)
from test.files.fakes import TEST_KEY, MemoryFileRepository, StorageServer
from test.image_samples import make_image


class Ready:
    def is_ready(self) -> bool:
        return True


@pytest.fixture
def file_repository() -> MemoryFileRepository:
    return MemoryFileRepository()


@pytest.fixture
def storage_server() -> StorageServer:
    return StorageServer()


@pytest.fixture
def file_logs() -> StringIO:
    return StringIO()


@pytest.fixture
def file_client(
    tmp_path: Path,
    file_repository: MemoryFileRepository,
    storage_server: StorageServer,
    file_logs: StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    secret = tmp_path / "password"
    secret.write_text("test-only-password", encoding="utf-8")
    settings = Settings.model_validate(
        {
            "APP_ENV": "test",
            "DB_PASSWORD_FILE": secret,
            "SUPABASE_ISSUER": "https://supabase.example.test/auth/v1",
            "SUPABASE_JWKS_URL": "https://supabase.example.test/auth/v1/.well-known/jwks.json",
        }
    )

    def logging_for_test(*, environment: str, log_level: str) -> None:
        configure_logging(environment=environment, log_level=log_level)
        for handler in logging.getLogger("personalization").handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setStream(file_logs)

    monkeypatch.setattr(bootstrap, "configure_logging", logging_for_test)
    adapter = storage_server.adapter()
    app = bootstrap.create_app(
        settings,
        Ready(),
        file_repository=file_repository,
        storage=adapter,
    )
    try:
        with TestClient(app) as client:
            yield client
    finally:
        adapter.close()


def test_real_jwt_upload_metadata_and_private_download(
    file_client: TestClient,
    sign_token: Callable[..., str],
    jwks_transport: object,
    storage_server: StorageServer,
    file_logs: StringIO,
) -> None:
    headers = {
        "Authorization": "Bearer " + sign_token(),
        "X-User-ID": str(UUID(int=999)),
        "X-App-Role": "administrador",
    }
    response = file_client.post(
        "/api/v1/files",
        headers=headers,
        files={
            "file": ("../../private-filename.php", make_image(), "image/png")
        },
    )
    assert response.status_code == 201
    body = response.json()
    assert body["ownerId"] == "11111111-1111-4111-8111-111111111111"
    assert body["state"] == "DISPONIBLE"
    assert "bucket" not in body and "objectKey" not in body
    location = response.headers["Location"]
    assert file_client.get(location, headers=headers).json() == body
    signed = file_client.post(location + "/download-urls", headers=headers)
    assert signed.status_code == 200
    assert signed.headers["Cache-Control"] == "no-store"
    assert signed.json()["downloadUrl"].startswith(
        "https://supabase.example.test/storage/v1/object/sign/"
    )
    output = file_logs.getvalue()
    assert "private-filename" not in output
    assert "private-signed-token" not in output
    assert TEST_KEY not in output
    assert headers["Authorization"] not in output


def test_authentication_happens_before_multipart_consumption(
    file_client: TestClient,
) -> None:
    def unread_body() -> Iterator[bytes]:
        raise AssertionError("Unauthenticated uploads must not read a body")
        yield b""

    response = file_client.post(
        "/api/v1/files",
        content=unread_body(),
        headers={"Content-Type": "multipart/form-data; boundary=unused"},
    )
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_ACCESS_TOKEN"


@pytest.mark.parametrize(
    "fields",
    [
        {"ownerId": "forged"},
        {"userId": "forged"},
        {"state": "DISPONIBLE"},
    ],
)
def test_multipart_cannot_assign_owner_or_internal_state(
    file_client: TestClient,
    sign_token: Callable[..., str],
    jwks_transport: object,
    fields: dict[str, str],
) -> None:
    response = file_client.post(
        "/api/v1/files",
        data=fields,
        files={"file": ("x.png", make_image(), "image/png")},
        headers={"Authorization": "Bearer " + sign_token()},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "INVALID_MULTIPART"


def test_other_client_is_forbidden_before_storage_signing(
    file_client: TestClient,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: object,
    storage_server: StorageServer,
) -> None:
    headers = {"Authorization": "Bearer " + sign_token()}
    response = file_client.post(
        "/api/v1/files",
        headers=headers,
        files={"file": ("x.png", make_image(), "image/png")},
    )
    location = response.headers["Location"]
    calls = len(storage_server.requests)
    claims["sub"] = str(UUID(int=2))
    stranger = {"Authorization": "Bearer " + sign_token(claims)}
    for method, url in (
        ("GET", location),
        ("POST", location + "/download-urls"),
    ):
        denied = file_client.request(method, url, headers=stranger)
        assert denied.status_code == 403
        assert denied.json()["code"] == "FORBIDDEN"
    assert len(storage_server.requests) == calls
    claims["app_metadata"] = {"app_role": "administrador"}
    admin = {"Authorization": "Bearer " + sign_token(claims)}
    assert (
        file_client.post(
            location + "/download-urls", headers=admin
        ).status_code
        == 200
    )


@pytest.mark.parametrize(
    ("content", "mime", "status"),
    [
        (b"", "image/png", 400),
        (b"GIF89a", "image/png", 415),
        (make_image(), "image/jpeg", 415),
        (make_image()[:-12], "image/png", 422),
    ],
)
def test_invalid_images_never_create_metadata_or_objects(
    file_client: TestClient,
    sign_token: Callable[..., str],
    jwks_transport: object,
    file_repository: MemoryFileRepository,
    storage_server: StorageServer,
    content: bytes,
    mime: str,
    status: int,
) -> None:
    response = file_client.post(
        "/api/v1/files",
        files={"file": ("private.png", content, mime)},
        headers={"Authorization": "Bearer " + sign_token()},
    )
    assert response.status_code == status
    assert response.headers["content-type"] == "application/problem+json"
    assert len(response.json()) == 7
    assert not file_repository.records
    assert not storage_server.objects
    assert not storage_server.requests


def test_chunked_body_limit_is_enforced_without_trusting_declared_length(
    file_client: TestClient,
    sign_token: Callable[..., str],
    jwks_transport: object,
) -> None:
    def body() -> Iterator[bytes]:
        yield b"x" * (MAX_MULTIPART_BYTES + 1)

    response = file_client.post(
        "/api/v1/files",
        content=body(),
        headers={
            "Authorization": "Bearer " + sign_token(),
            "Content-Type": "multipart/form-data; boundary=example",
        },
    )
    assert response.status_code == 413
    assert response.json()["code"] == "UPLOAD_BODY_TOO_LARGE"


def test_upload_capacity_is_bounded_and_does_not_read_busy_requests(
    file_client: TestClient,
    sign_token: Callable[..., str],
    jwks_transport: object,
) -> None:
    app = cast(FastAPI, file_client.app)

    async def acquire() -> None:
        await app.state.upload_gate.acquire()

    asyncio.run(acquire())
    try:
        response = file_client.post(
            "/api/v1/files",
            headers={
                "Authorization": "Bearer " + sign_token(),
                "Content-Type": "multipart/form-data; boundary=example",
            },
        )
        assert response.status_code == 429
        assert response.headers["Retry-After"] == "1"
    finally:
        app.state.upload_gate.release()


def test_public_contract_documents_real_file_resources(
    file_client: TestClient,
) -> None:
    document = file_client.get("/openapi.json").json()
    operation = document["paths"]["/api/v1/files"]["post"]
    assert operation["security"] == [{"supabase-jwt": []}]
    schema = operation["requestBody"]["content"]["multipart/form-data"][
        "schema"
    ]
    assert schema["required"] == ["file"]
    assert schema["additionalProperties"] is False
    assert (
        "application/problem+json" in operation["responses"]["413"]["content"]
    )


def test_parse_timeout_closes_partial_spooled_files(
    file_client: TestClient,
    sign_token: Callable[..., str],
    jwks_transport: object,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    handles: list[SpooledTemporaryFile[bytes]] = []

    def tracked_spool(
        *args: object, **kwargs: object
    ) -> SpooledTemporaryFile[bytes]:
        handle: SpooledTemporaryFile[bytes] = SpooledTemporaryFile(
            max_size=1024 * 1024, mode="w+b"
        )
        handles.append(handle)
        return handle

    monkeypatch.setattr(formparsers, "SpooledTemporaryFile", tracked_spool)
    monkeypatch.setattr(file_routes, "UPLOAD_PARSE_SECONDS", 0.02)
    app = cast(FastAPI, file_client.app)

    async def check_timeout() -> httpx.Response:
        async def body() -> AsyncIterator[bytes]:
            yield (
                b"--example\r\nContent-Disposition: form-data; "
                b'name="file"; filename="x.png"\r\n'
                b"Content-Type: image/png\r\n\r\n"
            )
            await asyncio.sleep(0.1)
            yield b"never-consumed\r\n--example--\r\n"

        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://testserver"
        ) as client:
            return await client.post(
                "/api/v1/files",
                content=body(),
                headers={
                    "Authorization": "Bearer " + sign_token(),
                    "Content-Type": "multipart/form-data; boundary=example",
                },
            )

    response = asyncio.run(check_timeout())
    assert response.status_code == 408
    assert response.json()["code"] == "UPLOAD_TIMEOUT"
    assert handles and all(handle.closed for handle in handles)
    assert not app.state.upload_gate.locked()


def test_storage_failure_is_recoverable_and_does_not_leak_details(
    file_client: TestClient,
    sign_token: Callable[..., str],
    jwks_transport: object,
    storage_server: StorageServer,
    file_repository: MemoryFileRepository,
    file_logs: StringIO,
) -> None:
    storage_server.upload_failure = "after-write"
    response = file_client.post(
        "/api/v1/files",
        headers={"Authorization": "Bearer " + sign_token()},
        files={"file": ("x.png", make_image(), "image/png")},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "STORAGE_UNAVAILABLE"
    assert len(response.json()) == 7
    assert len(file_repository.list_pending(100)) == 1
    metadata = file_client.get(
        response.headers["Location"],
        headers={"Authorization": "Bearer " + sign_token()},
    )
    assert metadata.status_code == 200
    assert metadata.json()["state"] == "PENDIENTE_CARGA"
    assert len(storage_server.objects) == 1
    output = response.text + file_logs.getvalue()
    assert "private-provider-detail" not in output
    assert TEST_KEY not in output


def test_unconfigured_storage_never_returns_fake_upload_success(
    file_client: TestClient,
    sign_token: Callable[..., str],
    jwks_transport: object,
    file_repository: MemoryFileRepository,
) -> None:
    first_app = cast(FastAPI, file_client.app)
    app = bootstrap.create_app(
        first_app.state.settings,
        Ready(),
        file_repository=file_repository,
    )
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/files",
            headers={"Authorization": "Bearer " + sign_token()},
            files={"file": ("x.png", make_image(), "image/png")},
        )
    assert response.status_code == 503
    assert response.json()["code"] == "STORAGE_NOT_CONFIGURED"
    assert not file_repository.records
