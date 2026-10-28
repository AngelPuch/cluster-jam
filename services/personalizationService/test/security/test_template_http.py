"""Verify admin-only template contracts with signed JWTs."""

from collections.abc import Callable, Iterator
from typing import cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from test.e2e.conftest import http_settings as http_settings
from test.security.test_print_http import Ready
from test.security.test_print_http import admin_headers as admin_headers
from test.templates.fakes import MemoryTemplateRepository, request_body

BASE = "/api/v1/admin/template-versions"


@pytest.fixture
def template_repository() -> MemoryTemplateRepository:
    return MemoryTemplateRepository()


@pytest.fixture
def template_client(
    http_settings: Settings, template_repository: MemoryTemplateRepository
) -> Iterator[TestClient]:
    with TestClient(
        create_app(
            http_settings, Ready(), template_repository=template_repository
        )
    ) as client:
        yield client


def test_admin_creates_reads_and_versions_exact_mm_and_cm(
    template_client: TestClient,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    body = request_body()
    created = template_client.post(BASE, headers=admin_headers, json=body)
    assert created.status_code == 201
    first = created.json()
    assert first["active"] is False and first["number"] == 1
    assert first["front"]["widthMm"] == "400.000"
    size = first["zones"][0]["sizes"][0]
    assert size["widthCm"] == "10.0000" and size["heightCm"] == "15.0000"
    assert size["surchargeCents"] == 1250 and size["currency"] == "MXN"
    assert (
        template_client.get(
            created.headers["Location"], headers=admin_headers
        ).json()
        == first
    )
    assert created.headers["Cache-Control"] == "no-store"
    stale = template_client.post(BASE, headers=admin_headers, json=body)
    assert (
        stale.status_code == 409
        and stale.json()["code"] == "TEMPLATE_VERSION_CONFLICT"
    )
    body["expectedVersion"] = 1
    second = template_client.post(BASE, headers=admin_headers, json=body)
    assert second.status_code == 201 and second.json()["number"] == 2
    assert second.json()["zones"][0]["id"] != first["zones"][0]["id"]
    page = template_client.get(
        BASE,
        headers=admin_headers,
        params={"productId": str(body["productId"]), "sizeId": 1, "limit": 1},
    ).json()
    assert len(page["items"]) == 1 and page["nextCursor"]
    assert "zones" not in page["items"][0]


@pytest.mark.parametrize(
    "method,suffix",
    [
        ("POST", ""),
        ("GET", ("?productId=11111111-1111-4111-8111-111111111111&sizeId=1")),
        ("GET", "/11111111-1111-4111-8111-111111111111"),
    ],
)
@pytest.mark.parametrize("authenticated,expected", [(False, 401), (True, 403)])
def test_all_operations_enforce_admin_before_data_access(
    template_client: TestClient,
    template_repository: MemoryTemplateRepository,
    sign_token: Callable[..., str],
    jwks_transport: object,
    method: str,
    suffix: str,
    authenticated: bool,
    expected: int,
) -> None:
    headers = (
        {"Authorization": "Bearer " + sign_token()} if authenticated else {}
    )
    response = template_client.request(
        method,
        BASE + suffix,
        headers=headers,
        json=request_body() if method == "POST" else None,
    )
    assert response.status_code == expected and len(response.json()) == 7
    assert response.headers["Content-Type"] == "application/problem+json"
    assert template_repository.calls == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("front", {"widthMm": 400, "heightMm": "600"}),
        ("front", {"widthMm": "NaN", "heightMm": "600"}),
        ("front", {"widthMm": "0.0001", "heightMm": "600"}),
        ("front", {"widthMm": "10001", "heightMm": "600"}),
        ("sizeId", True),
        ("sizeId", 0),
        ("expectedVersion", -1),
        ("active", True),
        ("actorId", "spoofed"),
        ("product_id", "wrong-alias"),
    ],
)
def test_strict_dtos_reject_invalid_fields_without_writing(
    template_client: TestClient,
    template_repository: MemoryTemplateRepository,
    admin_headers: dict[str, str],
    jwks_transport: object,
    field: str,
    value: object,
) -> None:
    body = request_body()
    body[field] = value
    response = template_client.post(BASE, headers=admin_headers, json=body)
    assert (
        response.status_code == 422
        and response.json()["code"] == "VALIDATION_ERROR"
    )
    assert len(response.json()) == 7 and template_repository.calls == 0


def test_geometry_errors_and_unavailable_database_are_sanitized(
    template_client: TestClient,
    template_repository: MemoryTemplateRepository,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    body = request_body()
    zones = cast(list[dict[str, object]], body["zones"])
    zones[0]["xMm"] = "201"
    response = template_client.post(BASE, headers=admin_headers, json=body)
    assert (
        response.status_code == 422
        and response.json()["code"] == "ZONE_OUTSIDE_TEMPLATE"
    )
    template_repository.unavailable = True
    response = template_client.post(
        BASE, headers=admin_headers, json=request_body()
    )
    assert (
        response.status_code == 503
        and response.json()["code"] == "TEMPLATE_DATABASE_UNAVAILABLE"
    )


def test_drafts_cannot_be_modified_deleted_or_published(
    template_client: TestClient,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    created = template_client.post(
        BASE, headers=admin_headers, json=request_body()
    )
    path = created.headers["Location"]
    for method in ("PATCH", "DELETE"):
        assert (
            template_client.request(
                method, path, headers=admin_headers, json={"active": True}
            ).status_code
            == 405
        )
    assert (
        template_client.post(
            path + "/publications", headers=admin_headers
        ).status_code
        == 404
    )
    assert (
        template_client.get(
            BASE + f"/{uuid4()}", headers=admin_headers
        ).status_code
        == 404
    )
    schema = template_client.get("/openapi.json").json()
    assert (
        schema["components"]["schemas"]["DimensionsRequest"]["properties"][
            "widthMm"
        ]["type"]
        == "string"
    )


def test_fractional_millimeters_are_exact_and_have_matching_cm(
    template_client: TestClient,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    body = request_body()
    zones = cast(list[dict[str, object]], body["zones"])
    sizes = cast(list[dict[str, object]], zones[0]["sizes"])
    sizes[0]["widthMm"] = "100.125"
    sizes[0]["heightMm"] = "150.001"
    response = template_client.post(BASE, headers=admin_headers, json=body)
    assert response.status_code == 201
    value = response.json()["zones"][0]["sizes"][0]
    assert value["widthMm"] == "100.125" and value["widthCm"] == "10.0125"
    assert value["heightMm"] == "150.001" and value["heightCm"] == "15.0001"
