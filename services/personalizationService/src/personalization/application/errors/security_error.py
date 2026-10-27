"""Describe authentication and authorization failures without tokens."""

from enum import StrEnum


class SecurityFailure(StrEnum):
    """Stable failures independent of HTTP and the identity provider."""

    INVALID_ACCESS_TOKEN = "INVALID_ACCESS_TOKEN"
    INVALID_APP_ROLE = "INVALID_APP_ROLE"
    KEYS_UNAVAILABLE = "SERVICE_UNAVAILABLE"
    FORBIDDEN = "FORBIDDEN"


class SecurityError(Exception):
    """Carry only a safe failure code across application boundaries."""

    def __init__(self, failure: SecurityFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure
