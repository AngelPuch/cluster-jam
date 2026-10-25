"""Describe the dependency required to accept service traffic."""

from typing import Protocol


class ReadinessPort(Protocol):
    """Check the service's own required infrastructure."""

    def is_ready(self) -> bool:
        """Return whether the service can serve its operations."""
        ...
