"""Describe versioned HTTP contracts and shared problem responses."""

from fastapi import FastAPI

from personalization.interfaces.http.dto.problem_details import ProblemDetails


def configure_openapi(app: FastAPI) -> None:
    """Document the actual Problem Details response format."""
    document = app.openapi()
    components = document.setdefault("components", {})
    components.setdefault("schemas", {})["ProblemDetails"] = (
        ProblemDetails.model_json_schema(by_alias=True)
    )
    components.setdefault("securitySchemes", {})["supabase-jwt"] = {
        "type": "http",
        "scheme": "bearer",
        "bearerFormat": "JWT",
        "description": (
            "Supabase access token with a protected application role"
        ),
    }
    content = {
        "application/problem+json": {
            "schema": {"$ref": "#/components/schemas/ProblemDetails"}
        }
    }
    for path in document["paths"].values():
        for method, operation in path.items():
            if method not in {"get", "post", "put", "patch", "delete", "head"}:
                continue
            responses = operation.setdefault("responses", {})
            responses["default"] = {
                "description": "RFC 9457 error with code and traceId",
                "content": content,
            }
            responses["500"] = {
                "description": "Unexpected server error",
                "content": content,
            }
            for status, response in responses.items():
                if status.isdigit() and int(status) >= 400:
                    response["content"] = content
    app.openapi_schema = document
