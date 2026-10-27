"""Prepare private Storage or reconcile acknowledged remote objects."""

import argparse
import logging
from uuid import UUID

from pydantic import ValidationError

from personalization.application.errors.file_error import (
    FileError,
    FileFailure,
)
from personalization.application.files.file_service import FileService
from personalization.application.images.validate_image_service import (
    ValidateImageService,
)
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.engine import (
    create_database_engine,
)
from personalization.infrastructure.database.file_repository import (
    SqlAlchemyFileRepository,
)
from personalization.infrastructure.images.pillow_image_inspector import (
    PillowImageInspector,
)
from personalization.infrastructure.observability.logging_config import (
    configure_logging,
)
from personalization.infrastructure.storage.supabase_storage import (
    SupabaseStorage,
)


def main() -> int:
    """Operate only on the configured service bucket and
    local database.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "action", choices=("check", "create", "pending", "reconcile")
    )
    parser.add_argument("--file-id", type=UUID)
    parser.add_argument("--limit", type=int, default=20)
    arguments = parser.parse_args()
    if arguments.action == "reconcile" and arguments.file_id is None:
        parser.error("reconcile requires --file-id")
    try:
        settings = Settings()
    except ValidationError:
        configure_logging(environment="unknown", log_level="ERROR")
        logging.getLogger("personalization.storage").error(
            "Storage command configuration is invalid",
            extra={
                "event": "storage.command.failed",
                "code": "CONFIGURATION_INVALID",
            },
        )
        return 2
    configure_logging(
        environment=settings.app_env, log_level=settings.log_level
    )
    logger = logging.getLogger("personalization.storage")
    engine = create_database_engine(settings)
    storage: SupabaseStorage | None = None
    try:
        repository = SqlAlchemyFileRepository(engine)
        if arguments.action == "pending":
            records = repository.list_pending(arguments.limit)
            logger.info(
                "Pending original upload intentions",
                extra={
                    "event": "storage.pending.listed",
                    "code": "PENDING_FILES",
                    "file_ids": [str(record.id) for record in records],
                },
            )
            return 0
        if not settings.storage_enabled:
            raise FileError(FileFailure.STORAGE_NOT_CONFIGURED)
        storage = SupabaseStorage(
            settings.storage_project_url,
            settings.storage_bucket,
            settings.storage_key,
        )
        if arguments.action == "create":
            storage.create_bucket()
        elif arguments.action == "check":
            storage.ensure_private()
        else:
            service = FileService(
                ValidateImageService(
                    PillowImageInspector(), settings.image_policy
                ),
                repository,
                storage,
                settings.storage_bucket,
                settings.download_url_ttl_seconds,
            )
            service.reconcile(arguments.file_id)
    except FileError as error:
        logger.error(
            "Storage command failed",
            extra={
                "event": "storage.command.failed",
                "code": error.failure.value,
            },
        )
        return 1
    finally:
        if storage is not None:
            storage.close()
        engine.dispose()
    logger.info(
        "Storage command completed",
        extra={"event": "storage.command.succeeded", "code": "STORAGE_READY"},
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
