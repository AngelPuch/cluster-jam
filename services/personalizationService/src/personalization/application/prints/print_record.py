"""Carry immutable administrative print views across ports."""

from dataclasses import dataclass
from uuid import UUID

MAX_SURCHARGE_CENTS = 9_007_199_254_740_991
MAX_VERSION_NUMBER = 2_147_483_647
MAX_DESCRIPTION_LENGTH = 2000


@dataclass(frozen=True)
class PrintVersion:
    id: UUID
    print_id: UUID
    number: int
    file_id: UUID
    surcharge_cents: int


@dataclass(frozen=True)
class PrintRecord:
    id: UUID
    name: str
    description: str | None
    active: bool
    latest_version: PrintVersion


@dataclass(frozen=True)
class PrintPage:
    items: tuple[PrintRecord, ...]
    next_cursor: str | None


@dataclass(frozen=True)
class PrintVersionPage:
    items: tuple[PrintVersion, ...]
    next_cursor: str | None
