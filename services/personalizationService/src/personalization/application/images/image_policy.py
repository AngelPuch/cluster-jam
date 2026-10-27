"""Bound image validation before allocating a decoded pixel buffer."""

from dataclasses import dataclass

from personalization.application.errors.image_validation_error import (
    ImageValidationError,
    ImageValidationFailure,
)

MAX_UPLOAD_BYTES = 10_000_000
MAX_IMAGE_SIDE_PX = 8192
MAX_IMAGE_PIXELS = 16_000_000


@dataclass(frozen=True)
class ImageValidationPolicy:
    """Allow deployment settings to tighten initial resource limits."""

    max_width_px: int = MAX_IMAGE_SIDE_PX
    max_height_px: int = MAX_IMAGE_SIDE_PX
    max_pixels: int = MAX_IMAGE_PIXELS

    def __post_init__(self) -> None:
        for value, ceiling in (
            (self.max_width_px, MAX_IMAGE_SIDE_PX),
            (self.max_height_px, MAX_IMAGE_SIDE_PX),
            (self.max_pixels, MAX_IMAGE_PIXELS),
        ):
            if type(value) is not int or not 1 <= value <= ceiling:
                raise ValueError("Image limits must be positive and bounded")

    def ensure_dimensions(self, width_px: int, height_px: int) -> None:
        """Validate encoded dimensions without floating point math."""
        if (
            width_px < 1
            or height_px < 1
            or width_px > self.max_width_px
            or height_px > self.max_height_px
            or width_px * height_px > self.max_pixels
        ):
            raise ImageValidationError(
                ImageValidationFailure.IMAGE_DIMENSIONS_EXCEEDED
            )
