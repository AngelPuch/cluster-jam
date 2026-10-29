"""Check only image-worker liveness, independently of PostgreSQL."""

import os
from pathlib import Path

from personalization.interfaces.workers.heartbeat import (
    default_heartbeat_file,
    heartbeat_is_healthy,
)


def main() -> int:
    try:
        poll = int(os.environ.get("WORKER_POLL_SECONDS", "10"))
        configured = int(
            os.environ.get("WORKER_HEARTBEAT_MAX_AGE_SECONDS", "180")
        )
        if not 1 <= poll <= 300 or not 30 <= configured <= 3600:
            return 1
        path = Path(
            os.environ.get(
                "WORKER_HEARTBEAT_FILE", str(default_heartbeat_file())
            )
        )
        return (
            0 if heartbeat_is_healthy(path, max(configured, poll * 3)) else 1
        )
    except ValueError, OSError:
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
