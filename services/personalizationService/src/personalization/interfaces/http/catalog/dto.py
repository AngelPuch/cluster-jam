"""Expose print prices and safe thumbnail references."""

from typing import Literal
from uuid import UUID

from personalization.application.catalog.catalog_record import CatalogPrint
from personalization.interfaces.http.dto.rest_model import RestModel


class CatalogVersionResponse(RestModel):
    id: UUID
    number: int
    surcharge_cents: int
    currency: Literal["MXN"] = "MXN"


class CatalogThumbnailResponse(RestModel):
    id: UUID
    mime_type: Literal["image/png"] = "image/png"
    width_px: int
    height_px: int
    size_bytes: int
    download_url_endpoint: str


class CatalogPrintResponse(RestModel):
    id: UUID
    name: str
    description: str | None
    version: CatalogVersionResponse
    thumbnail: CatalogThumbnailResponse

    @classmethod
    def from_record(cls, record: CatalogPrint) -> CatalogPrintResponse:
        return cls(
            id=record.id,
            name=record.name,
            description=record.description,
            version=CatalogVersionResponse(
                id=record.version_id,
                number=record.version_number,
                surcharge_cents=record.surcharge_cents,
            ),
            thumbnail=CatalogThumbnailResponse(
                id=record.thumbnail.id,
                width_px=record.thumbnail.width_px,
                height_px=record.thumbnail.height_px,
                size_bytes=record.thumbnail.size_bytes,
                download_url_endpoint=(
                    f"/api/v1/prints/{record.id}/versions/"
                    f"{record.version_id}/thumbnail/download-urls"
                ),
            ),
        )


class CatalogPageResponse(RestModel):
    items: list[CatalogPrintResponse]
    next_cursor: str | None
