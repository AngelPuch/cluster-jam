"""Discover durable image jobs from local print references."""

from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from uuid import UUID

from sqlalchemy import Engine, String, cast, exists, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session, aliased

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileRecord, FileState
from personalization.application.thumbnails.thumbnail import (
    THUMBNAIL_USAGE_PREFIX,
    thumbnail_id,
)
from personalization.infrastructure.database.derived_file_repository import (
    SqlAlchemyDerivedFileRepository,
)
from personalization.infrastructure.database.file_repository import map_file
from personalization.infrastructure.database.models.image_file import FileModel
from personalization.infrastructure.database.models.print_version import (
    PrintVersionModel,
)


class SqlAlchemyThumbnailRepository(SqlAlchemyDerivedFileRepository):
    def __init__(self, engine: Engine, bucket: str) -> None:
        super().__init__(engine)
        self._bucket = bucket

    def candidates(self, after: UUID | None, limit: int) -> list[FileRecord]:
        """Scan unique originals used by any preserved print version."""
        derived = aliased(FileModel)
        query = (
            select(FileModel)
            .where(
                FileModel.bucket == self._bucket,
                FileModel.usage == "ORIGINAL",
                FileModel.state == FileState.AVAILABLE.value,
                exists().where(PrintVersionModel.file_id == FileModel.id),
                ~exists().where(
                    derived.bucket == self._bucket,
                    derived.usage
                    == THUMBNAIL_USAGE_PREFIX + cast(FileModel.id, String),
                    derived.state == FileState.AVAILABLE.value,
                ),
            )
            .order_by(FileModel.id)
            .limit(max(1, min(limit, 100)))
        )
        if after is not None:
            query = query.where(FileModel.id > after)
        try:
            with Session(self._engine) as session:
                return [map_file(row) for row in session.scalars(query)]
        except SQLAlchemyError, ValueError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None

    @contextmanager
    def lock(self, source_id: UUID) -> Iterator[bool]:
        """Release locks by closing the physical database session."""
        key = int.from_bytes(
            sha256(b"thumbnail:v1:" + source_id.bytes).digest()[:8],
            signed=True,
        )
        try:
            with self._engine.connect() as connection:
                try:
                    acquired = (
                        connection.execute(
                            text("SELECT pg_try_advisory_lock(:key)"),
                            {"key": key},
                        ).scalar_one()
                        is True
                    )
                    connection.commit()
                    yield acquired
                finally:
                    # Never return a session lock to the pool.
                    connection.invalidate()
        except SQLAlchemyError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None

    def get(self, source_id: UUID) -> FileRecord | None:
        try:
            with Session(self._engine) as session:
                row = session.get(FileModel, thumbnail_id(source_id))
                return map_file(row) if row is not None else None
        except SQLAlchemyError, ValueError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None
