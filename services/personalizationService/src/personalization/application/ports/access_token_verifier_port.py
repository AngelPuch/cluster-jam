"""Define local token verification without coupling business to JWT."""

from typing import Protocol

from personalization.application.security.identity import VerifiedIdentity


class AccessTokenVerifierPort(Protocol):
    """Verify a token before exposing a trusted identity."""

    def verify(self, access_token: str) -> VerifiedIdentity:
        """Return a trusted actor or raise a sanitized SecurityError."""
        ...
