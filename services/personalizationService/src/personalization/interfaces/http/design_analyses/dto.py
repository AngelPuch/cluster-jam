"""Format approximate display values from exact business math."""

from decimal import ROUND_HALF_EVEN, Decimal, localcontext
from fractions import Fraction
from typing import Annotated, Literal, Self
from uuid import UUID

from pydantic import ConfigDict, Field, model_validator

from personalization.application.designs.analysis_record import (
    AnalysisSelection,
    DesignAnalysis,
    ResolutionStatus,
)
from personalization.application.templates.template_record import Side
from personalization.interfaces.http.dto.rest_model import RestModel


class SelectionRequest(RestModel):
    model_config = ConfigDict(
        populate_by_name=False, validate_by_name=False, validate_by_alias=True
    )
    zone_id: UUID
    zone_size_id: UUID
    print_version_id: UUID | None = None
    file_id: UUID | None = None

    @model_validator(mode="after")
    def exclusive_source(self) -> Self:
        if (self.print_version_id is None) == (self.file_id is None):
            raise ValueError("Choose exactly one immutable print or original")
        return self

    def selection(self) -> AnalysisSelection:
        return AnalysisSelection(
            self.zone_id,
            self.zone_size_id,
            self.print_version_id,
            self.file_id,
        )


class AnalysisRequest(RestModel):
    applications: Annotated[
        list[SelectionRequest], Field(min_length=1, max_length=20)
    ]


def decimal_display(value: Fraction, places: int) -> str:
    with localcontext() as context:
        context.prec = 60
        context.rounding = ROUND_HALF_EVEN
        result = Decimal(value.numerator) / Decimal(value.denominator)
        return format(result.quantize(Decimal(1).scaleb(-places)), "f")


class PlacementResponse(RestModel):
    x_mm: str
    y_mm: str
    width_mm: str
    height_mm: str


class ApplicationResponse(RestModel):
    zone_id: UUID
    zone_size_id: UUID
    print_version_id: UUID | None
    file_id: UUID | None
    side: Side
    image_width_px: int
    image_height_px: int
    placement: PlacementResponse
    effective_dpi: str
    resolution_status: ResolutionStatus
    zone_surcharge_cents: int
    print_surcharge_cents: int
    total_surcharge_cents: int


class AnalysisResponse(RestModel):
    template_id: UUID
    template_active: bool
    diagnostic_only: Literal[True] = True
    catalog_compatibility_verified: Literal[False] = False
    approximate: Literal[True] = True
    minimum_dpi: int | None
    currency: Literal["MXN"] = "MXN"
    applications: list[ApplicationResponse]
    personalization_surcharge_cents: int

    @classmethod
    def from_record(cls, record: DesignAnalysis) -> AnalysisResponse:
        applications = []
        for item in record.applications:
            position = item.placement
            applications.append(
                ApplicationResponse(
                    zone_id=item.selection.zone_id,
                    zone_size_id=item.selection.zone_size_id,
                    print_version_id=item.selection.print_version_id,
                    file_id=item.selection.file_id,
                    side=item.side,
                    image_width_px=item.geometry.width_px,
                    image_height_px=item.geometry.height_px,
                    placement=PlacementResponse(
                        x_mm=decimal_display(position.x_mm, 6),
                        y_mm=decimal_display(position.y_mm, 6),
                        width_mm=decimal_display(position.width_mm, 6),
                        height_mm=decimal_display(position.height_mm, 6),
                    ),
                    effective_dpi=decimal_display(item.effective_dpi, 3),
                    resolution_status=item.resolution_status,
                    zone_surcharge_cents=item.zone_surcharge_cents,
                    print_surcharge_cents=item.print_surcharge_cents,
                    total_surcharge_cents=item.total_surcharge_cents,
                )
            )
        return cls(
            template_id=record.template_id,
            template_active=record.template_active,
            minimum_dpi=record.minimum_dpi,
            applications=applications,
            personalization_surcharge_cents=record.personalization_surcharge_cents,
        )
