"""Create draft versions without inventing Catalog compatibility."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Request, Response

from personalization.application.templates.template_service import (
    TemplateService,
)
from personalization.interfaces.http.prints.routes import (
    Administrator,
    PageCursor,
    PageLimit,
)
from personalization.interfaces.http.security import SECURITY_PROBLEM_RESPONSES
from personalization.interfaces.http.templates.dto import (
    CreateTemplateRequest,
    TemplateHeaderResponse,
    TemplatePageResponse,
    TemplateResponse,
)

router = APIRouter(
    prefix="/api/v1/admin/template-versions",
    tags=["Draft template administration"],
    responses={
        **SECURITY_PROBLEM_RESPONSES,
        400: {"description": "Invalid or differently scoped cursor"},
        404: {"description": "Template version was not found"},
        409: {
            "description": "Expected version is stale or version limit reached"
        },
        422: {"description": "Invalid dimensions, zones, sizes, or money"},
    },
)


def get_template_service(request: Request) -> TemplateService:
    return cast(TemplateService, request.app.state.template_service)


UseCase = Annotated[TemplateService, Depends(get_template_service)]


@router.post("", status_code=201, response_model=TemplateResponse)
def create_template(
    body: CreateTemplateRequest,
    identity: Administrator,
    service: UseCase,
    response: Response,
) -> TemplateResponse:
    record = service.create(
        identity,
        body.product_id,
        body.size_id,
        body.expected_version,
        body.definition(),
    )
    response.headers["Location"] = (
        f"/api/v1/admin/template-versions/{record.header.id}"
    )
    response.headers["Cache-Control"] = "no-store"
    return TemplateResponse.from_record(record)


@router.get("", response_model=TemplatePageResponse)
def list_templates(
    identity: Administrator,
    service: UseCase,
    response: Response,
    product_id: Annotated[UUID, Query(alias="productId")],
    size_id: Annotated[int, Query(alias="sizeId", ge=1, le=32767)],
    limit: PageLimit = 20,
    cursor: PageCursor = None,
) -> TemplatePageResponse:
    page = service.list(identity, product_id, size_id, limit, cursor)
    response.headers["Cache-Control"] = "no-store"
    return TemplatePageResponse(
        items=[TemplateHeaderResponse.from_header(row) for row in page.items],
        next_cursor=page.next_cursor,
    )


@router.get("/{templateId}", response_model=TemplateResponse)
def get_template(
    template_id: Annotated[UUID, Path(alias="templateId")],
    identity: Administrator,
    service: UseCase,
    response: Response,
) -> TemplateResponse:
    response.headers["Cache-Control"] = "no-store"
    return TemplateResponse.from_record(service.get(identity, template_id))
