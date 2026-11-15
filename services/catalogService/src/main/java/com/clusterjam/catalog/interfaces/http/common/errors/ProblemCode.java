package com.clusterjam.catalog.interfaces.http.common.errors;

public enum ProblemCode {

    BAD_REQUEST(400, "The request could not be read."),
    UNAUTHORIZED(401, "Authentication is required."),
    FORBIDDEN(403, "Access is denied."),
    NOT_FOUND(404, "The requested resource was not found."),
    METHOD_NOT_ALLOWED(405, "This HTTP method is not supported for the resource."),
    NOT_ACCEPTABLE(406, "The requested response format is not available."),
    CONFLICT(409, "The request conflicts with the current resource state."),
    PRECONDITION_FAILED(412, "A request precondition was not met."),
    PAYLOAD_TOO_LARGE(413, "The request content exceeds the allowed size."),
    UNSUPPORTED_MEDIA_TYPE(415, "The request content type is not supported."),
    UNPROCESSABLE_ENTITY(422, "The request did not pass validation."),
    TOO_MANY_REQUESTS(429, "Too many requests were sent."),
    INTERNAL_SERVER_ERROR(500, "An unexpected error occurred."),
    SERVICE_UNAVAILABLE(503, "The service is temporarily unavailable."),
    HTTP_ERROR(0, "The request could not be completed.");

    private final int status;
    private final String detail;

    ProblemCode(int status, String detail) {
        this.status = status;
        this.detail = detail;
    }

    public int status() {
        return status;
    }

    public String detail() {
        return detail;
    }

    public static ProblemCode forStatus(int status) {
        for (ProblemCode code : values()) {
            if (code.status == status) {
                return code;
            }
        }
        return HTTP_ERROR;
    }
}
