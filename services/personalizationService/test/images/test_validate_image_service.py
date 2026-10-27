"""Exercise byte ceilings, declarations, and trusted upload metadata."""

from hashlib import sha256
from io import BytesIO
from uuid import UUID

import pytest

from personalization.application.errors.image_validation_error import (
    ImageValidationError,
    ImageValidationFailure,
)
from personalization.application.images.image_format import ImageFormat
from personalization.application.images.image_policy import (
    MAX_UPLOAD_BYTES,
    ImageValidationPolicy,
)
from personalization.application.images.validate_image_service import (
    PNG_SIGNATURE,
    ValidateImageService,
)
from personalization.application.images.validated_image import ImageInfo


class RecordingInspector:
    """Isolate application rules from the separately tested decoder."""

    def __init__(self) -> None:
        self.calls = 0
        self.info = ImageInfo(ImageFormat.PNG, 12, 8)

    def inspect(
        self,
        content: bytes,
        expected_format: ImageFormat,
        policy: ImageValidationPolicy,
    ) -> ImageInfo:
        self.calls += 1
        return self.info


class BoundedSource:
    """Track reads without allocating an oversized source in advance."""

    def __init__(self, size: int, chunk_limit: int = 65_536) -> None:
        self._size = size
        self._chunk_limit = chunk_limit
        self.position = 0
        self.requests: list[int] = []

    def read(self, size: int = -1) -> bytes:
        assert size > 0
        self.requests.append(size)
        count = min(size, self._chunk_limit, self._size - self.position)
        start = self.position
        self.position += count
        return (PNG_SIGNATURE[start : start + count] + b"x" * count)[:count]


@pytest.fixture
def inspector() -> RecordingInspector:
    return RecordingInspector()


@pytest.fixture
def validator(inspector: RecordingInspector) -> ValidateImageService:
    return ValidateImageService(inspector, ImageValidationPolicy())


@pytest.mark.parametrize("size", [MAX_UPLOAD_BYTES - 1, MAX_UPLOAD_BYTES])
def test_byte_limit_is_inclusive(
    validator: ValidateImageService,
    inspector: RecordingInspector,
    size: int,
) -> None:
    source = BoundedSource(size)
    result = validator.execute(source, "image/png")
    assert result.size_bytes == size
    assert source.position == size
    assert max(source.requests) <= 65_536
    assert result.sha256 == sha256(result.original_bytes).hexdigest()
    assert inspector.calls == 1


@pytest.mark.parametrize("size", [MAX_UPLOAD_BYTES + 1, 1_000_000_000])
def test_oversized_stream_stops_before_decoder(
    validator: ValidateImageService,
    inspector: RecordingInspector,
    size: int,
) -> None:
    source = BoundedSource(size)
    with pytest.raises(ImageValidationError) as caught:
        validator.execute(source)
    assert caught.value.failure is ImageValidationFailure.IMAGE_TOO_LARGE
    assert source.position == MAX_UPLOAD_BYTES + 1
    assert inspector.calls == 0


def test_short_non_seekable_reads_are_not_treated_as_end_of_input(
    validator: ValidateImageService,
) -> None:
    source = BoundedSource(30, chunk_limit=3)
    assert validator.execute(source).size_bytes == 30
    assert len(source.requests) == 11


@pytest.mark.parametrize(
    "mime",
    [
        None,
        "image/png",
        "IMAGE/PNG",
        "image/png; parameter=value",
        "application/octet-stream",
    ],
)
def test_accepted_declarations_never_replace_real_metadata(
    validator: ValidateImageService,
    mime: str | None,
) -> None:
    source = BytesIO(PNG_SIGNATURE + b"private-original-content")
    result = validator.execute(source, mime)
    assert source.closed is False
    assert result.mime_type == "image/png"
    assert result.object_key == f"{result.file_id}.png"
    assert UUID(str(result.file_id)).version == 4
    assert "private-original-content" not in repr(result)


@pytest.mark.parametrize(
    ("content", "mime", "failure"),
    [
        (b"", None, ImageValidationFailure.EMPTY_IMAGE),
        (
            b"GIF89a",
            "image/png",
            ImageValidationFailure.UNSUPPORTED_IMAGE_TYPE,
        ),
        (
            b"<svg/>",
            "image/png",
            ImageValidationFailure.UNSUPPORTED_IMAGE_TYPE,
        ),
        (
            PNG_SIGNATURE,
            "image/jpeg",
            ImageValidationFailure.IMAGE_MIME_MISMATCH,
        ),
        (
            PNG_SIGNATURE,
            "image/jpg",
            ImageValidationFailure.UNSUPPORTED_IMAGE_TYPE,
        ),
        (
            PNG_SIGNATURE,
            "text/plain",
            ImageValidationFailure.UNSUPPORTED_IMAGE_TYPE,
        ),
    ],
)
def test_empty_unsupported_and_conflicting_inputs_do_not_decode(
    validator: ValidateImageService,
    inspector: RecordingInspector,
    content: bytes,
    mime: str | None,
    failure: ImageValidationFailure,
) -> None:
    with pytest.raises(ImageValidationError) as caught:
        validator.execute(BytesIO(content), mime)
    assert caught.value.failure is failure
    assert inspector.calls == 0


def test_unreadable_stream_does_not_expose_internal_paths(
    validator: ValidateImageService,
) -> None:
    class UnreadableSource:
        def read(self, size: int = -1) -> bytes:
            raise OSError("private-file-location")

    with pytest.raises(ImageValidationError) as caught:
        validator.execute(UnreadableSource())
    assert caught.value.failure is ImageValidationFailure.IMAGE_READ_FAILED
    assert "private-file-location" not in str(caught.value)


@pytest.mark.parametrize(
    "info",
    [
        ImageInfo(ImageFormat.PNG, 8193, 1),
        ImageInfo(ImageFormat.PNG, 4001, 4000),
        ImageInfo(ImageFormat.JPEG, 12, 8),
    ],
)
def test_application_rechecks_decoder_metadata(
    validator: ValidateImageService,
    inspector: RecordingInspector,
    info: ImageInfo,
) -> None:
    inspector.info = info
    with pytest.raises(ImageValidationError):
        validator.execute(BytesIO(PNG_SIGNATURE))


@pytest.mark.parametrize(
    "limits",
    [
        {"max_width_px": 0},
        {"max_height_px": -1},
        {"max_pixels": 16_000_001},
        {"max_width_px": 8193},
        {"max_pixels": True},
    ],
)
def test_direct_policy_construction_cannot_disable_limits(
    limits: dict[str, int],
) -> None:
    with pytest.raises(ValueError):
        ImageValidationPolicy(**limits)
