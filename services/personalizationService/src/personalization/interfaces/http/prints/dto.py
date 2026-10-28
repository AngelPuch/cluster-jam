"""Expose camelCase administrative contracts with exact cents."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import ConfigDict, Field, StrictInt, StringConstraints

from personalization.application.prints.print_record import (
    MAX_DESCRIPTION_LENGTH,
    MAX_SURCHARGE_CENTS,
    MAX_VERSION_NUMBER,
    PrintRecord,
    PrintVersion,
)
from personalization.interfaces.http.dto.rest_model import RestModel

Surcharge = Annotated[StrictInt, Field(ge=0, le=MAX_SURCHARGE_CENTS)]
VersionNumber = Annotated[StrictInt, Field(ge=1, le=MAX_VERSION_NUMBER)]


class CreatePrintRequest(RestModel):
    model_config = ConfigDict(
        populate_by_name=False,
        validate_by_name=False,
        validate_by_alias=True,
    )
    name: Annotated[
        str,
        StringConstraints(
            strict=True,
            strip_whitespace=True,
            min_length=1,
            max_length=120,
        ),
    ]
    description: (
        Annotated[
            str,
            StringConstraints(
                strict=True,
                max_length=MAX_DESCRIPTION_LENGTH,
            ),
        ]
        | None
    ) = None
    file_id: UUID
    surcharge_cents: Surcharge


class CreatePrintVersionRequest(RestModel):
    model_config = ConfigDict(
        populate_by_name=False,
        validate_by_name=False,
        validate_by_alias=True,
    )
    expected_version: VersionNumber
    file_id: UUID
    surcharge_cents: Surcharge


class PrintVersionResponse(RestModel):
    id: UUID
    print_id: UUID
    number: int
    file_id: UUID
    surcharge_cents: int
    currency: Literal["MXN"] = "MXN"

    @classmethod
    def from_record(cls, record: PrintVersion) -> PrintVersionResponse:
        return cls(
            id=record.id,
            print_id=record.print_id,
            number=record.number,
            file_id=record.file_id,
            surcharge_cents=record.surcharge_cents,
        )


class PrintResponse(RestModel):
    id: UUID
    name: str
    description: str | None
    active: bool
    latest_version: PrintVersionResponse

    @classmethod
    def from_record(cls, record: PrintRecord) -> PrintResponse:
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            active=record.active,
            latest_version=PrintVersionResponse.from_record(
                record.latest_version
            ),
        )


class PrintPageResponse(RestModel):
    items: list[PrintResponse]
    next_cursor: str | None


class PrintVersionPageResponse(RestModel):
    items: list[PrintVersionResponse]
    next_cursor: str | None
