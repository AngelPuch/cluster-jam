"""Keep image rejection reasons independent from HTTP and Pillow."""

from enum import StrEnum


class ImageValidationFailure(StrEnum):
    """Expose stable codes without retaining image contents."""

    EMPTY_IMAGE = "EMPTY_IMAGE"
    IMAGE_TOO_LARGE = "IMAGE_TOO_LARGE"
    UNSUPPORTED_IMAGE_TYPE = "UNSUPPORTED_IMAGE_TYPE"
    IMAGE_MIME_MISMATCH = "IMAGE_MIME_MISMATCH"
    INVALID_IMAGE = "INVALID_IMAGE"
    IMAGE_DIMENSIONS_EXCEEDED = "IMAGE_DIMENSIONS_EXCEEDED"
    ANIMATED_IMAGE_NOT_SUPPORTED = "ANIMATED_IMAGE_NOT_SUPPORTED"
    IMAGE_READ_FAILED = "IMAGE_READ_FAILED"


class ImageValidationError(Exception):
    """Carry a safe reason without echoing decoder or upload details."""

    def __init__(self, failure: ImageValidationFailure) -> None:
        super().__init__(failure.value)
        self.failure = failure
