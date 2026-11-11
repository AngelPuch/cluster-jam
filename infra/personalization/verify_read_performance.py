"""Rehearse RNF05 on fresh PostgreSQL and the unchanged runtime image.

This opt-in probe never reads the developer database, credentials, or
Storage. It publishes no ports and removes only its own UUID resources.
"""

import argparse
import hashlib
import json
import os
import platform
import sys
import tempfile
from pathlib import Path
from typing import Any, BinaryIO, cast
from uuid import UUID, uuid5

from operation_tools.database import RecoveryDatabase
from operation_tools.runtime import (
    ROOT,
    ComposeContext,
    OperationError,
    json_object,
    run,
)
from verify_operations import migrate


def seed(identifier: str) -> None:
    # Match the worker's immutable thumbnail identity.
    namespace = UUID("310b89a7-6d45-5485-9ed7-305c39f4a24f")
    rows = []
    for index in range(1, 1001):
        original = f"00000000-0000-4000-8000-{index:012}"
        derived = uuid5(namespace, original)
        rows.append(f"('{original}'::uuid,'{derived}'::uuid)")
    derived_rows = ",".join(rows)
    sql = f"""
        INSERT INTO app.archivo
          (id,propietario_ref,bucket,objeto_clave,sha256,mime,bytes,
           ancho_px,alto_px,uso,estado)
        SELECT ('00000000-0000-4000-8000-'||lpad(i::text,12,'0'))::uuid,
          '00000000-0000-4000-8000-000000000001',
          'personalization-originals',
          '00000000-0000-4000-8000-'||lpad(i::text,12,'0')||'.png',
          repeat('a',64),'image/png',100,100,100,'ORIGINAL','DISPONIBLE'
        FROM generate_series(1,1000) i;
        WITH fixtures(original_id,thumbnail_id) AS (VALUES {derived_rows})
        INSERT INTO app.archivo
          (id,propietario_ref,bucket,objeto_clave,sha256,mime,bytes,
           ancho_px,alto_px,uso,estado)
        SELECT thumbnail_id,'00000000-0000-4000-8000-000000000001',
          'personalization-originals',thumbnail_id::text||'.png',
          repeat('b',64),'image/png',50,100,100,
          'MINIATURA_V1:'||original_id::text,'DISPONIBLE'
        FROM fixtures;
        INSERT INTO app.estampado (id,nombre,descripcion,activo)
        SELECT ('00000000-0000-4000-9000-'||lpad(i::text,12,'0'))::uuid,
          'Synthetic print '||i,'RNF05 synthetic fixture',true
        FROM generate_series(1,1000) i;
        INSERT INTO app.estampado_version
          (id,estampado_id,numero,archivo_id,recargo_centavos)
        SELECT ('00000000-0000-4000-8200-'||lpad((i*3+n)::text,12,'0'))::uuid,
          ('00000000-0000-4000-9000-'||lpad(i::text,12,'0'))::uuid,n,
          ('00000000-0000-4000-8000-'||lpad(i::text,12,'0'))::uuid,1234+n
        FROM generate_series(1,1000) i CROSS JOIN generate_series(1,3) n;
        ANALYZE app.archivo; ANALYZE app.estampado;
        ANALYZE app.estampado_version;
        SELECT json_build_object('seeded',true);
        """
    with tempfile.TemporaryFile() as source:
        source.write(sql.encode())
        source.seek(0)
        run(
            [
                "docker",
                "exec",
                "-i",
                "--user",
                "postgres",
                identifier,
                "psql",
                "-X",
                "-q",
                "--set",
                "ON_ERROR_STOP=1",
                "--username",
                "app_personalizacion",
                "--dbname",
                "personalizacion_db",
            ],
            input_file=cast(BinaryIO, source),
        )


def verify(users: int, seconds: int) -> dict[str, Any]:
    context = ComposeContext()
    services = context.model["services"]
    api_model = services["personalization"]
    runtime_image = api_model["image"]
    workers = int(api_model["environment"]["HTTP_WORKERS"])
    database = RecoveryDatabase(services["db-personalizacion"]["image"])
    api = database.project + "-read-api"
    client = database.project + "-read-client"
    probe = (
        ROOT / "services/personalizationService/test/performance/read_probe.py"
    )
    script = f"type=bind,source={probe},target=/qa/read_probe.py,readonly"
    try:
        identifier = database.start()
        migrate(database, runtime_image)
        seed(identifier)
        with tempfile.TemporaryDirectory(
            prefix="personalization-read-keys-"
        ) as temporary:
            materials = Path(temporary)
            if sys.platform == "win32":
                uid = "0:0"
            else:
                uid = f"{os.getuid()}:{os.getgid()}"
            run(
                [
                    "docker",
                    "run",
                    "--rm",
                    "--network",
                    "none",
                    "--user",
                    uid,
                    "--mount",
                    script,
                    "--mount",
                    f"type=bind,source={materials},target=/materials",
                    runtime_image,
                    "python",
                    "/qa/read_probe.py",
                    "prepare",
                    "--directory",
                    "/materials",
                ]
            )
            command = [
                "docker",
                "run",
                "-d",
                "--name",
                api,
                "--network",
                database.project + "_private",
                "--network-alias",
                "read-api",
                "--read-only",
                "--cap-drop",
                "ALL",
                "--security-opt",
                "no-new-privileges:true",
                "--memory",
                str(api_model["mem_limit"]),
                "--cpus",
                str(api_model["cpus"]),
                "--pids-limit",
                str(api_model["pids_limit"]),
                "--tmpfs",
                "/tmp:rw,noexec,nosuid,size=32m,mode=1777",
                "--log-opt",
                "max-size=10m",
                "--log-opt",
                "max-file=3",
                "--mount",
                script,
            ]
            for filename in (
                "jwks.json",
                "ca.crt",
                "server.crt",
                "server.key",
            ):
                command.extend(
                    [
                        "--mount",
                        f"type=bind,source={materials / filename},"
                        f"target=/qa/{filename},readonly",
                    ]
                )
            password_file = database.directory / "application_password"
            command.extend(
                [
                    "--mount",
                    f"type=bind,source={password_file},"
                    "target=/run/secrets/db_password,readonly",
                ]
            )
            for value in (
                "APP_ENV=test",
                "DB_HOST=db-personalizacion",
                "DB_PASSWORD_FILE=/run/secrets/db_password",
                "HTTP_HOST=0.0.0.0",
                "HTTP_PORT=8080",
                f"HTTP_WORKERS={workers}",
                "STORAGE_ENABLED=false",
                "LOG_LEVEL=INFO",
                "SUPABASE_ISSUER=https://localhost:8443/auth/v1",
                "SUPABASE_JWKS_URL=https://localhost:8443/auth/v1/.well-known/jwks.json",
                "SSL_CERT_FILE=/qa/ca.crt",
            ):
                command.extend(["--env", value])
            command.extend(
                [runtime_image, "python", "/qa/read_probe.py", "serve"]
            )
            run(command)
            readiness = """
import time
import urllib.request
for _ in range(60):
    try:
        urllib.request.urlopen(
            "http://127.0.0.1:8080/health/ready", timeout=2
        ).close()
        break
    except OSError:
        time.sleep(1)
else:
    raise SystemExit(1)
"""
            run(["docker", "exec", api, "python", "-c", readiness], timeout=90)
            result = json_object(
                run(
                    [
                        "docker",
                        "run",
                        "--rm",
                        "--name",
                        client,
                        "--network",
                        database.project + "_private",
                        "--read-only",
                        "--cap-drop",
                        "ALL",
                        "--security-opt",
                        "no-new-privileges:true",
                        "--memory",
                        "512m",
                        "--pids-limit",
                        "128",
                        "--mount",
                        script,
                        "--mount",
                        f"type=bind,source={materials / 'tokens.json'},"
                        "target=/qa/tokens.json,readonly",
                        runtime_image,
                        "python",
                        "/qa/read_probe.py",
                        "load",
                        "--users",
                        str(users),
                        "--seconds",
                        str(seconds),
                    ],
                    timeout=seconds + 120,
                )
            )
            counter = json.loads(
                run(
                    [
                        "docker",
                        "exec",
                        api,
                        "python",
                        "-c",
                        "import urllib.request; print(urllib.request.urlopen('https://localhost:8443/fixture-count',timeout=5).read().decode())",
                    ]
                )
            )
            if not 1 <= counter.get("jwks_requests", 0) <= workers:
                raise OperationError("JWKS_WAS_NOT_CACHED")
            result.update(counter)
            result["hardware"] = json.loads(
                run(["docker", "info", "--format", "{{json .}}"], timeout=30)
            )
            result["hardware"] = {
                name: result["hardware"][name]
                for name in (
                    "NCPU",
                    "MemTotal",
                    "KernelVersion",
                    "OperatingSystem",
                    "Architecture",
                )
            }
            result["hardware"]["host_platform"] = platform.platform()
            result["dataset"] = {
                "prints": 1000,
                "versions": 3000,
                "file_metadata": 2000,
                "page_size": 20,
                "real_storage_objects": 0,
            }
            result["api_limits"] = {
                "cpus": float(api_model["cpus"]),
                "memory_bytes": int(api_model["mem_limit"]),
                "http_workers": workers,
                "database_cpus": 1,
                "database_memory_bytes": 536870912,
            }
            result["runtime_image"] = runtime_image
            result["runtime_image_id"] = (
                run(
                    [
                        "docker",
                        "image",
                        "inspect",
                        "--format",
                        "{{.Id}}",
                        runtime_image,
                    ]
                )
                .decode()
                .strip()
            )
            result["database_image"] = services["db-personalizacion"]["image"]
            source_digest = hashlib.sha256()
            source_root = ROOT / "services/personalizationService"
            sources = sorted((source_root / "src").rglob("*.py"))
            sources.extend(
                source_root / name
                for name in ("pyproject.toml", "uv.lock", "Dockerfile")
            )
            for source in sources:
                source_digest.update(
                    source.relative_to(source_root).as_posix().encode()
                )
                source_digest.update(source.read_bytes())
            result["source_sha256"] = source_digest.hexdigest()
            result["revision"] = (
                run(["git", "rev-parse", "HEAD"]).decode().strip()
            )
            return result
    finally:
        for container in (client, api):
            try:
                run(["docker", "rm", "-f", container])
            except OperationError:
                pass
        database.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=30, choices=range(1, 101))
    parser.add_argument(
        "--seconds", type=int, default=300, choices=range(1, 1801)
    )
    arguments = parser.parse_args()
    result = verify(arguments.users, arguments.seconds)
    print(json.dumps(result))
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
