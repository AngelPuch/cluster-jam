"""Run the REST server with validated configuration."""

import logging
import os

import uvicorn
from pydantic import ValidationError

from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.observability.logging_config import (
    configure_logging,
)


def main() -> None:
    """Run Uvicorn with signal handling and JSON logging."""
    try:
        settings = Settings()
    except ValidationError:
        environment = os.environ.get("APP_ENV", "unknown")
        if environment not in {"development", "test", "production"}:
            environment = "unknown"
        configure_logging(environment=environment, log_level="INFO")
        logging.getLogger("personalization.lifecycle").error(
            "Service configuration is invalid",
            extra={
                "event": "service.configuration.invalid",
                "code": "CONFIGURATION_INVALID",
            },
        )
        raise SystemExit(2) from None
    configure_logging(
        environment=settings.app_env, log_level=settings.log_level
    )
    uvicorn.run(
        "personalization.bootstrap:create_app",
        factory=True,
        host=settings.http_host,
        port=settings.http_port,
        log_config=None,
        access_log=False,
        server_header=False,
        proxy_headers=False,
    )


if __name__ == "__main__":
    main()
