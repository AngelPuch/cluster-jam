"""Identify a derived image without adding undocumented SQL columns."""

from dataclasses import dataclass, field
from hashlib import sha256
from uuid import UUID, uuid5

from personalization.application.files.file_record import FileRecord, FileState

THUMBNAIL_NAMESPACE = UUID("310b89a7-6d45-5485-9ed7-305c39f4a24f")
THUMBNAIL_USAGE_PREFIX = "MINIATURA_V1:"
THUMBNAIL_SIDE_PX = 320


def thumbnail_id(source_id: UUID) -> UUID:
    """Keep the same immutable identifier across worker restarts."""
    return uuid5(THUMBNAIL_NAMESPACE, str(source_id))


@dataclass(frozen=True)
class RenderedThumbnail:
    content: bytes = field(repr=False)
    width_px: int
    height_px: int

    def record(self, source: FileRecord) -> FileRecord:
        derived_id = thumbnail_id(source.id)
        return FileRecord(
            id=derived_id,
            owner_id=source.owner_id,
            bucket=source.bucket,
            object_key=f"{derived_id}.png",
            mime_type="image/png",
            size_bytes=len(self.content),
            width_px=self.width_px,
            height_px=self.height_px,
            sha256=sha256(self.content).hexdigest(),
            usage=THUMBNAIL_USAGE_PREFIX + str(source.id),
            state=FileState.PENDING,
        )
