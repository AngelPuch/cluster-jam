"""Authorize catalog reads and issue short-lived thumbnail links."""

from datetime import UTC, datetime, timedelta
from uuid import UUID

from personalization.application.catalog.catalog_record import (
    CatalogPage,
    CatalogPrint,
)
from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.errors.security_error import (
    SecurityError,
    SecurityFailure,
)
from personalization.application.files.file_record import SignedDownload
from personalization.application.ports.print_catalog_port import (
    PrintCatalogPort,
)
from personalization.application.ports.private_storage_port import (
    PrivateStoragePort,
)
from personalization.application.prints.cursor import (
    decode_cursor,
    encode_cursor,
)
from personalization.application.prints.print_service import validate_limit
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)


def require_catalog_reader(identity: VerifiedIdentity) -> None:
    if identity.app_role not in (AppRole.CLIENT, AppRole.ADMINISTRATOR):
        raise SecurityError(SecurityFailure.FORBIDDEN)


def catalog_cursor(cursor: str | None) -> UUID | None:
    value = decode_cursor(cursor, "print-catalog")
    if value is None:
        return None
    try:
        parsed = UUID(value)
        if str(parsed) != value:
            raise ValueError
        return parsed
    except ValueError:
        raise PrintError(PrintFailure.INVALID_CURSOR) from None


class CatalogService:
    def __init__(
        self,
        repository: PrintCatalogPort,
        storage: PrivateStoragePort,
        ttl: int,
    ) -> None:
        self._repository = repository
        self._storage = storage
        self._ttl = ttl

    def list(
        self,
        identity: VerifiedIdentity,
        limit: int = 20,
        cursor: str | None = None,
    ) -> CatalogPage:
        require_catalog_reader(identity)
        validate_limit(limit)
        rows = self._repository.list(catalog_cursor(cursor), limit + 1)
        more = len(rows) > limit
        items = rows[:limit]
        return CatalogPage(
            items,
            encode_cursor("print-catalog", items[-1].id) if more else None,
        )

    def get(self, identity: VerifiedIdentity, print_id: UUID) -> CatalogPrint:
        require_catalog_reader(identity)
        record = self._repository.get(print_id)
        if record is None:
            raise PrintError(PrintFailure.PRINT_NOT_FOUND)
        return record

    def create_thumbnail_download(
        self,
        identity: VerifiedIdentity,
        print_id: UUID,
        version_id: UUID,
    ) -> SignedDownload:
        record = self.get(identity, print_id)
        if record.version_id != version_id:
            raise PrintError(PrintFailure.PRINT_VERSION_NOT_FOUND)
        self._storage.ensure_private()
        expires = datetime.now(UTC) + timedelta(seconds=self._ttl)
        url = self._storage.sign_download(record.thumbnail, self._ttl)
        return SignedDownload(record.thumbnail.id, expires, url)
