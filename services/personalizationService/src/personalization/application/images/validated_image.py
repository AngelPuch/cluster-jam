"""Return verified metadata and unchanged original bytes for storage."""

from dataclasses import dataclass, field
from uuid import UUID

from personalization.application.images.image_format import ImageFormat


@dataclass(frozen=True)
class ImageInfo:
    """Describe an original that the decoder successfully inspected."""

    image_format: ImageFormat
    width_px: int
    height_px: int


@dataclass(frozen=True)
class ValidatedImage:
    """Keep bytes out of representations and expose no storage URL."""

    file_id: UUID
    object_key: str
    mime_type: str
    size_bytes: int
    width_px: int
    height_px: int
    sha256: str
    original_bytes: bytes = field(repr=False)
