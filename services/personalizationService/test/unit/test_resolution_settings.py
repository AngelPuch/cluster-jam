"""Leave the quality threshold unset until the team chooses it."""

import pytest
from pydantic import ValidationError

from personalization.infrastructure.config.settings import Settings
from test.e2e.conftest import http_settings as http_settings


@pytest.mark.parametrize(
    "value,expected",
    [(None, None), ("", None), ("150", 150), ("300", 300), ("2400", 2400)],
)
def test_optional_dpi_is_explicit_not_a_hidden_default(
    http_settings: Settings, value: object, expected: int | None
) -> None:
    # Validate configuration using public aliases.
    data = {
        "APP_ENV": "test",
        "DB_PASSWORD_FILE": http_settings.db_password_file,
        "SUPABASE_ISSUER": str(http_settings.supabase_issuer),
        "SUPABASE_JWKS_URL": str(http_settings.supabase_jwks_url),
        "MIN_PRINT_DPI": value,
    }
    assert Settings.model_validate(data).min_print_dpi == expected


@pytest.mark.parametrize("value", [0, -1, 2401, "NaN", "150.5", True])
def test_invalid_dpi_cannot_start(
    http_settings: Settings, value: object
) -> None:
    with pytest.raises(ValidationError):
        Settings.model_validate(
            {
                "APP_ENV": "test",
                "DB_PASSWORD_FILE": http_settings.db_password_file,
                "SUPABASE_ISSUER": str(http_settings.supabase_issuer),
                "SUPABASE_JWKS_URL": str(http_settings.supabase_jwks_url),
                "MIN_PRINT_DPI": value,
            }
        )
