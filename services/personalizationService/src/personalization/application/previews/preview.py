"""Identify revision-specific private images without new SQL columns."""

from dataclasses import dataclass, field, replace
from fractions import Fraction
from hashlib import sha256
from uuid import UUID, uuid5

from personalization.application.designs.draft_record import (
    DesignState,
    DraftRecord,
    draft_revision,
)
from personalization.application.files.file_record import FileRecord, FileState
from personalization.application.templates.template_record import (
    Side,
    TemplateRecord,
)

PREVIEW_NAMESPACE = UUID("53072e72-d520-5c42-af8a-bf25c06a8583")
PREVIEW_SIDE_PX = 1024


def preview_revision(draft: DraftRecord) -> str:
    # Publishing previews must not change the input revision.
    return draft_revision(
        replace(
            draft,
            front_preview_id=None,
            back_preview_id=None,
            state=DesignState.DRAFT,
        )
    )


def preview_id(draft: DraftRecord, side: Side) -> UUID:
    return uuid5(
        PREVIEW_NAMESPACE, f"{draft.id}:{preview_revision(draft)}:{side.value}"
    )


def preview_usage(draft: DraftRecord, side: Side) -> str:
    return f"PREVIA_V1:{draft.id}:{preview_revision(draft)}:{side.value}"


def preview_scale(template: TemplateRecord) -> Fraction:
    header = template.header
    largest = max(
        header.front.width_mm,
        header.front.height_mm,
        header.back.width_mm,
        header.back.height_mm,
    )
    return Fraction(PREVIEW_SIDE_PX) / Fraction(largest)


def canvas_size(template: TemplateRecord, side: Side) -> tuple[int, int]:
    dimensions = (
        template.header.front if side is Side.FRONT else template.header.back
    )
    scale = preview_scale(template)
    return (
        max(1, round(Fraction(dimensions.width_mm) * scale)),
        max(1, round(Fraction(dimensions.height_mm) * scale)),
    )


@dataclass(frozen=True)
class RenderedPreview:
    side: Side
    content: bytes = field(repr=False)
    width_px: int
    height_px: int

    def record(self, draft: DraftRecord, bucket: str) -> FileRecord:
        identifier = preview_id(draft, self.side)
        return FileRecord(
            identifier,
            draft.owner_id,
            bucket,
            f"{identifier}.png",
            "image/png",
            len(self.content),
            self.width_px,
            self.height_px,
            sha256(self.content).hexdigest(),
            FileState.PENDING,
            preview_usage(draft, self.side),
        )


def check_preview(
    draft: DraftRecord, side: Side, record: FileRecord, bucket: str
) -> bool:
    return (
        record.id == preview_id(draft, side)
        and record.owner_id == draft.owner_id
        and record.bucket == bucket
        and record.object_key == f"{record.id}.png"
        and record.mime_type == "image/png"
        and record.usage == preview_usage(draft, side)
        and 1 <= record.width_px <= PREVIEW_SIDE_PX
        and 1 <= record.height_px <= PREVIEW_SIDE_PX
    )


@dataclass(frozen=True)
class PreviewStatus:
    draft: DraftRecord
    front: FileRecord | None
    back: FileRecord | None
