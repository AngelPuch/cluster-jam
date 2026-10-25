"""Keep HTTP error responses consistent and free of internal details."""

from http import HTTPStatus
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from personalization.application.errors.service_not_ready_error import (
    ServiceNotReadyError,
)
from personalization.interfaces.http.dto.problem_details import ProblemDetails

HTTP_ERROR_CODES = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    412: "PRECONDITION_FAILED",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_SERVER_ERROR",
    502: "BAD_GATEWAY",
    503: "SERVICE_UNAVAILABLE",
    504: "GATEWAY_TIMEOUT",
}


def problem_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    detail: str,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    """Include correlation and a path without its query string."""
    try:
        title = HTTPStatus(status_code).phrase
    except ValueError:
        title = "HTTP Error"
    trace_id = getattr(request.state, "trace_id", None) or uuid4().hex
    problem = ProblemDetails(
        type="about:blank",
        title=title,
        status=status_code,
        detail=detail,
        instance=request.url.path,
        code=code,
        trace_id=trace_id,
    )
    response_headers = {"Cache-Control": "no-store", **(headers or {})}
    return JSONResponse(
        status_code=status_code,
        content=problem.model_dump(mode="json", by_alias=True),
        media_type="application/problem+json",
        headers=response_headers,
    )


def unexpected_problem(request: Request) -> JSONResponse:
    """Return a safe response for an unexpected server exception."""
    return problem_response(
        request,
        status_code=500,
        code="INTERNAL_SERVER_ERROR",
        detail="An unexpected error prevented the request from completing.",
    )


async def http_exception_handler(
    request: Request, exception: Exception
) -> JSONResponse:
    """Preserve protocol headers and hide internal error details."""
    if not isinstance(exception, HTTPException):
        return unexpected_problem(request)
    status = exception.status_code
    detail = (
        exception.detail
        if status < 500 and isinstance(exception.detail, str)
        else "The service is temporarily unavailable."
    )
    return problem_response(
        request,
        status_code=status,
        code=HTTP_ERROR_CODES.get(status, "HTTP_ERROR"),
        detail=detail,
        headers=dict(exception.headers or {}),
    )


async def validation_exception_handler(
    request: Request, exception: Exception
) -> JSONResponse:
    """Report invalid JSON without exposing rejected values."""
    malformed_json = isinstance(exception, RequestValidationError) and any(
        error["type"] == "json_invalid" for error in exception.errors()
    )
    return problem_response(
        request,
        status_code=400 if malformed_json else 422,
        code="BAD_REQUEST" if malformed_json else "VALIDATION_ERROR",
        detail="Request body contains invalid JSON."
        if malformed_json
        else "Request validation failed.",
    )


async def readiness_exception_handler(
    request: Request, exception: Exception
) -> JSONResponse:
    """Map dependency outages to a temporary readiness failure."""
    return problem_response(
        request,
        status_code=503,
        code="SERVICE_NOT_READY",
        detail="The service is not ready to receive requests.",
    )


def configure_exception_handlers(app: FastAPI) -> None:
    """Override framework defaults at the HTTP boundary."""
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(
        RequestValidationError, validation_exception_handler
    )
    app.add_exception_handler(
        ServiceNotReadyError, readiness_exception_handler
    )
