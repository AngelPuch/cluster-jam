"""Verify operator setup, pending output, and sanitized failures."""

import json
import sys
from pathlib import Path

import pytest
from pydantic import SecretStr
from sqlalchemy import Engine

from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.storage import manage
from personalization.infrastructure.storage.supabase_storage import (
    SupabaseStorage,
)
from test.files.fakes import TEST_KEY, MemoryFileRepository, StorageServer


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    password = tmp_path / "password"
    password.write_text("test-only-password", encoding="utf-8")
    secret = tmp_path / "storage-key"
    secret.write_text(TEST_KEY, encoding="utf-8")
    return Settings.model_validate(
        {
            "APP_ENV": "test",
            "DB_PASSWORD_FILE": password,
            "SUPABASE_ISSUER": "https://supabase.example.test/auth/v1",
            "SUPABASE_JWKS_URL": "https://supabase.example.test/auth/v1/.well-known/jwks.json",
            "STORAGE_ENABLED": True,
            "WORKER_HEARTBEAT_FILE": tmp_path / "worker-health.json",
            "SUPABASE_STORAGE_KEY_FILE": secret,
        }
    )


@pytest.mark.parametrize("action", ["create", "check", "pending"])
def test_storage_operator_commands_are_structured_and_private(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    action: str,
) -> None:
    server = StorageServer()
    server.exists = action != "create"

    def configured_settings() -> Settings:
        return settings

    def storage(
        project_url: str, bucket: str, key: SecretStr
    ) -> SupabaseStorage:
        assert key.get_secret_value() == TEST_KEY
        return server.adapter()

    def repository(engine: Engine) -> MemoryFileRepository:
        return MemoryFileRepository()

    monkeypatch.setattr(manage, "Settings", configured_settings)
    monkeypatch.setattr(manage, "SupabaseStorage", storage)
    monkeypatch.setattr(manage, "SqlAlchemyFileRepository", repository)
    monkeypatch.setattr(sys, "argv", ["manage", action])
    assert manage.main() == 0
    output = capsys.readouterr()
    assert len(output.out.splitlines()) == 1
    event = json.loads(output.out)
    assert event["code"] == (
        "PENDING_FILES" if action == "pending" else "STORAGE_READY"
    )
    if action == "pending":
        assert event["file_ids"] == []
    assert TEST_KEY not in output.out + output.err


def test_storage_command_failures_do_not_print_remote_details(
    settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    server = StorageServer()
    server.status_override = 401

    def configured_settings() -> Settings:
        return settings

    def storage(
        project_url: str, bucket: str, key: SecretStr
    ) -> SupabaseStorage:
        return server.adapter()

    monkeypatch.setattr(manage, "Settings", configured_settings)
    monkeypatch.setattr(manage, "SupabaseStorage", storage)
    monkeypatch.setattr(sys, "argv", ["manage", "check"])
    assert manage.main() == 1
    output = capsys.readouterr()
    assert json.loads(output.out)["code"] == "STORAGE_UNAVAILABLE"
    assert "private-provider-detail" not in output.out + output.err
    assert TEST_KEY not in output.out + output.err


def test_storage_command_invalid_configuration_is_redacted(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def invalid_settings() -> Settings:
        return Settings.model_validate({"APP_ENV": "private-input"})

    monkeypatch.setattr(manage, "Settings", invalid_settings)
    monkeypatch.setattr(sys, "argv", ["manage", "check"])
    assert manage.main() == 2
    output = capsys.readouterr()
    assert json.loads(output.out)["code"] == "CONFIGURATION_INVALID"
    assert "private-input" not in output.out + output.err
