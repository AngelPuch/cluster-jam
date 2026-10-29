"""Check physical placement, alpha and EXIF in real PNGs."""

from dataclasses import replace
from decimal import Decimal
from io import BytesIO

import pytest
from PIL import Image

from personalization.application.designs.analysis_record import ResolvedSource
from personalization.application.files.file_record import FileRecord
from personalization.application.previews.preview import canvas_size
from personalization.application.templates.template_record import (
    Dimensions,
    Side,
)
from test.previews.fakes import preview_data, renderer
from test.thumbnails.fakes import source_record


@pytest.mark.parametrize("image_format", ["PNG", "JPEG"])
@pytest.mark.parametrize("orientation", range(1, 9))
def test_orientation_aspect_and_metadata_are_preserved_or_removed_correctly(
    image_format: str,
    orientation: int,
) -> None:
    data = preview_data()
    exif = Image.Exif()
    exif[274] = orientation
    exif[270] = "private-comment"
    with Image.new("RGB", (200, 100), "red") as source, BytesIO() as output:
        source.save(output, format=image_format, exif=exif)
        content = output.getvalue()
    record = source_record(
        content,
        width_px=200,
        height_px=100,
        mime_type="image/png" if image_format == "PNG" else "image/jpeg",
    )
    reads = []

    def read(_record: FileRecord) -> bytes:
        reads.append(_record.id)
        return content

    rendered = renderer().render(
        data.draft,
        data.analysis.template,
        (ResolvedSource(record, 0), ResolvedSource(record, 0)),
        read,
    )
    assert reads == [record.id]
    for result in rendered:
        with Image.open(BytesIO(result.content)) as image:
            assert not image.info and not image.getexif()
            assert image.size == (683, 1024)
            # Check the colored center and the white background.
            center = image.getpixel((256, 341))
            assert isinstance(center, tuple)
            assert center[0] > 240 and center[1] < 10
            assert image.getpixel((10, 10)) == (255, 255, 255, 255)
            # A rotated portrait fills a taller, narrower box.
            pixel = image.getpixel((256, 240))
            assert isinstance(pixel, tuple)
            assert (pixel[1] < 10) is (orientation >= 5)


def test_two_faces_share_one_physical_scale_and_empty_drafts_render() -> None:
    data = preview_data()
    template = replace(
        data.analysis.template,
        header=replace(
            data.analysis.template.header,
            back=Dimensions(Decimal("800"), Decimal("600")),
        ),
    )
    draft = replace(data.draft, applications=())
    assert canvas_size(template, Side.FRONT) == (512, 768)
    assert canvas_size(template, Side.BACK) == (1024, 768)
    outputs = renderer().render(draft, template, (), lambda _: None)
    assert [(image.width_px, image.height_px) for image in outputs] == [
        (512, 768),
        (1024, 768),
    ]
    assert all(b"private-comment" not in image.content for image in outputs)


def test_renderer_rejects_mismatched_source_metadata() -> None:
    data = preview_data()
    source = replace(data.analysis.sources.file, sha256="0" * 64)
    from personalization.application.errors.file_error import FileError
    from test.image_samples import make_image

    with pytest.raises(FileError):
        renderer().render(
            data.draft,
            data.analysis.template,
            (ResolvedSource(source, 0), ResolvedSource(source, 0)),
            lambda _: make_image(size=(200, 100)),
        )
