"""Describe the two permitted original image formats."""

from enum import StrEnum


class ImageFormat(StrEnum):
    """Separate decoded formats from MIME declarations."""

    PNG = "PNG"
    JPEG = "JPEG"

    @property
    def mime_type(self) -> str:
        """Return the canonical MIME determined from image contents."""
        return "image/png" if self is ImageFormat.PNG else "image/jpeg"

    @property
    def extension(self) -> str:
        """Choose a suffix without accepting a client filename."""
        return "png" if self is ImageFormat.PNG else "jpg"
