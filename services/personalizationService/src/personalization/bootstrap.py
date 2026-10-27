"""Wire the HTTP boundary to application ports and infrastructure."""

import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import Engine
from starlette.concurrency import run_in_threadpool

from personalization.application.health.readiness_service import (
    ReadinessService,
)
from personalization.application.images.validate_image_service import (
    ValidateImageService,
)
from personalization.application.ports.readiness_port import ReadinessPort
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.engine import (
    create_database_engine,
)
from personalization.infrastructure.database.readiness import (
    SqlAlchemyReadinessAdapter,
)
from personalization.infrastructure.images.pillow_image_inspector import (
    PillowImageInspector,
)
from personalization.infrastructure.observability.logging_config import (
    configure_logging,
)
from personalization.infrastructure.security.supabase_jwt_verifier import (
    SupabaseJwtVerifier,
)
from personalization.interfaces.http.app import create_http_app
from personalization.interfaces.http.request_context import (
    RequestContextMiddleware,
)


def create_app(
    settings: Settings | None = None,
    readiness_port: ReadinessPort | None = None,
) -> FastAPI:
    """Start independently and release resources on shutdown."""
    configuration = settings if settings is not None else Settings()
    configure_logging(
        environment=configuration.app_env, log_level=configuration.log_level
    )
    engine: Engine | None = None
    if readiness_port is None:
        engine = create_database_engine(configuration)
        readiness_port = SqlAlchemyReadinessAdapter(engine, configuration)
    provider = TracerProvider(
        resource=Resource.create(
            {
                "service.name": "personalization",
                "deployment.environment.name": configuration.app_env,
            }
        )
    )
    tracer = provider.get_tracer("personalization.http")
    logger = logging.getLogger("personalization.lifecycle")

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.access_token_verifier = SupabaseJwtVerifier(
            issuer=str(configuration.supabase_issuer),
            jwks_url=str(configuration.supabase_jwks_url),
        )
        app.state.image_validator = ValidateImageService(
            PillowImageInspector(), configuration.image_policy
        )
        logger.info("Service started", extra={"event": "service.started"})
        try:
            yield
        finally:
            if engine is not None:
                await run_in_threadpool(engine.dispose)
            provider.shutdown()
            logger.info("Service stopped", extra={"event": "service.stopped"})

    app = create_http_app(lifespan)
    app.state.settings = configuration
    app.state.readiness_service = ReadinessService(readiness_port)
    app.add_middleware(RequestContextMiddleware, tracer=tracer)
    return app
