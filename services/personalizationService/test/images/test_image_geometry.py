"""Verify JPEG/PNG orientation without loading or changing pixels."""

import struct
from dataclasses import replace
from io import BytesIO

import pytest
from PIL import Image, ImageOps, PngImagePlugin

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.images.image_policy import (
    ImageValidationPolicy,
)
from personalization.infrastructure.images.image_geometry import (
    PillowImageGeometry,
    png_metadata,
)
from test.files.fakes import BUCKET, StorageServer
from test.image_samples import make_image
from test.thumbnails.fakes import source_record


def move_after_pixels(content: bytes, kind: bytes) -> bytes:
    chunks = []
    selected = []
    offset = 8
    while offset + 12 <= len(content):
        length = struct.unpack(">I", content[offset : offset + 4])[0]
        end = offset + length + 12
        chunk = content[offset:end]
        if content[offset + 4 : offset + 8] == kind:
            selected.append(chunk)
        elif content[offset + 4 : offset + 8] == b"IEND":
            chunks.extend(selected)
            chunks.append(chunk)
        else:
            chunks.append(chunk)
        offset = end
    return content[:8] + b"".join(chunks)


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
@pytest.mark.parametrize("orientation", range(1, 9))
def test_header_geometry_matches_worker_orientation_without_pixel_decode(
    image_format: str,
    orientation: int,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    exif = Image.Exif()
    exif[274] = orientation
    content = make_image(image_format, size=(24, 12), exif=exif)
    mime = "image/png" if image_format == "PNG" else "image/jpeg"
    record = source_record(content, width_px=24, height_px=12, mime_type=mime)
    if image_format == "JPEG":
        record = replace(record, object_key=f"{record.id}.jpg")
    with Image.open(BytesIO(content)) as image:
        with ImageOps.exif_transpose(image) as oriented:
            expected = oriented.size

    def forbidden_load(self: Image.Image) -> None:
        raise AssertionError("Analysis must not decode pixels")

    monkeypatch.setattr(Image.Image, "load", forbidden_load)
    server = StorageServer()
    server.objects[f"{BUCKET}/{record.object_key}"] = content
    storage = server.adapter()
    try:
        result = PillowImageGeometry(storage, ImageValidationPolicy()).inspect(
            record
        )
        assert (result.width_px, result.height_px) == expected
        assert server.objects[f"{BUCKET}/{record.object_key}"] == content
    finally:
        storage.close()


@pytest.mark.parametrize("metadata_kind", [b"eXIf", b"iTXt"])
def test_png_metadata_after_idat_is_not_ignored(
    metadata_kind: bytes,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    if metadata_kind == b"eXIf":
        exif = Image.Exif()
        exif[274] = 6
        content = make_image(size=(24, 12), exif=exif)
    else:
        info = PngImagePlugin.PngInfo()
        info.add_itxt("XML:com.adobe.xmp", '<rdf tiff:Orientation="6"/>')
        content = make_image(size=(24, 12), pnginfo=info)
    content = move_after_pixels(content, metadata_kind)
    record = source_record(content, width_px=24, height_px=12)

    def forbidden_load(self: Image.Image) -> None:
        raise AssertionError("Metadata inspection must not decode pixels")

    monkeypatch.setattr(Image.Image, "load", forbidden_load)
    server = StorageServer()
    server.objects[f"{BUCKET}/{record.object_key}"] = content
    storage = server.adapter()
    try:
        result = PillowImageGeometry(storage, ImageValidationPolicy()).inspect(
            record
        )
        assert (result.width_px, result.height_px) == (12, 24)
    finally:
        storage.close()


def test_png_without_exif_keeps_raw_dimensions_without_decoding(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    content = make_image()
    record = source_record(content)

    def forbidden_load(self: Image.Image) -> None:
        raise AssertionError("No pixel decoding")

    monkeypatch.setattr(Image.Image, "load", forbidden_load)
    server = StorageServer()
    server.objects[f"{BUCKET}/{record.object_key}"] = content
    storage = server.adapter()
    try:
        result = PillowImageGeometry(storage, ImageValidationPolicy()).inspect(
            record
        )
        assert (result.width_px, result.height_px) == (12, 8)
    finally:
        storage.close()


@pytest.mark.parametrize("damage", ["hash", "dimensions", "orientation"])
def test_bad_original_metadata_never_produces_placement(damage: str) -> None:
    exif = Image.Exif()
    exif[274] = 9 if damage == "orientation" else 1
    content = make_image(exif=exif)
    record = source_record(content)
    if damage == "hash":
        record = replace(record, sha256="0" * 64)
    if damage == "dimensions":
        record = replace(record, width_px=99)
    server = StorageServer()
    server.objects[f"{BUCKET}/{record.object_key}"] = content
    storage = server.adapter()
    try:
        with pytest.raises(FileError) as error:
            PillowImageGeometry(storage, ImageValidationPolicy()).inspect(
                record
            )
        assert error.value.failure is FileFailure.FILE_INTEGRITY_MISMATCH
    finally:
        storage.close()


@pytest.mark.parametrize(
    "content",
    [
        b"invalid",
        b"\x89PNG\r\n\x1a\n",
        b"\x89PNG\r\n\x1a\n\xff\xff\xff\xffeXIf",
    ],
)
def test_broken_png_chunk_lengths_are_bounded(content: bytes) -> None:
    with pytest.raises(FileError):
        png_metadata(content)
