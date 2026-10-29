"""Verify deployment ordering and failure guards on Linux."""

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8", newline="\n")


def verify_deployment_commands() -> None:
    # Keep private fixture files owned by the POSIX runner.
    if sys.platform == "win32":
        container_user = "0:0"
    else:
        container_user = f"{os.getuid()}:{os.getgid()}"
    image = "cluster-jam/personalization:" + os.environ.get(
        "PERSONALIZATION_IMAGE_TAG", "0.1.0-local"
    )
    with tempfile.TemporaryDirectory(
        prefix="personalization-deploy-check-"
    ) as tmp:
        directory = Path(tmp)
        for scenario in (
            "success",
            "migration-failure",
            "storage-failure",
            "dirty",
        ):
            root = directory / scenario
            scripts = root / "infra" / "deploy"
            scripts.mkdir(parents=True)
            for name in (
                "deploy.sh",
                "deploy-personalization.sh",
                "compose.sh",
            ):
                shutil.copyfile(
                    ROOT / "infra" / "deploy" / name, scripts / name
                )
            for name in (
                "infra/personalization/deployment.env",
                "infra/shared/.env",
                "infra/shared/.pki/ca.crt",
                "infra/shared/.pki/personalization-grpc.crt",
                "infra/shared/.pki/personalization-grpc.key",
            ):
                write_file(root / name, "fixture\n")
            write_file(
                root / "bin" / "git",
                """#!/bin/sh
case "$1" in
    status) if [ "$DEPLOY_SCENARIO" = dirty ]; then echo ' M fixture'; fi ;;
    rev-parse) printf '%040d\\n' 1 ;;
    *) exit 2 ;;
esac
""",
            )
            write_file(
                root / "bin" / "python3",
                """#!/bin/sh
if [ "$1" = -c ]; then
    echo 0.1.0
else
    echo provision-local >> /work/commands.log
fi
""",
            )
            write_file(
                root / "bin" / "docker",
                """#!/bin/sh
printf '%s\\n' "$*" >> /work/commands.log
case "$*" in
    'compose --project-name cluster-jam-personalization '*)
        test -z "${SUPABASE_ISSUER+x}" || exit 17
        test -z "${PERSONALIZATION_IMAGE_TAG+x}" || exit 17
        test -z "${WORKER_BATCH_SIZE+x}" || exit 17
        ;;
esac
case "$*" in
    *'run --rm --no-deps --pull never personalization-migrate'*)
        test "$DEPLOY_SCENARIO" != migration-failure || exit 9 ;;
    *'run --rm --no-deps --pull never personalization-storage check'*)
        test "$DEPLOY_SCENARIO" != storage-failure || exit 8 ;;
esac
exit 0
""",
            )
            for file in (root / "bin").iterdir():
                file.chmod(0o755)
            # Mount only synthetic fixtures in this container.
            command = (
                "export PATH=/work/bin:$PATH; "
                "export SUPABASE_ISSUER=invalid-override; "
                "export PERSONALIZATION_IMAGE_TAG=invalid-override; "
                "export WORKER_BATCH_SIZE=invalid-override; "
                "cd /work; bash infra/deploy/deploy.sh personalization"
            )
            result = subprocess.run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--user",
                    container_user,
                    "--mount",
                    f"type=bind,source={root},target=/work",
                    "--env",
                    f"DEPLOY_SCENARIO={scenario}",
                    "--entrypoint",
                    "bash",
                    image,
                    "-c",
                    command,
                ],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            expected = {
                "success": 0,
                "migration-failure": 9,
                "storage-failure": 8,
                "dirty": 1,
            }[scenario]
            if result.returncode != expected:
                raise RuntimeError(f"Deployment guard failed: {scenario}")
            log = root / "commands.log"
            lines = (
                log.read_text(encoding="utf-8").splitlines()
                if log.exists()
                else []
            )
            if scenario == "dirty":
                if lines:
                    raise RuntimeError("Dirty deployment reached Docker")
                continue
            migrations = [
                i
                for i, line in enumerate(lines)
                if "run --rm --no-deps --pull never personalization-migrate"
                in line
            ]
            storage = [
                i
                for i, line in enumerate(lines)
                if "personalization-storage check" in line
                and "run --rm" in line
            ]
            launches = [
                i
                for i, line in enumerate(lines)
                if "personalization-worker personalization-grpc" in line
                and "up -d" in line
            ]
            gateways = [
                i
                for i, line in enumerate(lines)
                if "--project-name cluster-jam-shared" in line
                and "up -d" in line
            ]
            if not migrations:
                raise RuntimeError("Deployment skipped explicit migrations")
            if scenario != "success":
                if launches or gateways:
                    raise RuntimeError(
                        "A failed prerequisite started the release"
                    )
            elif not (
                storage
                and launches
                and gateways
                and migrations[0] < storage[0] < launches[0] < gateways[0]
            ):
                raise RuntimeError("Deployment started services out of order")
    print(
        "Deployment guards OK: clean Git, explicit migration, Storage before "
        "startup, failure stops, environment isolation and gateway order"
    )


if __name__ == "__main__":
    verify_deployment_commands()
