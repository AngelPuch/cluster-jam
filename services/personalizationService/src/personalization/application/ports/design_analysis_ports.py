"""Resolve trusted original-file data and oriented image geometry."""

from typing import Protocol

from personalization.application.designs.analysis_record import (
    AnalysisSelection,
    ImageGeometry,
    ResolvedSource,
)
from personalization.application.files.file_record import FileRecord


class AnalysisSourcePort(Protocol):
    def resolve(
        self, selections: tuple[AnalysisSelection, ...]
    ) -> tuple[ResolvedSource, ...]: ...


class ImageGeometryPort(Protocol):
    def inspect(self, record: FileRecord) -> ImageGeometry: ...
