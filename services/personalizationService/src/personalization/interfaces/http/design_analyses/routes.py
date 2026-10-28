"""Diagnose draft geometry and costs without persisting a design."""

from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Request, Response

from personalization.application.designs.design_analysis_service import (
    DesignAnalysisService,
)
from personalization.interfaces.http.design_analyses.dto import (
    AnalysisRequest,
    AnalysisResponse,
)
from personalization.interfaces.http.prints.routes import Administrator
from personalization.interfaces.http.security import SECURITY_PROBLEM_RESPONSES

router = APIRouter(
    prefix="/api/v1/admin/template-versions",
    tags=["Draft design analysis"],
    responses={
        **SECURITY_PROBLEM_RESPONSES,
        404: {"description": "Template or source not found"},
        409: {"description": "Original unavailable or inconsistent"},
        422: {"description": "Invalid selections, geometry, or money"},
    },
)


def get_service(request: Request) -> DesignAnalysisService:
    return cast(
        DesignAnalysisService, request.app.state.design_analysis_service
    )


@router.post("/{templateId}/design-analyses", response_model=AnalysisResponse)
def analyze_design(
    template_id: Annotated[UUID, Path(alias="templateId")],
    body: AnalysisRequest,
    identity: Administrator,
    service: Annotated[DesignAnalysisService, Depends(get_service)],
    response: Response,
) -> AnalysisResponse:
    result = service.analyze(
        identity,
        template_id,
        tuple(item.selection() for item in body.applications),
    )
    response.headers["Cache-Control"] = "no-store"
    return AnalysisResponse.from_record(result)
