"""Read catalog items and authorize only their current thumbnails."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response

from personalization.application.catalog.catalog_service import CatalogService
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from personalization.interfaces.http.catalog.dto import (
    CatalogPageResponse,
    CatalogPrintResponse,
)
from personalization.interfaces.http.files.dto import DownloadResponse
from personalization.interfaces.http.prints.routes import PageCursor, PageLimit
from personalization.interfaces.http.security import (
    SECURITY_PROBLEM_RESPONSES,
    require_roles,
)

router = APIRouter(
    prefix="/api/v1/prints",
    tags=["Print catalog"],
    responses={
        **SECURITY_PROBLEM_RESPONSES,
        400: {"description": "Invalid or differently scoped cursor"},
        404: {"description": "Print is unavailable or version is not current"},
        422: {"description": "Invalid identifier or pagination limit"},
    },
)
Reader = Annotated[
    VerifiedIdentity,
    Depends(require_roles(AppRole.CLIENT, AppRole.ADMINISTRATOR)),
]
PrintId = Annotated[UUID, Path(alias="printId")]
VersionId = Annotated[UUID, Path(alias="versionId")]


def get_catalog_service(request: Request) -> CatalogService:
    return cast(CatalogService, request.app.state.catalog_service)


UseCase = Annotated[CatalogService, Depends(get_catalog_service)]


@router.get("", response_model=CatalogPageResponse)
def list_catalog(
    identity: Reader,
    service: UseCase,
    response: Response,
    limit: PageLimit = 20,
    cursor: PageCursor = None,
) -> CatalogPageResponse:
    page = service.list(identity, limit, cursor)
    response.headers["Cache-Control"] = "no-store"
    return CatalogPageResponse(
        items=[CatalogPrintResponse.from_record(row) for row in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{printId}", response_model=CatalogPrintResponse)
def get_catalog_print(
    print_id: PrintId,
    identity: Reader,
    service: UseCase,
    response: Response,
) -> CatalogPrintResponse:
    response.headers["Cache-Control"] = "no-store"
    return CatalogPrintResponse.from_record(service.get(identity, print_id))


@router.post(
    "/{printId}/versions/{versionId}/thumbnail/download-urls",
    status_code=201,
    response_model=DownloadResponse,
)
def create_thumbnail_download(
    print_id: PrintId,
    version_id: VersionId,
    identity: Reader,
    service: UseCase,
    response: Response,
) -> DownloadResponse:
    result = service.create_thumbnail_download(identity, print_id, version_id)
    response.headers["Cache-Control"] = "no-store"
    return DownloadResponse(
        file_id=result.file_id,
        expires_at=result.expires_at,
        download_url=result.download_url,
    )
