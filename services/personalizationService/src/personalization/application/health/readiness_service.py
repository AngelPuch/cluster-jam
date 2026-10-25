"""Evaluate readiness independently of HTTP and persistence."""

from personalization.application.errors.service_not_ready_error import (
    ServiceNotReadyError,
)
from personalization.application.ports.readiness_port import ReadinessPort


class ReadinessService:
    """Require access to the service's own infrastructure."""

    def __init__(self, readiness: ReadinessPort) -> None:
        self._readiness = readiness

    def ensure_ready(self) -> None:
        """Fail with a domain error when this instance cannot serve."""
        if not self._readiness.is_ready():
            raise ServiceNotReadyError()
