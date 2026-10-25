"""Expose health without putting persistence access in controllers."""

from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request

from personalization.application.health.readiness_service import (
    ReadinessService,
)
from personalization.interfaces.http.dto.health_response import HealthResponse

router = APIRouter(prefix="/health", tags=["Health"])


def get_readiness_service(request: Request) -> ReadinessService:
    """Resolve the application service wired by the composition root."""
    return cast(ReadinessService, request.app.state.readiness_service)


@router.get("/live", response_model=HealthResponse)
async def get_liveness() -> HealthResponse:
    """Check the process without contacting any dependency."""
    return HealthResponse()


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={503: {"description": "Local database access is unavailable"}},
)
def get_readiness(
    readiness: Annotated[ReadinessService, Depends(get_readiness_service)],
) -> HealthResponse:
    """Check local database access in FastAPI's worker thread pool."""
    readiness.ensure_ready()
    return HealthResponse()
