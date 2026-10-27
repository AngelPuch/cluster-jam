"""Validate signed user tokens with a bounded, reusable JWKS cache."""

import json
import math
from uuid import UUID

import jwt
from jwt import PyJWKClient
from jwt.exceptions import (
    InvalidKeyError,
    InvalidTokenError,
    PyJWKClientConnectionError,
    PyJWKClientError,
    PyJWKSetError,
)

from personalization.application.errors.security_error import (
    SecurityError,
    SecurityFailure,
)
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)

ALLOWED_ALGORITHMS = ("ES256", "RS256")
JWKS_CACHE_SECONDS = 600
JWKS_TIMEOUT_SECONDS = 5
JWKS_REFRESH_COOLDOWN_SECONDS = 30


class SupabaseJwtVerifier:
    """Reuse public signing keys without retrieving user sessions."""

    def __init__(self, issuer: str, jwks_url: str) -> None:
        self._issuer = issuer
        self._keys = PyJWKClient(
            jwks_url,
            cache_jwk_set=True,
            lifespan=JWKS_CACHE_SECONDS,
            cache_keys=False,
            timeout=JWKS_TIMEOUT_SECONDS,
            cooldown_duration=JWKS_REFRESH_COOLDOWN_SECONDS,
        )

    def verify(self, access_token: str) -> VerifiedIdentity:
        """Verify signature and claims before extracting permissions."""
        try:
            header = jwt.get_unverified_header(access_token)
        except InvalidTokenError:
            raise SecurityError(SecurityFailure.INVALID_ACCESS_TOKEN) from None
        algorithm = header.get("alg")
        key_id = header.get("kid")
        if algorithm not in ALLOWED_ALGORITHMS or not isinstance(key_id, str):
            raise SecurityError(SecurityFailure.INVALID_ACCESS_TOKEN)
        if not key_id:
            raise SecurityError(SecurityFailure.INVALID_ACCESS_TOKEN)
        try:
            key = self._keys.get_signing_key(key_id)
        except PyJWKClientConnectionError, PyJWKSetError, json.JSONDecodeError:
            raise SecurityError(SecurityFailure.KEYS_UNAVAILABLE) from None
        except PyJWKClientError:
            raise SecurityError(SecurityFailure.INVALID_ACCESS_TOKEN) from None
        if key.algorithm_name != algorithm:
            raise SecurityError(SecurityFailure.INVALID_ACCESS_TOKEN)
        try:
            claims: dict[str, object] = jwt.decode(
                access_token,
                key.key,
                algorithms=list(ALLOWED_ALGORITHMS),
                issuer=self._issuer,
                audience="authenticated",
                options={"require": ["sub", "exp", "iss", "aud"]},
            )
        except (
            InvalidTokenError,
            InvalidKeyError,
            TypeError,
            ValueError,
            OverflowError,
        ):
            raise SecurityError(SecurityFailure.INVALID_ACCESS_TOKEN) from None
        subject = claims.get("sub")
        expiration = claims.get("exp")
        anonymous = claims.get("is_anonymous", False)
        if (
            claims.get("role") != "authenticated"
            or anonymous is not False
            or not isinstance(subject, str)
            or not isinstance(expiration, (int, float))
            or isinstance(expiration, bool)
        ):
            raise SecurityError(SecurityFailure.INVALID_ACCESS_TOKEN)
        try:
            if not math.isfinite(expiration):
                raise ValueError("Invalid expiration")
            user_id = UUID(subject)
        except ValueError, OverflowError:
            raise SecurityError(SecurityFailure.INVALID_ACCESS_TOKEN) from None
        metadata = claims.get("app_metadata")
        role = metadata.get("app_role") if isinstance(metadata, dict) else None
        if not isinstance(role, str):
            raise SecurityError(SecurityFailure.INVALID_APP_ROLE)
        try:
            app_role = AppRole(role)
        except ValueError, TypeError:
            raise SecurityError(SecurityFailure.INVALID_APP_ROLE) from None
        return VerifiedIdentity(user_id=user_id, app_role=app_role)
