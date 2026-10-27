"""Represent local file metadata without retaining credentials."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from uuid import UUID


class FileState(StrEnum):
    """Publish originals only after acknowledged storage success."""

    PENDING = "PENDIENTE_CARGA"
    AVAILABLE = "DISPONIBLE"


@dataclass(frozen=True)
class FileRecord:
    """Keep only metadata required by the documented archivo table."""

    id: UUID
    owner_id: UUID
    bucket: str
    object_key: str
    mime_type: str
    size_bytes: int
    width_px: int
    height_px: int
    sha256: str
    state: FileState
    usage: str = "ORIGINAL"


@dataclass(frozen=True)
class SignedDownload:
    """Do not expose bearer download URLs in object representations."""

    file_id: UUID
    expires_at: datetime
    download_url: str = field(repr=False)
