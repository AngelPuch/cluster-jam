"""Prepare Profile-only secrets using the already provisioned shared staging PKI."""

import importlib.util
import os
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[2]
PROFILE = ROOT / "infra" / "profile"
SPEC = importlib.util.spec_from_file_location(
    "cluster_profile_shared_prepare", ROOT / "infra" / "deploy" / "prepare.py"
)
assert SPEC and SPEC.loader
SHARED_PREPARE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(SHARED_PREPARE)


def prepare() -> None:
    shared = SHARED_PREPARE.SHARED
    for path in (
        shared / ".pki" / "ca.crt",
        shared / ".pki" / "ca.key",
        shared / ".secrets" / "rabbitmq_profile_password",
    ):
        if not path.is_file() or path.is_symlink():
            raise ValueError("Provision the shared staging PKI and broker first")
    SHARED_PREPARE.prepare_ca()
    for name in (".secrets", ".certificates"):
        SHARED_PREPARE.private_directory(PROFILE / name)
    for name in (
        "postgres_admin_password",
        "profile_db_password",
        "profile_db_migration_password",
    ):
        SHARED_PREPARE.secret(PROFILE, name)
    SHARED_PREPARE.leaf("profile-db", ["DNS:db-profile"], False)
    SHARED_PREPARE.save(
        PROFILE / ".secrets" / "profile-db.key",
        (shared / ".pki" / "profile-db.key").read_bytes(),
    )
    SHARED_PREPARE.save(
        PROFILE / ".certificates" / "profile-db.crt",
        (shared / ".pki" / "profile-db.crt").read_bytes(),
        0o644,
    )
    SHARED_PREPARE.save(
        PROFILE / ".certificates" / "profile-db-ca.crt",
        (shared / ".pki" / "ca.crt").read_bytes(),
        0o644,
    )
    password = (shared / ".secrets" / "rabbitmq_profile_password").read_text().strip()
    if not password or "\n" in password or "\r" in password:
        raise ValueError("Shared consumer secret is invalid")
    uri = (
        "amqps://profile-consumer:"
        + quote(password, safe="")
        + "@clusterjam-rabbitmq:5671/clusterjam\n"
    )
    SHARED_PREPARE.save(PROFILE / ".secrets" / "profile_rabbitmq_uri", uri.encode())


if __name__ == "__main__":
    try:
        if os.name != "posix":
            raise ValueError("Prepare deployment inside Ubuntu")
        os.umask(0o077)
        prepare()
    except (OSError, ValueError):
        raise SystemExit(
            "Profile preparation failed; check the shared PKI/broker and private directories. No secret values were logged."
        )
    print("Profile secrets and PostgreSQL TLS ready; existing credentials preserved.")
