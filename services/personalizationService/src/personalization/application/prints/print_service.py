"""Authorize administrators and validate versioning commands."""

from uuid import UUID

from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.errors.security_error import (
    SecurityError,
    SecurityFailure,
)
from personalization.application.ports.print_repository_port import (
    PrintRepositoryPort,
)
from personalization.application.prints.cursor import (
    encode_cursor,
    print_cursor,
    version_cursor,
)
from personalization.application.prints.print_record import (
    MAX_DESCRIPTION_LENGTH,
    MAX_SURCHARGE_CENTS,
    MAX_VERSION_NUMBER,
    PrintPage,
    PrintRecord,
    PrintVersion,
    PrintVersionPage,
)
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)


def require_administrator(identity: VerifiedIdentity) -> None:
    if identity.app_role is not AppRole.ADMINISTRATOR:
        raise SecurityError(SecurityFailure.FORBIDDEN)


def validate_surcharge(surcharge_cents: int) -> None:
    if type(surcharge_cents) is not int or not (
        0 <= surcharge_cents <= MAX_SURCHARGE_CENTS
    ):
        raise PrintError(PrintFailure.INVALID_PRINT_DATA)


def validate_limit(limit: int) -> None:
    if type(limit) is not int or not 1 <= limit <= 100:
        raise PrintError(PrintFailure.INVALID_PRINT_DATA)


class PrintService:
    def __init__(self, repository: PrintRepositoryPort) -> None:
        self._repository = repository

    def create(
        self,
        identity: VerifiedIdentity,
        name: str,
        description: str | None,
        file_id: UUID,
        surcharge_cents: int,
    ) -> PrintRecord:
        require_administrator(identity)
        validate_surcharge(surcharge_cents)
        name = name.strip()
        if not 1 <= len(name) <= 120 or (
            description is not None
            and len(description) > MAX_DESCRIPTION_LENGTH
        ):
            raise PrintError(PrintFailure.INVALID_PRINT_DATA)
        return self._repository.create(
            identity.user_id, name, description, file_id, surcharge_cents
        )

    def create_version(
        self,
        identity: VerifiedIdentity,
        print_id: UUID,
        expected_version: int,
        file_id: UUID,
        surcharge_cents: int,
    ) -> PrintVersion:
        require_administrator(identity)
        validate_surcharge(surcharge_cents)
        if type(expected_version) is not int or not (
            1 <= expected_version <= MAX_VERSION_NUMBER
        ):
            raise PrintError(PrintFailure.INVALID_PRINT_DATA)
        return self._repository.create_version(
            identity.user_id,
            print_id,
            expected_version,
            file_id,
            surcharge_cents,
        )

    def get(self, identity: VerifiedIdentity, print_id: UUID) -> PrintRecord:
        require_administrator(identity)
        return self._repository.get(print_id)

    def get_version(
        self,
        identity: VerifiedIdentity,
        print_id: UUID,
        version_id: UUID,
    ) -> PrintVersion:
        require_administrator(identity)
        return self._repository.get_version(print_id, version_id)

    def list(
        self,
        identity: VerifiedIdentity,
        limit: int = 20,
        cursor: str | None = None,
    ) -> PrintPage:
        require_administrator(identity)
        validate_limit(limit)
        records = self._repository.list(print_cursor(cursor), limit + 1)
        visible = records[:limit]
        next_cursor = (
            encode_cursor("prints", visible[-1].id)
            if len(records) > limit
            else None
        )
        return PrintPage(visible, next_cursor)

    def list_versions(
        self,
        identity: VerifiedIdentity,
        print_id: UUID,
        limit: int = 20,
        cursor: str | None = None,
    ) -> PrintVersionPage:
        require_administrator(identity)
        validate_limit(limit)
        records = self._repository.list_versions(
            print_id, version_cursor(cursor, print_id), limit + 1
        )
        visible = records[:limit]
        next_cursor = (
            encode_cursor(f"print-versions/{print_id}", visible[-1].number)
            if len(records) > limit
            else None
        )
        return PrintVersionPage(visible, next_cursor)
