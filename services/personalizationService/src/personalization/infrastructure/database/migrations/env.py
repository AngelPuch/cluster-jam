"""Run reviewed revisions without ORM table auto-creation."""

from alembic import context
from alembic.runtime.environment import NameFilterParentNames, NameFilterType
from sqlalchemy import Connection

from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.engine import (
    create_database_engine,
)
from personalization.infrastructure.database.models import Base


def include_name(
    name: str | None,
    type_: NameFilterType,
    parent_names: NameFilterParentNames,
) -> bool:
    """Limit autogeneration inspection to our own schema."""
    return name == "app" if type_ == "schema" else True


def migrate_connection(connection: Connection) -> None:
    """Share an explicit transaction with the migration command."""
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        version_table_schema="app",
        include_schemas=True,
        include_name=include_name,
        compare_type=True,
        compare_server_default=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations() -> None:
    """Export SQL offline or use a bounded local engine online."""
    if context.is_offline_mode():
        context.configure(
            url="postgresql+psycopg://",
            target_metadata=Base.metadata,
            literal_binds=True,
            version_table_schema="app",
            include_schemas=True,
        )
        with context.begin_transaction():
            context.run_migrations()
        return
    connection = context.config.attributes.get("connection")
    if isinstance(connection, Connection):
        migrate_connection(connection)
        return
    engine = create_database_engine(Settings())
    try:
        with engine.begin() as owned_connection:
            migrate_connection(owned_connection)
    finally:
        engine.dispose()


run_migrations()
