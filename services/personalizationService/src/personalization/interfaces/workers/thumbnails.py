"""Run thumbnail processing separately from the HTTP process."""

import argparse
import logging
import signal
from threading import Event
from types import FrameType
from uuid import UUID

from opentelemetry.sdk.trace import TracerProvider
from pydantic import ValidationError

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.images.validate_image_service import (
    ValidateImageService,
)
from personalization.application.thumbnails.thumbnail_worker import (
    ThumbnailWorker,
)
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.engine import (
    create_database_engine,
)
from personalization.infrastructure.database.readiness import (
    SqlAlchemyReadinessAdapter,
)
from personalization.infrastructure.database.thumbnail_repository import (
    SqlAlchemyThumbnailRepository,
)
from personalization.infrastructure.images.pillow_image_inspector import (
    PillowImageInspector,
)
from personalization.infrastructure.images.pillow_thumbnail_renderer import (
    PillowThumbnailRenderer,
)
from personalization.infrastructure.observability.logging_config import (
    configure_logging,
)
from personalization.infrastructure.storage.supabase_storage import (
    SupabaseStorage,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    arguments = parser.parse_args()
    try:
        settings = Settings()
    except ValidationError:
        configure_logging(environment="unknown", log_level="ERROR")
        logging.getLogger("personalization.worker").error(
            "Worker configuration is invalid",
            extra={"event": "worker.failed", "code": "CONFIGURATION_INVALID"},
        )
        return 2
    configure_logging(
        environment=settings.app_env, log_level=settings.log_level
    )
    logger = logging.getLogger("personalization.worker")
    engine = create_database_engine(settings)
    storage: SupabaseStorage | None = None
    provider = TracerProvider()
    tracer = provider.get_tracer("personalization.thumbnails")
    stop = Event()

    def request_stop(signum: int, frame: FrameType | None) -> None:
        stop.set()

    previous = {
        signum: signal.signal(signum, request_stop)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        if not settings.storage_enabled:
            raise FileError(FileFailure.STORAGE_NOT_CONFIGURED)
        storage = SupabaseStorage(
            settings.storage_project_url,
            settings.storage_bucket,
            settings.storage_key,
        )
        worker = ThumbnailWorker(
            SqlAlchemyThumbnailRepository(engine, settings.storage_bucket),
            storage,
            PillowThumbnailRenderer(
                ValidateImageService(
                    PillowImageInspector(), settings.image_policy
                )
            ),
        )
        readiness = SqlAlchemyReadinessAdapter(engine, settings)
        after: UUID | None = None
        failed = False
        logger.info("Worker started", extra={"event": "worker.started"})
        while not stop.is_set():
            with tracer.start_as_current_span("thumbnail.batch"):
                try:
                    if not readiness.is_ready():
                        raise FileError(FileFailure.FILE_DATABASE_UNAVAILABLE)
                    result = worker.batch(
                        after, settings.worker_batch_size, stop.is_set
                    )
                    after = result.after
                    failed = bool(result.failures)
                    if (
                        result.completed
                        or result.busy
                        or failed
                        or arguments.once
                    ):
                        logger.log(
                            logging.WARNING if failed else logging.INFO,
                            "Thumbnail batch completed",
                            extra={
                                "event": "worker.batch.completed",
                                "completed": result.completed,
                                "busy": result.busy,
                                "failures": len(result.failures),
                                "codes": sorted(set(result.failures)),
                            },
                        )
                except FileError as error:
                    failed = True
                    logger.warning(
                        "Thumbnail batch deferred",
                        extra={
                            "event": "worker.batch.failed",
                            "code": error.failure.value,
                        },
                    )
            if arguments.once:
                return 1 if failed else 0
            stop.wait(settings.worker_poll_seconds)
    except FileError as error:
        logger.error(
            "Worker cannot start",
            extra={"event": "worker.failed", "code": error.failure.value},
        )
        return 1
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)
        if storage is not None:
            storage.close()
        engine.dispose()
        provider.shutdown()
        logger.info("Worker stopped", extra={"event": "worker.stopped"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
