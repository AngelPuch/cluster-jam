"""Describe private file resources without exposing bucket paths."""

from datetime import datetime
from uuid import UUID

from pydantic import Field

from personalization.application.files.file_record import FileRecord, FileState
from personalization.interfaces.http.dto.rest_model import RestModel


class FileResponse(RestModel):
    """Expose safe file metadata with the project's
    camelCase aliases.
    """

    id: UUID
    owner_id: UUID
    mime_type: str
    size_bytes: int
    width_px: int
    height_px: int
    sha256: str
    state: FileState

    @classmethod
    def from_record(cls, record: FileRecord) -> FileResponse:
        """Keep ORM and storage details out of the HTTP contract."""
        return cls(
            id=record.id,
            owner_id=record.owner_id,
            mime_type=record.mime_type,
            size_bytes=record.size_bytes,
            width_px=record.width_px,
            height_px=record.height_px,
            sha256=record.sha256,
            state=record.state,
        )


class DownloadResponse(RestModel):
    """Return a short-lived bearer link without including it in repr."""

    file_id: UUID
    expires_at: datetime
    download_url: str = Field(repr=False)
