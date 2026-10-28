"""Fit images without distortion and calculate exact effective DPI."""

from fractions import Fraction

from personalization.application.designs.analysis_record import (
    AnalysisSelection,
    ApplicationAnalysis,
    ImageGeometry,
    Placement,
    ResolutionStatus,
    Target,
)
from personalization.application.errors.design_analysis_error import (
    AnalysisFailure,
    DesignAnalysisError,
)
from personalization.application.images.image_policy import (
    MAX_IMAGE_PIXELS,
    MAX_IMAGE_SIDE_PX,
)
from personalization.application.prints.print_record import MAX_SURCHARGE_CENTS
from personalization.application.templates.template_record import (
    MAX_TEMPLATE_ZONES,
    TemplateRecord,
)


def checked_amount(value: int) -> int:
    if type(value) is not int or not 0 <= value <= MAX_SURCHARGE_CENTS:
        raise DesignAnalysisError(
            AnalysisFailure.PERSONALIZATION_AMOUNT_OVERFLOW
        )
    return value


def resolve_targets(
    template: TemplateRecord, selections: tuple[AnalysisSelection, ...]
) -> tuple[Target, ...]:
    if not 1 <= len(selections) <= MAX_TEMPLATE_ZONES:
        raise DesignAnalysisError(AnalysisFailure.INVALID_DESIGN_ANALYSIS)
    seen: set[object] = set()
    targets: list[Target] = []
    for selection in selections:
        if (selection.print_version_id is None) == (selection.file_id is None):
            raise DesignAnalysisError(AnalysisFailure.INVALID_DESIGN_ANALYSIS)
        if selection.zone_id in seen:
            raise DesignAnalysisError(
                AnalysisFailure.DUPLICATE_ZONE_APPLICATION
            )
        seen.add(selection.zone_id)
        zone = next(
            (zone for zone in template.zones if zone.id == selection.zone_id),
            None,
        )
        if zone is None:
            raise DesignAnalysisError(AnalysisFailure.ZONE_NOT_IN_TEMPLATE)
        size = next(
            (size for size in zone.sizes if size.id == selection.zone_size_id),
            None,
        )
        if size is None:
            raise DesignAnalysisError(AnalysisFailure.SIZE_NOT_IN_ZONE)
        targets.append(Target(selection, zone, size))
    return tuple(targets)


def analyze_application(
    target: Target,
    image: ImageGeometry,
    print_surcharge_cents: int,
    minimum_dpi: int | None,
) -> ApplicationAnalysis:
    if (
        type(image.width_px) is not int
        or type(image.height_px) is not int
        or not 1 <= image.width_px <= MAX_IMAGE_SIDE_PX
        or not 1 <= image.height_px <= MAX_IMAGE_SIDE_PX
        or image.width_px * image.height_px > MAX_IMAGE_PIXELS
    ):
        raise DesignAnalysisError(AnalysisFailure.INVALID_IMAGE_GEOMETRY)
    if minimum_dpi is not None and (
        type(minimum_dpi) is not int or not 1 <= minimum_dpi <= 2400
    ):
        raise DesignAnalysisError(AnalysisFailure.INVALID_DESIGN_ANALYSIS)
    size = target.size.definition
    zone = target.zone.definition
    scale = min(
        Fraction(size.dimensions.width_mm) / image.width_px,
        Fraction(size.dimensions.height_mm) / image.height_px,
    )
    width = image.width_px * scale
    height = image.height_px * scale
    placement = Placement(
        Fraction(zone.x_mm) + (Fraction(zone.dimensions.width_mm) - width) / 2,
        Fraction(zone.y_mm)
        + (Fraction(zone.dimensions.height_mm) - height) / 2,
        width,
        height,
    )
    dpi = Fraction(127, 5) / scale
    status = ResolutionStatus.THRESHOLD_NOT_CONFIGURED
    if minimum_dpi is not None:
        status = (
            ResolutionStatus.INSUFFICIENT
            if dpi < minimum_dpi
            else ResolutionStatus.SUFFICIENT
        )
    zone_amount = checked_amount(size.surcharge_cents)
    print_amount = checked_amount(print_surcharge_cents)
    return ApplicationAnalysis(
        target.selection,
        zone.side,
        image,
        placement,
        dpi,
        status,
        zone_amount,
        print_amount,
        checked_amount(zone_amount + print_amount),
    )
