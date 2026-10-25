"""Validate process configuration and load its database secret."""

from pathlib import Path
from typing import Literal, Self

from pydantic import (
    Field,
    PrivateAttr,
    SecretStr,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    """Read configuration without exposing a database password."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
    )

    app_env: Literal["development", "test", "production"] = Field(
        validation_alias="APP_ENV"
    )
    http_port: int = Field(
        default=8080, gt=0, le=65535, validation_alias="HTTP_PORT"
    )
    grpc_port: int = Field(
        default=50051, gt=0, le=65535, validation_alias="GRPC_PORT"
    )
    log_level: Literal["DEBUG", "INFO", "WARN", "ERROR"] = Field(
        default="INFO", validation_alias="LOG_LEVEL"
    )
    db_host: str = Field(
        default="db-personalizacion",
        min_length=1,
        validation_alias="DB_HOST",
    )
    db_port: int = Field(
        default=5432, gt=0, le=65535, validation_alias="DB_PORT"
    )
    db_name: Literal["personalizacion_db"] = Field(
        default="personalizacion_db", validation_alias="DB_NAME"
    )
    db_user: Literal["app_personalizacion"] = Field(
        default="app_personalizacion", validation_alias="DB_USER"
    )
    db_schema: Literal["app"] = Field(
        default="app", validation_alias="DB_SCHEMA"
    )
    db_connect_timeout_seconds: int = Field(
        default=5,
        ge=1,
        le=30,
        validation_alias="DB_CONNECT_TIMEOUT_SECONDS",
    )
    db_password_file: Path = Field(validation_alias="DB_PASSWORD_FILE")
    _database_password: SecretStr = PrivateAttr()

    @model_validator(mode="after")
    def load_database_password(self) -> Self:
        """Load a mounted secret without echoing invalid contents."""
        try:
            password = self.db_password_file.read_text(
                encoding="utf-8"
            ).rstrip("\r\n")
        except OSError, UnicodeError:
            raise ValueError(
                "DB_PASSWORD_FILE must be a readable UTF-8 file"
            ) from None
        if not password or password.isspace():
            raise ValueError("DB_PASSWORD_FILE must not be empty")
        self._database_password = SecretStr(password)
        return self

    @property
    def database_url(self) -> URL:
        """Build an escaped URL whose default string hides secrets."""
        return URL.create(
            "postgresql+psycopg",
            username=self.db_user,
            password=self._database_password.get_secret_value(),
            host=self.db_host,
            port=self.db_port,
            database=self.db_name,
        )
