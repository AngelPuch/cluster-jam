"""Map original-file records using explicit local transactions."""

from uuid import UUID

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileRecord, FileState
from personalization.infrastructure.database.models.image_file import FileModel


def map_file(row: FileModel) -> FileRecord:
    """Copy metadata before the SQLAlchemy session is closed."""
    return FileRecord(
        id=row.id,
        owner_id=row.owner_id,
        bucket=row.bucket,
        object_key=row.object_key,
        mime_type=row.mime_type,
        size_bytes=row.size_bytes,
        width_px=row.width_px,
        height_px=row.height_px,
        sha256=row.sha256,
        usage=row.usage,
        state=FileState(row.state),
    )


class SqlAlchemyFileRepository:
    """Share a pool, but never share sessions between requests."""

    def __init__(self, engine: Engine) -> None:
        self._engine = engine

    def create_pending(self, record: FileRecord) -> None:
        """Commit the upload intention before any remote write."""
        try:
            with Session(self._engine) as session, session.begin():
                session.add(
                    FileModel(
                        id=record.id,
                        owner_id=record.owner_id,
                        bucket=record.bucket,
                        object_key=record.object_key,
                        sha256=record.sha256,
                        mime_type=record.mime_type,
                        size_bytes=record.size_bytes,
                        width_px=record.width_px,
                        height_px=record.height_px,
                        usage="ORIGINAL",
                        state=FileState.PENDING.value,
                    )
                )
        except SQLAlchemyError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None

    def get(self, file_id: UUID) -> FileRecord | None:
        """Read from personalizacion_db only."""
        try:
            with Session(self._engine) as session:
                row = session.get(FileModel, file_id)
                return map_file(row) if row is not None else None
        except SQLAlchemyError, ValueError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None

    def make_available(self, file_id: UUID) -> FileRecord:
        """Serialize publication and allow repeated acknowledgements."""
        try:
            with Session(self._engine) as session, session.begin():
                row = session.get(FileModel, file_id, with_for_update=True)
                if row is None:
                    raise FileError(FileFailure.FILE_NOT_FOUND)
                if row.usage != "ORIGINAL" or row.state not in (
                    FileState.PENDING.value,
                    FileState.AVAILABLE.value,
                ):
                    raise FileError(FileFailure.FILE_NOT_READY)
                row.state = FileState.AVAILABLE.value
                session.flush()
                result = map_file(row)
            return result
        except SQLAlchemyError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None

    def list_pending(self, limit: int) -> list[FileRecord]:
        """Bound recovery work independently from any caller
        argument.
        """
        limit = max(1, min(limit, 100))
        try:
            with Session(self._engine) as session:
                rows = session.scalars(
                    select(FileModel)
                    .where(
                        FileModel.usage == "ORIGINAL",
                        FileModel.state == FileState.PENDING.value,
                    )
                    .order_by(FileModel.id)
                    .limit(limit)
                ).all()
                return [map_file(row) for row in rows]
        except SQLAlchemyError, ValueError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None
