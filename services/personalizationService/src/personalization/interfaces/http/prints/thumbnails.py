"""Expose worker results without generating images in HTTP requests."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import Depends, Path, Request, Response

from personalization.application.thumbnails.thumbnail_service import (
    ThumbnailService,
)
from personalization.interfaces.http.files.dto import (
    DownloadResponse,
    FileResponse,
)
from personalization.interfaces.http.prints.routes import (
    Administrator,
    PrintId,
)
from personalization.interfaces.http.prints.routes import (
    router as router,
)


def get_thumbnail_service(request: Request) -> ThumbnailService:
    return cast(ThumbnailService, request.app.state.thumbnail_service)


ThumbnailUseCase = Annotated[ThumbnailService, Depends(get_thumbnail_service)]
VersionId = Annotated[UUID, Path(alias="versionId")]


@router.get(
    "/{printId}/versions/{versionId}/thumbnail", response_model=FileResponse
)
def get_thumbnail(
    print_id: PrintId,
    version_id: VersionId,
    identity: Administrator,
    service: ThumbnailUseCase,
    response: Response,
) -> FileResponse:
    response.headers["Cache-Control"] = "no-store"
    return FileResponse.from_record(
        service.get(identity, print_id, version_id)
    )


@router.post(
    "/{printId}/versions/{versionId}/thumbnail/download-urls",
    status_code=201,
    response_model=DownloadResponse,
)
def create_thumbnail_download(
    print_id: PrintId,
    version_id: VersionId,
    identity: Administrator,
    service: ThumbnailUseCase,
    response: Response,
) -> DownloadResponse:
    result = service.create_download(identity, print_id, version_id)
    response.headers["Cache-Control"] = "no-store"
    return DownloadResponse(
        file_id=result.file_id,
        expires_at=result.expires_at,
        download_url=result.download_url,
    )
