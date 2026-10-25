"""Reject invalid process configuration before startup."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from personalization.infrastructure.config.settings import Settings


@pytest.fixture(autouse=True)
def isolate_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Prevent machine-specific configuration from changing tests."""
    for name in (
        "APP_ENV",
        "HTTP_HOST",
        "HTTP_PORT",
        "GRPC_PORT",
        "LOG_LEVEL",
        "DB_HOST",
        "DB_PORT",
        "DB_NAME",
        "DB_USER",
        "DB_SCHEMA",
        "DB_CONNECT_TIMEOUT_SECONDS",
        "DB_PASSWORD_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    password_file = tmp_path / "database-password"
    password_file.write_text("test-only-password\n", encoding="utf-8")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(password_file))


def test_environment_is_required() -> None:
    with pytest.raises(ValidationError, match="APP_ENV"):
        Settings(_env_file=None)


def test_invalid_environment_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "staging")

    with pytest.raises(ValidationError, match="APP_ENV"):
        Settings(_env_file=None)


@pytest.mark.parametrize("variable", ["HTTP_PORT", "GRPC_PORT"])
@pytest.mark.parametrize("value", ["0", "-1", "65536", "invalid"])
def test_invalid_port_is_rejected(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValidationError, match=variable):
        Settings(_env_file=None)


def test_invalid_log_level_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("LOG_LEVEL", "TRACE")

    with pytest.raises(ValidationError, match="LOG_LEVEL"):
        Settings(_env_file=None)


def test_environment_overrides_local_file(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text(
        "APP_ENV=development\nHTTP_PORT=8080\n", encoding="utf-8"
    )
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("HTTP_PORT", "8081")

    settings = Settings(_env_file=env_file)

    assert settings.app_env == "production"
    assert settings.http_port == 8081


@pytest.mark.parametrize("value", ["0", "-1", "65536", "invalid"])
def test_invalid_database_port_is_rejected(
    monkeypatch: pytest.MonkeyPatch, value: str
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PORT", value)
    with pytest.raises(ValidationError, match="DB_PORT"):
        Settings(_env_file=None)


def test_database_password_file_is_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv("DB_PASSWORD_FILE")
    with pytest.raises(ValidationError, match="DB_PASSWORD_FILE"):
        Settings(_env_file=None)


def test_missing_secret_file_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(tmp_path / "missing"))
    with pytest.raises(ValidationError, match="readable UTF-8 file"):
        Settings(_env_file=None)


@pytest.mark.parametrize("value", ["", "\n", "  \n"])
def test_empty_database_secret_is_rejected(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, value: str
) -> None:
    password_file = tmp_path / "empty-secret"
    password_file.write_text(value, encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(password_file))
    with pytest.raises(ValidationError, match="must not be empty"):
        Settings(_env_file=None)


def test_secret_is_escaped_and_hidden(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    password = "test-only:p@ss/word?#%"
    password_file = tmp_path / "special-secret"
    password_file.write_text(password + "\n", encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(password_file))
    settings = Settings(_env_file=None)
    assert settings.database_url.password == password
    assert password not in repr(settings)
    assert password not in settings.model_dump_json()
    assert password not in str(settings.database_url)
