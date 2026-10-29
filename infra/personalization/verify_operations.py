"""Verify database and object recovery with disposable fixtures."""

import base64
import hashlib
import json
import os
import re
import shutil
import ssl
import tempfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from unittest.mock import patch
from urllib.request import HTTPSHandler, ProxyHandler, build_opener
from uuid import uuid4

from operation_tools import bundles
from operation_tools.bundles import (
    create_backup,
    restore_objects,
    restore_snapshot,
    verify_bundle,
)
from operation_tools.database import RecoveryDatabase, dump_database, inventory
from operation_tools.runtime import (
    DIRECTORY,
    ComposeContext,
    OperationError,
    run,
)
from operation_tools.storage import NoRedirect, StorageArchive

TEST_KEY = "sb_secret_" + "operations-fixture-only-" * 2
BUCKET = "personalization-originals"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwC"
    "AAAAC0lEQVR42mP8/x8AAwMCAO+aWWQAAAAASUVORK5CYII="
)


class StorageServer(ThreadingHTTPServer):
    daemon_threads = True

    def __init__(self) -> None:
        super().__init__(("127.0.0.1", 0), StorageHandler)
        self.objects: dict[str, bytes] = {}
        self.requests: list[str] = []
        self.posts = 0
        self.redirect = False


class StorageHandler(BaseHTTPRequestHandler):
    server: StorageServer

    def respond(self, code: int, data: bytes, *, image: bool = False) -> None:
        self.send_response(code)
        self.send_header(
            "Content-Type", "image/png" if image else "application/json"
        )
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self) -> None:
        self.server.requests.append(self.path)
        if self.headers.get("apikey") != TEST_KEY:
            self.respond(403, b"{}")
        elif self.path == "/storage/v1/bucket/" + BUCKET:
            self.respond(
                200,
                json.dumps(
                    {
                        "id": BUCKET,
                        "public": False,
                        "file_size_limit": 10_000_000,
                        "allowed_mime_types": ["image/png", "image/jpeg"],
                    }
                ).encode(),
            )
        elif self.server.redirect:
            self.send_response(302)
            self.send_header("Location", "/unexpected-redirect-target")
            self.send_header("Content-Length", "0")
            self.end_headers()
        else:
            key = self.path.rsplit("/", 1)[-1]
            if key in self.server.objects:
                self.respond(200, self.server.objects[key], image=True)
            else:
                self.respond(404, b'{"code":"NoSuchKey"}')

    def do_POST(self) -> None:
        if (
            self.headers.get("apikey") != TEST_KEY
            or self.headers.get("x-upsert") != "false"
        ):
            self.respond(403, b"{}")
            return
        length = int(self.headers.get("Content-Length", "0"))
        if not 1 <= length <= 10_000_000:
            self.respond(413, b"{}")
            return
        key = self.path.rsplit("/", 1)[-1]
        if key in self.server.objects:
            self.respond(409, b'{"error":"Duplicate"}')
            return
        self.server.posts += 1
        self.server.objects[key] = self.rfile.read(length)
        self.respond(200, json.dumps({"Key": BUCKET + "/" + key}).encode())

    def log_message(self, format: str, *args: object) -> None:
        return


class FixtureContext(ComposeContext):
    def __init__(
        self,
        database: RecoveryDatabase,
        identifier: str,
        image: str,
        origin: str,
        key_file: Path,
    ) -> None:
        self._identifier = identifier
        self.command = database.command
        self.gateway = database.command
        self.deployment = False
        self.model = {
            "services": {
                "db-personalizacion": {"image": image},
                "personalization": {
                    "environment": {
                        "SUPABASE_ISSUER": origin + "/auth/v1",
                        "SUPABASE_STORAGE_BUCKET": BUCKET,
                    }
                },
            },
            "secrets": {"supabase_storage_key": {"file": str(key_file)}},
        }

    def database_id(self) -> str:
        return self._identifier


def migrate(database: RecoveryDatabase, runtime_image: str) -> None:
    arguments = [
        "docker",
        "run",
        "--rm",
        "--network",
        database.project + "_private",
    ]
    for value in (
        "APP_ENV=test",
        "DB_HOST=db-personalizacion",
        "DB_PASSWORD_FILE=/run/secrets/db_password",
        "SUPABASE_ISSUER=https://supabase.example.test/auth/v1",
        "SUPABASE_JWKS_URL=https://supabase.example.test/auth/v1/.well-known/jwks.json",
    ):
        arguments.extend(["--env", value])
    arguments.extend(
        [
            "--mount",
            f"type=bind,source={database.directory / 'application_password'},"
            "target=/run/secrets/db_password,readonly",
            runtime_image,
            "python",
            "-m",
            "personalization.infrastructure.database.migrate",
            "upgrade",
        ]
    )
    run(arguments)


def verify_worker_liveness(
    database: RecoveryDatabase,
    directory: Path,
    runtime_image: str,
    key_file: Path,
) -> None:
    empty_env = directory / "empty.env"
    empty_env.touch()
    with patch.dict(
        os.environ,
        {
            "SUPABASE_ISSUER": "https://supabase.example.test/auth/v1",
            "SUPABASE_JWKS_URL": "https://supabase.example.test/auth/v1/.well-known/jwks.json",
        },
    ):
        model = json.loads(
            run(
                [
                    "docker",
                    "compose",
                    "--env-file",
                    str(empty_env),
                    "-f",
                    str(DIRECTORY / "compose.yaml"),
                    "--profile",
                    "images",
                    "config",
                    "--format",
                    "json",
                ]
            )
        )
    project = "personalization-worker-probe-" + uuid4().hex[:12]
    worker = model["services"]["personalization-worker"]
    worker["image"] = runtime_image
    worker.pop("depends_on", None)
    worker["environment"].update(
        {
            "APP_ENV": "test",
            "WORKER_POLL_SECONDS": "1",
            "WORKER_HEARTBEAT_MAX_AGE_SECONDS": "30",
            "STORAGE_ENABLED": "true",
            "SUPABASE_STORAGE_KEY_FILE": "/run/secrets/supabase_storage_key",
        }
    )
    worker["secrets"].append(
        {"source": "fixture_storage_key", "target": "supabase_storage_key"}
    )
    worker["healthcheck"].update({"interval": "1s", "start_period": "1s"})
    model["name"] = project
    model["services"] = {"personalization-worker": worker}
    model["networks"] = {
        "personalization-db": {
            "external": True,
            "name": database.project + "_private",
        }
    }
    model.pop("volumes", None)
    model["secrets"] = {
        "personalization_db_password": {
            "file": str(database.directory / "application_password")
        },
        "fixture_storage_key": {"file": str(key_file)},
    }
    configuration = directory / "worker.json"
    configuration.write_text(json.dumps(model), encoding="utf-8")
    command = [
        "docker",
        "compose",
        "-p",
        project,
        "-f",
        str(configuration),
        "--profile",
        "images",
    ]
    try:
        run(
            [
                *command,
                "up",
                "-d",
                "--no-build",
                "--wait",
                "--wait-timeout",
                "45",
            ]
        )
        run([*database.command, "stop", "db-personalizacion"])
        run(
            [
                *command,
                "exec",
                "-T",
                "personalization-worker",
                "python",
                "-m",
                "personalization.interfaces.workers.health",
            ]
        )
        run([*database.command, "up", "-d", "--wait", "--wait-timeout", "90"])
        run([*command, "stop", "personalization-worker"])
        logs = run(
            [
                *command,
                "logs",
                "--no-color",
                "--no-log-prefix",
                "personalization-worker",
            ]
        )
        assert TEST_KEY.encode() not in logs
        events = [
            json.loads(line)
            for line in logs.splitlines()
            if line.startswith(b"{")
        ]
        assert events[0]["event"] == "worker.started"
        assert events[-1]["event"] == "worker.stopped"
        print(
            "Worker liveness OK: readonly image, tmpfs, "
            "heartbeat during DB outage, graceful stop and private logs"
        )
    finally:
        assert re.fullmatch(
            r"personalization-worker-probe-[0-9a-f]{12}", project
        )
        run([*command, "down", "--remove-orphans"])


def seed(container: str, file_ids: list[str]) -> None:
    owner, print_id, print_version, template, zone, size, design = [
        str(uuid4()) for _ in range(7)
    ]
    digest = hashlib.sha256(PNG).hexdigest()
    rows = ",".join(
        f"('{identifier}','{owner}','{BUCKET}','{identifier}.png',"
        f"'{digest}','image/png',{len(PNG)},1,1,"
        f"'{'ORIGINAL' if index != 1 else 'PREVIA_V1:fixture'}',"
        f"'{'DISPONIBLE' if index != 2 else 'PENDIENTE_CARGA'}')"
        for index, identifier in enumerate(file_ids)
    )
    sql = f"""
        BEGIN;
        INSERT INTO app.archivo (id,propietario_ref,bucket,
          objeto_clave,sha256,mime,
          bytes,ancho_px,alto_px,uso,estado) VALUES {rows};
        INSERT INTO app.estampado (id,nombre,
          activo) VALUES ('{print_id}','Recovery fixture',false);
        INSERT INTO app.estampado_version (id,estampado_id,numero,
          archivo_id,recargo_centavos)
          VALUES ('{print_version}','{print_id}',1,'{file_ids[0]}',1234);
        INSERT INTO app.plantilla_version (id,producto_ref,talla_ref,numero,
          ancho_frente_mm,alto_frente_mm,ancho_espalda_mm,
          alto_espalda_mm,activa)
          VALUES ('{template}','{uuid4()}',1,1,300,400,300,400,false);
        INSERT INTO app.zona (id,plantilla_id,cara,codigo,x_mm,y_mm,
          ancho_mm,alto_mm)
          VALUES ('{zone}','{template}','FRENTE','CHEST',10,10,100,100);
        INSERT INTO app.tamano_zona (id,zona_id,etiqueta,ancho_mm,
          alto_mm,recargo_centavos)
          VALUES ('{size}','{zone}','CHICO',50,50,100);
        INSERT INTO app.diseno (id,usuario_ref,variante_ref,
          plantilla_id,estado,
          version,previa_frente_id) VALUES ('{design}','{owner}','{uuid4()}',
          '{template}','BORRADOR',3,'{file_ids[1]}');
        INSERT INTO app.aplicacion (id,diseno_id,zona_id,tamano_id,
          estampado_version_id)
          VALUES ('{uuid4()}','{design}','{zone}','{size}','{print_version}');
        INSERT INTO app.auditoria_local (id,accion,recurso,recurso_id,detalle)
          VALUES ('{uuid4()}','RECOVERY_FIXTURE','diseno','{design}',
          '{{"private_note":"fixture-audit-not-for-logs"}}');
        COMMIT;
    """
    run(
        [
            "docker",
            "exec",
            "--user",
            "postgres",
            container,
            "psql",
            "-X",
            "-q",
            "--set",
            "ON_ERROR_STOP=1",
            "--username",
            "app_personalizacion",
            "--dbname",
            "personalizacion_db",
            "--command",
            sql,
        ]
    )


def verify_operations() -> None:
    image_match = re.search(
        r"^\s+image: (postgres:[^\s]+)$",
        (DIRECTORY / "compose.yaml").read_text(),
        re.MULTILINE,
    )
    if image_match is None:
        raise RuntimeError("The pinned PostgreSQL image is missing")
    image = image_match[1]
    runtime_image = "cluster-jam/personalization:" + os.environ.get(
        "PERSONALIZATION_IMAGE_TAG", "0.1.0-local"
    )
    database = RecoveryDatabase(image)
    server = StorageServer()
    thread: Thread | None = None
    with tempfile.TemporaryDirectory(
        prefix="personalization-operation-check-"
    ) as temporary:
        directory = Path(temporary)
        key_file = directory / "server-key"
        key_file.write_text(TEST_KEY)
        key_file.chmod(0o444)
        openssl = shutil.which("openssl")
        if openssl is None:
            raise RuntimeError("OpenSSL is required")
        certificate, key = directory / "server.crt", directory / "server.key"
        run(
            [
                openssl,
                "req",
                "-x509",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-days",
                "1",
                "-subj",
                "/CN=localhost",
                "-addext",
                "subjectAltName=DNS:localhost,IP:127.0.0.1",
                "-out",
                str(certificate),
                "-keyout",
                str(key),
            ]
        )
        tls = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        tls.load_cert_chain(certificate, key)
        server.socket = tls.wrap_socket(server.socket, server_side=True)
        thread = Thread(target=server.serve_forever, daemon=True)
        thread.start()
        origin = "https://127.0.0.1:" + str(server.server_port)
        try:
            identifier = database.start()
            migrate(database, runtime_image)
            verify_worker_liveness(
                database, directory, runtime_image, key_file
            )
            file_ids = [str(uuid4()) for _ in range(3)]
            seed(identifier, file_ids)
            for value in file_ids[:2]:
                server.objects[value + ".png"] = PNG
            context = FixtureContext(
                database, identifier, image, origin, key_file
            )

            def storage_for_test(current: ComposeContext) -> StorageArchive:
                archive = StorageArchive(origin, BUCKET, key_file)
                archive._opener = build_opener(
                    ProxyHandler({}),
                    NoRedirect(),
                    HTTPSHandler(
                        context=ssl.create_default_context(
                            cafile=str(certificate)
                        )
                    ),
                )
                return archive

            with patch.object(bundles, "storage_client", storage_for_test):
                output = directory / "backups"
                original = inventory(identifier)
                bundle = create_backup(context, output)
                assert bundle.metadata["row_counts"] == original["counts"]
                assert (
                    len(bundle.available) == 2
                    and bundle.metadata["pending_files"] == 1
                )
                assert all(
                    count > 0
                    for count in bundle.metadata["row_counts"].values()
                )
                assert (
                    TEST_KEY.encode()
                    not in (bundle.directory / "manifest.json").read_bytes()
                )
                assert file_ids[2] + ".png" not in " ".join(server.requests)
                restore_snapshot(bundle)
                assert inventory(identifier) == original
                del server.objects[file_ids[0] + ".png"]
                assert restore_objects(bundle, context) == 1
                assert restore_objects(bundle, context) == 0
                assert server.posts == 1
                server.objects[file_ids[0] + ".png"] = b"conflicting-content"
                try:
                    restore_objects(bundle, context)
                except OperationError as error:
                    assert error.code == "STORAGE_INTEGRITY_MISMATCH"
                else:
                    raise AssertionError("Conflicting image was accepted")
                assert server.posts == 1
                server.objects[file_ids[0] + ".png"] = PNG

                original_dump = dump_database
                added = str(uuid4())

                def dump_then_change_source(
                    container: str, target: Path
                ) -> None:
                    original_dump(container, target)
                    # Commit this row after the dump snapshot.
                    sql = (
                        "INSERT INTO app.archivo SELECT '"
                        + added
                        + "'::uuid,propietario_ref,bucket,'"
                        + added
                        + ".png',sha256,mime,bytes,ancho_px,"
                        "alto_px,uso,estado "
                        "FROM app.archivo WHERE id='" + file_ids[0] + "'"
                    )
                    run(
                        [
                            "docker",
                            "exec",
                            "--user",
                            "postgres",
                            container,
                            "psql",
                            "-X",
                            "-q",
                            "--set",
                            "ON_ERROR_STOP=1",
                            "--username",
                            "app_personalizacion",
                            "--dbname",
                            "personalizacion_db",
                            "--command",
                            sql,
                        ]
                    )
                    server.objects[added + ".png"] = PNG

                with patch.object(
                    bundles, "dump_database", dump_then_change_source
                ):
                    raced = create_backup(context, output)
                assert raced.metadata["row_counts"]["archivo"] == 3
                assert inventory(identifier)["counts"]["archivo"] == 4
                assert added not in {entry.id for entry in raced.objects}
                restore_snapshot(raced)
                server.redirect = True
                try:
                    create_backup(context, output)
                except OperationError:
                    pass
                else:
                    raise AssertionError(
                        "Redirecting Storage endpoint was accepted"
                    )
                server.redirect = False
                assert "/unexpected-redirect-target" not in server.requests
                assert len(list(output.iterdir())) == 2
                assert (
                    verify_bundle(bundle.directory).metadata == bundle.metadata
                )

                workspace = directory / "retained-recovery"
                retained = restore_snapshot(bundle, workspace)
                model = json.loads((workspace / "compose.json").read_text())
                assert model["name"] == retained and not model["services"][
                    "db-personalizacion"
                ].get("ports")
                assert workspace.resolve().is_relative_to(directory.resolve())
                overlay = json.loads(
                    (workspace / "recovery.override.yaml").read_text()
                )
                assert (
                    overlay["volumes"]["personalization-data"]["name"]
                    == retained + "_data"
                )
                assert not run(
                    [
                        "docker",
                        "compose",
                        "-p",
                        retained,
                        "-f",
                        str(workspace / "compose.json"),
                        "ps",
                        "--status",
                        "running",
                        "--quiet",
                    ]
                ).strip()
                try:
                    restore_snapshot(bundle, workspace)
                except OperationError as error:
                    assert error.code == "RECOVERY_WORKSPACE_MUST_BE_NEW"
                else:
                    raise AssertionError(
                        "Existing recovery workspace was reused"
                    )
                finally:
                    assert re.fullmatch(
                        r"personalization-recovery-[0-9a-f]{12}", retained
                    )
                    run(
                        [
                            "docker",
                            "compose",
                            "-p",
                            retained,
                            "-f",
                            str(workspace / "compose.json"),
                            "down",
                            "--volumes",
                            "--remove-orphans",
                        ]
                    )
            print(
                "Operations recovery OK: tables/audit, exact snapshot, "
                "original/preview bytes, pending intentions, create-only "
                "recovery, conflicts, redirects and atomic publication"
            )
        finally:
            database.close()
            if thread is not None:
                server.shutdown()
                thread.join(timeout=5)
            server.server_close()


if __name__ == "__main__":
    verify_operations()
