"""Verify the actual Profile image with disposable TLS PostgreSQL/RabbitMQ/JWKS/HTTPS containers."""

import argparse
import importlib.util
import json
import os
import re
import shutil
import subprocess
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "infra" / "profile"
SPEC = importlib.util.spec_from_file_location(
    "profile_fixture_prepare", BASE / "prepare.py"
)
assert SPEC and SPEC.loader
PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PREPARE)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    project = "profile-verify-" + uuid.uuid4().hex[:16]
    fixture_root = (BASE / ".verify").resolve()
    directory = fixture_root / project
    directory.mkdir(parents=True, mode=0o700)
    shared = directory / "shared"
    profile = directory / "profile"
    prep = PREPARE.SHARED_PREPARE
    prep.SHARED = shared
    prep.AUTH = directory / "auth"
    PREPARE.PROFILE = profile
    for path in (shared / ".secrets", shared / ".pki", prep.AUTH / ".secrets"):
        prep.private_directory(path)
    prep.prepare_definitions()
    prep.prepare_ca()
    prep.leaf("https", ["DNS:clusterjam.test", "DNS:localhost"], False)
    prep.leaf("rabbitmq", ["DNS:clusterjam-rabbitmq"], False)
    prep.leaf("profile-jwks", ["DNS:profile-jwks"], False)
    PREPARE.prepare()
    result = {"checks": []}
    environment = {
        **os.environ,
        "PROFILE_IMAGE": args.image,
        "SUPABASE_URL": "https://profile-jwks:8443",
        "SUPABASE_JWKS_URL": "https://profile-jwks:8443/auth/v1/.well-known/jwks.json",
        "LOG_LEVEL": "INFO",
    }

    def path(value):
        return str(value.resolve()).replace("\\", "/")

    def secret(value):
        return {"file": path(value)}

    def mount(value, target):
        return {
            "type": "bind",
            "source": path(value),
            "target": target,
            "read_only": True,
        }

    ca = shared / ".pki" / "ca.crt"
    fixture_volumes = [mount(ca, "/fixture/ca.crt")]
    node_health = [
        "CMD",
        "node",
        "-e",
        "fetch('https://profile-jwks:8443/health/live',{signal:AbortSignal.timeout(2000)}).then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))",
    ]
    overlay = {
        "networks": {"backend": {"external": False, "name": project + "-backend"}},
        "secrets": {
            "profile_db_admin_password": secret(
                profile / ".secrets" / "postgres_admin_password"
            ),
            "profile_db_password": secret(profile / ".secrets" / "profile_db_password"),
            "profile_db_migration_password": secret(
                profile / ".secrets" / "profile_db_migration_password"
            ),
            "profile_db_tls_key": secret(profile / ".secrets" / "profile-db.key"),
            "profile_rabbitmq_uri": secret(
                profile / ".secrets" / "profile_rabbitmq_uri"
            ),
            "verify_https_key": secret(shared / ".pki" / "https.key"),
            "verify_broker_key": secret(shared / ".pki" / "rabbitmq.key"),
            "verify_broker_definitions": secret(
                shared / ".secrets" / "rabbitmq_definitions.json"
            ),
        },
        "configs": {
            "profile_db_certificate": secret(
                profile / ".certificates" / "profile-db.crt"
            ),
            "profile_db_ca": secret(profile / ".certificates" / "profile-db-ca.crt"),
            "cluster_ca": secret(ca),
            "verify_https_cert": secret(shared / ".pki" / "https.crt"),
            "verify_broker_cert": secret(shared / ".pki" / "rabbitmq.crt"),
            "verify_nginx": secret(ROOT / "infra" / "shared" / "nginx.conf"),
            "verify_proxy": secret(ROOT / "infra" / "shared" / "nginx-proxy.conf"),
            "verify_rabbitmq": secret(ROOT / "infra" / "shared" / "rabbitmq.conf"),
        },
        "services": {
            "rabbitmq": {
                "image": "rabbitmq:4.4.0@sha256:485319d42170eab53d8a030e1cc49d95e41f5d325479fa504736db8091981eb7",
                "hostname": "clusterjam-rabbitmq",
                "networks": {"backend": {"aliases": ["clusterjam-rabbitmq"]}},
                "secrets": [
                    {"source": "verify_broker_key", "target": "rabbitmq_key"},
                    {
                        "source": "verify_broker_definitions",
                        "target": "rabbitmq_definitions",
                    },
                ],
                "configs": [
                    {
                        "source": "verify_broker_cert",
                        "target": "/run/config/rabbitmq.crt",
                    },
                    {"source": "cluster_ca", "target": "/run/config/cluster-ca.crt"},
                    {
                        "source": "verify_rabbitmq",
                        "target": "/etc/rabbitmq/rabbitmq.conf",
                    },
                ],
                "healthcheck": {
                    "test": ["CMD", "rabbitmq-diagnostics", "-q", "check_running"],
                    "interval": "5s",
                    "timeout": "10s",
                    "retries": 24,
                },
                "mem_limit": "768m",
                "cpus": 1.0,
            },
            "jwks": {
                "image": args.image,
                "command": ["node", "/fixture/jwks.cjs"],
                "networks": {"backend": {"aliases": ["profile-jwks"]}},
                "environment": {"NODE_EXTRA_CA_CERTS": "/fixture/ca.crt"},
                "volumes": fixture_volumes
                + [
                    mount(BASE / "stack_jwks.cjs", "/fixture/jwks.cjs"),
                    mount(shared / ".pki" / "profile-jwks.crt", "/fixture/server.crt"),
                    mount(shared / ".pki" / "profile-jwks.key", "/fixture/server.key"),
                ],
                "healthcheck": {
                    "test": node_health,
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 12,
                },
                "mem_limit": "256m",
            },
            "nginx": {
                "image": "nginx:1.30.6-trixie@sha256:51047bea59fed88fbd1f52565d2f5fabcb82d311cf6c9e507a10ce74bb3bc3f0",
                "user": "101:101",
                "entrypoint": ["nginx"],
                "command": ["-g", "daemon off;"],
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "tmpfs": ["/tmp:size=64m,mode=1777"],
                "networks": {"backend": {"aliases": ["clusterjam.test"]}},
                "secrets": [{"source": "verify_https_key", "target": "https_key"}],
                "configs": [
                    {"source": "verify_https_cert", "target": "/run/config/https.crt"},
                    {"source": "cluster_ca", "target": "/run/config/cluster-ca.crt"},
                    {"source": "verify_nginx", "target": "/etc/nginx/nginx.conf"},
                    {
                        "source": "verify_proxy",
                        "target": "/etc/nginx/cluster-proxy.conf",
                    },
                ],
                "healthcheck": {
                    "test": [
                        "CMD",
                        "curl",
                        "-fsS",
                        "http://127.0.0.1:8080/health/live",
                    ],
                    "interval": "5s",
                    "timeout": "3s",
                    "retries": 12,
                },
                "mem_limit": "128m",
            },
            "probe": {
                "image": args.image,
                "profiles": ["verify"],
                "entrypoint": ["node", "/fixture/probe.cjs"],
                "command": ["flow"],
                "networks": ["backend"],
                "environment": {"NODE_EXTRA_CA_CERTS": "/fixture/ca.crt"},
                "volumes": fixture_volumes
                + [
                    mount(BASE / "stack_probe.cjs", "/fixture/probe.cjs"),
                    mount(
                        prep.AUTH / ".secrets" / "auth_rabbitmq_url",
                        "/fixture/publisher-uri",
                    ),
                ],
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "mem_limit": "256m",
            },
        },
    }
    overlay_path = directory / "compose.json"
    overlay_path.write_text(json.dumps(overlay), encoding="utf8")
    compose = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(BASE / "compose.yaml"),
        "-f",
        str(overlay_path),
    ]

    def run(*arguments, timeout=240, input_text=None, quiet=False):
        completed = subprocess.run(
            [*compose, *arguments],
            check=False,
            env=environment,
            cwd=ROOT,
            input=input_text,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        if completed.returncode:
            # Emit bounded diagnostics only after removing all generated secret values.
            diagnostic = completed.stderr[-6000:]
            if arguments[0] != "config" and not quiet:
                for secrets_dir in (
                    shared / ".secrets",
                    profile / ".secrets",
                    prep.AUTH / ".secrets",
                ):
                    for item in secrets_dir.iterdir():
                        if item.is_file() and not item.name.endswith(".key"):
                            value = item.read_text().strip()
                            if value:
                                diagnostic = diagnostic.replace(value, "[REDACTED]")
                diagnostic = re.sub(
                    r"-----BEGIN .*?PRIVATE KEY-----.*?-----END .*?PRIVATE KEY-----",
                    "[REDACTED KEY]",
                    diagnostic,
                    flags=re.DOTALL,
                )
                print(diagnostic, flush=True)
            raise RuntimeError(
                "Profile verification step failed: " + " ".join(arguments[:3])
            )
        return completed.stdout

    def probe(mode, quiet=False):
        output = run("run", "--rm", "--no-deps", "probe", mode, quiet=quiet)
        result["checks"].extend(json.loads(output.strip().splitlines()[-1])["checks"])

    def ready():
        for _ in range(40):
            try:
                probe("persisted", quiet=True)
                return
            except RuntimeError:
                time.sleep(1)
        raise RuntimeError("Profile readiness did not recover")

    try:
        print("Profile stack: validating private Compose model", flush=True)
        model = json.loads(run("config", "--format", "json"))
        assert not model["services"]["db-profile"].get("ports")
        assert not model["services"]["profile"].get("ports")
        assert model["networks"]["profile-db"]["internal"]
        assert not model["networks"]["backend"].get("external", False)
        print(
            "Profile stack: starting real TLS dependencies and migration job",
            flush=True,
        )
        run(
            "up",
            "-d",
            "--wait",
            "--wait-timeout",
            "180",
            "rabbitmq",
            "jwks",
            "db-profile",
        )
        run("run", "--rm", "--no-deps", "profile-migrate")
        run("run", "--rm", "--no-deps", "profile-migrate")
        result["checks"].append("fresh-and-repeat-compiled-migrations")
        run("up", "-d", "--wait", "--wait-timeout", "180", "profile", "nginx")
        run("exec", "-T", "nginx", "nginx", "-t")
        print(
            "Profile stack: exercising HTTPS, registration, profile and owned addresses",
            flush=True,
        )
        probe("flow")
        database_checks = run(
            "exec",
            "-T",
            "profile",
            "node",
            input_text=(BASE / "stack_database.cjs").read_text(),
        )
        result["checks"].extend(json.loads(database_checks.strip())["checks"])
        output = subprocess.run(
            ["docker", "inspect", project + "-profile-1", project + "-db-profile-1"],
            capture_output=True,
            text=True,
            check=True,
        )
        runtime, db = json.loads(output.stdout)
        assert (
            runtime["Config"]["User"] == "node"
            and runtime["HostConfig"]["ReadonlyRootfs"]
        )
        assert runtime["HostConfig"]["CapDrop"] == ["ALL"]
        assert set(db["NetworkSettings"]["Networks"]) == {project + "_profile-db"}
        assert not db["HostConfig"].get("PortBindings")
        assert not any(
            value.startswith(("DB_PASSWORD=", "RABBITMQ_URI="))
            for value in runtime["Config"]["Env"]
        )
        result["checks"].append(
            "nonroot-readonly-runtime-isolated-database-and-mounted-secrets"
        )
        print("Profile stack: verifying outages and durable recovery", flush=True)
        for dependency in ("rabbitmq", "db-profile"):
            run("stop", dependency)
            probe("down")
            run("start", dependency)
            ready()
            print("Profile stack: recovered " + dependency, flush=True)
        logs = run("logs", "--no-color", "profile")
        correlation = '"trace_id":"' + "3" * 32 + '"'
        assert correlation in logs
        assert correlation in run("logs", "--no-color", "nginx")
        result["checks"].append("w3c-correlation-across-gateway-and-profile-logs")
        for value in (profile / ".secrets").iterdir():
            if value.name.endswith(".key"):
                continue
            assert value.read_text().strip() not in logs
        for value in (
            "stack-initial@example.test",
            "stack-contact@example.test",
            "Test street",
            "Stack Customer",
        ):
            assert value not in logs
        print("Profile stack: checking private logs and SIGTERM cleanup", flush=True)
        current = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.RestartCount}}",
                project + "-profile-1",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        assert current.stdout.strip() == "0", (
            "Profile unexpectedly restarted during dependency outages"
        )
        run("stop", "-t", "35", "profile")
        state = subprocess.run(
            [
                "docker",
                "inspect",
                "--format",
                "{{.State.ExitCode}}",
                project + "-profile-1",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        # Nest re-emits SIGTERM after cleanup, so a graceful stop can report 128+15.
        assert state.stdout.strip() in {"0", "143"}, (
            "Unexpected Profile shutdown status"
        )
        assert '"event":"service.stopped"' in run("logs", "--no-color", "profile")
        connections = run(
            "exec",
            "-T",
            "db-profile",
            "psql",
            "-U",
            "postgres",
            "-d",
            "profile_db",
            "-At",
            "-c",
            "SELECT count(*) FROM pg_stat_activity WHERE usename='app_profile'",
        )
        assert connections.strip() == "0", "Runtime database pool did not close"
        consumers = json.loads(
            run(
                "exec",
                "-T",
                "rabbitmq",
                "rabbitmqctl",
                "list_consumers",
                "-p",
                "clusterjam",
                "--formatter",
                "json",
            )
        )
        assert consumers == [], "Registration consumer did not close"
        result["checks"].extend(
            [
                "private-data-excluded-from-logs",
                "graceful-sigterm-consumer-and-database-shutdown",
            ]
        )
        print(json.dumps(result, indent=2), flush=True)
    finally:
        if not re.fullmatch(r"profile-verify-[a-f0-9]{16}", project):
            raise RuntimeError("Unsafe project cleanup")
        run("down", "--volumes", "--remove-orphans")
        target = directory.resolve()
        if target.parent != fixture_root or target.name != project:
            raise RuntimeError("Unsafe fixture cleanup path")

        def writable_cleanup(function, value, error):
            os.chmod(value, 0o700)
            function(value)

        shutil.rmtree(target, onexc=writable_cleanup)


if __name__ == "__main__":
    try:
        main()
    except (
        OSError,
        ValueError,
        AssertionError,
        RuntimeError,
        subprocess.SubprocessError,
    ) as error:
        print(
            str(error)
            if isinstance(error, RuntimeError)
            else "Profile stack verification failed; no secrets were logged."
        )
        raise SystemExit(1)
