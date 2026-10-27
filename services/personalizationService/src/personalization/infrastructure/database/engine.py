"""Create bounded, reusable database connection pools."""

from sqlalchemy import Engine, create_engine

from personalization.infrastructure.config.settings import Settings


def create_database_engine(settings: Settings) -> Engine:
    """Configure timeouts without exposing SQL parameter values."""
    return create_engine(
        settings.database_url,
        connect_args={
            "connect_timeout": settings.db_connect_timeout_seconds,
            "options": ("-c statement_timeout=5000 -c search_path=pg_catalog"),
        },
        pool_pre_ping=True,
        pool_timeout=settings.db_connect_timeout_seconds,
        pool_size=5,
        max_overflow=5,
        hide_parameters=True,
    )
