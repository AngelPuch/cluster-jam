"""Read source metadata and immutable print prices in batches."""

from sqlalchemy import Engine, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from personalization.application.designs.analysis_record import (
    AnalysisSelection,
    ResolvedSource,
)
from personalization.application.errors.design_analysis_error import (
    AnalysisFailure,
    DesignAnalysisError,
)
from personalization.application.files.file_record import FileState
from personalization.infrastructure.database.file_repository import map_file
from personalization.infrastructure.database.models.image_file import FileModel
from personalization.infrastructure.database.models.print_version import (
    PrintVersionModel,
)


class SqlAlchemyAnalysisSourceRepository:
    def __init__(self, engine: Engine, bucket: str) -> None:
        self._engine = engine
        self._bucket = bucket

    def resolve(
        self, selections: tuple[AnalysisSelection, ...]
    ) -> tuple[ResolvedSource, ...]:
        own_ids = {
            item.file_id for item in selections if item.file_id is not None
        }
        version_ids = {
            item.print_version_id
            for item in selections
            if item.print_version_id is not None
        }
        try:
            with Session(self._engine) as session:
                originals = (
                    {
                        row.id: ResolvedSource(map_file(row), 0)
                        for row in session.scalars(
                            select(FileModel).where(FileModel.id.in_(own_ids))
                        )
                    }
                    if own_ids
                    else {}
                )
                prints = (
                    {
                        version.id: ResolvedSource(
                            map_file(row), version.surcharge_cents
                        )
                        for version, row in session.execute(
                            select(PrintVersionModel, FileModel)
                            .join(
                                FileModel,
                                FileModel.id == PrintVersionModel.file_id,
                            )
                            .where(PrintVersionModel.id.in_(version_ids))
                        )
                    }
                    if version_ids
                    else {}
                )
                result: list[ResolvedSource] = []
                for selection in selections:
                    if selection.print_version_id is not None:
                        source = prints.get(selection.print_version_id)
                    elif selection.file_id is not None:
                        source = originals.get(selection.file_id)
                    else:
                        raise DesignAnalysisError(
                            AnalysisFailure.INVALID_DESIGN_ANALYSIS
                        )
                    if source is None:
                        raise DesignAnalysisError(
                            AnalysisFailure.ANALYSIS_SOURCE_NOT_FOUND
                        )
                    record = source.file
                    if (
                        record.usage != "ORIGINAL"
                        or record.state is not FileState.AVAILABLE
                        or record.bucket != self._bucket
                    ):
                        raise DesignAnalysisError(
                            AnalysisFailure.ANALYSIS_SOURCE_NOT_READY
                        )
                    result.append(source)
                return tuple(result)
        except SQLAlchemyError, ValueError:
            raise DesignAnalysisError(
                AnalysisFailure.ANALYSIS_DATABASE_UNAVAILABLE
            ) from None
