"""Build HTTP contracts without credentials or database access."""

from importlib.metadata import version

from fastapi import FastAPI
from starlette.types import Lifespan

from personalization.interfaces.http.errors.problem_handlers import (
    configure_exception_handlers,
)
from personalization.interfaces.http.health.routes import router
from personalization.interfaces.http.openapi import configure_openapi


def create_http_app(lifespan: Lifespan[FastAPI] | None = None) -> FastAPI:
    """Share route definitions for runtime and offline OpenAPI."""
    app = FastAPI(
        title="Cluster JAM Personalization Service",
        version=version("cluster-jam-personalization-service"),
        description=(
            "Technical HTTP foundation. Business REST resources will use "
            "/api/v1. JWT authorization is implemented in a later increment."
        ),
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        redirect_slashes=False,
        lifespan=lifespan,
    )
    app.include_router(router)
    configure_exception_handlers(app)
    configure_openapi(app)
    return app
