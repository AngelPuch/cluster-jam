"""Authenticate HTTP requests and require explicit role policies."""

from collections.abc import Callable
from typing import Annotated, cast

from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from personalization.application.errors.security_error import (
    SecurityError,
    SecurityFailure,
)
from personalization.application.ports.access_token_verifier_port import (
    AccessTokenVerifierPort,
)
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)

bearer = HTTPBearer(
    auto_error=False,
    scheme_name="supabase-jwt",
    description="Supabase access token with a protected application role",
)

SECURITY_PROBLEM_RESPONSES: dict[int | str, dict[str, object]] = {
    status: {
        "description": description,
        "content": {
            "application/problem+json": {
                "schema": {"$ref": "#/components/schemas/ProblemDetails"}
            }
        },
    }
    for status, description in (
        (401, "Missing or invalid user access token"),
        (403, "Invalid application role or insufficient permission"),
        (503, "Required public signing keys are unavailable"),
    )
}


def get_access_token_verifier(request: Request) -> AccessTokenVerifierPort:
    """Resolve the verifier initialized during startup."""
    return cast(
        AccessTokenVerifierPort, request.app.state.access_token_verifier
    )


def current_identity(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None, Depends(bearer)
    ],
    verifier: Annotated[
        AccessTokenVerifierPort, Depends(get_access_token_verifier)
    ],
) -> VerifiedIdentity:
    """Run potentially blocking JWKS work in FastAPI's thread pool."""
    if len(request.headers.getlist("Authorization")) != 1:
        raise SecurityError(SecurityFailure.INVALID_ACCESS_TOKEN)
    if credentials is None or any(
        character.isspace() for character in credentials.credentials
    ):
        raise SecurityError(SecurityFailure.INVALID_ACCESS_TOKEN)
    return verifier.verify(credentials.credentials)


def require_roles(
    *roles: AppRole,
) -> Callable[..., VerifiedIdentity]:
    """Require a verified actor and an explicit role allowlist."""

    def allowed(
        identity: Annotated[VerifiedIdentity, Depends(current_identity)],
    ) -> VerifiedIdentity:
        if not roles or identity.app_role not in roles:
            raise SecurityError(SecurityFailure.FORBIDDEN)
        return identity

    return allowed
