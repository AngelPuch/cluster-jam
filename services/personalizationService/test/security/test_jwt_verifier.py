"""Exercise the actual crypto verifier, claims, cache, and rotation."""

import json
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import Protocol
from uuid import UUID

import jwt
import pytest

from personalization.application.errors.security_error import (
    SecurityError,
    SecurityFailure,
)
from personalization.application.security.identity import AppRole
from personalization.infrastructure.security.supabase_jwt_verifier import (
    SupabaseJwtVerifier,
)

ISSUER = "https://supabase.example.test/auth/v1"


class Transport(Protocol):
    calls: int
    unavailable: bool
    malformed: bool
    keys: list[dict[str, object]]


@pytest.fixture
def verifier() -> SupabaseJwtVerifier:
    return SupabaseJwtVerifier(ISSUER, ISSUER + "/.well-known/jwks.json")


@pytest.mark.parametrize("algorithm", ["ES256", "RS256"])
def test_valid_asymmetric_signatures(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    jwks_transport: Transport,
    algorithm: str,
) -> None:
    identity = verifier.verify(sign_token(algorithm=algorithm))
    assert identity.user_id == UUID("11111111-1111-4111-8111-111111111111")
    assert identity.app_role is AppRole.CLIENT
    assert jwks_transport.calls == 1


@pytest.mark.parametrize("claim", ["sub", "exp", "iss", "aud"])
def test_missing_required_claim(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: Transport,
    claim: str,
) -> None:
    del claims[claim]
    with pytest.raises(SecurityError) as caught:
        verifier.verify(sign_token(claims))
    assert caught.value.failure is SecurityFailure.INVALID_ACCESS_TOKEN


@pytest.mark.parametrize(
    ("claim", "value"),
    [
        ("sub", "not-a-uuid"),
        ("sub", 123),
        ("exp", 1),
        ("exp", "9999999999"),
        ("exp", True),
        ("exp", float("inf")),
        ("exp", float("nan")),
        ("iss", "https://another.example/auth/v1"),
        ("aud", "service_role"),
        ("role", "service_role"),
        ("role", None),
        ("is_anonymous", True),
        ("is_anonymous", "false"),
        ("nbf", 9999999999),
    ],
)
def test_invalid_user_claims(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: Transport,
    claim: str,
    value: object,
) -> None:
    claims[claim] = value
    with pytest.raises(SecurityError) as caught:
        verifier.verify(sign_token(claims))
    assert caught.value.failure is SecurityFailure.INVALID_ACCESS_TOKEN


@pytest.mark.parametrize(
    "metadata",
    [
        None,
        {},
        {"app_role": "Administrador"},
        {"app_role": "superadmin"},
        {"app_role": ["cliente"]},
        {"app_role": None},
        "administrador",
    ],
)
def test_only_protected_application_roles_are_accepted(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: Transport,
    metadata: object,
) -> None:
    claims["app_metadata"] = metadata
    claims["user_metadata"] = {"app_role": "administrador"}
    with pytest.raises(SecurityError) as caught:
        verifier.verify(sign_token(claims))
    assert caught.value.failure is SecurityFailure.INVALID_APP_ROLE


def test_untrusted_metadata_cannot_elevate_client(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: Transport,
) -> None:
    claims["user_metadata"] = {"app_role": "administrador"}
    claims["aud"] = ["authenticated", "another-audience"]
    assert verifier.verify(sign_token(claims)).app_role is AppRole.CLIENT


@pytest.mark.parametrize("algorithm", ["HS256", "none"])
def test_symmetric_and_unsigned_tokens_never_fetch_keys(
    verifier: SupabaseJwtVerifier,
    claims: dict[str, object],
    jwks_transport: Transport,
    algorithm: str,
) -> None:
    token = jwt.encode(
        claims,
        "a" * 64 if algorithm == "HS256" else "",
        algorithm=algorithm,
        headers={"kid": "ES256"},
    )
    with pytest.raises(SecurityError) as caught:
        verifier.verify(token)
    assert caught.value.failure is SecurityFailure.INVALID_ACCESS_TOKEN
    assert jwks_transport.calls == 0


@pytest.mark.parametrize("token", ["invalid", "a.b.c", "", "Bearer a.b.c"])
def test_malformed_tokens_are_safe(
    verifier: SupabaseJwtVerifier,
    jwks_transport: Transport,
    token: str,
) -> None:
    with pytest.raises(SecurityError) as caught:
        verifier.verify(token)
    assert caught.value.failure is SecurityFailure.INVALID_ACCESS_TOKEN
    assert jwks_transport.calls == 0


def test_forged_signature_is_rejected(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    jwks_transport: Transport,
) -> None:
    token = sign_token(rotated=True, kid="ES256")
    with pytest.raises(SecurityError) as caught:
        verifier.verify(token)
    assert caught.value.failure is SecurityFailure.INVALID_ACCESS_TOKEN


def test_cache_serves_parallel_requests_with_one_download(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    jwks_transport: Transport,
) -> None:
    token = sign_token()
    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(verifier.verify, [token] * 32))
    assert len(results) == 32
    assert jwks_transport.calls == 1


def test_rotation_and_unknown_kid_refresh_cooldown(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    jwks_transport: Transport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [time.monotonic()]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    rotated_key = jwks_transport.keys.pop()
    verifier.verify(sign_token())
    with pytest.raises(SecurityError) as caught:
        verifier.verify(sign_token(rotated=True))
    assert caught.value.failure is SecurityFailure.INVALID_ACCESS_TOKEN
    assert jwks_transport.calls == 1
    jwks_transport.keys.append(rotated_key)
    clock[0] += 31
    verifier.verify(sign_token(rotated=True))
    assert jwks_transport.calls == 2


def test_cache_expiration_removes_retired_keys(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    jwks_transport: Transport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [time.monotonic()]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    token = sign_token()
    verifier.verify(token)
    jwks_transport.keys = [
        key for key in jwks_transport.keys if key["kid"] != "ES256"
    ]
    clock[0] += 601
    with pytest.raises(SecurityError) as caught:
        verifier.verify(token)
    assert caught.value.failure is SecurityFailure.INVALID_ACCESS_TOKEN
    assert jwks_transport.calls == 2


def test_warm_cache_survives_outage_until_ttl(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    jwks_transport: Transport,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    clock = [time.monotonic()]
    monkeypatch.setattr(time, "monotonic", lambda: clock[0])
    token = sign_token()
    verifier.verify(token)
    jwks_transport.unavailable = True
    verifier.verify(token)
    assert jwks_transport.calls == 1
    clock[0] += 601
    with pytest.raises(SecurityError) as caught:
        verifier.verify(token)
    assert caught.value.failure is SecurityFailure.KEYS_UNAVAILABLE


@pytest.mark.parametrize("failure", ["unavailable", "malformed", "empty"])
def test_cold_provider_failure_is_service_unavailable(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    jwks_transport: Transport,
    failure: str,
) -> None:
    if failure == "empty":
        jwks_transport.keys = []
    else:
        setattr(jwks_transport, failure, True)
    with pytest.raises(SecurityError) as caught:
        verifier.verify(sign_token())
    assert caught.value.failure is SecurityFailure.KEYS_UNAVAILABLE
    assert "private-provider-detail" not in str(caught.value)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("kid", ""),
        ("kid", None),
        ("alg", "RS256"),
    ],
)
def test_invalid_header_or_key_algorithm(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    jwks_transport: Transport,
    field: str,
    value: object,
) -> None:
    token = sign_token()
    header = jwt.get_unverified_header(token)
    header[field] = value
    encoded = jwt.utils.base64url_encode(json.dumps(header).encode()).decode()
    altered = ".".join([encoded, *token.split(".")[1:]])
    with pytest.raises(SecurityError) as caught:
        verifier.verify(altered)
    assert caught.value.failure is SecurityFailure.INVALID_ACCESS_TOKEN


def test_modified_payload_cannot_grant_admin_role(
    verifier: SupabaseJwtVerifier,
    sign_token: Callable[..., str],
    jwks_transport: Transport,
    claims: dict[str, object],
) -> None:
    token = sign_token()
    claims["app_metadata"] = {"app_role": "administrador"}
    payload = jwt.utils.base64url_encode(json.dumps(claims).encode()).decode()
    header, _, signature = token.split(".")
    altered = ".".join([header, payload, signature])
    with pytest.raises(SecurityError) as caught:
        verifier.verify(altered)
    assert caught.value.failure is SecurityFailure.INVALID_ACCESS_TOKEN
