"""Keep catalog test data independent of SQL and real identities."""

from dataclasses import replace
from uuid import UUID, uuid4

from personalization.application.catalog.catalog_record import CatalogPrint
from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.files.file_record import FileState
from test.image_samples import make_image
from test.thumbnails.fakes import source_record
from test.thumbnails.test_thumbnail_worker import renderer


def catalog_record(print_id: UUID | None = None) -> CatalogPrint:
    source = source_record()
    thumbnail = renderer().render(source, make_image()).record(source)
    return CatalogPrint(
        print_id or uuid4(),
        "Logo",
        "Preloaded print",
        uuid4(),
        1,
        1250,
        replace(thumbnail, state=FileState.AVAILABLE),
    )


class MemoryCatalogRepository:
    def __init__(self) -> None:
        self.rows: dict[UUID, CatalogPrint] = {}
        self.calls = 0
        self.unavailable = False

    def _check(self) -> None:
        self.calls += 1
        if self.unavailable:
            raise PrintError(PrintFailure.PRINT_DATABASE_UNAVAILABLE)

    def list(self, after: UUID | None, limit: int) -> tuple[CatalogPrint, ...]:
        self._check()
        return tuple(
            sorted(
                (
                    row
                    for row in self.rows.values()
                    if after is None or row.id.int > after.int
                ),
                key=lambda row: row.id.int,
            )[:limit]
        )

    def get(self, print_id: UUID) -> CatalogPrint | None:
        self._check()
        return self.rows.get(print_id)
