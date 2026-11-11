"""Share bounded processing results across image worker tasks."""

from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ImageBatch:
    completed: int
    busy: int
    failures: tuple[str, ...]
    after: UUID | None
