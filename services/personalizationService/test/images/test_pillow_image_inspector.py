"""Exercise real PNG/JPEG structure checks and pixel decoding."""

import struct
import warnings
import zlib
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
from io import BytesIO

import pytest
from PIL import Image, ImageFile

from personalization.application.errors.image_validation_error import (
    ImageValidationError,
    ImageValidationFailure,
)
from personalization.application.images.image_policy import (
    ImageValidationPolicy,
)
from personalization.application.images.validate_image_service import (
    ValidateImageService,
)
from personalization.infrastructure.images.pillow_image_inspector import (
    PillowImageInspector,
)
from test.image_samples import make_image


@pytest.fixture
def validator() -> ValidateImageService:
    return ValidateImageService(
        PillowImageInspector(), ImageValidationPolicy()
    )


@pytest.mark.parametrize(
    ("image_format", "mode"),
    [
        ("PNG", "RGB"),
        ("PNG", "RGBA"),
        ("PNG", "L"),
        ("PNG", "P"),
        ("PNG", "I;16"),
        ("JPEG", "RGB"),
        ("JPEG", "L"),
        ("JPEG", "CMYK"),
    ],
)
def test_real_originals_are_decoded_without_modification(
    validator: ValidateImageService,
    image_format: str,
    mode: str,
) -> None:
    content = make_image(image_format, mode=mode)
    result = validator.execute(BytesIO(content))
    assert (result.width_px, result.height_px) == (12, 8)
    assert result.original_bytes == content
    assert result.sha256 == sha256(content).hexdigest()
    assert result.mime_type == (
        "image/png" if image_format == "PNG" else "image/jpeg"
    )
    assert result.object_key.endswith(
        ".png" if image_format == "PNG" else ".jpg"
    )


def test_progressive_jpeg_is_supported(
    validator: ValidateImageService,
) -> None:
    assert (
        validator.execute(
            BytesIO(make_image("JPEG", progressive=True))
        ).mime_type
        == "image/jpeg"
    )


@pytest.mark.parametrize("image_format", ["GIF", "BMP", "TIFF"])
def test_other_decodable_formats_are_rejected(
    validator: ValidateImageService,
    image_format: str,
) -> None:
    content = make_image(image_format, mode="RGB")
    with pytest.raises(ImageValidationError) as caught:
        validator.execute(BytesIO(content), "image/png")
    assert (
        caught.value.failure is ImageValidationFailure.UNSUPPORTED_IMAGE_TYPE
    )


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
def test_truncated_original_is_rejected(
    validator: ValidateImageService,
    image_format: str,
) -> None:
    content = make_image(image_format)
    truncated = content[:-12] if image_format == "PNG" else content[:-2]
    with pytest.raises(ImageValidationError) as caught:
        validator.execute(BytesIO(truncated))
    assert caught.value.failure is ImageValidationFailure.INVALID_IMAGE


def test_bad_png_crc_is_rejected(validator: ValidateImageService) -> None:
    content = bytearray(make_image())
    content[content.index(b"IDAT") + 4] ^= 1
    with pytest.raises(ImageValidationError) as caught:
        validator.execute(BytesIO(content))
    assert caught.value.failure is ImageValidationFailure.INVALID_IMAGE


def test_valid_crc_does_not_replace_full_pixel_decode(
    validator: ValidateImageService,
) -> None:
    original = make_image()
    offset = original.index(b"IDAT") - 4
    original_length = int.from_bytes(original[offset : offset + 4], "big")
    data = b"not-a-zlib-image-stream"
    chunk = struct.pack(">I", len(data)) + b"IDAT" + data
    chunk += struct.pack(">I", zlib.crc32(b"IDAT" + data))
    corrupt = (
        original[:offset] + chunk + original[offset + original_length + 12 :]
    )
    with Image.open(BytesIO(corrupt)) as image:
        image.verify()
    with pytest.raises(ImageValidationError) as caught:
        validator.execute(BytesIO(corrupt))
    assert caught.value.failure is ImageValidationFailure.INVALID_IMAGE


def test_animated_png_is_rejected(validator: ValidateImageService) -> None:
    with (
        Image.new("RGBA", (12, 8), "red") as first,
        Image.new("RGBA", (12, 8), "blue") as second,
        BytesIO() as output,
    ):
        first.save(
            output,
            format="PNG",
            save_all=True,
            append_images=[second],
            duration=100,
            loop=0,
        )
        content = output.getvalue()
    with pytest.raises(ImageValidationError) as caught:
        validator.execute(BytesIO(content))
    assert caught.value.failure is (
        ImageValidationFailure.ANIMATED_IMAGE_NOT_SUPPORTED
    )


@pytest.mark.parametrize(
    ("size", "policy", "accepted"),
    [
        ((12, 8), ImageValidationPolicy(12, 8, 96), True),
        ((13, 8), ImageValidationPolicy(12, 8, 104), False),
        ((12, 9), ImageValidationPolicy(12, 8, 108), False),
        ((12, 8), ImageValidationPolicy(12, 8, 95), False),
    ],
)
def test_dimension_and_pixel_limits_are_inclusive(
    size: tuple[int, int],
    policy: ImageValidationPolicy,
    accepted: bool,
) -> None:
    service = ValidateImageService(PillowImageInspector(), policy)
    content = make_image(size=size)
    if accepted:
        assert service.execute(BytesIO(content)).width_px == size[0]
    else:
        with pytest.raises(ImageValidationError) as caught:
            service.execute(BytesIO(content))
        assert caught.value.failure is (
            ImageValidationFailure.IMAGE_DIMENSIONS_EXCEEDED
        )


@pytest.mark.parametrize("side", [8193, 10000, 50000])
def test_large_headers_are_rejected_before_pixel_allocation(
    validator: ValidateImageService,
    monkeypatch: pytest.MonkeyPatch,
    side: int,
) -> None:
    original = bytearray(make_image(size=(2, 2)))
    original[16:24] = struct.pack(">II", side, side)
    original[29:33] = struct.pack(">I", zlib.crc32(original[12:29]))

    def unexpected_load(self: Image.Image) -> None:
        raise AssertionError("Oversized headers must not allocate pixels")

    monkeypatch.setattr(ImageFile.ImageFile, "load", unexpected_load)
    with pytest.raises(ImageValidationError) as caught:
        validator.execute(BytesIO(original))
    assert caught.value.failure is (
        ImageValidationFailure.IMAGE_DIMENSIONS_EXCEEDED
    )


def test_concurrent_validation_does_not_change_decoder_globals(
    validator: ValidateImageService,
) -> None:
    content = make_image()
    filters = list(warnings.filters)
    pillow_limit = Image.MAX_IMAGE_PIXELS
    strict = ImageFile.LOAD_TRUNCATED_IMAGES
    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(
            pool.map(lambda _: validator.execute(BytesIO(content)), range(24))
        )
    assert len({result.object_key for result in results}) == 24
    assert {result.sha256 for result in results} == {
        sha256(content).hexdigest()
    }
    assert warnings.filters == filters
    assert Image.MAX_IMAGE_PIXELS == pillow_limit
    assert ImageFile.LOAD_TRUNCATED_IMAGES is strict is False


def test_invalid_apng_warning_is_a_sanitized_rejection(
    validator: ValidateImageService,
    capsys: pytest.CaptureFixture[str],
) -> None:
    original = make_image()
    payload = b"acTL" + struct.pack(">II", 0, 0)
    chunk = struct.pack(">I", 8) + payload
    chunk += struct.pack(">I", zlib.crc32(payload))
    content = original[:33] + chunk + original[33:]
    with pytest.raises(ImageValidationError) as caught:
        validator.execute(BytesIO(content))
    assert caught.value.failure is ImageValidationFailure.INVALID_IMAGE
    assert capsys.readouterr().err == ""
