"""Resolve test metadata without a production authorization bypass."""

from dataclasses import dataclass, replace
from uuid import UUID, uuid4

from personalization.application.designs.analysis_record import (
    AnalysisSelection,
    ImageGeometry,
    ResolvedSource,
)
from personalization.application.errors.design_analysis_error import (
    AnalysisFailure,
    DesignAnalysisError,
)
from personalization.application.files.file_record import FileRecord
from personalization.application.templates.template_record import (
    Side,
    TemplateRecord,
)
from test.image_samples import make_image
from test.templates.fakes import MemoryTemplateRepository, definition
from test.thumbnails.fakes import source_record


class MemoryAnalysisSources:
    def __init__(self, file: FileRecord, print_id: UUID) -> None:
        self.file = file
        self.print_id = print_id
        self.calls = 0

    def resolve(
        self, selections: tuple[AnalysisSelection, ...]
    ) -> tuple[ResolvedSource, ...]:
        self.calls += 1
        result = []
        for item in selections:
            if item.file_id == self.file.id and item.print_version_id is None:
                result.append(ResolvedSource(self.file, 0))
            elif (
                item.print_version_id == self.print_id and item.file_id is None
            ):
                result.append(ResolvedSource(self.file, 500))
            else:
                raise DesignAnalysisError(
                    AnalysisFailure.ANALYSIS_SOURCE_NOT_FOUND
                )
        return tuple(result)


class MemoryImageGeometry:
    def __init__(self) -> None:
        self.calls: list[UUID] = []

    def inspect(self, record: FileRecord) -> ImageGeometry:
        self.calls.append(record.id)
        return ImageGeometry(record.width_px, record.height_px)


@dataclass
class AnalysisData:
    templates: MemoryTemplateRepository
    template: TemplateRecord
    sources: MemoryAnalysisSources
    geometry: MemoryImageGeometry
    selections: tuple[AnalysisSelection, ...]


def analysis_data() -> AnalysisData:
    value = definition()
    value = replace(
        value, zones=(*value.zones, replace(value.zones[0], side=Side.BACK))
    )
    templates = MemoryTemplateRepository()
    template = templates.create(uuid4(), uuid4(), 1, 0, value)
    file = source_record(
        make_image(size=(200, 100)), width_px=200, height_px=100
    )
    print_id = uuid4()
    selections = (
        AnalysisSelection(
            template.zones[0].id,
            template.zones[0].sizes[0].id,
            print_version_id=print_id,
        ),
        AnalysisSelection(
            template.zones[1].id,
            template.zones[1].sizes[0].id,
            file_id=file.id,
        ),
    )
    return AnalysisData(
        templates,
        template,
        MemoryAnalysisSources(file, print_id),
        MemoryImageGeometry(),
        selections,
    )
