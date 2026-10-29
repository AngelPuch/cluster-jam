"""Read previews without running Pillow or uploading from HTTP."""

from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import Depends, Path, Request, Response

from personalization.application.previews.preview_service import PreviewService
from personalization.application.templates.template_record import Side
from personalization.interfaces.http.design_drafts.preconditions import (
    draft_etag,
)
from personalization.interfaces.http.design_drafts.routes import (
    DesignId,
)
from personalization.interfaces.http.design_drafts.routes import (
    router as router,
)
from personalization.interfaces.http.dto.rest_model import RestModel
from personalization.interfaces.http.files.dto import (
    DownloadResponse,
    FileResponse,
)
from personalization.interfaces.http.prints.routes import Administrator


class PreviewResponse(RestModel):
    design_id: UUID
    design_version: int
    status: Literal["PENDING", "READY"]
    approximate: Literal[True] = True
    representation: Literal["SCHEMATIC_TEMPLATE"] = "SCHEMATIC_TEMPLATE"
    catalog_compatibility_verified: Literal[False] = False
    checkout_ready: Literal[False] = False
    front: FileResponse | None
    back: FileResponse | None


def get_preview_service(request: Request) -> PreviewService:
    return cast(PreviewService, request.app.state.preview_service)


PreviewUseCase = Annotated[PreviewService, Depends(get_preview_service)]


@router.get("/{designId}/previews", response_model=PreviewResponse)
def get_previews(
    design_id: DesignId,
    identity: Administrator,
    service: PreviewUseCase,
    response: Response,
) -> PreviewResponse:
    value = service.get(identity, design_id)
    response.headers["Cache-Control"] = "no-store"
    response.headers["ETag"] = draft_etag(value.draft)
    if value.front is None or value.back is None:
        response.headers["Retry-After"] = "10"
    return PreviewResponse(
        design_id=value.draft.id,
        design_version=value.draft.version,
        status="READY" if value.front and value.back else "PENDING",
        front=FileResponse.from_record(value.front) if value.front else None,
        back=FileResponse.from_record(value.back) if value.back else None,
    )


@router.post(
    "/{designId}/previews/{side}/download-urls",
    status_code=201,
    response_model=DownloadResponse,
)
def create_preview_download(
    design_id: DesignId,
    side: Annotated[Side, Path()],
    identity: Administrator,
    service: PreviewUseCase,
    response: Response,
) -> DownloadResponse:
    value = service.create_download(identity, design_id, side)
    response.headers["Cache-Control"] = "no-store"
    return DownloadResponse(
        file_id=value.file_id,
        expires_at=value.expires_at,
        download_url=value.download_url,
    )
