"""Validate template geometry before any database transaction."""

import re
from decimal import Decimal
from itertools import combinations

from personalization.application.errors.template_error import (
    TemplateError,
    TemplateFailure,
)
from personalization.application.prints.print_record import MAX_SURCHARGE_CENTS
from personalization.application.templates.template_record import (
    MAX_MEASUREMENT_MM,
    MAX_TEMPLATE_ZONES,
    MEASUREMENT_QUANTUM,
    Dimensions,
    Side,
    SizeLabel,
    TemplateDefinition,
)


def measurement(value: Decimal, *, zero: bool = False) -> None:
    if (
        not isinstance(value, Decimal)
        or not value.is_finite()
        or value < 0
        or (not zero and value == 0)
        or value > MAX_MEASUREMENT_MM
        or value.quantize(MEASUREMENT_QUANTUM) != value
    ):
        raise TemplateError(TemplateFailure.INVALID_TEMPLATE_DATA)


def dimensions(value: Dimensions) -> None:
    measurement(value.width_mm)
    measurement(value.height_mm)


def validate_definition(definition: TemplateDefinition) -> None:
    dimensions(definition.front)
    dimensions(definition.back)
    if not 1 <= len(definition.zones) <= MAX_TEMPLATE_ZONES:
        raise TemplateError(TemplateFailure.INVALID_TEMPLATE_DATA)
    codes: set[tuple[Side, str]] = set()
    for zone in definition.zones:
        if (
            not isinstance(zone.side, Side)
            or re.fullmatch(r"[a-z][a-z0-9-]{0,39}", zone.code) is None
        ):
            raise TemplateError(TemplateFailure.INVALID_TEMPLATE_DATA)
        key = (zone.side, zone.code)
        if key in codes:
            raise TemplateError(TemplateFailure.DUPLICATE_ZONE)
        codes.add(key)
        measurement(zone.x_mm, zero=True)
        measurement(zone.y_mm, zero=True)
        dimensions(zone.dimensions)
        canvas = (
            definition.front if zone.side is Side.FRONT else definition.back
        )
        if (
            zone.x_mm + zone.dimensions.width_mm > canvas.width_mm
            or zone.y_mm + zone.dimensions.height_mm > canvas.height_mm
        ):
            raise TemplateError(TemplateFailure.ZONE_OUTSIDE_TEMPLATE)
        if not 1 <= len(zone.sizes) <= 3:
            raise TemplateError(TemplateFailure.INVALID_TEMPLATE_DATA)
        labels: set[SizeLabel] = set()
        for size in zone.sizes:
            if not isinstance(size.label, SizeLabel):
                raise TemplateError(TemplateFailure.INVALID_TEMPLATE_DATA)
            if size.label in labels:
                raise TemplateError(TemplateFailure.DUPLICATE_ZONE_SIZE)
            labels.add(size.label)
            dimensions(size.dimensions)
            if (
                size.dimensions.width_mm > zone.dimensions.width_mm
                or size.dimensions.height_mm > zone.dimensions.height_mm
            ):
                raise TemplateError(TemplateFailure.SIZE_OUTSIDE_ZONE)
            if (
                type(size.surcharge_cents) is not int
                or not 0 <= size.surcharge_cents <= MAX_SURCHARGE_CENTS
            ):
                raise TemplateError(TemplateFailure.INVALID_TEMPLATE_DATA)
    for first, second in combinations(definition.zones, 2):
        if first.side is second.side and (
            first.x_mm < second.x_mm + second.dimensions.width_mm
            and second.x_mm < first.x_mm + first.dimensions.width_mm
            and first.y_mm < second.y_mm + second.dimensions.height_mm
            and second.y_mm < first.y_mm + first.dimensions.height_mm
        ):
            raise TemplateError(TemplateFailure.ZONES_OVERLAP)
