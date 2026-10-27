"""Authenticate before consuming a bounded multipart upload."""

import asyncio
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response
from starlette.concurrency import run_in_threadpool
from starlette.datastructures import UploadFile
from starlette.exceptions import HTTPException

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_service import FileService
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from personalization.interfaces.http.files.dto import (
    DownloadResponse,
    FileResponse,
)
from personalization.interfaces.http.files.upload_limits import (
    UPLOAD_PARSE_SECONDS,
    check_upload_headers,
)
from personalization.interfaces.http.security import (
    SECURITY_PROBLEM_RESPONSES,
    require_roles,
)

router = APIRouter(prefix="/api/v1/files", tags=["Files"])
FileIdentity = Annotated[
    VerifiedIdentity,
    Depends(require_roles(AppRole.CLIENT, AppRole.ADMINISTRATOR)),
]


def get_file_service(request: Request) -> FileService:
    """Resolve the composed use case rather than
    creating adapters here.
    """
    return cast(FileService, request.app.state.file_service)


FileUseCase = Annotated[FileService, Depends(get_file_service)]
FileId = Annotated[UUID, Path(alias="fileId")]


@router.post(
    "",
    status_code=201,
    response_model=FileResponse,
    responses={
        **SECURITY_PROBLEM_RESPONSES,
        400: {"description": "Invalid multipart upload"},
        408: {"description": "Upload body timeout"},
        413: {"description": "File or request body exceeds the limit"},
        415: {"description": "Unsupported or conflicting image type"},
        422: {"description": "Invalid image or dimensions"},
        429: {"description": "Another upload is in progress"},
    },
    openapi_extra={
        "requestBody": {
            "required": True,
            "content": {
                "multipart/form-data": {
                    "schema": {
                        "type": "object",
                        "required": ["file"],
                        "additionalProperties": False,
                        "properties": {
                            "file": {"type": "string", "format": "binary"}
                        },
                    }
                }
            },
        }
    },
)
async def upload_file(
    request: Request,
    response: Response,
    identity: FileIdentity,
    service: FileUseCase,
) -> FileResponse:
    """Parse after JWT dependencies, then validate outside the event
    loop.
    """
    check_upload_headers(request)
    gate = cast(asyncio.BoundedSemaphore, request.app.state.upload_gate)
    if gate.locked():
        raise FileError(FileFailure.UPLOAD_BUSY)
    async with gate:
        try:
            async with asyncio.timeout(UPLOAD_PARSE_SECONDS):
                form = await request.form(max_files=1, max_fields=0)
            try:
                parts = form.getlist("file")
                if (
                    len(form) != 1
                    or len(parts) != 1
                    or not isinstance(parts[0], UploadFile)
                ):
                    raise FileError(FileFailure.INVALID_MULTIPART)
                upload = parts[0]
                record = await run_in_threadpool(
                    service.upload,
                    identity,
                    upload.file,
                    upload.content_type,
                )
            finally:
                await form.close()
        except HTTPException:
            raise FileError(FileFailure.INVALID_MULTIPART) from None
        except TimeoutError:
            raise FileError(FileFailure.UPLOAD_TIMEOUT) from None
        except OSError:
            raise FileError(FileFailure.IMAGE_READ_FAILED) from None
    response.headers["Location"] = f"/api/v1/files/{record.id}"
    response.headers["Cache-Control"] = "no-store"
    return FileResponse.from_record(record)


@router.get(
    "/{fileId}",
    response_model=FileResponse,
    responses={
        **SECURITY_PROBLEM_RESPONSES,
        404: {"description": "File not found"},
    },
)
def get_file(
    file_id: FileId,
    response: Response,
    identity: FileIdentity,
    service: FileUseCase,
) -> FileResponse:
    """Return metadata only to the owner or an
    authorized administrator.
    """
    response.headers["Cache-Control"] = "no-store"
    return FileResponse.from_record(service.get(identity, file_id))


@router.post(
    "/{fileId}/download-urls",
    response_model=DownloadResponse,
    responses={
        **SECURITY_PROBLEM_RESPONSES,
        404: {"description": "File not found"},
        409: {"description": "File upload is not available yet"},
    },
)
def create_download_url(
    file_id: FileId,
    response: Response,
    identity: FileIdentity,
    service: FileUseCase,
) -> DownloadResponse:
    """Grant one short-lived link after local authorization checks."""
    result = service.create_download(identity, file_id)
    response.headers["Cache-Control"] = "no-store"
    return DownloadResponse(
        file_id=result.file_id,
        expires_at=result.expires_at,
        download_url=result.download_url,
    )
