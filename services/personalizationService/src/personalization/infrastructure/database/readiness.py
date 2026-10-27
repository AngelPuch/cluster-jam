"""Adapt local database availability to the readiness port."""

from sqlalchemy import Engine, text
from sqlalchemy.exc import SQLAlchemyError

from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.check import DATABASE_ACCESS_QUERY
from personalization.infrastructure.database.migration_config import (
    CURRENT_REVISION,
)


class SqlAlchemyReadinessAdapter:
    """Reuse the pool to verify local database access."""

    def __init__(self, engine: Engine, settings: Settings) -> None:
        self._engine = engine
        self._settings = settings

    def is_ready(self) -> bool:
        """Report temporary connection failures as not ready."""
        try:
            with self._engine.connect() as connection:
                result = connection.execute(
                    DATABASE_ACCESS_QUERY,
                    {
                        "database_name": self._settings.db_name,
                        "database_user": self._settings.db_user,
                        "schema_name": self._settings.db_schema,
                    },
                )
                if result.scalar_one() is not True:
                    return False
                revisions = (
                    connection.execute(
                        text("SELECT version_num FROM app.alembic_version")
                    )
                    .scalars()
                    .all()
                )
                return revisions == [CURRENT_REVISION]
        except SQLAlchemyError:
            return False
