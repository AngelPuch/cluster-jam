"""Persist administrative drafts while Catalog remains unintegrated."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Path, Request, Response

from personalization.application.designs.draft_record import DraftRecord
from personalization.application.designs.draft_service import DraftService
from personalization.interfaces.http.design_drafts.dto import (
    DraftPageResponse,
    DraftRequest,
    DraftResponse,
    DraftSummaryResponse,
)
from personalization.interfaces.http.design_drafts.preconditions import (
    draft_condition,
    draft_etag,
)
from personalization.interfaces.http.prints.preconditions import ETAG_RESPONSE
from personalization.interfaces.http.prints.routes import (
    Administrator,
    PageCursor,
    PageLimit,
)
from personalization.interfaces.http.security import SECURITY_PROBLEM_RESPONSES

router = APIRouter(
    prefix="/api/v1/admin/design-drafts",
    tags=["Administrative design drafts"],
    responses={
        **SECURITY_PROBLEM_RESPONSES,
        400: {"description": "Invalid cursor or precondition"},
        404: {"description": "Design, template or original not found"},
        409: {
            "description": (
                "Frozen design, exhausted version, or source not ready"
            )
        },
        412: {"description": "Draft changed; read it again"},
        422: {"description": "Invalid selections or draft data"},
        428: {"description": "Read the draft and send If-Match"},
    },
)


def get_service(request: Request) -> DraftService:
    return cast(DraftService, request.app.state.draft_service)


UseCase = Annotated[DraftService, Depends(get_service)]
DesignId = Annotated[UUID, Path(alias="designId")]


def respond(
    record: DraftRecord, response: Response, *, created: bool = False
) -> DraftResponse:
    response.headers["ETag"] = draft_etag(record)
    response.headers["Cache-Control"] = "no-store"
    if created:
        response.headers["Location"] = (
            f"/api/v1/admin/design-drafts/{record.id}"
        )
    return DraftResponse.from_record(record)


@router.post(
    "",
    status_code=201,
    response_model=DraftResponse,
    responses={201: ETAG_RESPONSE},
)
def create_draft(
    body: DraftRequest,
    identity: Administrator,
    service: UseCase,
    response: Response,
) -> DraftResponse:
    return respond(
        service.create(identity, body.content()), response, created=True
    )


@router.get("", response_model=DraftPageResponse)
def list_drafts(
    identity: Administrator,
    service: UseCase,
    response: Response,
    limit: PageLimit = 20,
    cursor: PageCursor = None,
) -> DraftPageResponse:
    page = service.list(identity, limit, cursor)
    response.headers["Cache-Control"] = "no-store"
    return DraftPageResponse(
        items=[DraftSummaryResponse.from_record(row) for row in page.items],
        next_cursor=page.next_cursor,
    )


@router.get(
    "/{designId}", response_model=DraftResponse, responses={200: ETAG_RESPONSE}
)
def get_draft(
    design_id: DesignId,
    identity: Administrator,
    service: UseCase,
    response: Response,
) -> DraftResponse:
    return respond(service.get(identity, design_id), response)


@router.put(
    "/{designId}", response_model=DraftResponse, responses={200: ETAG_RESPONSE}
)
def replace_draft(
    design_id: DesignId,
    body: DraftRequest,
    identity: Administrator,
    service: UseCase,
    response: Response,
    if_match: Annotated[list[str] | None, Header(alias="If-Match")] = None,
) -> DraftResponse:
    return respond(
        service.update(
            identity, design_id, body.content(), draft_condition(if_match)
        ),
        response,
    )


@router.post(
    "/{designId}/copies",
    status_code=201,
    response_model=DraftResponse,
    responses={201: ETAG_RESPONSE},
)
def copy_draft(
    design_id: DesignId,
    identity: Administrator,
    service: UseCase,
    response: Response,
) -> DraftResponse:
    return respond(service.copy(identity, design_id), response, created=True)
