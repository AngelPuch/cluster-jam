"""Check database access without creating or changing domain tables."""

import json
import logging
import os
import socket
import sys
from datetime import UTC, datetime
from importlib.metadata import version

from pydantic import ValidationError
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from personalization.infrastructure.config.settings import Settings

DATABASE_ACCESS_QUERY = text(
    """
    SELECT current_database() = :database_name
        AND current_user = :database_user
        AND EXISTS (
            SELECT 1 FROM pg_namespace
            WHERE nspname = :schema_name
                AND pg_get_userbyid(nspowner) = current_user
        )
        AND NOT EXISTS (
            SELECT 1 FROM pg_roles
            WHERE rolname = current_user
                AND (rolsuper OR rolcreatedb OR rolcreaterole
                    OR rolreplication OR rolbypassrls)
        )
    """
)


def check_database(settings: Settings) -> bool:
    """Confirm service ownership and least-privilege credentials."""
    engine = create_engine(
        settings.database_url,
        connect_args={
            "connect_timeout": settings.db_connect_timeout_seconds,
            "options": "-c statement_timeout=5000",
        },
        hide_parameters=True,
    )
    try:
        with engine.connect() as connection:
            result = connection.execute(
                DATABASE_ACCESS_QUERY,
                {
                    "database_name": settings.db_name,
                    "database_user": settings.db_user,
                    "schema_name": settings.db_schema,
                },
            )
            return result.scalar_one() is True
    finally:
        engine.dispose()


def _log_result(
    logger: logging.Logger,
    *,
    succeeded: bool,
    environment: str,
    code: str,
) -> None:
    """Emit one sanitized JSON event for this technical command."""
    level = logging.INFO if succeeded else logging.ERROR
    logger.log(
        level,
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "level": "INFO" if succeeded else "ERROR",
                "service_name": "personalization",
                "service_version": version(
                    "cluster-jam-personalization-service"
                ),
                "environment": environment,
                "instance_id": socket.gethostname(),
                "event": (
                    "database.check.succeeded"
                    if succeeded
                    else "database.check.failed"
                ),
                "message": (
                    "Database access verified"
                    if succeeded
                    else "Database check failed"
                ),
                "code": code,
                "trace_id": None,
                "span_id": None,
            }
        ),
    )


def main() -> int:
    """Return zero only for valid configuration and database access."""
    logger = logging.getLogger("personalization.database_check")
    logger.handlers.clear()
    logger.addHandler(logging.StreamHandler(sys.stdout))
    logger.propagate = False
    logger.setLevel(logging.INFO)
    environment = os.environ.get("APP_ENV", "unknown")
    try:
        settings = Settings()
        environment = settings.app_env
        logger.setLevel(
            "WARNING" if settings.log_level == "WARN" else settings.log_level
        )
        succeeded = check_database(settings)
    except ValidationError:
        code = "CONFIGURATION_INVALID"
    except SQLAlchemyError:
        code = "DATABASE_UNAVAILABLE"
    else:
        code = (
            "DATABASE_READY"
            if succeeded
            else "DATABASE_CONFIGURATION_MISMATCH"
        )
        _log_result(
            logger,
            succeeded=succeeded,
            environment=environment,
            code=code,
        )
        return 0 if succeeded else 1
    _log_result(logger, succeeded=False, environment=environment, code=code)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
