"""Read published current versions with their available thumbnails."""

from typing import Protocol
from uuid import UUID

from personalization.application.catalog.catalog_record import CatalogPrint


class PrintCatalogPort(Protocol):
    def list(
        self, after: UUID | None, limit: int
    ) -> tuple[CatalogPrint, ...]: ...

    def get(self, print_id: UUID) -> CatalogPrint | None: ...
