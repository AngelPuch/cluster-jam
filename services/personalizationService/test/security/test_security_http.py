"""Test role and ownership guards through real HTTP dependencies."""

import logging
from collections.abc import Callable, Iterator
from io import StringIO
from pathlib import Path
from typing import Annotated, Protocol
from uuid import UUID

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

import personalization.bootstrap as bootstrap
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from personalization.application.security.permissions import (
    require_resource_owner,
)
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.observability.logging_config import (
    configure_logging,
)
from personalization.interfaces.http.dto.rest_model import RestModel
from personalization.interfaces.http.openapi import configure_openapi
from personalization.interfaces.http.security import (
    SECURITY_PROBLEM_RESPONSES,
    require_roles,
)

OWNER = UUID("11111111-1111-4111-8111-111111111111")
OTHER = UUID("22222222-2222-4222-8222-222222222222")
BASE = "/api/v1/security-fixture"


class Transport(Protocol):
    calls: int
    unavailable: bool


class Ready:
    def is_ready(self) -> bool:
        return True


class IdentityResponse(RestModel):
    user_id: UUID
    app_role: AppRole


@pytest.fixture
def security_logs() -> StringIO:
    return StringIO()


@pytest.fixture
def security_client(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    security_logs: StringIO,
) -> Iterator[TestClient]:
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

    def test_logging(*, environment: str, log_level: str) -> None:
        configure_logging(environment=environment, log_level=log_level)
        for handler in logging.getLogger("personalization").handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setStream(security_logs)

    monkeypatch.setattr(bootstrap, "configure_logging", test_logging)
    app = bootstrap.create_app(settings, Ready())
    add_fixture_routes(app)
    configure_openapi(app)
    with TestClient(app) as client:
        yield client


def add_fixture_routes(app: FastAPI) -> None:
    """Keep demonstration routes exclusively in the test suite."""

    @app.get(BASE + "/admin", responses=SECURITY_PROBLEM_RESPONSES)
    def admin(
        identity: Annotated[
            VerifiedIdentity, Depends(require_roles(AppRole.ADMINISTRATOR))
        ],
    ) -> IdentityResponse:
        return IdentityResponse(
            user_id=identity.user_id, app_role=identity.app_role
        )

    @app.get(BASE + "/owner")
    def owner(
        identity: Annotated[
            VerifiedIdentity,
            Depends(require_roles(AppRole.CLIENT, AppRole.ADMINISTRATOR)),
        ],
    ) -> IdentityResponse:
        require_resource_owner(identity, OWNER)
        return IdentityResponse(
            user_id=identity.user_id, app_role=identity.app_role
        )

    @app.get(BASE + "/admin-exception")
    def admin_exception(
        identity: Annotated[
            VerifiedIdentity,
            Depends(require_roles(AppRole.CLIENT, AppRole.ADMINISTRATOR)),
        ],
    ) -> dict[str, str]:
        require_resource_owner(identity, OWNER, allow_administrator=True)
        return {"status": "ok"}

    @app.get(BASE + "/no-policy")
    def no_policy(
        identity: Annotated[VerifiedIdentity, Depends(require_roles())],
    ) -> dict[str, str]:
        return {"status": "unexpected"}


@pytest.mark.parametrize("authorization", [None, "Basic abc", "Bearer bad"])
def test_missing_or_invalid_token_problem(
    security_client: TestClient,
    authorization: str | None,
) -> None:
    headers = {} if authorization is None else {"Authorization": authorization}
    response = security_client.get(BASE + "/admin", headers=headers)
    assert response.status_code == 401
    assert response.headers["WWW-Authenticate"] == "Bearer"
    assert response.headers["content-type"] == "application/problem+json"
    body = response.json()
    assert set(body) == {
        "type",
        "title",
        "status",
        "detail",
        "instance",
        "code",
        "traceId",
    }
    assert body["code"] == "INVALID_ACCESS_TOKEN"
    assert body["traceId"] == response.headers["traceparent"].split("-")[1]


def test_admin_identity_is_trusted_and_camel_case(
    security_client: TestClient,
    claims: dict[str, object],
    sign_token: Callable[..., str],
    jwks_transport: Transport,
) -> None:
    claims["app_metadata"] = {"app_role": "administrador"}
    response = security_client.get(
        BASE + "/admin",
        headers={"Authorization": "Bearer " + sign_token(claims)},
    )
    assert response.status_code == 200
    assert response.json() == {
        "userId": str(OWNER),
        "appRole": "administrador",
    }


@pytest.mark.parametrize(
    ("path", "subject", "role", "status", "code"),
    [
        ("/admin", OWNER, "cliente", 403, "FORBIDDEN"),
        ("/admin", OWNER, "superadmin", 403, "INVALID_APP_ROLE"),
        ("/owner", OWNER, "cliente", 200, None),
        ("/owner", OTHER, "cliente", 403, "FORBIDDEN"),
        ("/owner", OTHER, "administrador", 403, "FORBIDDEN"),
        ("/admin-exception", OTHER, "administrador", 200, None),
        ("/no-policy", OWNER, "administrador", 403, "FORBIDDEN"),
    ],
)
def test_explicit_role_and_server_ownership_policies(
    security_client: TestClient,
    claims: dict[str, object],
    sign_token: Callable[..., str],
    jwks_transport: Transport,
    path: str,
    subject: UUID,
    role: str,
    status: int,
    code: str | None,
) -> None:
    claims.update({"sub": str(subject), "app_metadata": {"app_role": role}})
    response = security_client.get(
        BASE + path,
        headers={
            "Authorization": "Bearer " + sign_token(claims),
            "X-App-Role": "administrador",
            "X-User-ID": str(OWNER),
        },
    )
    assert response.status_code == status
    if code:
        assert response.json()["code"] == code
        assert "WWW-Authenticate" not in response.headers


def test_duplicate_credentials_are_rejected(
    security_client: TestClient,
    sign_token: Callable[..., str],
    jwks_transport: Transport,
) -> None:
    response = security_client.get(
        BASE + "/owner",
        headers=[
            ("Authorization", "Bearer " + sign_token()),
            ("Authorization", "Bearer " + sign_token()),
        ],
    )
    assert response.status_code == 401
    assert jwks_transport.calls == 0


def test_jwks_outage_is_safe_and_technical_routes_stay_public(
    security_client: TestClient,
    sign_token: Callable[..., str],
    jwks_transport: Transport,
    security_logs: StringIO,
) -> None:
    jwks_transport.unavailable = True
    token = sign_token()
    response = security_client.get(
        BASE + "/owner?token=private-query",
        headers={"Authorization": "Bearer " + token},
    )
    assert response.status_code == 503
    assert response.json()["code"] == "SERVICE_UNAVAILABLE"
    assert response.json()["instance"] == BASE + "/owner"
    for path in ("/health/live", "/health/ready", "/docs", "/openapi.json"):
        assert security_client.get(path).status_code == 200
    assert jwks_transport.calls == 1
    output = security_logs.getvalue() + response.text
    assert token not in output
    assert "private-provider-detail" not in output
    assert "private-query" not in output


def test_protected_openapi_documents_bearer_and_problem_responses(
    security_client: TestClient,
    jwks_transport: Transport,
) -> None:
    document = security_client.get("/openapi.json").json()
    operation = document["paths"][BASE + "/admin"]["get"]
    assert operation["security"] == [{"supabase-jwt": []}]
    for status in ("401", "403", "503"):
        assert (
            "application/problem+json"
            in operation["responses"][status]["content"]
        )
    assert "security" not in document["paths"]["/health/live"]["get"]
    assert jwks_transport.calls == 0
