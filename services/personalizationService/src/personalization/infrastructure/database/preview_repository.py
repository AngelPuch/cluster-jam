"""Attach both previews only to their unchanged input revision."""

from collections.abc import Iterator
from contextlib import contextmanager
from hashlib import sha256
from uuid import UUID, uuid4

from sqlalchemy import Engine, or_, select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from personalization.application.designs.draft_record import (
    DesignState,
    DraftRecord,
)
from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileState
from personalization.application.previews.preview import (
    check_preview,
    preview_id,
    preview_revision,
)
from personalization.application.templates.template_record import Side
from personalization.infrastructure.database.derived_file_repository import (
    SqlAlchemyDerivedFileRepository,
)
from personalization.infrastructure.database.design_repository import (
    read_design,
)
from personalization.infrastructure.database.file_repository import map_file
from personalization.infrastructure.database.models.audit_entry import (
    AuditEntryModel,
)
from personalization.infrastructure.database.models.design import DesignModel
from personalization.infrastructure.database.models.image_file import FileModel


class SqlAlchemyPreviewRepository(SqlAlchemyDerivedFileRepository):
    def __init__(self, engine: Engine, bucket: str) -> None:
        super().__init__(engine)
        self._bucket = bucket

    def candidates(self, after: UUID | None, limit: int) -> list[UUID]:
        statement = (
            select(DesignModel.id)
            .where(
                DesignModel.state == DesignState.DRAFT.value,
                or_(
                    DesignModel.front_preview_id.is_(None),
                    DesignModel.back_preview_id.is_(None),
                ),
            )
            .order_by(DesignModel.id)
            .limit(max(1, min(limit, 100)))
        )
        if after is not None:
            statement = statement.where(DesignModel.id > after)
        try:
            with Session(self._engine) as session:
                return list(session.scalars(statement))
        except SQLAlchemyError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None

    @contextmanager
    def lock(self, design_id: UUID) -> Iterator[bool]:
        key = int.from_bytes(
            sha256(b"preview:v1:" + design_id.bytes).digest()[:8], signed=True
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
                    connection.invalidate()
        except SQLAlchemyError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None

    def get_draft(self, design_id: UUID) -> DraftRecord | None:
        try:
            with Session(self._engine) as session, session.begin():
                row = session.scalar(
                    select(DesignModel)
                    .where(DesignModel.id == design_id)
                    .with_for_update(read=True)
                )
                return None if row is None else read_design(session, row)
        except SQLAlchemyError, ValueError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None

    def attach(self, draft: DraftRecord) -> bool:
        try:
            with Session(self._engine) as session, session.begin():
                row = session.get(DesignModel, draft.id, with_for_update=True)
                if row is None or row.state != DesignState.DRAFT.value:
                    return False
                current = read_design(session, row)
                if preview_revision(current) != preview_revision(draft):
                    return False
                identifiers = [preview_id(draft, side) for side in Side]
                for side, file_id in zip(Side, identifiers, strict=True):
                    image = session.get(FileModel, file_id)
                    if (
                        image is None
                        or image.state != FileState.AVAILABLE.value
                        or not check_preview(
                            draft, side, map_file(image), self._bucket
                        )
                    ):
                        raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
                if (row.front_preview_id, row.back_preview_id) == tuple(
                    identifiers
                ):
                    return True
                row.front_preview_id, row.back_preview_id = identifiers
                session.add(
                    AuditEntryModel(
                        id=uuid4(),
                        actor_id=row.user_id,
                        action="DESIGN_PREVIEWS_GENERATED",
                        resource="diseno",
                        resource_id=row.id,
                        detail={
                            "version": row.version,
                            "renderVersion": "V1",
                            "approximate": True,
                            "catalogValidation": "PENDING",
                        },
                    )
                )
                session.flush()
            return True
        except SQLAlchemyError, ValueError:
            raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE) from None
