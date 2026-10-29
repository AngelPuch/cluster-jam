"""Verify administrative analysis without accepting client prices."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import cast
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from personalization.application.designs.design_analysis_service import (
    DesignAnalysisService,
)
from personalization.application.errors.design_analysis_error import (
    AnalysisFailure,
    DesignAnalysisError,
)
from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from test.designs.fakes import AnalysisData, analysis_data
from test.e2e.conftest import http_settings as http_settings
from test.security.test_print_http import Ready
from test.security.test_print_http import admin_headers as admin_headers


@dataclass
class AnalysisHttp:
    client: TestClient
    data: AnalysisData

    @property
    def path(self) -> str:
        return (
            f"/api/v1/admin/template-versions/{self.data.template.header.id}"
            "/design-analyses"
        )

    def body(self) -> dict[str, object]:
        return {
            "applications": [
                {
                    "zoneId": str(item.zone_id),
                    "zoneSizeId": str(item.zone_size_id),
                    "printVersionId": str(item.print_version_id),
                }
                if item.print_version_id
                else {
                    "zoneId": str(item.zone_id),
                    "zoneSizeId": str(item.zone_size_id),
                    "fileId": str(item.file_id),
                }
                for item in self.data.selections
            ]
        }


@pytest.fixture
def analysis_http(http_settings: Settings) -> Iterator[AnalysisHttp]:
    data = analysis_data()
    app = create_app(
        http_settings,
        Ready(),
        template_repository=data.templates,
        analysis_sources=data.sources,
        image_geometry=data.geometry,
    )
    with TestClient(app) as client:
        yield AnalysisHttp(client, data)


def test_analysis_returns_computed_geometry_and_safe_per_unit_money(
    analysis_http: AnalysisHttp,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    data = analysis_http
    response = data.client.post(
        data.path, json=data.body(), headers=admin_headers
    )
    assert response.status_code == 200
    body = response.json()
    assert (
        body["diagnosticOnly"] is True
        and body["catalogCompatibilityVerified"] is False
    )
    assert body["templateActive"] is False and body["minimumDpi"] is None
    assert (
        body["personalizationSurchargeCents"] == 3000
        and body["currency"] == "MXN"
    )
    first, second = body["applications"]
    assert first["placement"] == {
        "xMm": "100.000000",
        "yMm": "175.000000",
        "widthMm": "100.000000",
        "heightMm": "50.000000",
    }
    assert first["effectiveDpi"] == "50.800"
    assert first["resolutionStatus"] == "THRESHOLD_NOT_CONFIGURED"
    assert (
        first["printSurchargeCents"] == 500
        and second["printSurchargeCents"] == 0
    )
    assert data.data.geometry.calls == [data.data.sources.file.id]
    assert (
        response.headers["Cache-Control"] == "no-store"
        and "Location" not in response.headers
    )
    repeated = data.client.post(
        data.path, json=data.body(), headers=admin_headers
    )
    assert repeated.json() == body
    assert len(data.data.templates.records) == 1


def test_configured_low_dpi_warns_without_rejecting(
    analysis_http: AnalysisHttp,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    data = analysis_http.data
    cast(
        FastAPI, analysis_http.client.app
    ).state.design_analysis_service = DesignAnalysisService(
        data.templates, data.sources, data.geometry, 300
    )
    response = analysis_http.client.post(
        analysis_http.path, json=analysis_http.body(), headers=admin_headers
    )
    assert response.status_code == 200 and response.json()["minimumDpi"] == 300
    assert all(
        row["resolutionStatus"] == "INSUFFICIENT"
        for row in response.json()["applications"]
    )


@pytest.mark.parametrize("authenticated,expected", [(False, 401), (True, 403)])
def test_missing_jwt_and_customer_are_rejected_before_reading_originals(
    analysis_http: AnalysisHttp,
    sign_token: Callable[..., str],
    jwks_transport: object,
    authenticated: bool,
    expected: int,
) -> None:
    headers = (
        {"Authorization": "Bearer " + sign_token()} if authenticated else {}
    )
    response = analysis_http.client.post(
        analysis_http.path, headers=headers, json=analysis_http.body()
    )
    assert response.status_code == expected and len(response.json()) == 7
    assert (
        analysis_http.data.sources.calls == 0
        and analysis_http.data.geometry.calls == []
    )


@pytest.mark.parametrize(
    "damage",
    ["both", "neither", "price", "position", "quantity", "threshold", "empty"],
)
def test_client_supplied_prices_geometry_or_threshold_are_not_accepted(
    analysis_http: AnalysisHttp,
    admin_headers: dict[str, str],
    jwks_transport: object,
    damage: str,
) -> None:
    body = analysis_http.body()
    applications = cast(list[dict[str, object]], body["applications"])
    match damage:
        case "both":
            applications[0]["fileId"] = str(uuid4())
        case "neither":
            applications[0].pop("printVersionId")
        case "price":
            applications[0]["surchargeCents"] = 1
        case "position":
            applications[0]["xMm"] = "0"
        case "quantity":
            body["quantity"] = 2
        case "threshold":
            body["minimumDpi"] = 1
        case "empty":
            body["applications"] = []
    response = analysis_http.client.post(
        analysis_http.path, headers=admin_headers, json=body
    )
    assert (
        response.status_code == 422
        and response.json()["code"] == "VALIDATION_ERROR"
    )
    assert analysis_http.data.geometry.calls == []


@pytest.mark.parametrize(
    "failure,status",
    [
        (AnalysisFailure.ZONE_NOT_IN_TEMPLATE, 422),
        (AnalysisFailure.SIZE_NOT_IN_ZONE, 422),
        (AnalysisFailure.DUPLICATE_ZONE_APPLICATION, 422),
        (AnalysisFailure.ANALYSIS_SOURCE_NOT_FOUND, 404),
        (AnalysisFailure.ANALYSIS_SOURCE_NOT_READY, 409),
        (AnalysisFailure.INVALID_IMAGE_GEOMETRY, 409),
        (AnalysisFailure.PERSONALIZATION_AMOUNT_OVERFLOW, 422),
        (AnalysisFailure.ANALYSIS_DATABASE_UNAVAILABLE, 503),
    ],
)
def test_failures_use_problem_details(
    analysis_http: AnalysisHttp,
    admin_headers: dict[str, str],
    jwks_transport: object,
    monkeypatch: pytest.MonkeyPatch,
    failure: AnalysisFailure,
    status: int,
) -> None:
    def failed(*args: object, **kwargs: object) -> object:
        raise DesignAnalysisError(failure)

    monkeypatch.setattr(analysis_http.data.sources, "resolve", failed)
    response = analysis_http.client.post(
        analysis_http.path, headers=admin_headers, json=analysis_http.body()
    )
    assert (
        response.status_code == status
        and response.json()["code"] == failure.value
    )
    assert response.headers["Content-Type"] == "application/problem+json"
    assert (
        len(response.json()) == 7 and analysis_http.data.geometry.calls == []
    )
