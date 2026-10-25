"""Reject invalid process configuration before startup."""

from pathlib import Path

import pytest
from pydantic import ValidationError

from personalization.infrastructure.config.settings import Settings


@pytest.fixture(autouse=True)
def isolate_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent machine-specific configuration from changing tests."""
    for name in ("APP_ENV", "HTTP_PORT", "GRPC_PORT", "LOG_LEVEL"):
        monkeypatch.delenv(name, raising=False)


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
