"""Require full decoding without coupling application code to Pillow."""

from typing import Protocol

from personalization.application.images.image_format import ImageFormat
from personalization.application.images.image_policy import (
    ImageValidationPolicy,
)
from personalization.application.images.validated_image import ImageInfo


class ImageInspectorPort(Protocol):
    """Inspect bounded content and enforce limits before decoding."""

    def inspect(
        self,
        content: bytes,
        expected_format: ImageFormat,
        policy: ImageValidationPolicy,
    ) -> ImageInfo:
        """Return metadata after a complete successful decode."""
        ...
