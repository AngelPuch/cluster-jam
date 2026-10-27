"""Validate original uploads before assigning trusted file metadata."""

from hashlib import sha256
from uuid import uuid4

from personalization.application.errors.image_validation_error import (
    ImageValidationError,
    ImageValidationFailure,
)
from personalization.application.images.image_format import ImageFormat
from personalization.application.images.image_policy import (
    MAX_UPLOAD_BYTES,
    ImageValidationPolicy,
)
from personalization.application.images.validated_image import ValidatedImage
from personalization.application.ports.image_inspector_port import (
    ImageInspectorPort,
)
from personalization.application.ports.image_source_port import ImageSourcePort

READ_CHUNK_BYTES = 65_536
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
JPEG_SIGNATURE = b"\xff\xd8\xff"


class ValidateImageService:
    """Validate uploads independently of persistence."""

    def __init__(
        self,
        inspector: ImageInspectorPort,
        policy: ImageValidationPolicy,
    ) -> None:
        self._inspector = inspector
        self._policy = policy

    def execute(
        self,
        source: ImageSourcePort,
        declared_mime: str | None = None,
    ) -> ValidatedImage:
        """Return metadata after successful image validation."""
        content = self._read_content(source)
        image_format = self._detect_format(content)
        self._validate_declared_mime(declared_mime, image_format)
        info = self._inspector.inspect(content, image_format, self._policy)
        self._policy.ensure_dimensions(info.width_px, info.height_px)
        if info.image_format is not image_format:
            raise ImageValidationError(ImageValidationFailure.INVALID_IMAGE)
        file_id = uuid4()
        return ValidatedImage(
            file_id=file_id,
            object_key=f"{file_id}.{image_format.extension}",
            mime_type=image_format.mime_type,
            size_bytes=len(content),
            width_px=info.width_px,
            height_px=info.height_px,
            sha256=sha256(content).hexdigest(),
            original_bytes=content,
        )

    def _read_content(self, source: ImageSourcePort) -> bytes:
        """Read at most the byte ceiling plus one before rejecting."""
        content = bytearray()
        try:
            while True:
                chunk = source.read(
                    min(READ_CHUNK_BYTES, MAX_UPLOAD_BYTES + 1 - len(content))
                )
                if not chunk:
                    break
                if len(content) + len(chunk) > MAX_UPLOAD_BYTES:
                    raise ImageValidationError(
                        ImageValidationFailure.IMAGE_TOO_LARGE
                    )
                content.extend(chunk)
        except OSError, ValueError:
            raise ImageValidationError(
                ImageValidationFailure.IMAGE_READ_FAILED
            ) from None
        if not content:
            raise ImageValidationError(ImageValidationFailure.EMPTY_IMAGE)
        return bytes(content)

    def _detect_format(self, content: bytes) -> ImageFormat:
        """Require PNG or JPEG magic bytes before decoding."""
        if content.startswith(PNG_SIGNATURE):
            return ImageFormat.PNG
        if content.startswith(JPEG_SIGNATURE):
            return ImageFormat.JPEG
        raise ImageValidationError(
            ImageValidationFailure.UNSUPPORTED_IMAGE_TYPE
        )

    def _validate_declared_mime(
        self,
        declared_mime: str | None,
        image_format: ImageFormat,
    ) -> None:
        """Check specific declarations against actual image types."""
        if declared_mime is None:
            return
        mime_type = declared_mime.partition(";")[0].strip().lower()
        if mime_type == "application/octet-stream":
            return
        if mime_type not in {"image/png", "image/jpeg"}:
            raise ImageValidationError(
                ImageValidationFailure.UNSUPPORTED_IMAGE_TYPE
            )
        if mime_type != image_format.mime_type:
            raise ImageValidationError(
                ImageValidationFailure.IMAGE_MIME_MISMATCH
            )
