"""Keep HTTP error responses consistent and free of internal details."""

from http import HTTPStatus
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.errors.image_validation_error import (
    ImageValidationError,
    ImageValidationFailure,
)
from personalization.application.errors.print_error import (
    PrintError,
    PrintFailure,
)
from personalization.application.errors.security_error import (
    SecurityError,
    SecurityFailure,
)
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


async def security_exception_handler(
    request: Request, exception: Exception
) -> JSONResponse:
    """Map security errors without exposing provider details."""
    if not isinstance(exception, SecurityError):
        return unexpected_problem(request)
    status, detail = {
        SecurityFailure.INVALID_ACCESS_TOKEN: (
            401,
            "A valid user access token is required.",
        ),
        SecurityFailure.INVALID_APP_ROLE: (
            403,
            "The token has no valid protected application role.",
        ),
        SecurityFailure.FORBIDDEN: (
            403,
            "The identity is not permitted to perform this operation.",
        ),
        SecurityFailure.KEYS_UNAVAILABLE: (
            503,
            "The required public signing keys are unavailable.",
        ),
    }[exception.failure]
    return problem_response(
        request,
        status_code=status,
        code=exception.failure.value,
        detail=detail,
        headers={"WWW-Authenticate": "Bearer"} if status == 401 else None,
    )


async def image_validation_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    """Describe image rejections without leaking decoder diagnostics."""
    if not isinstance(exception, ImageValidationError):
        return unexpected_problem(request)
    status, detail = {
        ImageValidationFailure.EMPTY_IMAGE: (
            400,
            "The uploaded image is empty.",
        ),
        ImageValidationFailure.IMAGE_TOO_LARGE: (
            413,
            "The image exceeds 10,000,000 bytes.",
        ),
        ImageValidationFailure.UNSUPPORTED_IMAGE_TYPE: (
            415,
            "Only PNG and JPEG images are supported.",
        ),
        ImageValidationFailure.IMAGE_MIME_MISMATCH: (
            415,
            "The declared MIME type does not match the image contents.",
        ),
        ImageValidationFailure.INVALID_IMAGE: (
            422,
            "The image is damaged or cannot be fully decoded.",
        ),
        ImageValidationFailure.IMAGE_DIMENSIONS_EXCEEDED: (
            422,
            "The image exceeds the permitted dimensions or pixel count.",
        ),
        ImageValidationFailure.ANIMATED_IMAGE_NOT_SUPPORTED: (
            422,
            "Animated or multi-frame originals are not supported.",
        ),
        ImageValidationFailure.IMAGE_READ_FAILED: (
            503,
            "The uploaded image could not be read.",
        ),
    }[exception.failure]
    return problem_response(
        request,
        status_code=status,
        code=exception.failure.value,
        detail=detail,
    )


async def file_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    """Preserve file failure codes without remote diagnostic details."""
    if not isinstance(exception, FileError):
        return unexpected_problem(request)
    status, detail = {
        FileFailure.FILE_NOT_FOUND: (404, "The original file was not found."),
        FileFailure.FILE_NOT_READY: (
            409,
            "The original upload is not available yet.",
        ),
        FileFailure.FILE_DATABASE_UNAVAILABLE: (
            503,
            "File metadata is temporarily unavailable.",
        ),
        FileFailure.STORAGE_NOT_CONFIGURED: (
            503,
            "Private file storage is not configured.",
        ),
        FileFailure.STORAGE_UNAVAILABLE: (
            503,
            "Private file storage is temporarily unavailable.",
        ),
        FileFailure.STORAGE_BUCKET_UNSAFE: (
            503,
            "The file bucket does not meet the required configuration.",
        ),
        FileFailure.FILE_INTEGRITY_MISMATCH: (
            409,
            "The stored original does not match its verified metadata.",
        ),
        FileFailure.INVALID_MULTIPART: (
            400,
            "Use multipart/form-data with exactly one file field named file.",
        ),
        FileFailure.UPLOAD_BODY_TOO_LARGE: (
            413,
            "The upload request body exceeds the permitted size.",
        ),
        FileFailure.UPLOAD_BUSY: (
            429,
            "Another upload is in progress. Try again shortly.",
        ),
        FileFailure.UPLOAD_TIMEOUT: (
            408,
            "The upload request body was not received in time.",
        ),
        FileFailure.IMAGE_READ_FAILED: (
            503,
            "The uploaded image could not be read.",
        ),
    }[exception.failure]
    headers: dict[str, str] = {}
    if status == 429:
        headers["Retry-After"] = "1"
    if exception.file_id is not None:
        headers["Location"] = f"/api/v1/files/{exception.file_id}"
    return problem_response(
        request,
        status_code=status,
        code=exception.failure.value,
        detail=detail,
        headers=headers or None,
    )


async def print_exception_handler(
    request: Request,
    exception: Exception,
) -> JSONResponse:
    """Hide persistence diagnostics and report stable print failures."""
    if not isinstance(exception, PrintError):
        return unexpected_problem(request)
    status, detail = {
        PrintFailure.PRINT_NOT_FOUND: (404, "The print was not found."),
        PrintFailure.PRINT_VERSION_NOT_FOUND: (
            404,
            "The print version was not found.",
        ),
        PrintFailure.PRINT_FILE_NOT_FOUND: (
            404,
            "The original file was not found.",
        ),
        PrintFailure.INVALID_PRINT_FILE: (
            409,
            "Choose an available original in the service bucket.",
        ),
        PrintFailure.PRINT_VERSION_CONFLICT: (
            409,
            "The latest print version changed; reload before editing.",
        ),
        PrintFailure.PRINT_VERSION_LIMIT: (
            409,
            "The print cannot accept another version.",
        ),
        PrintFailure.PRINT_DATABASE_UNAVAILABLE: (
            503,
            "Print metadata is temporarily unavailable.",
        ),
        PrintFailure.INVALID_PRINT_DATA: (
            422,
            "Print data does not meet the required constraints.",
        ),
        PrintFailure.INVALID_CURSOR: (
            400,
            "The cursor is invalid for this collection.",
        ),
    }[exception.failure]
    return problem_response(
        request,
        status_code=status,
        code=exception.failure.value,
        detail=detail,
    )


def configure_exception_handlers(app: FastAPI) -> None:
    """Override framework defaults at the HTTP boundary."""
    app.add_exception_handler(PrintError, print_exception_handler)
    app.add_exception_handler(FileError, file_exception_handler)
    app.add_exception_handler(
        ImageValidationError, image_validation_exception_handler
    )
    app.add_exception_handler(SecurityError, security_exception_handler)
    app.add_exception_handler(HTTPException, http_exception_handler)
    app.add_exception_handler(
        RequestValidationError, validation_exception_handler
    )
    app.add_exception_handler(
        ServiceNotReadyError, readiness_exception_handler
    )
