"""Write one sanitized JSON record per event to standard output."""

import json
import logging
import socket
import sys
from datetime import UTC, datetime
from importlib.metadata import version

from opentelemetry import trace

ALLOWED_LOG_FIELDS = (
    "http_method",
    "http_route",
    "status_code",
    "duration_ms",
    "request_id",
    "error_type",
    "code",
)


class JsonLogFormatter(logging.Formatter):
    """Serialize only approved metadata and the active span context."""

    def __init__(self, environment: str) -> None:
        super().__init__()
        self._environment = environment
        self._instance_id = socket.gethostname()
        self._service_version = version("cluster-jam-personalization-service")

    def format(self, record: logging.LogRecord) -> str:
        """Exclude sensitive data and arbitrary log extras."""
        context = trace.get_current_span().get_span_context()
        own_event = record.name.startswith("personalization")
        payload: dict[str, object] = {
            "timestamp": datetime.fromtimestamp(record.created, UTC)
            .isoformat()
            .replace("+00:00", "Z"),
            "level": "WARN"
            if record.levelno == logging.WARNING
            else record.levelname,
            "service_name": "personalization",
            "service_version": self._service_version,
            "environment": self._environment,
            "instance_id": self._instance_id,
            "event": record.__dict__.get("event", "server.lifecycle"),
            "message": record.getMessage()
            if own_event
            else "HTTP server lifecycle event",
            "trace_id": f"{context.trace_id:032x}"
            if context.is_valid
            else None,
            "span_id": f"{context.span_id:016x}" if context.is_valid else None,
        }
        for field in ALLOWED_LOG_FIELDS:
            if field in record.__dict__:
                payload[field] = record.__dict__[field]
        return json.dumps(payload, ensure_ascii=True)


def configure_logging(*, environment: str, log_level: str) -> None:
    """Configure service loggers and the HTTP server."""
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonLogFormatter(environment))
    level = logging.WARNING if log_level == "WARN" else log_level
    logger = logging.getLogger("personalization")
    logger.handlers.clear()
    logger.addHandler(handler)
    logger.setLevel(level)
    logger.propagate = False
    for name in ("personalization.http", "personalization.lifecycle"):
        child = logging.getLogger(name)
        child.handlers.clear()
        child.setLevel(logging.NOTSET)
        child.propagate = True
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        server_logger = logging.getLogger(name)
        server_logger.handlers.clear()
        server_logger.addHandler(handler)
        server_logger.setLevel(level)
        server_logger.propagate = False
