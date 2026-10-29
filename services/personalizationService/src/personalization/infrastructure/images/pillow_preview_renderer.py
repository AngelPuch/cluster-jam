"""Compose bounded schematic previews using exact physical placement."""

from collections.abc import Callable
from fractions import Fraction
from io import BytesIO
from uuid import UUID

from PIL import Image, ImageDraw, ImageOps

from personalization.application.designs.analysis_record import (
    ImageGeometry,
    ResolvedSource,
    Target,
)
from personalization.application.designs.design_rules import (
    analyze_application,
    resolve_targets,
)
from personalization.application.designs.draft_record import DraftRecord
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
from personalization.application.previews.preview import (
    RenderedPreview,
    canvas_size,
    preview_scale,
)
from personalization.application.templates.template_record import (
    Side,
    TemplateDefinition,
    TemplateRecord,
)
from personalization.application.templates.template_rules import (
    validate_definition,
)


class PillowPreviewRenderer:
    def __init__(self, validator: ValidateImageService) -> None:
        self._validator = validator

    def render(
        self,
        draft: DraftRecord,
        template: TemplateRecord,
        sources: tuple[ResolvedSource, ...],
        read: Callable[[FileRecord], bytes | None],
    ) -> tuple[RenderedPreview, RenderedPreview]:
        validate_definition(
            TemplateDefinition(
                template.header.front,
                template.header.back,
                tuple(zone.definition for zone in template.zones),
            )
        )
        choices = draft.content.applications
        targets = resolve_targets(template, choices) if choices else ()
        if (
            len(targets) != len(sources)
            or template.header.id != draft.template_id
        ):
            raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
        scale = preview_scale(template)
        canvases = {
            side: Image.new("RGBA", canvas_size(template, side), "white")
            for side in Side
        }
        try:
            for zone in template.zones:
                value = zone.definition
                bounds = tuple(
                    round(Fraction(item) * scale)
                    for item in (
                        value.x_mm,
                        value.y_mm,
                        value.x_mm + value.dimensions.width_mm,
                        value.y_mm + value.dimensions.height_mm,
                    )
                )
                ImageDraw.Draw(canvases[value.side]).rectangle(
                    bounds, outline=(220, 220, 220, 255), width=1
                )
            groups: dict[UUID, list[tuple[Target, ResolvedSource]]] = {}
            for target, resolved in zip(targets, sources, strict=True):
                groups.setdefault(resolved.file.id, []).append(
                    (target, resolved)
                )
            for group in groups.values():
                self._stamp(group, read, scale, canvases)
            outputs: list[RenderedPreview] = []
            for side in Side:
                canvas = canvases[side]
                with BytesIO() as output:
                    canvas.save(output, format="PNG", compress_level=6)
                    outputs.append(
                        RenderedPreview(
                            side,
                            output.getvalue(),
                            canvas.width,
                            canvas.height,
                        )
                    )
            return outputs[0], outputs[1]
        finally:
            for canvas in canvases.values():
                canvas.close()

    def _stamp(
        self,
        group: list[tuple[Target, ResolvedSource]],
        read: Callable[[FileRecord], bytes | None],
        scale: Fraction,
        canvases: dict[Side, Image.Image],
    ) -> None:
        source = group[0][1].file
        content = read(source)
        if content is None:
            raise FileError(FileFailure.FILE_NOT_READY)
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
                orientation = image.getexif().get(274, 1)
                if type(orientation) is not int or orientation not in range(
                    1, 9
                ):
                    raise FileError(FileFailure.FILE_INTEGRITY_MISMATCH)
                ImageOps.exif_transpose(image, in_place=True)
                with image.convert("RGBA") as rgba:
                    for target, resolved in group:
                        analyzed = analyze_application(
                            target,
                            ImageGeometry(rgba.width, rgba.height),
                            resolved.print_surcharge_cents,
                            None,
                        )
                        value = analyzed.placement
                        canvas = canvases[analyzed.side]
                        x0 = max(
                            0, min(canvas.width, round(value.x_mm * scale))
                        )
                        y0 = max(
                            0, min(canvas.height, round(value.y_mm * scale))
                        )
                        x1 = max(
                            0,
                            min(
                                canvas.width,
                                round((value.x_mm + value.width_mm) * scale),
                            ),
                        )
                        y1 = max(
                            0,
                            min(
                                canvas.height,
                                round((value.y_mm + value.height_mm) * scale),
                            ),
                        )
                        if x0 < x1 and y0 < y1:
                            with rgba.resize(
                                (x1 - x0, y1 - y0), Image.Resampling.LANCZOS
                            ) as stamp:
                                canvas.alpha_composite(stamp, (x0, y0))
        except OSError, ValueError, UserWarning:
            raise ImageValidationError(
                ImageValidationFailure.INVALID_IMAGE
            ) from None
