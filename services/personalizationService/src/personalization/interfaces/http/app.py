"""Build HTTP contracts without credentials or database access."""

from importlib.metadata import version

from fastapi import FastAPI
from starlette.types import Lifespan

from personalization.interfaces.http.errors.problem_handlers import (
    configure_exception_handlers,
)
from personalization.interfaces.http.files.routes import router as files_router
from personalization.interfaces.http.health.routes import router
from personalization.interfaces.http.openapi import configure_openapi
from personalization.interfaces.http.prints.thumbnails import (
    router as prints_router,
)


def create_http_app(lifespan: Lifespan[FastAPI] | None = None) -> FastAPI:
    """Share route definitions for runtime and offline OpenAPI."""
    app = FastAPI(
        title="Cluster JAM Personalization Service",
        version=version("cluster-jam-personalization-service"),
        description=(
            "Private image files with local JWT authorization, "
            "validated originals, short-lived downloads, and administrative "
            "print versioning with atomic audit records."
        ),
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        redirect_slashes=False,
        lifespan=lifespan,
    )
    app.include_router(router)
    app.include_router(files_router)
    app.include_router(prints_router)
    configure_exception_handlers(app)
    configure_openapi(app)
    return app
