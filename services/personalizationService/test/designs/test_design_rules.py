"""Check exact placement, DPI boundaries and safe integer money."""

from dataclasses import replace
from decimal import Decimal
from fractions import Fraction
from uuid import uuid4

import pytest

from personalization.application.designs.analysis_record import (
    AnalysisSelection,
    ImageGeometry,
    ResolutionStatus,
)
from personalization.application.designs.design_analysis_service import (
    DesignAnalysisService,
)
from personalization.application.designs.design_rules import (
    analyze_application,
    resolve_targets,
)
from personalization.application.errors.design_analysis_error import (
    AnalysisFailure,
    DesignAnalysisError,
)
from personalization.application.errors.security_error import SecurityError
from personalization.application.prints.print_record import MAX_SURCHARGE_CENTS
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from test.designs.fakes import analysis_data


@pytest.mark.parametrize(
    "pixels,expected",
    [
        ((2000, 1000), (100, 175, 100, 50)),
        ((1000, 2000), (Fraction(225, 2), 125, 75, 150)),
        ((1000, 1000), (100, 150, 100, 100)),
    ],
)
def test_fit_preserves_ratio_and_centers_within_allowed_size(
    pixels: tuple[int, int],
    expected: tuple[Fraction | int, ...],
) -> None:
    data = analysis_data()
    target = resolve_targets(data.template, data.selections)[0]
    result = analyze_application(target, ImageGeometry(*pixels), 500, None)
    placement = result.placement
    assert (
        placement.x_mm,
        placement.y_mm,
        placement.width_mm,
        placement.height_mm,
    ) == expected
    assert placement.width_mm / placement.height_mm == Fraction(*pixels)
    assert placement.width_mm <= target.size.definition.dimensions.width_mm
    assert placement.height_mm <= target.size.definition.dimensions.height_mm
    assert result.total_surcharge_cents == 1750


@pytest.mark.parametrize(
    "pixels,status",
    [
        (299, ResolutionStatus.INSUFFICIENT),
        (300, ResolutionStatus.SUFFICIENT),
        (301, ResolutionStatus.SUFFICIENT),
    ],
)
def test_exact_dpi_boundary_does_not_depend_on_rounded_display(
    pixels: int, status: ResolutionStatus
) -> None:
    data = analysis_data()
    target = resolve_targets(data.template, data.selections)[0]
    size = replace(
        target.size,
        definition=replace(
            target.size.definition,
            dimensions=replace(
                target.size.definition.dimensions,
                width_mm=Decimal("25.4"),
                height_mm=Decimal("25.4"),
            ),
        ),
    )
    result = analyze_application(
        replace(target, size=size), ImageGeometry(pixels, pixels), 0, 300
    )
    assert (
        result.effective_dpi == pixels and result.resolution_status is status
    )


def test_two_sides_sum_surcharges_once_and_reuse_one_image_read() -> None:
    data = analysis_data()
    service = DesignAnalysisService(
        data.templates, data.sources, data.geometry, None
    )
    identity = VerifiedIdentity(uuid4(), AppRole.ADMINISTRATOR)
    before = dict(data.templates.records)
    result = service.analyze(
        identity, data.template.header.id, data.selections
    )
    assert result.personalization_surcharge_cents == 3000
    assert all(
        item.resolution_status is ResolutionStatus.THRESHOLD_NOT_CONFIGURED
        for item in result.applications
    )
    assert result.minimum_dpi is None and data.geometry.calls == [
        data.sources.file.id
    ]
    assert data.templates.records == before


@pytest.mark.parametrize(
    "damage,expected",
    [
        ("zone", AnalysisFailure.ZONE_NOT_IN_TEMPLATE),
        ("size", AnalysisFailure.SIZE_NOT_IN_ZONE),
        ("duplicate", AnalysisFailure.DUPLICATE_ZONE_APPLICATION),
        ("both", AnalysisFailure.INVALID_DESIGN_ANALYSIS),
        ("neither", AnalysisFailure.INVALID_DESIGN_ANALYSIS),
        ("empty", AnalysisFailure.INVALID_DESIGN_ANALYSIS),
    ],
)
def test_invalid_selections_fail_before_source_io(
    damage: str, expected: AnalysisFailure
) -> None:
    data = analysis_data()
    first = data.selections[0]
    selections: tuple[AnalysisSelection, ...]
    match damage:
        case "zone":
            selections = (replace(first, zone_id=uuid4()),)
        case "size":
            selections = (
                replace(first, zone_size_id=data.selections[1].zone_size_id),
            )
        case "duplicate":
            selections = (first, first)
        case "both":
            selections = (replace(first, file_id=data.sources.file.id),)
        case "neither":
            selections = (replace(first, print_version_id=None),)
        case _:
            selections = ()
    with pytest.raises(DesignAnalysisError) as error:
        DesignAnalysisService(
            data.templates, data.sources, data.geometry, None
        ).analyze(
            VerifiedIdentity(uuid4(), AppRole.ADMINISTRATOR),
            data.template.header.id,
            selections,
        )
    assert error.value.failure is expected
    assert data.sources.calls == 0 and data.geometry.calls == []


def test_client_cannot_analyze_even_a_known_draft() -> None:
    data = analysis_data()
    with pytest.raises(SecurityError):
        DesignAnalysisService(
            data.templates, data.sources, data.geometry, None
        ).analyze(
            VerifiedIdentity(uuid4(), AppRole.CLIENT),
            data.template.header.id,
            data.selections,
        )
    assert data.sources.calls == 0 and data.geometry.calls == []


def test_total_overflow_is_rejected_before_reading_any_image() -> None:
    data = analysis_data()
    zones = tuple(
        replace(
            zone,
            sizes=(
                replace(
                    zone.sizes[0],
                    definition=replace(
                        zone.sizes[0].definition,
                        surcharge_cents=MAX_SURCHARGE_CENTS,
                    ),
                ),
            ),
            definition=replace(
                zone.definition,
                sizes=(
                    replace(
                        zone.definition.sizes[0],
                        surcharge_cents=MAX_SURCHARGE_CENTS,
                    ),
                ),
            ),
        )
        for zone in data.template.zones
    )
    data.templates.records[data.template.header.id] = replace(
        data.template, zones=zones
    )
    selections = tuple(
        replace(item, print_version_id=None, file_id=data.sources.file.id)
        for item in data.selections
    )
    with pytest.raises(DesignAnalysisError) as error:
        DesignAnalysisService(
            data.templates, data.sources, data.geometry, None
        ).analyze(
            VerifiedIdentity(uuid4(), AppRole.ADMINISTRATOR),
            data.template.header.id,
            selections,
        )
    assert (
        error.value.failure is AnalysisFailure.PERSONALIZATION_AMOUNT_OVERFLOW
    )
    assert data.geometry.calls == []


@pytest.mark.parametrize("pixels", [(0, 1), (-1, 10), (8193, 1), (5000, 5000)])
def test_invalid_pixel_geometry_is_rejected(pixels: tuple[int, int]) -> None:
    data = analysis_data()
    with pytest.raises(DesignAnalysisError) as error:
        analyze_application(
            resolve_targets(data.template, data.selections)[0],
            ImageGeometry(*pixels),
            0,
            None,
        )
    assert error.value.failure is AnalysisFailure.INVALID_IMAGE_GEOMETRY
