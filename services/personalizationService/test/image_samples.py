"""Generate tiny image fixtures without files or external services."""

from io import BytesIO

from PIL import Image


def make_image(
    image_format: str = "PNG",
    *,
    mode: str | None = None,
    size: tuple[int, int] = (12, 8),
    **options: object,
) -> bytes:
    """Return a real encoded image with configurable codec options."""
    selected_mode = mode or ("RGB" if image_format == "JPEG" else "RGBA")
    with Image.new(selected_mode, size) as image, BytesIO() as output:
        image.save(output, format=image_format, **options)
        return output.getvalue()
