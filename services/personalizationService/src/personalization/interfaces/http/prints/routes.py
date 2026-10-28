"""Restrict print version administration to protected admin JWTs."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Query, Request, Response

from personalization.application.prints.print_service import PrintService
from personalization.application.security.identity import (
    AppRole,
    VerifiedIdentity,
)
from personalization.interfaces.http.prints.dto import (
    CreatePrintRequest,
    CreatePrintVersionRequest,
    PrintPageResponse,
    PrintResponse,
    PrintVersionPageResponse,
    PrintVersionResponse,
    UpdatePrintRequest,
)
from personalization.interfaces.http.prints.preconditions import (
    ETAG_RESPONSE,
    parse_if_match,
    print_etag,
)
from personalization.interfaces.http.security import (
    SECURITY_PROBLEM_RESPONSES,
    require_roles,
)

router = APIRouter(
    prefix="/api/v1/admin/prints",
    tags=["Print administration"],
    responses={
        **SECURITY_PROBLEM_RESPONSES,
        400: {"description": "Malformed JSON or invalid cursor"},
        404: {"description": "Print or original file not found"},
        409: {"description": "Unavailable file or conflicting version"},
        422: {"description": "Invalid administrative data"},
    },
)
Administrator = Annotated[
    VerifiedIdentity,
    Depends(require_roles(AppRole.ADMINISTRATOR)),
]


def get_print_service(request: Request) -> PrintService:
    return cast(PrintService, request.app.state.print_service)


PrintUseCase = Annotated[PrintService, Depends(get_print_service)]
PrintId = Annotated[UUID, Path(alias="printId")]
PageLimit = Annotated[int, Query(ge=1, le=100)]
PageCursor = Annotated[str | None, Query(min_length=1, max_length=256)]


@router.post(
    "",
    status_code=201,
    response_model=PrintResponse,
    responses={201: ETAG_RESPONSE},
)
def create_print(
    body: CreatePrintRequest,
    identity: Administrator,
    service: PrintUseCase,
    response: Response,
) -> PrintResponse:
    record = service.create(
        identity,
        body.name,
        body.description,
        body.file_id,
        body.surcharge_cents,
    )
    response.headers["Location"] = f"/api/v1/admin/prints/{record.id}"
    response.headers["Cache-Control"] = "no-store"
    response.headers["ETag"] = print_etag(record)
    return PrintResponse.from_record(record)


@router.get("", response_model=PrintPageResponse)
def list_prints(
    identity: Administrator,
    service: PrintUseCase,
    response: Response,
    limit: PageLimit = 20,
    cursor: PageCursor = None,
) -> PrintPageResponse:
    page = service.list(identity, limit, cursor)
    response.headers["Cache-Control"] = "no-store"
    return PrintPageResponse(
        items=[PrintResponse.from_record(row) for row in page.items],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{printId}",
    response_model=PrintResponse,
    responses={200: ETAG_RESPONSE},
)
def get_print(
    print_id: PrintId,
    identity: Administrator,
    service: PrintUseCase,
    response: Response,
) -> PrintResponse:
    response.headers["Cache-Control"] = "no-store"
    record = service.get(identity, print_id)
    response.headers["ETag"] = print_etag(record)
    return PrintResponse.from_record(record)


@router.post(
    "/{printId}/versions",
    status_code=201,
    response_model=PrintVersionResponse,
)
def create_print_version(
    print_id: PrintId,
    body: CreatePrintVersionRequest,
    identity: Administrator,
    service: PrintUseCase,
    response: Response,
) -> PrintVersionResponse:
    record = service.create_version(
        identity,
        print_id,
        body.expected_version,
        body.file_id,
        body.surcharge_cents,
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["Location"] = (
        f"/api/v1/admin/prints/{print_id}/versions/{record.id}"
    )
    return PrintVersionResponse.from_record(record)


@router.get("/{printId}/versions", response_model=PrintVersionPageResponse)
def list_print_versions(
    print_id: PrintId,
    identity: Administrator,
    service: PrintUseCase,
    response: Response,
    limit: PageLimit = 20,
    cursor: PageCursor = None,
) -> PrintVersionPageResponse:
    page = service.list_versions(identity, print_id, limit, cursor)
    response.headers["Cache-Control"] = "no-store"
    return PrintVersionPageResponse(
        items=[PrintVersionResponse.from_record(row) for row in page.items],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{printId}/versions/{versionId}",
    response_model=PrintVersionResponse,
)
def get_print_version(
    print_id: PrintId,
    version_id: Annotated[UUID, Path(alias="versionId")],
    identity: Administrator,
    service: PrintUseCase,
    response: Response,
) -> PrintVersionResponse:
    response.headers["Cache-Control"] = "no-store"
    return PrintVersionResponse.from_record(
        service.get_version(identity, print_id, version_id)
    )


@router.patch(
    "/{printId}",
    response_model=PrintResponse,
    responses={
        200: ETAG_RESPONSE,
        412: {"description": "The selected strong validator is stale"},
        428: {"description": "Read the resource and supply If-Match"},
    },
)
def update_print(
    print_id: PrintId,
    body: UpdatePrintRequest,
    identity: Administrator,
    service: PrintUseCase,
    response: Response,
    if_match: Annotated[list[str] | None, Header(alias="If-Match")] = None,
) -> PrintResponse:
    record = service.update(
        identity,
        print_id,
        body.to_changes(),
        parse_if_match(if_match),
    )
    response.headers["Cache-Control"] = "no-store"
    response.headers["ETag"] = print_etag(record)
    return PrintResponse.from_record(record)
