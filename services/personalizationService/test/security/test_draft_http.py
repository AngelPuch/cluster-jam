"""Verify persisted draft HTTP contracts with real signed JWTs."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from personalization.application.designs.draft_record import DesignState
from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from test.designs.draft_fakes import MemoryDesignRepository
from test.designs.fakes import AnalysisData, analysis_data
from test.e2e.conftest import http_settings as http_settings
from test.security.test_print_http import Ready
from test.security.test_print_http import admin_headers as admin_headers

BASE = "/api/v1/admin/design-drafts"


@dataclass
class DraftHttp:
    client: TestClient
    data: AnalysisData
    repository: MemoryDesignRepository

    def body(self) -> dict[str, object]:
        return {
            "variantId": str(uuid4()),
            "templateId": str(self.data.template.header.id),
            "applications": [
                {
                    "zoneId": str(item.zone_id),
                    "zoneSizeId": str(item.zone_size_id),
                    "printVersionId": str(item.print_version_id),
                }
                for item in self.data.selections[:1]
            ],
        }


@pytest.fixture
def draft_http(http_settings: Settings) -> Iterator[DraftHttp]:
    data = analysis_data()
    repository = MemoryDesignRepository()
    app = create_app(
        http_settings,
        Ready(),
        template_repository=data.templates,
        design_repository=repository,
    )
    with TestClient(app) as client:
        yield DraftHttp(client, data, repository)


def test_create_edit_clear_noop_and_copy(
    draft_http: DraftHttp,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    data = draft_http
    body = data.body()
    created = data.client.post(BASE, json=body, headers=admin_headers)
    assert created.status_code == 201
    original = created.json()
    path = created.headers["Location"]
    etag = created.headers["ETag"]
    assert original["ownerId"] == "11111111-1111-4111-8111-111111111111"
    assert original["state"] == "BORRADOR" and original["version"] == 1
    assert (
        original["catalogCompatibilityVerified"] is False
        and original["checkoutReady"] is False
    )
    assert data.client.get(path, headers=admin_headers).json() == original
    same = data.client.put(
        path, headers={**admin_headers, "If-Match": etag}, json=body
    )
    assert same.status_code == 200 and same.headers["ETag"] == etag
    body["applications"] = []
    changed = data.client.put(
        path, headers={**admin_headers, "If-Match": etag}, json=body
    )
    assert changed.status_code == 200 and changed.json()["version"] == 2
    assert (
        changed.json()["applications"] == []
        and changed.headers["ETag"] != etag
    )
    copy = data.client.post(path + "/copies", headers=admin_headers)
    assert copy.status_code == 201 and copy.json()["id"] != original["id"]
    assert copy.json()["version"] == 1 and copy.headers["ETag"]
    assert copy.headers["Cache-Control"] == "no-store"
    assert (
        data.client.get(path, headers=admin_headers).json() == changed.json()
    )


@pytest.mark.parametrize(
    "tag,status,code",
    [
        (None, 428, "DESIGN_PRECONDITION_REQUIRED"),
        ("unquoted", 400, "INVALID_DESIGN_PRECONDITION"),
        ('"stale"', 412, "DESIGN_PRECONDITION_FAILED"),
        ('W/"weak"', 412, "DESIGN_PRECONDITION_FAILED"),
    ],
)
def test_edit_requires_a_matching_strong_validator(
    draft_http: DraftHttp,
    admin_headers: dict[str, str],
    jwks_transport: object,
    tag: str | None,
    status: int,
    code: str,
) -> None:
    body = draft_http.body()
    created = draft_http.client.post(BASE, headers=admin_headers, json=body)
    headers = dict(admin_headers)
    if tag is not None:
        headers["If-Match"] = tag
    response = draft_http.client.put(
        created.headers["Location"], headers=headers, json=body
    )
    assert response.status_code == status and response.json()["code"] == code
    assert len(response.json()) == 7 and len(draft_http.repository.audit) == 1


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", ""),
        ("GET", ""),
        ("GET", "/11111111-1111-4111-8111-111111111111"),
        ("PUT", "/11111111-1111-4111-8111-111111111111"),
        ("POST", "/11111111-1111-4111-8111-111111111111/copies"),
    ],
)
@pytest.mark.parametrize("authenticated,status", [(False, 401), (True, 403)])
def test_every_operation_requires_administrator(
    draft_http: DraftHttp,
    sign_token: Callable[..., str],
    jwks_transport: object,
    method: str,
    path: str,
    authenticated: bool,
    status: int,
) -> None:
    headers = (
        {"Authorization": "Bearer " + sign_token()} if authenticated else {}
    )
    response = draft_http.client.request(
        method,
        BASE + path,
        headers=headers,
        json=draft_http.body()
        if method in ("POST", "PUT") and not path.endswith("copies")
        else None,
    )
    assert response.status_code == status and len(response.json()) == 7
    assert draft_http.repository.calls == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("ownerId", "spoofed"),
        ("state", "CONGELADO"),
        ("version", 77),
        ("frontPreviewId", str(uuid4())),
        ("totalAmountCents", 1),
    ],
)
def test_server_owned_fields_cannot_be_assigned(
    draft_http: DraftHttp,
    admin_headers: dict[str, str],
    jwks_transport: object,
    field: str,
    value: object,
) -> None:
    body = draft_http.body()
    body[field] = value
    response = draft_http.client.post(BASE, headers=admin_headers, json=body)
    assert (
        response.status_code == 422
        and response.json()["code"] == "VALIDATION_ERROR"
    )
    assert draft_http.repository.calls == 0


def test_other_admin_cannot_get_edit_or_copy_and_lists_only_owned(
    draft_http: DraftHttp,
    admin_headers: dict[str, str],
    claims: dict[str, object],
    sign_token: Callable[..., str],
    jwks_transport: object,
) -> None:
    body = draft_http.body()
    created = draft_http.client.post(BASE, headers=admin_headers, json=body)
    path = created.headers["Location"]
    headers = {
        "Authorization": "Bearer "
        + sign_token(
            {
                **claims,
                "sub": str(uuid4()),
                "app_metadata": {"app_role": "administrador"},
            }
        ),
        "If-Match": created.headers["ETag"],
    }
    for method, target in [
        ("GET", path),
        ("PUT", path),
        ("POST", path + "/copies"),
    ]:
        response = draft_http.client.request(
            method,
            target,
            headers=headers,
            json=body if method == "PUT" else None,
        )
        assert (
            response.status_code == 403
            and response.json()["code"] == "FORBIDDEN"
        )
    assert draft_http.client.get(BASE, headers=headers).json() == {
        "items": [],
        "nextCursor": None,
    }


def test_frozen_copy_and_rejected_mutation(
    draft_http: DraftHttp,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    body = draft_http.body()
    created = draft_http.client.post(BASE, headers=admin_headers, json=body)
    design_id = UUID(created.json()["id"])
    frozen = replace(
        draft_http.repository.records[design_id], state=DesignState.FROZEN
    )
    draft_http.repository.records[design_id] = frozen
    current = draft_http.client.get(
        created.headers["Location"], headers=admin_headers
    )
    changed = draft_http.client.put(
        created.headers["Location"],
        headers={**admin_headers, "If-Match": current.headers["ETag"]},
        json=body,
    )
    assert (
        changed.status_code == 409
        and changed.json()["code"] == "DESIGN_NOT_EDITABLE"
    )
    copy = draft_http.client.post(
        created.headers["Location"] + "/copies", headers=admin_headers
    )
    assert copy.status_code == 201 and copy.json()["id"] != str(design_id)
    assert copy.json()["state"] == "BORRADOR"
    assert draft_http.repository.records[design_id] == frozen
