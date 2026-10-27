"""Verify PNG/JPEG structure and fully decode bounded originals."""

import struct
import warnings
import zlib
from io import BytesIO

from PIL import Image

from personalization.application.errors.image_validation_error import (
    ImageValidationError,
    ImageValidationFailure,
)
from personalization.application.images.image_format import ImageFormat
from personalization.application.images.image_policy import (
    ImageValidationPolicy,
)
from personalization.application.images.validated_image import ImageInfo


class PillowImageInspector:
    """Decode originals without changing Pillow limits."""

    def __init__(self) -> None:
        # Configure warnings during composition, before requests.
        warnings.filterwarnings(
            "error", category=UserWarning, module=r"^PIL(?:\.|$)"
        )
        warnings.filterwarnings(
            "error", category=Image.DecompressionBombWarning
        )

    def inspect(
        self,
        content: bytes,
        expected_format: ImageFormat,
        policy: ImageValidationPolicy,
    ) -> ImageInfo:
        """Check dimensions before loading the pixel buffer."""
        try:
            with BytesIO(content) as original:
                with Image.open(
                    original, formats=[expected_format.value]
                ) as image:
                    if image.format != expected_format.value:
                        raise ImageValidationError(
                            ImageValidationFailure.UNSUPPORTED_IMAGE_TYPE
                        )
                    policy.ensure_dimensions(image.width, image.height)
                    if getattr(image, "n_frames", 1) != 1:
                        raise ImageValidationError(
                            ImageValidationFailure.ANIMATED_IMAGE_NOT_SUPPORTED
                        )
                    info = ImageInfo(
                        image_format=expected_format,
                        width_px=image.width,
                        height_px=image.height,
                    )
                    image.verify()
            with BytesIO(content) as original:
                with Image.open(
                    original, formats=[expected_format.value]
                ) as image:
                    image.load()
            return info
        except Image.DecompressionBombError, Image.DecompressionBombWarning:
            raise ImageValidationError(
                ImageValidationFailure.IMAGE_DIMENSIONS_EXCEEDED
            ) from None
        except (
            OSError,
            UserWarning,
            ValueError,
            SyntaxError,
            EOFError,
            OverflowError,
            struct.error,
            zlib.error,
        ):
            raise ImageValidationError(
                ImageValidationFailure.INVALID_IMAGE
            ) from None
