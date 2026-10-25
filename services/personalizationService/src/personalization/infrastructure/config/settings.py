"""Validate process configuration before service startup."""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Read the environment and an optional local development file."""

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
