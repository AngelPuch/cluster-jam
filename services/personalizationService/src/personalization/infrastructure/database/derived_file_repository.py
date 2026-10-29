"""Commit derived-file intentions before immutable remote uploads."""

from dataclasses import replace
from uuid import UUID

from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileRecord, FileState
from personalization.infrastructure.database.file_repository import map_file
from personalization.infrastructure.database.models.image_file import FileModel


class SqlAlchemyDerivedFileRepository:
    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def get_file(self, file_id: UUID) -> FileRecord | None:
        try:
            with Session(self._engine) as session:
                row = session.get(FileModel, file_id)
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
