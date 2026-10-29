"""Verify preview permissions with real signed JWTs."""

from collections.abc import Callable
from dataclasses import replace
from uuid import uuid4

from fastapi.testclient import TestClient

from personalization.application.designs.draft_record import DesignCondition
from personalization.application.previews.preview_worker import PreviewWorker
from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from test.e2e.conftest import http_settings as http_settings
from test.files.fakes import BUCKET, MemoryFileRepository
from test.previews.fakes import preview_data, renderer
from test.security.test_print_http import Ready
from test.security.test_print_http import admin_headers as admin_headers


def test_pending_ready_download_and_revision_invalidation(
    http_settings: Settings,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    data = preview_data()
    from uuid import UUID

    owner = UUID("11111111-1111-4111-8111-111111111111")
    data.draft = replace(data.draft, owner_id=owner)
    data.designs.records[data.draft.id] = data.draft
    storage = data.server.adapter()
    files = MemoryFileRepository()
    files.records = data.previews.records
    app = create_app(
        http_settings,
        Ready(),
        storage=storage,
        template_repository=data.analysis.templates,
        design_repository=data.designs,
        preview_repository=data.previews,
        file_repository=files,
    )
    path = f"/api/v1/admin/design-drafts/{data.draft.id}/previews"
    try:
        with TestClient(app) as client:
            pending = client.get(path, headers=admin_headers)
            assert (
                pending.status_code == 200
                and pending.json()["status"] == "PENDING"
            )
            assert (
                pending.headers["Retry-After"] == "10"
                and not data.server.requests
            )
            assert (
                client.post(
                    path + "/FRONT/download-urls", headers=admin_headers
                ).status_code
                == 409
            )
            worker = PreviewWorker(
                data.previews,
                data.analysis.templates,
                data.analysis.sources,
                storage,
                renderer(),
                BUCKET,
            )
            assert worker.process(data.draft.id)
            data.server.requests.clear()
            ready = client.get(path, headers=admin_headers)
            assert (
                ready.status_code == 200 and ready.json()["status"] == "READY"
            )
            assert ready.json()["approximate"] is True
            assert ready.json()["representation"] == "SCHEMATIC_TEMPLATE"
            assert (
                not ready.json()["checkoutReady"] and not data.server.requests
            )
            assert ready.headers["ETag"] != pending.headers["ETag"]
            assert ready.headers["Cache-Control"] == "no-store"
            # Publishing changes the ETag even without a content edit.
            chosen = data.draft.content.applications[0]
            stale = client.put(
                path.removesuffix("/previews"),
                headers={**admin_headers, "If-Match": pending.headers["ETag"]},
                json={
                    "variantId": str(data.draft.variant_id),
                    "templateId": str(data.draft.template_id),
                    "applications": [
                        {
                            "zoneId": str(chosen.zone_id),
                            "zoneSizeId": str(chosen.zone_size_id),
                            "printVersionId": str(chosen.print_version_id)
                            if chosen.print_version_id
                            else None,
                            "fileId": str(chosen.file_id)
                            if chosen.file_id
                            else None,
                        }
                    ],
                },
            )
            assert stale.status_code == 412
            assert stale.json()["code"] == "DESIGN_PRECONDITION_FAILED"
            malformed = client.get(
                "/api/v1/files/not-a-uuid", headers=admin_headers
            )
            assert malformed.status_code == 422
            derived = client.get(
                "/api/v1/files/" + ready.json()["front"]["id"],
                headers=admin_headers,
            )
            assert derived.status_code == 404
            assert derived.json()["code"] == "FILE_NOT_FOUND"
            for side in ("FRONT", "BACK"):
                download = client.post(
                    path + f"/{side}/download-urls", headers=admin_headers
                )
                assert (
                    download.status_code == 201
                    and download.json()["downloadUrl"]
                )
            current = data.designs.records[data.draft.id]
            data.designs.update(
                owner,
                current.id,
                replace(current.content, applications=()),
                DesignCondition(any_existing=True),
            )
            assert (
                client.get(path, headers=admin_headers).json()["status"]
                == "PENDING"
            )
            assert (
                client.post(
                    path + "/BACK/download-urls", headers=admin_headers
                ).status_code
                == 409
            )
            assert (
                client.post(
                    path + "/SIDE/download-urls", headers=admin_headers
                ).status_code
                == 422
            )
    finally:
        storage.close()


def test_anonymous_client_other_admin_and_unknown_draft(
    http_settings: Settings,
    admin_headers: dict[str, str],
    jwks_transport: object,
    sign_token: Callable[..., str],
    claims: dict[str, object],
) -> None:
    data = preview_data()
    app = create_app(
        http_settings,
        Ready(),
        template_repository=data.analysis.templates,
        design_repository=data.designs,
        preview_repository=data.previews,
    )
    path = f"/api/v1/admin/design-drafts/{data.draft.id}/previews"
    other = {
        "Authorization": "Bearer "
        + sign_token(
            {
                **claims,
                "sub": str(uuid4()),
                "app_metadata": {"app_role": "administrador"},
            }
        )
    }
    with TestClient(app) as client:
        for method, url in [
            ("GET", path),
            ("POST", path + "/FRONT/download-urls"),
        ]:
            for headers, status in [
                ({}, 401),
                ({"Authorization": "Bearer " + sign_token()}, 403),
                (other, 403),
            ]:
                response = client.request(method, url, headers=headers)
                assert (
                    response.status_code == status
                    and len(response.json()) == 7
                )
                assert (
                    response.headers["Content-Type"]
                    == "application/problem+json"
                )
        assert (
            client.get(
                f"/api/v1/admin/design-drafts/{uuid4()}/previews",
                headers=admin_headers,
            ).status_code
            == 404
        )
