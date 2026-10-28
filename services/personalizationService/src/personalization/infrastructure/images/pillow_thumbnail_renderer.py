"""Produce small PNGs while preserving aspect ratio and transparency."""

from io import BytesIO

from PIL import Image, ImageOps

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.errors.image_validation_error import (
    ImageValidationError,
    ImageValidationFailure,
)
from personalization.application.files.file_record import FileRecord
from personalization.application.images.validate_image_service import (
    ValidateImageService,
)
from personalization.application.thumbnails.thumbnail import (
    THUMBNAIL_SIDE_PX,
    RenderedThumbnail,
)


class PillowThumbnailRenderer:
    def __init__(self, validator: ValidateImageService) -> None:
        self._validator = validator

    def render(self, source: FileRecord, content: bytes) -> RenderedThumbnail:
        """Revalidate, preserve proportions, and remove metadata."""
        checked = self._validator.execute(BytesIO(content), source.mime_type)
        if (
            checked.sha256 != source.sha256
            or checked.size_bytes != source.size_bytes
            or checked.width_px != source.width_px
            or checked.height_px != source.height_px
        ):
            raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
        try:
            with Image.open(
                BytesIO(content), formats=["PNG", "JPEG"]
            ) as image:
                ImageOps.exif_transpose(image, in_place=True)
                image.thumbnail(
                    (THUMBNAIL_SIDE_PX, THUMBNAIL_SIDE_PX),
                    Image.Resampling.LANCZOS,
                )
                with image.convert("RGBA") as rgba:
                    with Image.frombytes(
                        "RGBA", rgba.size, rgba.tobytes()
                    ) as clean:
                        with BytesIO() as output:
                            clean.save(output, format="PNG", compress_level=6)
                            return RenderedThumbnail(
                                output.getvalue(), clean.width, clean.height
                            )
        except OSError, ValueError, UserWarning:
            raise ImageValidationError(
                ImageValidationFailure.INVALID_IMAGE
            ) from None
