"""Verify Docker packaging, isolation, and a disposable data volume."""

import json
import subprocess
from pathlib import Path
from uuid import uuid4


def run_command(arguments: list[str], *, capture: bool = False) -> str:
    """Run a bounded command without printing credential contents."""
    result = subprocess.run(
        arguments,
        check=True,
        text=True,
        capture_output=capture,
        timeout=900,
    )
    return result.stdout.strip() if capture else ""


def verify_stack() -> None:
    """Delete only the temporary Compose project's test resources."""
    directory = Path(__file__).resolve().parent
    project_name = f"personalization-verify-{uuid4().hex[:12]}"
    compose = [
        "docker",
        "compose",
        "--project-name",
        project_name,
        "--file",
        str(directory / "compose.yaml"),
    ]
    run_command([*compose, "config", "--quiet"])
    run_command(
        [
            *compose,
            "--profile",
            "tools",
            "build",
            "personalization-check",
        ]
    )
    try:
        run_command(
            [
                *compose,
                "up",
                "--detach",
                "--wait",
                "--wait-timeout",
                "120",
                "db-personalizacion",
            ]
        )
        run_command(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "personalization-check",
            ]
        )
        user_id = run_command(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "personalization-check",
                "python",
                "-c",
                "import os; print(os.getuid())",
            ],
            capture=True,
        )
        if user_id != "10001":
            raise RuntimeError("The runtime user must not be root")
        container_id = run_command(
            [
                *compose,
                "ps",
                "--quiet",
                "db-personalizacion",
            ],
            capture=True,
        )
        ports = json.loads(
            run_command(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{json .NetworkSettings.Ports}}",
                    container_id,
                ],
                capture=True,
            )
        )
        if ports.get("5432/tcp"):
            raise RuntimeError("PostgreSQL must not publish host ports")
        networks = json.loads(
            run_command(
                [
                    "docker",
                    "inspect",
                    "--format",
                    "{{json .NetworkSettings.Networks}}",
                    container_id,
                ],
                capture=True,
            )
        )
        if len(networks) != 1:
            raise RuntimeError("The database needs one private network")
        network = next(iter(networks))
        internal = run_command(
            [
                "docker",
                "network",
                "inspect",
                "--format",
                "{{.Internal}}",
                network,
            ],
            capture=True,
        )
        if internal != "true":
            raise RuntimeError("The database network must be internal")
        sql_command = [
            *compose,
            "exec",
            "--no-TTY",
            "db-personalizacion",
            "psql",
            "-U",
            "postgres",
            "-d",
            "personalizacion_db",
            "--tuples-only",
            "--no-align",
            "--command",
        ]
        system_id_sql = "SELECT system_identifier FROM pg_control_system()"
        original_id = run_command([*sql_command, system_id_sql], capture=True)
        table_count = run_command(
            [
                *sql_command,
                "SELECT count(*) FROM information_schema.tables "
                "WHERE table_schema = 'app'",
            ],
            capture=True,
        )
        if table_count != "0":
            raise RuntimeError("Domain tables must await migrations")
        run_command(
            [
                *compose,
                "up",
                "--detach",
                "--wait",
                "--wait-timeout",
                "120",
                "--force-recreate",
                "db-personalizacion",
            ]
        )
        restored_id = run_command([*sql_command, system_id_sql], capture=True)
        if not original_id or restored_id != original_id:
            raise RuntimeError("Recreation did not preserve PostgreSQL")
        run_command(
            [
                *compose,
                "run",
                "--rm",
                "--no-deps",
                "personalization-check",
            ]
        )
        print(
            "Docker checks passed: runtime user, DB access, private "
            "network, unpublished port, and volume persistence"
        )
    finally:
        # This UUID project owns only disposable test resources.
        run_command(
            [
                *compose,
                "--profile",
                "tools",
                "down",
                "--volumes",
                "--remove-orphans",
            ]
        )


if __name__ == "__main__":
    verify_stack()
