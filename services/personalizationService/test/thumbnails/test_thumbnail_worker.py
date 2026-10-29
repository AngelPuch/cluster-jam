"""Verify real image rendering and durable worker recovery."""

from collections.abc import Callable
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from uuid import uuid4

import pytest
from PIL import Image

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.errors.image_validation_error import (
    ImageValidationError,
)
from personalization.application.files.file_record import FileRecord, FileState
from personalization.application.images.image_policy import (
    ImageValidationPolicy,
)
from personalization.application.images.validate_image_service import (
    ValidateImageService,
)
from personalization.application.thumbnails.thumbnail import thumbnail_id
from personalization.application.thumbnails.thumbnail_worker import (
    ThumbnailWorker,
)
from personalization.infrastructure.images.pillow_image_inspector import (
    PillowImageInspector,
)
from personalization.infrastructure.images.pillow_thumbnail_renderer import (
    PillowThumbnailRenderer,
)
from test.files.fakes import BUCKET, StorageServer
from test.image_samples import make_image
from test.thumbnails.fakes import MemoryThumbnailRepository, source_record


def renderer() -> PillowThumbnailRenderer:
    return PillowThumbnailRenderer(
        ValidateImageService(PillowImageInspector(), ImageValidationPolicy())
    )


@pytest.mark.parametrize(
    "image_format,mode,size,expected",
    [
        ("PNG", "RGBA", (1200, 600), (320, 160)),
        ("JPEG", "RGB", (600, 1200), (160, 320)),
        ("JPEG", "CMYK", (100, 50), (100, 50)),
        ("PNG", "P", (10, 20), (10, 20)),
        ("PNG", "RGBA", (1, 1), (1, 1)),
        ("PNG", "RGBA", (8192, 1), (320, 1)),
    ],
)
def test_renderer_preserves_ratio_without_upscaling(
    image_format: str,
    mode: str,
    size: tuple[int, int],
    expected: tuple[int, int],
) -> None:
    content = make_image(image_format, mode=mode, size=size)
    mime = "image/jpeg" if image_format == "JPEG" else "image/png"
    source = source_record(
        content, width_px=size[0], height_px=size[1], mime_type=mime
    )
    rendered = renderer().render(source, content)
    with Image.open(BytesIO(rendered.content)) as image:
        assert image.size == expected
        assert image.format == "PNG" and image.mode == "RGBA"
        pixel = image.getpixel((0, 0))
        assert isinstance(pixel, tuple)
        assert pixel[3] == (0 if mode == "RGBA" else 255)
    assert (rendered.width_px, rendered.height_px) == expected


def test_exif_orientation_is_applied_and_metadata_is_removed() -> None:
    exif = Image.Exif()
    exif[274] = 6
    exif[315] = "private-author"
    content = make_image("JPEG", size=(600, 300), exif=exif)
    source = source_record(
        content, width_px=600, height_px=300, mime_type="image/jpeg"
    )
    result = renderer().render(source, content)
    with Image.open(BytesIO(result.content)) as image:
        assert image.size == (160, 320)
        assert not image.getexif() and "exif" not in image.info
    assert b"private-author" not in result.content
    assert sha256(content).hexdigest() == source.sha256


@pytest.mark.parametrize(
    "damage",
    [
        lambda row: replace(row, width_px=999),
        lambda row: replace(row, height_px=999),
        lambda row: replace(row, sha256="0" * 64),
        lambda row: replace(row, size_bytes=1),
    ],
)
def test_source_metadata_must_match_bytes(
    damage: Callable[[FileRecord], FileRecord],
) -> None:
    with pytest.raises(FileError) as caught:
        renderer().render(damage(source_record()), make_image())
    assert caught.value.failure is FileFailure.FILE_INTEGRITY_MISMATCH


def test_invalid_image_is_rejected_before_rendering() -> None:
    with pytest.raises(ImageValidationError):
        renderer().render(source_record(b"not-image"), b"not-image")


@pytest.mark.parametrize(
    "failure", [None, "before-write", "after-write", "database"]
)
def test_worker_recovers_each_cut_without_duplicate_or_overwrite(
    failure: str | None,
) -> None:
    server = StorageServer()
    repository = MemoryThumbnailRepository()
    source = source_record()
    original = make_image()
    server.objects[f"{BUCKET}/{source.object_key}"] = original
    storage = server.adapter()
    worker = ThumbnailWorker(repository, storage, renderer())
    try:
        if failure == "database":
            repository.fail_publish = True
        else:
            server.upload_failure = failure
        if failure is not None:
            with pytest.raises(FileError):
                worker.process(source)
            pending = repository.get(source.id)
            assert pending is not None and pending.state is FileState.PENDING
        server.upload_failure = None
        repository.fail_publish = False
        assert worker.process(source)
        derived = repository.get(source.id)
        assert derived is not None and derived.state is FileState.AVAILABLE
        assert derived.id == thumbnail_id(source.id)
        assert derived.owner_id == source.owner_id
        assert server.objects[f"{BUCKET}/{source.object_key}"] == original
        assert len(server.objects) == 2
        uploads = [
            request for request in server.requests if request.method == "POST"
        ]
        expected = 2 if failure == "before-write" else 1
        assert len(uploads) == expected
        assert all(r.headers["x-upsert"] == "false" for r in uploads)
        assert worker.process(source)
        assert (
            len([r for r in server.requests if r.method == "POST"]) == expected
        )
    finally:
        storage.close()


def test_uncommitted_intention_prevents_remote_write() -> None:
    repository = MemoryThumbnailRepository()
    repository.fail_reserve = True
    server = StorageServer()
    source = source_record()
    server.objects[f"{BUCKET}/{source.object_key}"] = make_image()
    storage = server.adapter()
    try:
        with pytest.raises(FileError):
            ThumbnailWorker(repository, storage, renderer()).process(source)
        assert all(r.method != "POST" for r in server.requests)
    finally:
        storage.close()


def test_busy_source_does_not_contact_storage() -> None:
    repository = MemoryThumbnailRepository()
    source = source_record()
    repository.claimed.add(source.id)
    server = StorageServer()
    storage = server.adapter()
    try:
        assert not ThumbnailWorker(repository, storage, renderer()).process(
            source
        )
        assert not server.requests
    finally:
        storage.close()


def test_pending_remote_corruption_is_never_overwritten() -> None:
    repository = MemoryThumbnailRepository()
    source = source_record()
    record = renderer().render(source, make_image()).record(source)
    repository.records[record.id] = record
    server = StorageServer()
    server.objects[f"{BUCKET}/{record.object_key}"] = b"corrupt"
    storage = server.adapter()
    try:
        with pytest.raises(FileError) as caught:
            ThumbnailWorker(repository, storage, renderer()).process(source)
        assert caught.value.failure is FileFailure.FILE_INTEGRITY_MISMATCH
        pending = repository.get(source.id)
        assert pending is not None and pending.state is FileState.PENDING
        assert all(r.method != "POST" for r in server.requests)
    finally:
        storage.close()


def test_invalid_relation_is_rejected_before_object_read() -> None:
    repository = MemoryThumbnailRepository()
    source = source_record()
    record = renderer().render(source, make_image()).record(source)
    repository.records[record.id] = replace(record, owner_id=uuid4())
    server = StorageServer()
    storage = server.adapter()
    try:
        with pytest.raises(FileError):
            ThumbnailWorker(repository, storage, renderer()).process(source)
        assert len(server.requests) == 1  # Bucket check only.
    finally:
        storage.close()


def test_batch_advances_after_failure_and_honors_shutdown() -> None:
    repository = MemoryThumbnailRepository()
    repository.sources = sorted(
        [source_record(), source_record()], key=lambda r: r.id.int
    )
    server = StorageServer()
    good = repository.sources[1]
    server.objects[f"{BUCKET}/{good.object_key}"] = make_image()
    storage = server.adapter()
    worker = ThumbnailWorker(repository, storage, renderer())
    try:
        result = worker.batch(None, 10)
        assert result.completed == 1 and len(result.failures) == 1
        assert result.after == good.id
        assert worker.batch(result.after, 10).after is None
        assert worker.batch(None, 10, lambda: True).completed == 0
    finally:
        storage.close()


@pytest.mark.parametrize(
    "state,usage",
    [
        (FileState.PENDING, "ORIGINAL"),
        (FileState.AVAILABLE, "PREVIEW"),
    ],
)
def test_only_available_originals_can_be_processed(
    state: FileState, usage: str
) -> None:
    storage = StorageServer().adapter()
    try:
        with pytest.raises(FileError):
            ThumbnailWorker(
                MemoryThumbnailRepository(), storage, renderer()
            ).process(source_record(state=state, usage=usage))
    finally:
        storage.close()
