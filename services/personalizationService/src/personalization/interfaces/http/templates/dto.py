"""Use exact decimal strings for millimeters and centimeters."""

import re
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    BeforeValidator,
    ConfigDict,
    Field,
    StrictInt,
    StringConstraints,
)

from personalization.application.prints.print_record import (
    MAX_SURCHARGE_CENTS,
    MAX_VERSION_NUMBER,
)
from personalization.application.templates.template_record import (
    Dimensions,
    Side,
    SizeDefinition,
    SizeLabel,
    TemplateDefinition,
    TemplateHeader,
    TemplateRecord,
    ZoneDefinition,
)
from personalization.interfaces.http.dto.rest_model import RestModel


def decimal_string(value: object) -> str:
    if (
        not isinstance(value, str)
        or re.fullmatch(r"(?:0|[1-9][0-9]{0,4})(?:\.[0-9]{1,3})?", value)
        is None
    ):
        raise ValueError("Measurements require bounded decimal strings")
    return value


Millimeters = Annotated[
    Decimal,
    BeforeValidator(decimal_string, json_schema_input_type=str),
    Field(gt=0, le=10000),
]
Coordinate = Annotated[
    Decimal,
    BeforeValidator(decimal_string, json_schema_input_type=str),
    Field(ge=0, le=10000),
]
Surcharge = Annotated[StrictInt, Field(ge=0, le=MAX_SURCHARGE_CENTS)]


class TemplateInput(RestModel):
    model_config = ConfigDict(
        populate_by_name=False, validate_by_name=False, validate_by_alias=True
    )


class DimensionsRequest(TemplateInput):
    width_mm: Millimeters
    height_mm: Millimeters

    def definition(self) -> Dimensions:
        return Dimensions(self.width_mm, self.height_mm)


class SizeRequest(TemplateInput):
    label: SizeLabel
    width_mm: Millimeters
    height_mm: Millimeters
    surcharge_cents: Surcharge

    def definition(self) -> SizeDefinition:
        return SizeDefinition(
            self.label,
            Dimensions(self.width_mm, self.height_mm),
            self.surcharge_cents,
        )


class ZoneRequest(TemplateInput):
    code: Annotated[
        str, StringConstraints(strict=True, pattern=r"^[a-z][a-z0-9-]{0,39}$")
    ]
    side: Side
    x_mm: Coordinate
    y_mm: Coordinate
    width_mm: Millimeters
    height_mm: Millimeters
    sizes: Annotated[list[SizeRequest], Field(min_length=1, max_length=3)]

    def definition(self) -> ZoneDefinition:
        return ZoneDefinition(
            self.code,
            self.side,
            self.x_mm,
            self.y_mm,
            Dimensions(self.width_mm, self.height_mm),
            tuple(size.definition() for size in self.sizes),
        )


class CreateTemplateRequest(TemplateInput):
    product_id: UUID
    size_id: Annotated[StrictInt, Field(ge=1, le=32767)]
    expected_version: Annotated[StrictInt, Field(ge=0, le=MAX_VERSION_NUMBER)]
    front: DimensionsRequest
    back: DimensionsRequest
    zones: Annotated[list[ZoneRequest], Field(min_length=1, max_length=20)]

    def definition(self) -> TemplateDefinition:
        return TemplateDefinition(
            self.front.definition(),
            self.back.definition(),
            tuple(zone.definition() for zone in self.zones),
        )


def mm(value: Decimal) -> str:
    return format(value.quantize(Decimal("0.001")), "f")


def cm(value: Decimal) -> str:
    return format((value / 10).quantize(Decimal("0.0001")), "f")


class DimensionsResponse(RestModel):
    width_mm: str
    height_mm: str

    @classmethod
    def from_dimensions(cls, value: Dimensions) -> DimensionsResponse:
        return cls(width_mm=mm(value.width_mm), height_mm=mm(value.height_mm))


class SizeResponse(RestModel):
    id: UUID
    label: SizeLabel
    width_mm: str
    height_mm: str
    width_cm: str
    height_cm: str
    surcharge_cents: int
    currency: Literal["MXN"] = "MXN"


class ZoneResponse(RestModel):
    id: UUID
    code: str
    side: Side
    x_mm: str
    y_mm: str
    width_mm: str
    height_mm: str
    sizes: list[SizeResponse]


class TemplateHeaderResponse(RestModel):
    id: UUID
    product_id: UUID
    size_id: int
    number: int
    active: bool
    front: DimensionsResponse
    back: DimensionsResponse

    @classmethod
    def from_header(cls, header: TemplateHeader) -> TemplateHeaderResponse:
        return cls(
            id=header.id,
            product_id=header.product_id,
            size_id=header.size_id,
            number=header.number,
            active=header.active,
            front=DimensionsResponse.from_dimensions(header.front),
            back=DimensionsResponse.from_dimensions(header.back),
        )


class TemplateResponse(TemplateHeaderResponse):
    zones: list[ZoneResponse]

    @classmethod
    def from_record(cls, record: TemplateRecord) -> TemplateResponse:
        header = record.header
        zones: list[ZoneResponse] = []
        for zone in sorted(
            record.zones,
            key=lambda item: (
                list(Side).index(item.definition.side),
                item.definition.code,
            ),
        ):
            value = zone.definition
            sizes = [
                SizeResponse(
                    id=size.id,
                    label=size.definition.label,
                    width_mm=mm(size.definition.dimensions.width_mm),
                    height_mm=mm(size.definition.dimensions.height_mm),
                    width_cm=cm(size.definition.dimensions.width_mm),
                    height_cm=cm(size.definition.dimensions.height_mm),
                    surcharge_cents=size.definition.surcharge_cents,
                )
                for size in sorted(
                    zone.sizes,
                    key=lambda item: list(SizeLabel).index(
                        item.definition.label
                    ),
                )
            ]
            zones.append(
                ZoneResponse(
                    id=zone.id,
                    code=value.code,
                    side=value.side,
                    x_mm=mm(value.x_mm),
                    y_mm=mm(value.y_mm),
                    width_mm=mm(value.dimensions.width_mm),
                    height_mm=mm(value.dimensions.height_mm),
                    sizes=sizes,
                )
            )
        return cls(
            id=header.id,
            product_id=header.product_id,
            size_id=header.size_id,
            number=header.number,
            active=header.active,
            front=DimensionsResponse.from_dimensions(header.front),
            back=DimensionsResponse.from_dimensions(header.back),
            zones=zones,
        )


class TemplatePageResponse(RestModel):
    items: list[TemplateHeaderResponse]
    next_cursor: str | None
