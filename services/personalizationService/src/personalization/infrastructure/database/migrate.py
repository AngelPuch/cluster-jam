"""Apply explicit schema migrations before starting API replicas."""

import argparse
import logging
from io import StringIO
from typing import Literal

from alembic import command
from alembic.util.exc import CommandError
from pydantic import ValidationError
from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.check import DATABASE_ACCESS_QUERY
from personalization.infrastructure.database.engine import (
    create_database_engine,
)
from personalization.infrastructure.database.migration_config import (
    migration_config,
)
from personalization.infrastructure.observability.logging_config import (
    configure_logging,
)

type MigrationAction = Literal["upgrade", "check", "current"]
MIGRATION_LOCK_ID = 485741092403


def run_migrations(
    engine: Engine, settings: Settings, action: MigrationAction
) -> str:
    """Serialize migration operations within one local transaction."""
    with engine.begin() as connection:
        permitted = connection.execute(
            DATABASE_ACCESS_QUERY,
            {
                "database_name": settings.db_name,
                "database_user": settings.db_user,
                "schema_name": settings.db_schema,
            },
        ).scalar_one()
        if permitted is not True:
            raise RuntimeError("Database ownership validation failed")
        connection.execute(
            text("SELECT pg_advisory_xact_lock(:lock_id)"),
            {"lock_id": MIGRATION_LOCK_ID},
        )
        output = StringIO()
        configuration = migration_config()
        configuration.stdout = output
        configuration.attributes["connection"] = connection
        if action == "upgrade":
            command.upgrade(configuration, "head")
        elif action == "check":
            command.check(configuration)
        else:
            command.current(configuration, check_heads=True)
        return output.getvalue()


def main() -> int:
    """Emit sanitized structured results without printing SQL errors."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("upgrade", "check", "current"))
    arguments = parser.parse_args()
    try:
        settings = Settings()
    except ValidationError:
        configure_logging(environment="unknown", log_level="ERROR")
        logging.getLogger("personalization.migrations").error(
            "Migration configuration is invalid",
            extra={
                "event": "database.migration.failed",
                "code": "CONFIGURATION_INVALID",
            },
        )
        return 2
    configure_logging(
        environment=settings.app_env, log_level=settings.log_level
    )
    logger = logging.getLogger("personalization.migrations")
    engine = create_database_engine(settings)
    try:
        run_migrations(engine, settings, arguments.action)
    except SQLAlchemyError, CommandError, RuntimeError:
        logger.error(
            "Schema migration command failed",
            extra={
                "event": "database.migration.failed",
                "code": "MIGRATION_FAILED",
            },
        )
        return 1
    finally:
        engine.dispose()
    logger.info(
        "Schema migration command completed",
        extra={
            "event": f"database.migration.{arguments.action}.succeeded",
            "code": "MIGRATION_SUCCEEDED",
        },
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
