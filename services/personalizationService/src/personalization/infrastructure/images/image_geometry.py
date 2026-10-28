"""Inspect image orientation without decoding pixels."""

import struct
import zlib
from io import BytesIO

from PIL import ExifTags, Image

from personalization.application.designs.analysis_record import ImageGeometry
from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_record import FileRecord
from personalization.application.images.image_policy import (
    ImageValidationPolicy,
)
from personalization.application.ports.thumbnail_ports import (
    ThumbnailStoragePort,
)


def png_metadata(content: bytes) -> bytes:
    """Collect verified PNG metadata without compressed pixels."""
    result = bytearray(content[:8])
    offset = 8
    while offset + 12 <= len(content):
        length = struct.unpack(">I", content[offset : offset + 4])[0]
        end = offset + 12 + length
        if end > len(content):
            raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
        kind = content[offset + 4 : offset + 8]
        if kind == b"IEND":
            # Open metadata at IDAT without loading pixels.
            result.extend(
                struct.pack(">I", 0)
                + b"IDAT"
                + struct.pack(">I", zlib.crc32(b"IDAT"))
            )
            result.extend(content[offset:end])
            return bytes(result)
        if kind != b"IDAT":
            result.extend(content[offset:end])
        offset = end
    raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)


class PillowImageGeometry:
    def __init__(
        self, storage: ThumbnailStoragePort, policy: ImageValidationPolicy
    ) -> None:
        self._storage = storage
        self._policy = policy

    def inspect(self, record: FileRecord) -> ImageGeometry:
        self._storage.ensure_private()
        content = self._storage.read_verified(record)
        if content is None:
            raise FileError(FileFailure.FILE_NOT_READY)
        metadata = (
            png_metadata(content)
            if record.mime_type == "image/png"
            else content
        )
        try:
            with Image.open(
                BytesIO(metadata), formats=["PNG", "JPEG"]
            ) as image:
                expected = "PNG" if record.mime_type == "image/png" else "JPEG"
                if image.format != expected or image.size != (
                    record.width_px,
                    record.height_px,
                ):
                    raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
                self._policy.ensure_dimensions(image.width, image.height)
                # Use the metadata reader without loading pixels.
                orientation = Image.Image.getexif(image).get(
                    ExifTags.Base.Orientation, 1
                )
                if type(orientation) is not int or orientation not in range(
                    1, 9
                ):
                    raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
                width, height = image.size
                return (
                    ImageGeometry(height, width)
                    if orientation >= 5
                    else ImageGeometry(width, height)
                )
        except OSError, ValueError, SyntaxError, UserWarning, EOFError:
            raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH) from None


class UnavailableImageGeometry:
    def inspect(self, record: FileRecord) -> ImageGeometry:
        raise FileError(FileFailure.STORAGE_NOT_CONFIGURED)
