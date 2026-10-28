"""Verify real JWT guards and administrative REST contracts."""

from collections.abc import Callable, Iterator
from pathlib import Path
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from personalization.application.errors.print_error import PrintFailure
from personalization.bootstrap import create_app
from personalization.infrastructure.config.settings import Settings
from test.files.fakes import MemoryFileRepository
from test.prints.fakes import MemoryPrintRepository

BASE = "/api/v1/admin/prints"


class Ready:
    def is_ready(self) -> bool:
        return True


@pytest.fixture
def print_repository() -> MemoryPrintRepository:
    return MemoryPrintRepository()


@pytest.fixture
def print_client(
    tmp_path: Path,
    print_repository: MemoryPrintRepository,
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
    with TestClient(
        create_app(
            settings,
            Ready(),
            file_repository=MemoryFileRepository(),
            print_repository=print_repository,
        )
    ) as client:
        yield client


@pytest.fixture
def admin_headers(
    sign_token: Callable[..., str],
    claims: dict[str, object],
) -> dict[str, str]:
    payload = {**claims, "app_metadata": {"app_role": "administrador"}}
    return {"Authorization": "Bearer " + sign_token(payload)}


def body() -> dict[str, object]:
    return {
        "name": "Logo",
        "description": None,
        "fileId": str(uuid4()),
        "surchargeCents": 1250,
    }


def test_real_admin_jwt_create_version_history_and_locations(
    print_client: TestClient,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    created = print_client.post(BASE, headers=admin_headers, json=body())
    assert created.status_code == 201
    record = created.json()
    assert record["latestVersion"]["currency"] == "MXN"
    assert record["latestVersion"]["number"] == 1
    assert record["latestVersion"]["surchargeCents"] == 1250
    path = created.headers["Location"]
    assert print_client.get(path, headers=admin_headers).json() == record
    first = record["latestVersion"]
    request = {
        "expectedVersion": 1,
        "fileId": str(uuid4()),
        "surchargeCents": 2000,
    }
    version = print_client.post(
        path + "/versions", headers=admin_headers, json=request
    )
    assert version.status_code == 201
    assert version.json()["number"] == 2
    assert (
        print_client.get(
            version.headers["Location"], headers=admin_headers
        ).json()
        == version.json()
    )
    history = print_client.get(path + "/versions", headers=admin_headers)
    assert history.json() == {
        "items": [first, version.json()],
        "nextCursor": None,
    }
    stale = print_client.post(
        path + "/versions", headers=admin_headers, json=request
    )
    assert stale.status_code == 409
    assert stale.json()["code"] == "PRINT_VERSION_CONFLICT"
    assert len(stale.json()) == 7
    assert version.headers["Cache-Control"] == "no-store"


@pytest.mark.parametrize(
    "method,path,payload",
    [
        ("get", BASE, None),
        ("post", BASE, body()),
        ("get", BASE + "/" + str(UUID(int=1)), None),
        ("get", BASE + "/" + str(UUID(int=1)) + "/versions", None),
        (
            "post",
            BASE + "/" + str(UUID(int=1)) + "/versions",
            {
                "expectedVersion": 1,
                "fileId": str(uuid4()),
                "surchargeCents": 0,
            },
        ),
        (
            "get",
            BASE + "/" + str(UUID(int=1)) + "/versions/" + str(uuid4()),
            None,
        ),
    ],
)
def test_all_endpoints_reject_no_token_and_client_role(
    print_client: TestClient,
    print_repository: MemoryPrintRepository,
    sign_token: Callable[..., str],
    jwks_transport: object,
    method: str,
    path: str,
    payload: dict[str, object] | None,
) -> None:
    anonymous = print_client.request(method, path, json=payload)
    assert anonymous.status_code == 401
    forbidden = print_client.request(
        method,
        path,
        json=payload,
        headers={
            "Authorization": "Bearer " + sign_token(),
            "X-App-Role": "administrador",
        },
    )
    assert forbidden.status_code == 403
    assert print_repository.calls == 0


@pytest.mark.parametrize(
    "field,value",
    [
        ("name", "   "),
        ("name", "x" * 121),
        ("description", "x" * 2001),
        ("surchargeCents", -1),
        ("surchargeCents", 1.5),
        ("surchargeCents", True),
        ("surchargeCents", "1200"),
        ("surchargeCents", 9_007_199_254_740_992),
        ("fileId", "bad-uuid"),
        ("active", True),
        ("actorId", str(uuid4())),
    ],
)
def test_invalid_commands_cannot_write(
    print_client: TestClient,
    print_repository: MemoryPrintRepository,
    admin_headers: dict[str, str],
    jwks_transport: object,
    field: str,
    value: object,
) -> None:
    payload = {**body(), field: value}
    response = print_client.post(BASE, headers=admin_headers, json=payload)
    assert response.status_code == 422
    assert response.headers["Content-Type"].startswith(
        "application/problem+json"
    )
    assert print_repository.calls == 0


def test_snake_case_input_is_not_a_second_wire_contract(
    print_client: TestClient,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    payload = body()
    payload["file_id"] = payload.pop("fileId")
    response = print_client.post(BASE, headers=admin_headers, json=payload)
    assert response.status_code == 422


def test_pagination_and_invalid_query_parameters(
    print_client: TestClient,
    admin_headers: dict[str, str],
    jwks_transport: object,
) -> None:
    for _ in range(3):
        assert (
            print_client.post(
                BASE, headers=admin_headers, json=body()
            ).status_code
            == 201
        )
    first = print_client.get(
        BASE, headers=admin_headers, params={"limit": 2}
    ).json()
    last = print_client.get(
        BASE,
        headers=admin_headers,
        params={
            "limit": 2,
            "cursor": first["nextCursor"],
        },
    ).json()
    assert len(first["items"]) == 2 and len(last["items"]) == 1
    assert last["nextCursor"] is None
    assert (
        print_client.get(
            BASE, headers=admin_headers, params={"limit": 101}
        ).status_code
        == 422
    )
    invalid = print_client.get(
        BASE, headers=admin_headers, params={"cursor": "bad"}
    )
    assert invalid.status_code == 400
    assert invalid.json()["code"] == "INVALID_CURSOR"


@pytest.mark.parametrize(
    "failure,status",
    [
        (PrintFailure.PRINT_NOT_FOUND, 404),
        (PrintFailure.PRINT_VERSION_NOT_FOUND, 404),
        (PrintFailure.PRINT_FILE_NOT_FOUND, 404),
        (PrintFailure.INVALID_PRINT_FILE, 409),
        (PrintFailure.PRINT_VERSION_CONFLICT, 409),
        (PrintFailure.PRINT_VERSION_LIMIT, 409),
        (PrintFailure.PRINT_DATABASE_UNAVAILABLE, 503),
        (PrintFailure.INVALID_PRINT_DATA, 422),
        (PrintFailure.INVALID_CURSOR, 400),
    ],
)
def test_failures_use_safe_correlated_problem_details(
    print_client: TestClient,
    print_repository: MemoryPrintRepository,
    admin_headers: dict[str, str],
    jwks_transport: object,
    failure: PrintFailure,
    status: int,
) -> None:
    print_repository.failure = failure
    response = print_client.get(BASE, headers=admin_headers)
    assert response.status_code == status
    problem = response.json()
    assert len(problem) == 7 and problem["code"] == failure.value
    assert problem["traceId"] == response.headers["traceparent"].split("-")[1]
    assert "SELECT" not in response.text


def test_openapi_contains_only_admin_secured_print_contracts(
    print_client: TestClient,
) -> None:
    schema = print_client.get("/openapi.json").json()
    assert "/api/v1/prints" not in schema["paths"]
    for path, methods in schema["paths"].items():
        if path.startswith(BASE):
            for operation in methods.values():
                assert operation["security"]
                assert (
                    "application/problem+json"
                    in (operation["responses"]["403"]["content"])
                )
    assert (
        "fileId"
        in schema["components"]["schemas"]["CreatePrintRequest"]["properties"]
    )
