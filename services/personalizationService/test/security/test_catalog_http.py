"""Verify customer JWT access without exposing private originals."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from personalization.application.catalog.catalog_record import CatalogPrint
from personalization.application.prints.cursor import encode_cursor
from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from test.catalog.fakes import MemoryCatalogRepository, catalog_record
from test.e2e.conftest import http_settings as http_settings
from test.files.fakes import MemoryFileRepository, StorageServer
from test.prints.fakes import MemoryPrintRepository
from test.security.test_print_http import Ready
from test.thumbnails.fakes import MemoryThumbnailRepository

BASE = "/api/v1/prints"


@dataclass
class CatalogHttp:
    client: TestClient
    repository: MemoryCatalogRepository
    server: StorageServer
    row: CatalogPrint


@pytest.fixture
def catalog_http(http_settings: Settings) -> Iterator[CatalogHttp]:
    repository = MemoryCatalogRepository()
    row = catalog_record()
    repository.rows[row.id] = row
    server = StorageServer()
    storage = server.adapter()
    app = create_app(
        http_settings,
        Ready(),
        file_repository=MemoryFileRepository(),
        print_repository=MemoryPrintRepository(),
        storage=storage,
        thumbnail_repository=MemoryThumbnailRepository(),
        catalog_repository=repository,
    )
    try:
        with TestClient(app) as client:
            yield CatalogHttp(client, repository, server, row)
    finally:
        storage.close()


@pytest.mark.parametrize("role", ["cliente", "administrador"])
def test_catalog_contract_and_download_use_real_signed_jwt(
    catalog_http: CatalogHttp,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: object,
    role: str,
) -> None:
    data = catalog_http
    headers = {
        "Authorization": "Bearer "
        + sign_token(
            {
                **claims,
                "app_metadata": {"app_role": role},
            }
        )
    }
    response = data.client.get(BASE, headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {"items", "nextCursor"} and body["nextCursor"] is None
    item = body["items"][0]
    assert set(item) == {"id", "name", "description", "version", "thumbnail"}
    assert set(item["version"]) == {
        "id",
        "number",
        "surchargeCents",
        "currency",
    }
    assert item["version"]["surchargeCents"] == 1250
    assert item["version"]["currency"] == "MXN"
    assert set(item["thumbnail"]) == {
        "id",
        "mimeType",
        "widthPx",
        "heightPx",
        "sizeBytes",
        "downloadUrlEndpoint",
    }
    assert response.headers["Cache-Control"] == "no-store"
    detail = data.client.get(BASE + f"/{data.row.id}", headers=headers)
    assert detail.json() == item
    assert not data.server.requests
    download = data.client.post(
        item["thumbnail"]["downloadUrlEndpoint"], headers=headers
    )
    assert download.status_code == 201
    assert download.json()["fileId"] == str(data.row.thumbnail.id)
    assert download.headers["Cache-Control"] == "no-store"
    assert "ownerId" not in response.text and "objectKey" not in response.text


@pytest.mark.parametrize(
    "method,suffix",
    [
        ("GET", ""),
        ("GET", "/00000000-0000-4000-8000-000000000001"),
        (
            "POST",
            (
                "/00000000-0000-4000-8000-000000000001/versions/"
                "00000000-0000-4000-8000-000000000002/thumbnail/download-urls"
            ),
        ),
    ],
)
def test_every_catalog_operation_requires_jwt(
    catalog_http: CatalogHttp,
    method: str,
    suffix: str,
) -> None:
    response = catalog_http.client.request(method, BASE + suffix)
    assert response.status_code == 401
    assert response.json()["code"] == "INVALID_ACCESS_TOKEN"
    assert len(response.json()) == 7
    assert (
        catalog_http.repository.calls == 0 and not catalog_http.server.requests
    )


@pytest.mark.parametrize(
    "query,status,code",
    [
        ("?cursor=invalid", 400, "INVALID_CURSOR"),
        (
            "?cursor=" + encode_cursor("prints", UUID(int=1)),
            400,
            "INVALID_CURSOR",
        ),
        ("?cursor=", 422, "VALIDATION_ERROR"),
        ("?limit=0", 422, "VALIDATION_ERROR"),
        ("?limit=101", 422, "VALIDATION_ERROR"),
        ("?limit=abc", 422, "VALIDATION_ERROR"),
    ],
)
def test_invalid_pagination_is_problem_json(
    catalog_http: CatalogHttp,
    sign_token: Callable[..., str],
    jwks_transport: object,
    query: str,
    status: int,
    code: str,
) -> None:
    response = catalog_http.client.get(
        BASE + query, headers={"Authorization": "Bearer " + sign_token()}
    )
    assert response.status_code == status and response.json()["code"] == code
    assert response.headers["Content-Type"] == "application/problem+json"
    assert len(response.json()) == 7
    assert catalog_http.repository.calls == 0


def test_pagination_and_visibility_changes(
    catalog_http: CatalogHttp,
    sign_token: Callable[..., str],
    jwks_transport: object,
) -> None:
    data = catalog_http
    second = catalog_record()
    data.repository.rows[second.id] = second
    headers = {"Authorization": "Bearer " + sign_token()}
    first = data.client.get(BASE + "?limit=1", headers=headers).json()
    assert len(first["items"]) == 1 and first["nextCursor"]
    next_page = data.client.get(
        BASE,
        params={"limit": 1, "cursor": first["nextCursor"]},
        headers=headers,
    ).json()
    assert next_page["nextCursor"] is None and len(next_page["items"]) == 1
    assert next_page["items"][0]["id"] != first["items"][0]["id"]
    data.repository.rows.clear()
    assert data.client.get(BASE, headers=headers).json() == {
        "items": [],
        "nextCursor": None,
    }
    hidden = data.client.get(BASE + f"/{data.row.id}", headers=headers)
    assert hidden.status_code == 404
    stale = data.client.post(
        BASE
        + f"/{second.id}/versions/{second.version_id}/thumbnail/download-urls",
        headers=headers,
    )
    assert stale.status_code == 404 and not data.server.requests


def test_database_and_storage_failures_are_safe(
    catalog_http: CatalogHttp,
    sign_token: Callable[..., str],
    jwks_transport: object,
) -> None:
    data = catalog_http
    headers = {"Authorization": "Bearer " + sign_token()}
    data.repository.unavailable = True
    response = data.client.get(BASE, headers=headers)
    assert (
        response.status_code == 503
        and response.json()["code"] == "PRINT_DATABASE_UNAVAILABLE"
    )
    data.repository.unavailable = False
    data.server.status_override = 403
    path = (
        BASE
        + f"/{data.row.id}/versions/{data.row.version_id}"
        + "/thumbnail/download-urls"
    )
    response = data.client.post(path, headers=headers)
    assert (
        response.status_code == 503
        and response.json()["code"] == "STORAGE_UNAVAILABLE"
    )
    assert "private-provider-detail" not in response.text


def test_client_catalog_access_does_not_grant_administrative_access(
    catalog_http: CatalogHttp,
    sign_token: Callable[..., str],
    jwks_transport: object,
) -> None:
    headers = {"Authorization": "Bearer " + sign_token()}
    assert catalog_http.client.get(BASE, headers=headers).status_code == 200
    response = catalog_http.client.post(
        "/api/v1/admin/prints", headers=headers, json={}
    )
    assert (
        response.status_code == 403 and response.json()["code"] == "FORBIDDEN"
    )
