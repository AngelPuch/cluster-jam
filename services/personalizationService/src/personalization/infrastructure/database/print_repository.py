"""Serialize append-only print versions in PostgreSQL transactions."""

from uuid import UUID, uuid4

from sqlalchemy import Engine, func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.prints.print_record import (
    MAX_VERSION_NUMBER,
    PrintRecord,
    PrintVersion,
)
from personalization.infrastructure.database.models.audit_entry import (
    AuditEntryModel,
)
from personalization.infrastructure.database.models.image_file import FileModel
from personalization.infrastructure.database.models.print import PrintModel
from personalization.infrastructure.database.models.print_version import (
    PrintVersionModel,
)


def map_version(row: PrintVersionModel) -> PrintVersion:
    return PrintVersion(
        row.id, row.print_id, row.number, row.file_id, row.surcharge_cents
    )


def map_print(row: PrintModel, version: PrintVersionModel) -> PrintRecord:
    return PrintRecord(
        row.id, row.name, row.description, row.active, map_version(version)
    )


def audit_version(
    session: Session, actor_id: UUID, version: PrintVersion, action: str
) -> None:
    session.add(
        AuditEntryModel(
            id=uuid4(),
            actor_id=actor_id,
            action=action,
            resource="estampado",
            resource_id=version.print_id,
            detail={
                "versionId": str(version.id),
                "versionNumber": version.number,
                "fileId": str(version.file_id),
                "surchargeCents": version.surcharge_cents,
                "currency": "MXN",
            },
        )
    )


class SqlAlchemyPrintRepository:
    def __init__(self, engine: Engine, bucket: str) -> None:
        self._engine = engine
        self._bucket = bucket

    def _require_file(self, session: Session, file_id: UUID) -> None:
        row = session.get(FileModel, file_id)
        if row is None:
            raise PrintError(PrintFailure.PRINT_FILE_NOT_FOUND)
        if (
            row.state != "DISPONIBLE"
            or row.usage != "ORIGINAL"
            or row.bucket != self._bucket
        ):
            raise PrintError(PrintFailure.INVALID_PRINT_FILE)

    def create(
        self,
        actor_id: UUID,
        name: str,
        description: str | None,
        file_id: UUID,
        surcharge_cents: int,
    ) -> PrintRecord:
        try:
            with Session(self._engine) as session, session.begin():
                self._require_file(session, file_id)
                row = PrintModel(
                    id=uuid4(),
                    name=name,
                    description=description,
                    active=True,
                )
                session.add(row)
                session.flush()
                version = PrintVersionModel(
                    id=uuid4(),
                    print_id=row.id,
                    number=1,
                    file_id=file_id,
                    surcharge_cents=surcharge_cents,
                )
                session.add(version)
                session.flush()
                result = map_print(row, version)
                audit_version(
                    session, actor_id, result.latest_version, "PRINT_CREATED"
                )
            return result
        except SQLAlchemyError:
            raise PrintError(PrintFailure.PRINT_DATABASE_UNAVAILABLE) from None

    def create_version(
        self,
        actor_id: UUID,
        print_id: UUID,
        expected_version: int,
        file_id: UUID,
        surcharge_cents: int,
    ) -> PrintVersion:
        try:
            with Session(self._engine) as session, session.begin():
                row = session.get(PrintModel, print_id, with_for_update=True)
                if row is None:
                    raise PrintError(PrintFailure.PRINT_NOT_FOUND)
                latest = session.scalar(
                    select(PrintVersionModel)
                    .where(PrintVersionModel.print_id == print_id)
                    .order_by(PrintVersionModel.number.desc())
                    .limit(1)
                )
                if latest is None:
                    raise PrintError(PrintFailure.PRINT_DATABASE_UNAVAILABLE)
                if latest.number != expected_version:
                    raise PrintError(PrintFailure.PRINT_VERSION_CONFLICT)
                if latest.number == MAX_VERSION_NUMBER:
                    raise PrintError(PrintFailure.PRINT_VERSION_LIMIT)
                self._require_file(session, file_id)
                version = PrintVersionModel(
                    id=uuid4(),
                    print_id=print_id,
                    number=latest.number + 1,
                    file_id=file_id,
                    surcharge_cents=surcharge_cents,
                )
                session.add(version)
                session.flush()
                result = map_version(version)
                audit_version(
                    session, actor_id, result, "PRINT_VERSION_CREATED"
                )
            return result
        except SQLAlchemyError:
            raise PrintError(PrintFailure.PRINT_DATABASE_UNAVAILABLE) from None

    def get(self, print_id: UUID) -> PrintRecord:
        try:
            with Session(self._engine) as session:
                row = session.get(PrintModel, print_id)
                if row is None:
                    raise PrintError(PrintFailure.PRINT_NOT_FOUND)
                version = session.scalar(
                    select(PrintVersionModel)
                    .where(PrintVersionModel.print_id == print_id)
                    .order_by(PrintVersionModel.number.desc())
                    .limit(1)
                )
                if version is None:
                    raise PrintError(PrintFailure.PRINT_DATABASE_UNAVAILABLE)
                return map_print(row, version)
        except SQLAlchemyError:
            raise PrintError(PrintFailure.PRINT_DATABASE_UNAVAILABLE) from None

    def get_version(
        self,
        print_id: UUID,
        version_id: UUID,
    ) -> PrintVersion:
        try:
            with Session(self._engine) as session:
                row = session.scalar(
                    select(PrintVersionModel).where(
                        PrintVersionModel.id == version_id,
                        PrintVersionModel.print_id == print_id,
                    )
                )
                if row is None:
                    raise PrintError(PrintFailure.PRINT_VERSION_NOT_FOUND)
                return map_version(row)
        except SQLAlchemyError:
            raise PrintError(PrintFailure.PRINT_DATABASE_UNAVAILABLE) from None

    def list(self, after: UUID | None, limit: int) -> tuple[PrintRecord, ...]:
        latest = (
            select(
                PrintVersionModel.print_id.label("print_id"),
                func.max(PrintVersionModel.number).label("number"),
            )
            .group_by(PrintVersionModel.print_id)
            .subquery()
        )
        statement = (
            select(PrintModel, PrintVersionModel)
            .join(latest, latest.c.print_id == PrintModel.id)
            .join(
                PrintVersionModel,
                (
                    (PrintVersionModel.print_id == PrintModel.id)
                    & (PrintVersionModel.number == latest.c.number)
                ),
            )
            .order_by(PrintModel.id)
            .limit(limit)
        )
        if after is not None:
            statement = statement.where(PrintModel.id > after)
        try:
            with Session(self._engine) as session:
                return tuple(
                    map_print(row, version)
                    for row, version in session.execute(statement)
                )
        except SQLAlchemyError:
            raise PrintError(PrintFailure.PRINT_DATABASE_UNAVAILABLE) from None

    def list_versions(
        self,
        print_id: UUID,
        after: int | None,
        limit: int,
    ) -> tuple[PrintVersion, ...]:
        statement = (
            select(PrintVersionModel)
            .where(PrintVersionModel.print_id == print_id)
            .order_by(PrintVersionModel.number, PrintVersionModel.id)
            .limit(limit)
        )
        if after is not None:
            statement = statement.where(PrintVersionModel.number > after)
        try:
            with Session(self._engine) as session:
                if session.get(PrintModel, print_id) is None:
                    raise PrintError(PrintFailure.PRINT_NOT_FOUND)
                return tuple(
                    map_version(row) for row in session.scalars(statement)
                )
        except SQLAlchemyError:
            raise PrintError(PrintFailure.PRINT_DATABASE_UNAVAILABLE) from None
