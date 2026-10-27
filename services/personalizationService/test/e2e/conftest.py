"""Provide deterministic HTTP application dependencies."""

import logging
from collections.abc import Iterator
from io import StringIO
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import personalization.bootstrap as bootstrap
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.observability.logging_config import (
    configure_logging,
)


class FakeReadinessPort:
    """Control availability without external infrastructure."""

    def __init__(self) -> None:
        self.ready = True
        self.calls = 0

    def is_ready(self) -> bool:
        self.calls += 1
        return self.ready


@pytest.fixture
def http_settings(tmp_path: Path) -> Settings:
    password_file = tmp_path / "test-secret"
    password_file.write_text("test-only-password", encoding="utf-8")
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "DB_PASSWORD_FILE": password_file,
            "SUPABASE_ISSUER": "https://supabase.example.test/auth/v1",
            "SUPABASE_JWKS_URL": "https://supabase.example.test/auth/v1/.well-known/jwks.json",
        }
    )


@pytest.fixture
def readiness_port() -> FakeReadinessPort:
    return FakeReadinessPort()


@pytest.fixture
def http_logs() -> StringIO:
    return StringIO()


@pytest.fixture
def client(
    http_settings: Settings,
    readiness_port: FakeReadinessPort,
    http_logs: StringIO,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    def configure_test_logging(*, environment: str, log_level: str) -> None:
        configure_logging(environment=environment, log_level=log_level)
        for handler in logging.getLogger("personalization").handlers:
            if isinstance(handler, logging.StreamHandler):
                handler.setStream(http_logs)

    monkeypatch.setattr(bootstrap, "configure_logging", configure_test_logging)
    with TestClient(
        bootstrap.create_app(http_settings, readiness_port)
    ) as test_client:
        yield test_client
