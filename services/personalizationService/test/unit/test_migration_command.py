"""Check migration command exit codes and credential privacy."""

import json
import sys
from pathlib import Path

import pytest
from alembic.util.exc import CommandError
from sqlalchemy import Engine
from sqlalchemy.exc import SQLAlchemyError

from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database import migrate
from personalization.infrastructure.database.migrate import MigrationAction


@pytest.fixture
def migration_settings(tmp_path: Path) -> Settings:
    secret = tmp_path / "password"
    secret.write_text("test-private-password", encoding="utf-8")
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "DB_PASSWORD_FILE": secret,
            "SUPABASE_ISSUER": "https://supabase.example.test/auth/v1",
            "SUPABASE_JWKS_URL": "https://supabase.example.test/auth/v1/.well-known/jwks.json",
        }
    )


@pytest.mark.parametrize("action", ["upgrade", "check", "current"])
def test_successful_migration_command_reports_one_event(
    migration_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    def configured_settings() -> Settings:
        return migration_settings

    def migration(
        engine: Engine, settings: Settings, selected: MigrationAction
    ) -> str:
        assert settings is migration_settings
        assert selected == action
        return ""

    monkeypatch.setattr(migrate, "Settings", configured_settings)
    monkeypatch.setattr(migrate, "run_migrations", migration)
    monkeypatch.setattr(sys, "argv", ["migrate", action])
    assert migrate.main() == 0
    output = capsys.readouterr()
    assert output.err == ""
    assert len(output.out.splitlines()) == 1
    assert json.loads(output.out)["code"] == "MIGRATION_SUCCEEDED"
    assert "test-private-password" not in output.out


@pytest.mark.parametrize(
    "failure",
    [
        SQLAlchemyError("test-private-password"),
        CommandError("private-schema-detail"),
        RuntimeError("private-owner-detail"),
    ],
)
def test_migration_failure_hides_provider_details(
    migration_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    failure: Exception,
) -> None:
    def configured_settings() -> Settings:
        return migration_settings

    def migration(
        engine: Engine, settings: Settings, action: MigrationAction
    ) -> str:
        raise failure

    monkeypatch.setattr(migrate, "Settings", configured_settings)
    monkeypatch.setattr(migrate, "run_migrations", migration)
    monkeypatch.setattr(sys, "argv", ["migrate", "upgrade"])
    assert migrate.main() == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["code"] == "MIGRATION_FAILED"
    assert "private" not in output.out + output.err


def test_migration_rejects_invalid_configuration_before_connecting(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def invalid_settings() -> Settings:
        return Settings.model_validate({"APP_ENV": "private-input"})

    monkeypatch.setattr(migrate, "Settings", invalid_settings)
    monkeypatch.setattr(sys, "argv", ["migrate", "upgrade"])
    assert migrate.main() == 2
    output = capsys.readouterr()
    assert json.loads(output.out)["code"] == "CONFIGURATION_INVALID"
    assert "private-input" not in output.out + output.err
