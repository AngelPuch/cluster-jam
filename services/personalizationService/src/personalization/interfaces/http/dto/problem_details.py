"""Describe the project's RFC 9457 HTTP error contract."""

from pydantic import Field

from personalization.interfaces.http.dto.rest_model import RestModel


class ProblemDetails(RestModel):
    """Expose stable error codes and the request's trace identifier."""

    type: str
    title: str
    status: int = Field(ge=400, le=599)
    detail: str
    instance: str
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]*$")
    trace_id: str = Field(pattern=r"^[0-9a-f]{32}$")
