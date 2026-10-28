"""Discover durable image jobs from local print references."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import replace
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
from personalization.infrastructure.database.file_repository import map_file
from personalization.infrastructure.database.models.image_file import FileModel
from personalization.infrastructure.database.models.print_version import (
    PrintVersionModel,
)


class SqlAlchemyThumbnailRepository:
    def __init__(self, engine: Engine, bucket: str) -> None:
        self._engine = engine
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

    def reserve(self, record: FileRecord) -> FileRecord:
        """Commit exact expected metadata before the first upload."""
        try:
            with Session(self._engine) as session, session.begin():
                row = session.get(FileModel, record.id)
                if row is None:
                    row = FileModel(
                        id=record.id,
                        owner_id=record.owner_id,
                        bucket=record.bucket,
                        object_key=record.object_key,
                        sha256=record.sha256,
                        mime_type=record.mime_type,
                        size_bytes=record.size_bytes,
                        width_px=record.width_px,
                        height_px=record.height_px,
                        usage=record.usage,
                        state=FileState.PENDING.value,
                    )
                    session.add(row)
                    session.flush()
                return map_file(row)
        except SQLAlchemyError, ValueError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None

    def publish(self, record: FileRecord) -> FileRecord:
        try:
            with Session(self._engine) as session, session.begin():
                row = session.get(FileModel, record.id, with_for_update=True)
                if row is None or map_file(row) not in (
                    record,
                    replace(record, state=FileState.AVAILABLE),
                ):
                    raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
                row.state = FileState.AVAILABLE.value
                session.flush()
                result = map_file(row)
            return result
        except SQLAlchemyError, ValueError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None
