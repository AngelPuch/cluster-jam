"""Carry only server-selected catalog records across ports."""

from dataclasses import dataclass
from uuid import UUID

from personalization.application.files.file_record import FileRecord


@dataclass(frozen=True)
class CatalogPrint:
    id: UUID
    name: str
    description: str | None
    version_id: UUID
    version_number: int
    surcharge_cents: int
    thumbnail: FileRecord


@dataclass(frozen=True)
class CatalogPage:
    items: tuple[CatalogPrint, ...]
    next_cursor: str | None
