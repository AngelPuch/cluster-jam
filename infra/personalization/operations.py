"""Back up, rehearse recovery, and inspect service health."""

import argparse
import time
from datetime import UTC, datetime
from pathlib import Path

from operation_tools.bundles import (
    create_backup,
    file_digest,
    restore_objects,
    restore_snapshot,
    verify_bundle,
)
from operation_tools.runtime import (
    ComposeContext,
    OperationError,
    configure_logging,
)
from operation_tools.status import inspect_status


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deployment", action="store_true")
    commands = parser.add_subparsers(dest="action", required=True)
    backup = commands.add_parser("backup")
    backup.add_argument("--output", type=Path, required=True)
    for name in ("verify", "restore-check", "restore", "restore-objects"):
        command = commands.add_parser(name)
        command.add_argument("--backup", type=Path, required=True)
        if name == "restore":
            command.add_argument("--workspace", type=Path, required=True)
    status = commands.add_parser("status")
    status.add_argument("--require-worker", action="store_true")
    status.add_argument("--require-rpc", action="store_true")
    status.add_argument("--require-https", action="store_true")
    status.add_argument("--backup", type=Path)
    status.add_argument("--max-backup-age-seconds", type=int)
    arguments = parser.parse_args()
    logger = configure_logging(
        "production" if arguments.deployment else "development"
    )
    started = time.monotonic()
    try:
        extra: dict[str, object] = {
            "event": f"operations.{arguments.action}.completed"
        }
        if arguments.action == "status":
            context = ComposeContext(deployment=arguments.deployment)
            healthy, checks = inspect_status(
                context,
                require_worker=arguments.require_worker,
                require_rpc=arguments.require_rpc,
                require_https=arguments.require_https,
            )
            extra["checks"] = checks
            if (
                arguments.max_backup_age_seconds is not None
                and arguments.max_backup_age_seconds <= 0
            ):
                raise OperationError("INVALID_BACKUP_AGE_LIMIT")
            if arguments.backup is not None:
                bundle = verify_bundle(arguments.backup)
                age = (
                    datetime.now(UTC)
                    - datetime.fromisoformat(bundle.metadata["created_at"])
                ).total_seconds()
                extra["backup_age_seconds"] = max(0, round(age))
                checks["backup_integrity"] = "ok"
                if (
                    arguments.max_backup_age_seconds is not None
                    and age > arguments.max_backup_age_seconds
                ):
                    checks["backup_age"] = "failed"
                    healthy = False
            elif arguments.max_backup_age_seconds is not None:
                raise OperationError("BACKUP_REQUIRED_FOR_AGE_CHECK")
            extra["code"] = (
                "OPERATIONS_HEALTHY" if healthy else "OPERATIONS_UNHEALTHY"
            )
            logger.log(
                20 if healthy else 40,
                "Operational health inspection completed",
                extra=extra,
            )
            return 0 if healthy else 1
        if arguments.action == "backup":
            context = ComposeContext(deployment=arguments.deployment)
            bundle = create_backup(context, arguments.output)
        else:
            bundle = verify_bundle(arguments.backup)
        if arguments.action in {"restore-check", "restore"}:
            extra["recovery_project"] = restore_snapshot(
                bundle,
                arguments.workspace if arguments.action == "restore" else None,
            )
        if arguments.action == "restore-objects":
            extra["object_count"] = restore_objects(
                bundle, ComposeContext(deployment=arguments.deployment)
            )
        else:
            extra["object_count"] = len(bundle.available)
        extra.update(
            backup_id=bundle.metadata["backup_id"],
            pending_files=bundle.metadata["pending_files"],
            manifest_sha256=file_digest(bundle.directory / "manifest.json"),
            duration_ms=round((time.monotonic() - started) * 1000),
            code="OPERATION_SUCCEEDED",
        )
        logger.info("Operational command completed", extra=extra)
        return 0
    except OperationError as error:
        code = error.code
    except (OSError, ValueError, TypeError, KeyError):
        code = "INVALID_OPERATION_INPUT"
    logger.error(
        "Operational command failed",
        extra={
            "event": "operations.failed",
            "code": code,
            "duration_ms": round((time.monotonic() - started) * 1000),
        },
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
