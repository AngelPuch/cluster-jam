"""Use exact fractions for physical geometry and integer cents."""

from dataclasses import dataclass
from enum import StrEnum
from fractions import Fraction
from uuid import UUID

from personalization.application.files.file_record import FileRecord
from personalization.application.templates.template_record import (
    Side,
    SizeRecord,
    ZoneRecord,
)


@dataclass(frozen=True)
class AnalysisSelection:
    zone_id: UUID
    zone_size_id: UUID
    print_version_id: UUID | None = None
    file_id: UUID | None = None


@dataclass(frozen=True)
class ResolvedSource:
    file: FileRecord
    print_surcharge_cents: int


@dataclass(frozen=True)
class ImageGeometry:
    width_px: int
    height_px: int


@dataclass(frozen=True)
class Target:
    selection: AnalysisSelection
    zone: ZoneRecord
    size: SizeRecord


@dataclass(frozen=True)
class Placement:
    x_mm: Fraction
    y_mm: Fraction
    width_mm: Fraction
    height_mm: Fraction


class ResolutionStatus(StrEnum):
    THRESHOLD_NOT_CONFIGURED = "THRESHOLD_NOT_CONFIGURED"
    SUFFICIENT = "SUFFICIENT"
    INSUFFICIENT = "INSUFFICIENT"


@dataclass(frozen=True)
class ApplicationAnalysis:
    selection: AnalysisSelection
    side: Side
    geometry: ImageGeometry
    placement: Placement
    effective_dpi: Fraction
    resolution_status: ResolutionStatus
    zone_surcharge_cents: int
    print_surcharge_cents: int
    total_surcharge_cents: int


@dataclass(frozen=True)
class DesignAnalysis:
    template_id: UUID
    template_active: bool
    minimum_dpi: int | None
    applications: tuple[ApplicationAnalysis, ...]
    personalization_surcharge_cents: int
