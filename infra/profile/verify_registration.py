"""Run one real local signup/outbox/broker/profile acceptance scenario, then clean owned resources."""

import json
import os
import re
import shutil
import socket
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "infra" / "profile"


def main():
    for port in (54321, 54322, 54324, 55439, 5679):
        with socket.socket() as probe:
            if probe.connect_ex(("127.0.0.1", port)) == 0:
                raise RuntimeError(
                    "A local acceptance port is already occupied; no existing service was stopped."
                )
    project = "profile-registration-" + uuid.uuid4().hex[:16]
    fixture_root = (BASE / ".verify").resolve()
    directory = fixture_root / project
    supabase = directory / "supabase"
    supabase.mkdir(parents=True, mode=0o700)
    source = ROOT / "services" / "authService" / "supabase"
    config = (source / "config.toml").read_text(encoding="utf8")
    config = re.sub(
        r"^project_id\s*=.*$",
        'project_id = "' + project + '"',
        config,
        count=1,
        flags=re.MULTILINE,
    )
    (supabase / "config.toml").write_text(config, encoding="utf8")
    shutil.copytree(source / "migrations", supabase / "migrations")
    shutil.copytree(source / "templates", supabase / "templates")
    cli = [
        "node",
        str(
            ROOT
            / "services"
            / "authService"
            / "node_modules"
            / "supabase"
            / "dist"
            / "supabase.js"
        ),
        "--workdir",
        str(directory),
        "--agent",
        "no",
    ]
    compose = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(BASE / "compose.registration.yaml"),
    ]
    env = {**os.environ}

    def run(command, *, timeout=240, capture=True, child_env=None, cwd=ROOT):
        result = subprocess.run(
            command,
            cwd=cwd,
            env=child_env or env,
            capture_output=capture,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            check=False,
        )
        if result.returncode:
            raise RuntimeError(
                "Registration acceptance command failed; captured local configuration was not printed."
            )
        return result.stdout if capture else ""

    try:
        print(
            "Registration acceptance: starting minimal disposable Supabase", flush=True
        )
        run(
            [
                *cli,
                "start",
                "--exclude",
                "realtime,storage-api,imgproxy,postgrest,postgres-meta,studio,edge-runtime,logflare,vector,supavisor",
            ],
            timeout=360,
        )
        status = json.loads(run([*cli, "status", "--output", "json"]))
        api = status.get("API_URL")
        key = status.get("PUBLISHABLE_KEY") or status.get("ANON_KEY")
        database = status.get("DB_URL")
        if not api or not key or not database:
            raise RuntimeError(
                "Local Supabase status did not provide the required acceptance settings."
            )
        run([*compose, "up", "-d", "--wait", "--wait-timeout", "120"])
        print("Registration acceptance: building the two applications once", flush=True)
        npm = "npm.cmd" if os.name == "nt" else "npm"
        run([npm, "--prefix", str(ROOT / "services" / "authService"), "run", "build"])
        run(
            [npm, "--prefix", str(ROOT / "services" / "profileService"), "run", "build"]
        )
        child = {
            **env,
            "PROFILE_REGISTRATION_LOCAL": "true",
            "SUPABASE_URL": api,
            "SUPABASE_PUBLISHABLE_KEY": key,
            "PROFILE_REGISTRATION_SUPABASE_DB": database,
            "PROFILE_TEST_DATABASE_URL": "postgresql://profile_test:registration-local-only@127.0.0.1:55439/postgres",
            "PROFILE_TEST_RABBITMQ_URI": "amqp://registration-test:registration-local-only@127.0.0.1:5679/profile-registration",
        }
        print(
            "Registration acceptance: executing the single real signup flow", flush=True
        )
        # The child handles only safe result messages; provider keys remain in its environment.
        run(
            ["node", str(BASE / "check_registration.cjs")],
            timeout=90,
            capture=False,
            child_env=child,
            cwd=directory,
        )
    finally:
        if not re.fullmatch(r"profile-registration-[a-f0-9]{16}", project):
            raise RuntimeError("Unsafe cleanup project name.")
        run([*cli, "stop", "--no-backup"], timeout=120)
        run([*compose, "down", "--volumes", "--remove-orphans"], timeout=120)
        target = directory.resolve()
        if target.parent != fixture_root or target.name != project:
            raise RuntimeError("Unsafe cleanup fixture path.")

        def writable_cleanup(function, path, error):
            os.chmod(path, 0o700)
            function(path)

        shutil.rmtree(target, onexc=writable_cleanup)


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(
            str(error)
            if isinstance(error, RuntimeError)
            else "Registration acceptance failed; no private values were logged."
        )
        raise SystemExit(1)
