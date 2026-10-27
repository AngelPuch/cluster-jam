"""Own one fresh disposable schema for integration tests."""

from collections.abc import Iterator

import pytest
from alembic import command
from sqlalchemy import Engine, inspect

from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.engine import (
    create_database_engine,
)
from personalization.infrastructure.database.migrate import run_migrations
from personalization.infrastructure.database.migration_config import (
    migration_config,
)
from personalization.infrastructure.database.readiness import (
    SqlAlchemyReadinessAdapter,
)


@pytest.fixture(scope="session")
def settings() -> Settings:
    return Settings()


@pytest.fixture(scope="session")
def engine(settings: Settings) -> Iterator[Engine]:
    database = create_database_engine(settings)
    try:
        # Never reset a populated development or production schema.
        if inspect(database).get_table_names(schema="app"):
            raise RuntimeError("Integration tests require an empty app schema")
        readiness = SqlAlchemyReadinessAdapter(database, settings)
        assert readiness.is_ready() is False
        run_migrations(database, settings, "upgrade")
        assert readiness.is_ready() is True
        yield database
        with database.begin() as connection:
            configuration = migration_config()
            configuration.attributes["connection"] = connection
            command.downgrade(configuration, "base")
        assert inspect(database).get_table_names(schema="app") == [
            "alembic_version"
        ]
        assert readiness.is_ready() is False
        run_migrations(database, settings, "upgrade")
        run_migrations(database, settings, "check")
        assert readiness.is_ready() is True
    finally:
        database.dispose()
