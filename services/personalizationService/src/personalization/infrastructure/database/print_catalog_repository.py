"""Read catalog visibility and current prices in one SQL snapshot."""

from uuid import UUID

from sqlalchemy import Engine, Select, String, cast, select, true
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from personalization.application.catalog.catalog_record import CatalogPrint
from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.prints.print_record import MAX_SURCHARGE_CENTS
from personalization.application.thumbnails.thumbnail import (
    THUMBNAIL_SIDE_PX,
    THUMBNAIL_USAGE_PREFIX,
    thumbnail_id,
)
from personalization.infrastructure.database.file_repository import map_file
from personalization.infrastructure.database.models.image_file import FileModel
from personalization.infrastructure.database.models.print import PrintModel
from personalization.infrastructure.database.models.print_version import (
    PrintVersionModel,
)


def map_catalog(
    row: PrintModel,
    version: PrintVersionModel,
    thumbnail: FileModel,
) -> CatalogPrint:
    """Fail closed if stored metadata violates the derived identity."""
    if (
        thumbnail.id != thumbnail_id(version.file_id)
        or not 0 <= version.surcharge_cents <= MAX_SURCHARGE_CENTS
    ):
        raise PrintError(PrintFailure.PRINT_DATABASE_UNAVAILABLE)
    return CatalogPrint(
        row.id,
        row.name,
        row.description,
        version.id,
        version.number,
        version.surcharge_cents,
        map_file(thumbnail),
    )


def catalog_statement(
    bucket: str,
) -> Select[PrintModel, PrintVersionModel, FileModel]:
    """Reuse the query without sharing request filters."""
    original = aliased(FileModel)
    latest = (
        select(PrintVersionModel)
        .where(PrintVersionModel.print_id == PrintModel.id)
        .order_by(PrintVersionModel.number.desc())
        .limit(1)
        .correlate(PrintModel)
        .lateral()
    )
    current_version = aliased(PrintVersionModel, latest)
    thumbnail_query = (
        select(FileModel)
        .where(
            FileModel.usage
            == THUMBNAIL_USAGE_PREFIX + cast(original.id, String),
            FileModel.state == "DISPONIBLE",
            FileModel.bucket == bucket,
            FileModel.owner_id == original.owner_id,
            FileModel.mime_type == "image/png",
            FileModel.width_px.between(1, THUMBNAIL_SIDE_PX),
            FileModel.height_px.between(1, THUMBNAIL_SIDE_PX),
            FileModel.object_key == cast(FileModel.id, String) + ".png",
        )
        # Preserve every match while keeping this lookup correlated.
        # PostgreSQL must not flatten it into a global thumbnail scan.
        .offset(0)
        .correlate(original)
        .lateral()
    )
    thumbnail = aliased(FileModel, thumbnail_query)
    return (
        select(PrintModel, current_version, thumbnail)
        .select_from(PrintModel)
        .join(current_version, true())
        .join(original, original.id == current_version.file_id)
        .join(thumbnail, true())
        .where(
            PrintModel.active.is_(True),
            original.usage == "ORIGINAL",
            original.state == "DISPONIBLE",
            original.bucket == bucket,
        )
        .order_by(PrintModel.id)
    )


class SqlAlchemyPrintCatalogRepository:
    def __init__(self, engine: Engine, bucket: str) -> None:
        self._engine = engine
        self._statement = catalog_statement(bucket)

    def _read(
        self,
        *,
        print_id: UUID | None = None,
        after: UUID | None = None,
        limit: int = 1,
    ) -> tuple[CatalogPrint, ...]:
        statement = self._statement.limit(max(1, min(limit, 101)))
        if after is not None:
            statement = statement.where(PrintModel.id > after)
        if print_id is not None:
            statement = statement.where(PrintModel.id == print_id)
        try:
            with Session(self._engine) as session:
                return tuple(
                    map_catalog(row, version, derived)
                    for row, version, derived in session.execute(statement)
                )
        except SQLAlchemyError, ValueError:
            raise PrintError(PrintFailure.PRINT_DATABASE_UNAVAILABLE) from None

    def list(self, after: UUID | None, limit: int) -> tuple[CatalogPrint, ...]:
        return self._read(after=after, limit=limit)

    def get(self, print_id: UUID) -> CatalogPrint | None:
        records = self._read(print_id=print_id)
        return records[0] if records else None
