"""Wire the HTTP boundary to application ports and infrastructure."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import Engine
from starlette.concurrency import run_in_threadpool

from personalization.application.catalog.catalog_service import CatalogService
from personalization.application.designs.design_analysis_service import (
    DesignAnalysisService,
)
from personalization.application.designs.draft_service import DraftService
from personalization.application.files.file_service import FileService
from personalization.application.health.readiness_service import (
    ReadinessService,
)
from personalization.application.images.validate_image_service import (
    ValidateImageService,
)
from personalization.application.ports.design_analysis_ports import (
    AnalysisSourcePort,
    ImageGeometryPort,
)
from personalization.application.ports.design_repository_port import (
    DesignRepositoryPort,
)
from personalization.application.ports.file_repository_port import (
    FileRepositoryPort,
)
from personalization.application.ports.preview_ports import (
    PreviewRepositoryPort,
)
from personalization.application.ports.print_catalog_port import (
    PrintCatalogPort,
)
from personalization.application.ports.print_repository_port import (
    PrintRepositoryPort,
)
from personalization.application.ports.private_storage_port import (
    PrivateStoragePort,
)
from personalization.application.ports.readiness_port import ReadinessPort
from personalization.application.ports.template_repository_port import (
    TemplateRepositoryPort,
)
from personalization.application.ports.thumbnail_ports import (
    ThumbnailRepositoryPort,
)
from personalization.application.previews.preview_service import PreviewService
from personalization.application.prints.print_service import PrintService
from personalization.application.templates.template_service import (
    TemplateService,
)
from personalization.application.thumbnails.thumbnail_service import (
    ThumbnailService,
)
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.analysis_repository import (
    SqlAlchemyAnalysisSourceRepository,
)
from personalization.infrastructure.database.design_repository import (
    SqlAlchemyDesignRepository,
)
from personalization.infrastructure.database.engine import (
    create_database_engine,
)
from personalization.infrastructure.database.file_repository import (
    SqlAlchemyFileRepository,
)
from personalization.infrastructure.database.preview_repository import (
    SqlAlchemyPreviewRepository,
)
from personalization.infrastructure.database.print_catalog_repository import (
    SqlAlchemyPrintCatalogRepository,
)
from personalization.infrastructure.database.print_repository import (
    SqlAlchemyPrintRepository,
)
from personalization.infrastructure.database.readiness import (
    SqlAlchemyReadinessAdapter,
)
from personalization.infrastructure.database.template_repository import (
    SqlAlchemyTemplateRepository,
)
from personalization.infrastructure.database.thumbnail_repository import (
    SqlAlchemyThumbnailRepository,
)
from personalization.infrastructure.images.image_geometry import (
    PillowImageGeometry,
    UnavailableImageGeometry,
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
from personalization.infrastructure.storage.supabase_storage import (
    SupabaseStorage,
)
from personalization.infrastructure.storage.unavailable_storage import (
    UnavailableStorage,
)
from personalization.interfaces.http.app import create_http_app
from personalization.interfaces.http.files.upload_limits import (
    UploadBodyLimitMiddleware,
)
from personalization.interfaces.http.request_context import (
    RequestContextMiddleware,
)


def create_app(
    settings: Settings | None = None,
    readiness_port: ReadinessPort | None = None,
    *,
    file_repository: FileRepositoryPort | None = None,
    storage: PrivateStoragePort | None = None,
    print_repository: PrintRepositoryPort | None = None,
    thumbnail_repository: ThumbnailRepositoryPort | None = None,
    catalog_repository: PrintCatalogPort | None = None,
    template_repository: TemplateRepositoryPort | None = None,
    analysis_sources: AnalysisSourcePort | None = None,
    image_geometry: ImageGeometryPort | None = None,
    design_repository: DesignRepositoryPort | None = None,
    preview_repository: PreviewRepositoryPort | None = None,
) -> FastAPI:
    """Start independently and release resources on shutdown."""
    configuration = settings if settings is not None else Settings()
    configure_logging(
        environment=configuration.app_env, log_level=configuration.log_level
    )
    engine: Engine | None = None
    if (
        readiness_port is None
        or file_repository is None
        or print_repository is None
        or thumbnail_repository is None
        or catalog_repository is None
        or template_repository is None
        or analysis_sources is None
        or design_repository is None
        or preview_repository is None
    ):
        engine = create_database_engine(configuration)
        if readiness_port is None:
            readiness_port = SqlAlchemyReadinessAdapter(engine, configuration)
        if file_repository is None:
            file_repository = SqlAlchemyFileRepository(engine)
        if print_repository is None:
            print_repository = SqlAlchemyPrintRepository(
                engine, configuration.storage_bucket
            )
        if thumbnail_repository is None:
            thumbnail_repository = SqlAlchemyThumbnailRepository(
                engine, configuration.storage_bucket
            )
        if catalog_repository is None:
            catalog_repository = SqlAlchemyPrintCatalogRepository(
                engine, configuration.storage_bucket
            )
        if template_repository is None:
            template_repository = SqlAlchemyTemplateRepository(engine)
        if analysis_sources is None:
            analysis_sources = SqlAlchemyAnalysisSourceRepository(
                engine, configuration.storage_bucket
            )
        if design_repository is None:
            design_repository = SqlAlchemyDesignRepository(
                engine, configuration.storage_bucket
            )
        if preview_repository is None:
            preview_repository = SqlAlchemyPreviewRepository(
                engine, configuration.storage_bucket
            )
    outbound: SupabaseStorage | None = None
    if storage is None:
        if configuration.storage_enabled:
            outbound = SupabaseStorage(
                configuration.storage_project_url,
                configuration.storage_bucket,
                configuration.storage_key,
            )
            storage = outbound
        else:
            storage = UnavailableStorage()
    if image_geometry is None:
        image_geometry = (
            PillowImageGeometry(outbound, configuration.image_policy)
            if outbound is not None
            else UnavailableImageGeometry()
        )
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
        app.state.file_service = FileService(
            app.state.image_validator,
            file_repository,
            storage,
            configuration.storage_bucket,
            configuration.download_url_ttl_seconds,
        )
        app.state.print_service = PrintService(print_repository)
        app.state.thumbnail_service = ThumbnailService(
            print_repository,
            thumbnail_repository,
            storage,
            configuration.storage_bucket,
            configuration.download_url_ttl_seconds,
        )
        app.state.catalog_service = CatalogService(
            catalog_repository, storage, configuration.download_url_ttl_seconds
        )
        app.state.template_service = TemplateService(template_repository)
        app.state.draft_service = DraftService(
            design_repository, template_repository
        )
        app.state.preview_service = PreviewService(
            app.state.draft_service,
            preview_repository,
            storage,
            configuration.storage_bucket,
            configuration.download_url_ttl_seconds,
        )
        app.state.design_analysis_service = DesignAnalysisService(
            template_repository,
            analysis_sources,
            image_geometry,
            configuration.min_print_dpi,
        )
        app.state.upload_gate = asyncio.BoundedSemaphore(1)
        logger.info("Service started", extra={"event": "service.started"})
        try:
            yield
        finally:
            if outbound is not None:
                await run_in_threadpool(outbound.close)
            if engine is not None:
                await run_in_threadpool(engine.dispose)
            provider.shutdown()
            logger.info("Service stopped", extra={"event": "service.stopped"})

    app = create_http_app(lifespan)
    app.state.settings = configuration
    app.state.readiness_service = ReadinessService(readiness_port)
    app.add_middleware(UploadBodyLimitMiddleware)
    app.add_middleware(RequestContextMiddleware, tracer=tracer)
    return app
