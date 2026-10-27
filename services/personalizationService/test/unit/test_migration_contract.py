"""Validate offline migration delivery without database credentials."""

from io import StringIO

from alembic import command
from alembic.script import ScriptDirectory

from personalization.infrastructure.database.migration_config import (
    CURRENT_REVISION,
    migration_config,
)
from personalization.infrastructure.database.models import Base, FileModel


def test_packaged_migrations_have_one_expected_head() -> None:
    scripts = ScriptDirectory.from_config(migration_config())
    assert scripts.get_heads() == [CURRENT_REVISION]


def test_offline_upgrade_and_rollback_do_not_need_credentials() -> None:
    upgrade = StringIO()
    command.upgrade(migration_config(upgrade), "head", sql=True)
    sql = upgrade.getvalue()
    assert "CREATE TABLE app.archivo" in sql
    assert "CREATE TABLE app.auditoria_local" in sql
    assert "FOREIGN KEY(tamano_id, zona_id)" in sql
    assert "CREATE TABLE public." not in sql
    assert "CREATE DATABASE" not in sql
    rollback = StringIO()
    command.downgrade(
        migration_config(rollback), CURRENT_REVISION + ":base", sql=True
    )
    assert "DROP TABLE app.archivo" in rollback.getvalue()


def test_external_references_never_become_foreign_keys() -> None:
    for table in Base.metadata.tables.values():
        assert table.schema == "app"
        for constraint in table.foreign_key_constraints:
            assert constraint.referred_table.schema == "app"
            assert constraint.referred_table.metadata is Base.metadata
            assert constraint.ondelete is None


def test_english_attributes_map_to_spanish_sql_columns() -> None:
    column = FileModel.owner_id.property.columns[0]
    assert column.name == "propietario_ref"
    assert FileModel.__table__.c.bytes.type.__class__.__name__ == "BigInteger"
