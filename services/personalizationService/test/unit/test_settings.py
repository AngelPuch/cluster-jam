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
        "STORAGE_ENABLED",
        "SUPABASE_STORAGE_BUCKET",
        "SUPABASE_STORAGE_KEY_FILE",
        "DOWNLOAD_URL_TTL_SECONDS",
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
        "IMAGE_MAX_WIDTH_PX",
        "IMAGE_MAX_HEIGHT_PX",
        "IMAGE_MAX_PIXELS",
        "SUPABASE_ISSUER",
        "SUPABASE_JWKS_URL",
    ):
        monkeypatch.delenv(name, raising=False)
    password_file = tmp_path / "database-password"
    password_file.write_text("test-only-password\n", encoding="utf-8")
    monkeypatch.setenv("DB_PASSWORD_FILE", str(password_file))
    monkeypatch.setenv(
        "SUPABASE_ISSUER", "https://supabase.example.test/auth/v1"
    )
    monkeypatch.setenv(
        "SUPABASE_JWKS_URL",
        "https://supabase.example.test/auth/v1/.well-known/jwks.json",
    )


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


@pytest.mark.parametrize("variable", ["SUPABASE_ISSUER", "SUPABASE_JWKS_URL"])
def test_public_identity_configuration_is_required(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.delenv(variable)
    with pytest.raises(ValidationError, match=variable):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("SUPABASE_ISSUER", "http://supabase.example.test/auth/v1"),
        ("SUPABASE_ISSUER", "https://supabase.example.test/auth/v1/"),
        (
            "SUPABASE_ISSUER",
            "https://name:secret@supabase.example.test/auth/v1",
        ),
        ("SUPABASE_ISSUER", "https://supabase.example.test/auth/v1?query=yes"),
        (
            "SUPABASE_JWKS_URL",
            "https://other.example/auth/v1/.well-known/jwks.json",
        ),
        ("SUPABASE_JWKS_URL", "https://supabase.example.test/unexpected"),
        (
            "SUPABASE_JWKS_URL",
            "https://supabase.example.test/auth/v1#fragment",
        ),
    ],
)
def test_identity_urls_reject_unsafe_or_mismatched_values(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize(
    "variable",
    [
        "IMAGE_MAX_WIDTH_PX",
        "IMAGE_MAX_HEIGHT_PX",
        "IMAGE_MAX_PIXELS",
    ],
)
@pytest.mark.parametrize("value", ["0", "-1", "invalid", "16000001"])
def test_image_resource_limits_are_positive_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
    variable: str,
    value: str,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv(variable, value)
    with pytest.raises(ValidationError, match=variable):
        Settings(_env_file=None)


def test_image_resource_limits_can_be_tightened(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("IMAGE_MAX_WIDTH_PX", "1024")
    monkeypatch.setenv("IMAGE_MAX_HEIGHT_PX", "768")
    monkeypatch.setenv("IMAGE_MAX_PIXELS", "500000")
    policy = Settings(_env_file=None).image_policy
    assert policy.max_width_px == 1024
    assert policy.max_height_px == 768
    assert policy.max_pixels == 500000


def test_storage_is_disabled_until_explicitly_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    assert Settings(_env_file=None).storage_enabled is False


@pytest.mark.parametrize(
    "key", ["", "sb_publishable_public", "eyJ.legacy.key", "sb_secret_short"]
)
def test_storage_rejects_non_backend_keys(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    key: str,
) -> None:
    secret = tmp_path / "storage-key"
    secret.write_text(key, encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("STORAGE_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_STORAGE_KEY_FILE", str(secret))
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_storage_key_file_is_required_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("STORAGE_ENABLED", "true")
    with pytest.raises(ValidationError, match="SUPABASE_STORAGE_KEY_FILE"):
        Settings(_env_file=None)


def test_valid_storage_key_is_hidden_in_settings_repr(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    value = "sb_secret_" + "test-only-material" * 2
    secret = tmp_path / "storage-key"
    secret.write_text(value, encoding="utf-8")
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("STORAGE_ENABLED", "true")
    monkeypatch.setenv("SUPABASE_STORAGE_KEY_FILE", str(secret))
    settings = Settings(_env_file=None)
    assert value not in repr(settings)
    assert settings.storage_key.get_secret_value() == value
    assert settings.storage_project_url == "https://supabase.example.test"


@pytest.mark.parametrize(
    "bucket", ["../private", "public/bucket", "name with spaces", "UPPERCASE"]
)
def test_storage_bucket_is_one_safe_path_segment(
    monkeypatch: pytest.MonkeyPatch,
    bucket: str,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("SUPABASE_STORAGE_BUCKET", bucket)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


@pytest.mark.parametrize("ttl", ["0", "301", "invalid"])
def test_download_url_ttl_is_short_and_bounded(
    monkeypatch: pytest.MonkeyPatch,
    ttl: str,
) -> None:
    monkeypatch.setenv("APP_ENV", "test")
    monkeypatch.setenv("DOWNLOAD_URL_TTL_SECONDS", ttl)
    with pytest.raises(ValidationError):
        Settings(_env_file=None)
