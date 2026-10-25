"""Verify technical exit codes and sanitized database diagnostics."""

import json
from pathlib import Path

import pytest
from sqlalchemy.exc import SQLAlchemyError

from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database import check


@pytest.fixture
def configured_settings(tmp_path: Path) -> Settings:
    secret_file = tmp_path / "database-secret"
    secret_file.write_text("test-only-password", encoding="utf-8")
    return Settings.model_validate(
        {"APP_ENV": "test", "DB_PASSWORD_FILE": secret_file}
    )


@pytest.mark.parametrize("accessible", [True, False])
def test_database_access_controls_exit_status(
    configured_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    accessible: bool,
) -> None:
    def fake_settings() -> Settings:
        return configured_settings

    def fake_check(settings: Settings) -> bool:
        return accessible

    monkeypatch.setattr(check, "Settings", fake_settings)
    monkeypatch.setattr(check, "check_database", fake_check)

    assert check.main() == (0 if accessible else 1)
    output = capsys.readouterr().out
    event = json.loads(output)
    assert len(output.splitlines()) == 1
    assert event["code"] == (
        "DATABASE_READY" if accessible else "DATABASE_CONFIGURATION_MISMATCH"
    )
    assert "test-only-password" not in output


def test_database_failure_hides_connection_details(
    configured_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def fake_settings() -> Settings:
        return configured_settings

    def failed_check(settings: Settings) -> bool:
        raise SQLAlchemyError("password=test-only-password")

    monkeypatch.setattr(check, "Settings", fake_settings)
    monkeypatch.setattr(check, "check_database", failed_check)

    assert check.main() == 1
    output = capsys.readouterr().out
    assert json.loads(output)["code"] == "DATABASE_UNAVAILABLE"
    assert "test-only-password" not in output


def test_configuration_failure_hides_invalid_input(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def invalid_settings() -> Settings:
        return Settings.model_validate({"APP_ENV": "private-input"})

    monkeypatch.setattr(check, "Settings", invalid_settings)

    assert check.main() == 1
    output = capsys.readouterr().out
    assert json.loads(output)["code"] == "CONFIGURATION_INVALID"
    assert "private-input" not in output
