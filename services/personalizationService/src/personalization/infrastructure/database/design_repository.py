"""Serialize draft changes with authoritative ownership and bindings."""

from uuid import UUID, uuid4

from sqlalchemy import Engine, delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from personalization.application.designs.analysis_record import (
    AnalysisSelection,
)
from personalization.application.designs.draft_record import (
    DesignCondition,
    DesignState,
    DraftContent,
    DraftRecord,
    SavedApplication,
    draft_revision,
)
from personalization.application.errors.design_error import (
    DesignError,
    DesignFailure,
)
from personalization.application.errors.security_error import (
    SecurityError,
    SecurityFailure,
)
from personalization.application.prints.print_record import MAX_VERSION_NUMBER
from personalization.infrastructure.database.analysis_repository import (
    read_analysis_sources,
)
from personalization.infrastructure.database.models.application import (
    ApplicationModel,
)
from personalization.infrastructure.database.models.audit_entry import (
    AuditEntryModel,
)
from personalization.infrastructure.database.models.design import DesignModel
from personalization.infrastructure.database.models.template_version import (
    TemplateVersionModel,
)
from personalization.infrastructure.database.models.zone import ZoneModel
from personalization.infrastructure.database.models.zone_size import (
    ZoneSizeModel,
)


def map_application(row: ApplicationModel) -> SavedApplication:
    return SavedApplication(
        row.id,
        AnalysisSelection(
            row.zone_id,
            row.zone_size_id,
            row.print_version_id,
            row.user_file_id,
        ),
    )


def map_design(
    row: DesignModel, applications: tuple[SavedApplication, ...] = ()
) -> DraftRecord:
    return DraftRecord(
        row.id,
        row.user_id,
        row.variant_id,
        row.template_id,
        DesignState(row.state),
        row.version,
        row.front_preview_id,
        row.back_preview_id,
        applications,
    )


def owned_row(
    session: Session, owner_id: UUID, design_id: UUID, *, lock: bool = False
) -> DesignModel:
    row = session.get(DesignModel, design_id, with_for_update=lock)
    if row is None:
        raise DesignError(DesignFailure.DESIGN_NOT_FOUND)
    # A saved draft stays private to its owner even among admins.
    if row.user_id != owner_id:
        raise SecurityError(SecurityFailure.FORBIDDEN)
    return row


def read_design(session: Session, row: DesignModel) -> DraftRecord:
    applications = session.scalars(
        select(ApplicationModel)
        .where(ApplicationModel.design_id == row.id)
        .order_by(ApplicationModel.zone_id)
    ).all()
    return map_design(
        row, tuple(map_application(item) for item in applications)
    )


class SqlAlchemyDesignRepository:
    def __init__(self, engine: Engine, bucket: str) -> None:
        self._engine = engine
        self._bucket = bucket

    def _bindings(self, session: Session, content: DraftContent) -> None:
        if session.get(TemplateVersionModel, content.template_id) is None:
            raise DesignError(DesignFailure.INVALID_DESIGN_DATA)
        choices = content.applications
        if not choices:
            return
        # Recheck bindings inside the write transaction.
        pairs = set(
            session.execute(
                select(ZoneModel.id, ZoneSizeModel.id)
                .join(ZoneSizeModel, ZoneSizeModel.zone_id == ZoneModel.id)
                .where(
                    ZoneModel.template_id == content.template_id,
                    ZoneModel.id.in_({item.zone_id for item in choices}),
                )
            )
        )
        if any(
            (item.zone_id, item.zone_size_id) not in pairs for item in choices
        ):
            raise DesignError(DesignFailure.INVALID_DESIGN_DATA)
        if len({item.zone_id for item in choices}) != len(choices):
            raise DesignError(DesignFailure.INVALID_DESIGN_DATA)
        if any(
            (item.file_id is None) == (item.print_version_id is None)
            for item in choices
        ):
            raise DesignError(DesignFailure.INVALID_DESIGN_DATA)
        read_analysis_sources(session, self._bucket, choices)

    def _audit(
        self,
        session: Session,
        row: DesignModel,
        action: str,
        count: int,
        source: DraftRecord | None = None,
    ) -> None:
        detail: dict[str, object] = {
            "version": row.version,
            "templateId": str(row.template_id),
            "applicationCount": count,
            "state": row.state,
            "catalogValidation": "PENDING",
        }
        if source is not None:
            detail.update(
                {
                    "sourceDesignId": str(source.id),
                    "sourceVersion": source.version,
                }
            )
        session.add(
            AuditEntryModel(
                id=uuid4(),
                actor_id=row.user_id,
                action=action,
                resource="diseno",
                resource_id=row.id,
                detail=detail,
            )
        )

    def _applications(
        self, session: Session, row: DesignModel, content: DraftContent
    ) -> None:
        for item in content.applications:
            session.add(
                ApplicationModel(
                    id=uuid4(),
                    design_id=row.id,
                    zone_id=item.zone_id,
                    zone_size_id=item.zone_size_id,
                    print_version_id=item.print_version_id,
                    user_file_id=item.file_id,
                )
            )
        session.flush()

    def _create(
        self,
        session: Session,
        owner_id: UUID,
        content: DraftContent,
        source: DraftRecord | None = None,
    ) -> DraftRecord:
        self._bindings(session, content)
        row = DesignModel(
            id=uuid4(),
            user_id=owner_id,
            variant_id=content.variant_id,
            template_id=content.template_id,
            state=DesignState.DRAFT.value,
            version=1,
            front_preview_id=None,
            back_preview_id=None,
        )
        session.add(row)
        session.flush()
        self._applications(session, row, content)
        self._audit(
            session,
            row,
            "DESIGN_DRAFT_COPIED" if source else "DESIGN_DRAFT_CREATED",
            len(content.applications),
            source,
        )
        session.flush()
        return read_design(session, row)

    def create(self, owner_id: UUID, content: DraftContent) -> DraftRecord:
        try:
            with Session(self._engine) as session, session.begin():
                result = self._create(session, owner_id, content.canonical())
            return result
        except SQLAlchemyError, ValueError:
            raise DesignError(
                DesignFailure.DESIGN_DATABASE_UNAVAILABLE
            ) from None

    def get(self, owner_id: UUID, design_id: UUID) -> DraftRecord:
        try:
            with Session(self._engine) as session, session.begin():
                # Share-lock the root while reading its children.
                statement = (
                    select(DesignModel)
                    .where(DesignModel.id == design_id)
                    .with_for_update(read=True)
                )
                row = session.scalar(statement)
                if row is None:
                    raise DesignError(DesignFailure.DESIGN_NOT_FOUND)
                if row.user_id != owner_id:
                    raise SecurityError(SecurityFailure.FORBIDDEN)
                return read_design(session, row)
        except SQLAlchemyError, ValueError:
            raise DesignError(
                DesignFailure.DESIGN_DATABASE_UNAVAILABLE
            ) from None

    def update(
        self,
        owner_id: UUID,
        design_id: UUID,
        content: DraftContent,
        condition: DesignCondition,
    ) -> DraftRecord:
        try:
            with Session(self._engine) as session, session.begin():
                row = owned_row(session, owner_id, design_id, lock=True)
                previous = read_design(session, row)
                if previous.state is not DesignState.DRAFT:
                    raise DesignError(DesignFailure.DESIGN_NOT_EDITABLE)
                if not condition.matches(draft_revision(previous)):
                    raise DesignError(DesignFailure.DESIGN_PRECONDITION_FAILED)
                canonical = content.canonical()
                self._bindings(session, canonical)
                if previous.content != canonical:
                    if row.version == MAX_VERSION_NUMBER:
                        raise DesignError(DesignFailure.DESIGN_VERSION_LIMIT)
                    session.execute(
                        delete(ApplicationModel).where(
                            ApplicationModel.design_id == row.id
                        )
                    )
                    session.flush()
                    row.variant_id = canonical.variant_id
                    row.template_id = canonical.template_id
                    row.version += 1
                    row.front_preview_id = None
                    row.back_preview_id = None
                    session.flush()
                    self._applications(session, row, canonical)
                    self._audit(
                        session,
                        row,
                        "DESIGN_DRAFT_UPDATED",
                        len(canonical.applications),
                    )
                    session.flush()
                result = read_design(session, row)
            return result
        except SQLAlchemyError, ValueError:
            raise DesignError(
                DesignFailure.DESIGN_DATABASE_UNAVAILABLE
            ) from None

    def copy(self, owner_id: UUID, design_id: UUID) -> DraftRecord:
        try:
            with Session(self._engine) as session, session.begin():
                original = read_design(
                    session, owned_row(session, owner_id, design_id, lock=True)
                )
                result = self._create(
                    session, owner_id, original.content, original
                )
            return result
        except SQLAlchemyError, ValueError:
            raise DesignError(
                DesignFailure.DESIGN_DATABASE_UNAVAILABLE
            ) from None

    def list(
        self, owner_id: UUID, after: UUID | None, limit: int
    ) -> tuple[DraftRecord, ...]:
        statement = (
            select(DesignModel)
            .where(DesignModel.user_id == owner_id)
            .order_by(DesignModel.id)
            .limit(max(1, min(limit, 101)))
        )
        if after is not None:
            statement = statement.where(DesignModel.id > after)
        try:
            with Session(self._engine) as session:
                return tuple(
                    map_design(row) for row in session.scalars(statement)
                )
        except SQLAlchemyError, ValueError:
            raise DesignError(
                DesignFailure.DESIGN_DATABASE_UNAVAILABLE
            ) from None
