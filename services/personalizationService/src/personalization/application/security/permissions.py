"""Apply ownership policy to owner IDs obtained by the server."""

from uuid import UUID

from personalization.application.errors.security_error import (
    SecurityError,
    SecurityFailure,
)
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)


def require_resource_owner(
    identity: VerifiedIdentity,
    owner_id: UUID,
    *,
    allow_administrator: bool = False,
) -> None:
    """Require ownership or an explicitly permitted admin exception."""
    if identity.user_id == owner_id:
        return
    if allow_administrator and identity.app_role is AppRole.ADMINISTRATOR:
        return
    raise SecurityError(SecurityFailure.FORBIDDEN)
