"""Sign real tokens and replace only the remote JWKS transport."""

import copy
import io
import json
import time
import urllib.error
import urllib.request
from collections.abc import Callable

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

ISSUER = "https://supabase.example.test/auth/v1"
USER_ID = "11111111-1111-4111-8111-111111111111"


class JwksTransport:
    """Expose public keys without providing an Auth user endpoint."""

    def __init__(self, keys: list[dict[str, object]]) -> None:
        self.keys = keys
        self.calls = 0
        self.unavailable = False
        self.malformed = False
        self.urls: list[str] = []

    def open(
        self, request: urllib.request.Request, timeout: float
    ) -> io.BytesIO:
        self.calls += 1
        self.urls.append(request.full_url)
        assert request.full_url == ISSUER + "/.well-known/jwks.json"
        assert timeout == 5
        if self.unavailable:
            raise urllib.error.URLError("private-provider-detail")
        payload = (
            b"invalid-json"
            if self.malformed
            else json.dumps({"keys": self.keys}).encode()
        )
        return io.BytesIO(payload)


@pytest.fixture(scope="session")
def signing_keys() -> dict[
    str, ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey
]:
    return {
        "ES256": ec.generate_private_key(ec.SECP256R1()),
        "RS256": rsa.generate_private_key(65537, 2048),
        "rotated": ec.generate_private_key(ec.SECP256R1()),
    }


@pytest.fixture
def claims() -> dict[str, object]:
    return {
        "sub": USER_ID,
        "iss": ISSUER,
        "aud": "authenticated",
        "exp": int(time.time()) + 300,
        "role": "authenticated",
        "is_anonymous": False,
        "app_metadata": {"app_role": "cliente"},
    }


@pytest.fixture
def sign_token(
    signing_keys: dict[str, ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey],
    claims: dict[str, object],
) -> Callable[..., str]:
    def sign(
        payload: dict[str, object] | None = None,
        *,
        algorithm: str = "ES256",
        kid: str | None = None,
        rotated: bool = False,
    ) -> str:
        key = signing_keys["rotated" if rotated else algorithm]
        return jwt.encode(
            copy.deepcopy(payload if payload is not None else claims),
            key,
            algorithm=algorithm,
            headers={"kid": kid or ("rotated" if rotated else algorithm)},
        )

    return sign


@pytest.fixture
def jwks_transport(
    signing_keys: dict[str, ec.EllipticCurvePrivateKey | rsa.RSAPrivateKey],
    monkeypatch: pytest.MonkeyPatch,
) -> JwksTransport:
    keys = []
    for name, key in signing_keys.items():
        algorithm = "RS256" if name == "RS256" else "ES256"
        jwk = json.loads(
            jwt.get_algorithm_by_name(algorithm).to_jwk(key.public_key())
        )
        jwk.update({"kid": name, "alg": algorithm, "use": "sig"})
        keys.append(jwk)
    transport = JwksTransport(keys)

    def build_opener(*handlers: object) -> JwksTransport:
        return transport

    monkeypatch.setattr(urllib.request, "build_opener", build_opener)
    return transport
