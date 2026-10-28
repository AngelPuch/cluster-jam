"""Represent exact millimeters independently of HTTP and SQL."""

from dataclasses import dataclass
from decimal import Decimal
from enum import StrEnum
from uuid import UUID

MAX_TEMPLATE_ZONES = 20
MAX_MEASUREMENT_MM = Decimal("10000")
MEASUREMENT_QUANTUM = Decimal("0.001")


class Side(StrEnum):
    FRONT = "FRONT"
    BACK = "BACK"


class SizeLabel(StrEnum):
    SMALL = "SMALL"
    MEDIUM = "MEDIUM"
    LARGE = "LARGE"


@dataclass(frozen=True)
class Dimensions:
    width_mm: Decimal
    height_mm: Decimal


@dataclass(frozen=True)
class SizeDefinition:
    label: SizeLabel
    dimensions: Dimensions
    surcharge_cents: int


@dataclass(frozen=True)
class ZoneDefinition:
    code: str
    side: Side
    x_mm: Decimal
    y_mm: Decimal
    dimensions: Dimensions
    sizes: tuple[SizeDefinition, ...]


@dataclass(frozen=True)
class TemplateDefinition:
    front: Dimensions
    back: Dimensions
    zones: tuple[ZoneDefinition, ...]


@dataclass(frozen=True)
class SizeRecord:
    id: UUID
    definition: SizeDefinition


@dataclass(frozen=True)
class ZoneRecord:
    id: UUID
    definition: ZoneDefinition
    sizes: tuple[SizeRecord, ...]


@dataclass(frozen=True)
class TemplateHeader:
    id: UUID
    product_id: UUID
    size_id: int
    number: int
    front: Dimensions
    back: Dimensions
    active: bool


@dataclass(frozen=True)
class TemplateRecord:
    header: TemplateHeader
    zones: tuple[ZoneRecord, ...]


@dataclass(frozen=True)
class TemplatePage:
    items: tuple[TemplateHeader, ...]
    next_cursor: str | None
