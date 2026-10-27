"""Read binary streams while preserving caller ownership."""

from typing import Protocol


class ImageSourcePort(Protocol):
    """Read a bounded chunk from the caller-owned upload stream."""

    def read(self, size: int = -1) -> bytes:
        """Read up to size bytes; empty bytes mark end of input."""
        ...
