"""Track image-worker progress without contacting dependencies."""

import json
import math
import os
import tempfile
import time
from pathlib import Path


def default_heartbeat_file() -> Path:
    return (
        Path(os.environ.get("TMPDIR") or os.environ.get("TEMP") or "/tmp")
        / "personalization-images-health.json"
    )


def heartbeat_is_healthy(path: Path, max_age: int) -> bool:
    try:
        if path.is_symlink() or not 30 <= max_age <= 3600:
            return False
        with path.open("rb") as stream:
            content = stream.read(1025)
        if len(content) > 1024:
            return False
        payload: object = json.loads(content)
        if not isinstance(payload, dict) or payload.get("status") != "running":
            return False
        timestamp = payload.get("updated_at")
        if isinstance(timestamp, bool) or not isinstance(
            timestamp, int | float
        ):
            return False
        age = time.time() - timestamp
        return math.isfinite(age) and -5 <= age <= max_age
    except OSError, ValueError, TypeError:
        return False


class WorkerHeartbeat:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._last_write = float("-inf")
        self._owned = False

    def pulse(self, *, force: bool = False) -> None:
        now = time.monotonic()
        if not force and now - self._last_write < 5:
            return
        descriptor, temporary = tempfile.mkstemp(dir=self._path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
                json.dump(
                    {"status": "running", "updated_at": time.time()}, stream
                )
            os.replace(temporary, self._path)
            self._owned = True
            self._last_write = now
        finally:
            Path(temporary).unlink(missing_ok=True)

    def close(self) -> None:
        if self._owned:
            self._path.unlink(missing_ok=True)
