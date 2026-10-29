"""Prepare deployment secrets and a private staging PKI on Ubuntu."""

import argparse
import base64
import getpass
import hashlib
import hmac
import ipaddress
import json
import os
import re
import secrets
import subprocess
from pathlib import Path
from urllib.parse import parse_qs, quote, urlsplit

BASE = Path(__file__).resolve().parent.parent
SHARED = BASE / "shared"
AUTH = BASE / "auth"


def openssl(*arguments: str) -> bytes:
    """Keep OpenSSL diagnostics and private material off console logs."""
    result = subprocess.run(
        ["openssl", *arguments], capture_output=True, check=False
    )
    if result.returncode:
        raise ValueError("Certificate operation failed")
    return result.stdout


def private_directory(path: Path) -> None:
    if path.is_symlink():
        raise ValueError("Deployment directories must not be symlinks")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)


def save(path: Path, value: bytes, mode: int = 0o444) -> None:
    """Preserve unchanged files and mounted inodes when updating content."""
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ValueError("Deployment files must be regular files")
    if path.exists() and path.read_bytes() == value:
        path.chmod(mode)
        return
    if path.exists():
        path.chmod(0o600)
    with path.open("wb") as stream:
        os.chmod(path, 0o600)
        stream.write(value)
        stream.flush()
        os.fsync(stream.fileno())
    path.chmod(mode)


def secret(directory: Path, name: str, *, prompt: str | None = None) -> str:
    path = directory / ".secrets" / name
    if path.is_symlink():
        raise ValueError("Secrets must not be symlinks")
    if path.exists():
        if not path.is_file():
            raise ValueError("Secrets must be regular files")
        value = path.read_text(encoding="utf-8").strip()
    else:
        value = (
            getpass.getpass(prompt).strip()
            if prompt
            else (secrets.token_urlsafe(32))
        )
    if not value or "\n" in value or "\r" in value:
        raise ValueError("A required secret is empty or invalid")
    save(path, (value + "\n").encode())
    return value


def password_hash(password: str, old: str | None = None) -> str:
    if old is not None:
        try:
            decoded = base64.b64decode(old, validate=True)
            candidate = hashlib.sha256(
                decoded[:4] + password.encode()
            ).digest()
            if len(decoded) == 36 and hmac.compare_digest(
                decoded[4:], candidate
            ):
                return old
        except ValueError:
            pass
    salt = secrets.token_bytes(4)
    digest = hashlib.sha256(salt + password.encode()).digest()
    return base64.b64encode(salt + digest).decode()


def prepare_definitions() -> None:
    target = SHARED / ".secrets" / "rabbitmq_definitions.json"
    previous = json.loads(target.read_text()) if target.exists() else {}
    previous_hashes = {
        row["name"]: row["password_hash"] for row in previous.get("users", [])
    }
    identities = (
        ("clusterjam-admin", "rabbitmq_admin_password", ["administrator"]),
        ("auth-publisher", "rabbitmq_auth_password", []),
        ("profile-consumer", "rabbitmq_profile_password", []),
    )
    users = []
    publisher_password = ""
    for name, file, tags in identities:
        password = secret(SHARED, file)
        if name == "auth-publisher":
            publisher_password = password
        users.append(
            {
                "name": name,
                "password_hash": password_hash(
                    password, previous_hashes.get(name)
                ),
                "hashing_algorithm": "rabbit_password_hashing_sha256",
                "tags": tags,
            }
        )
    queue = "profile.identity.user-registered.v1"
    definitions = {
        "users": users,
        "vhosts": [{"name": "clusterjam", "default_queue_type": "classic"}],
        "permissions": [
            {
                "user": "clusterjam-admin",
                "vhost": "clusterjam",
                "configure": ".*",
                "write": ".*",
                "read": ".*",
            },
            {
                "user": "auth-publisher",
                "vhost": "clusterjam",
                "configure": r"^identity\.events$",
                "write": r"^identity\.events$",
                "read": "^$",
            },
            {
                "user": "profile-consumer",
                "vhost": "clusterjam",
                "configure": r"^profile\.identity\.user-registered\.v1$",
                "write": "^$",
                "read": r"^profile\.identity\.user-registered\.v1$",
            },
        ],
        "exchanges": [
            {
                "name": "identity.events",
                "vhost": "clusterjam",
                "type": "topic",
                "durable": True,
                "auto_delete": False,
                "internal": False,
                "arguments": {},
            }
        ],
        "queues": [
            {
                "name": queue,
                "vhost": "clusterjam",
                "durable": True,
                "auto_delete": False,
                "arguments": {},
            }
        ],
        "bindings": [
            {
                "source": "identity.events",
                "vhost": "clusterjam",
                "destination": queue,
                "destination_type": "queue",
                "routing_key": "identity.user.registered.v1",
                "arguments": {},
            }
        ],
    }
    save(target, (json.dumps(definitions, indent=2) + "\n").encode())
    url = (
        "amqps://auth-publisher:"
        + quote(publisher_password, safe="")
        + "@clusterjam-rabbitmq:5671/clusterjam"
    )
    save(AUTH / ".secrets" / "auth_rabbitmq_url", (url + "\n").encode())


def prepare_ca() -> None:
    key = SHARED / ".pki" / "ca.key"
    certificate = SHARED / ".pki" / "ca.crt"
    if key.exists() != certificate.exists():
        raise ValueError("Restore the existing CA pair before continuing")
    if not key.exists():
        openssl(
            "genpkey",
            "-algorithm",
            "RSA",
            "-pkeyopt",
            "rsa_keygen_bits:3072",
            "-out",
            str(key),
        )
        key.chmod(0o600)
        openssl(
            "req",
            "-new",
            "-x509",
            "-key",
            str(key),
            "-sha256",
            "-days",
            "3650",
            "-subj",
            "/CN=ClusterJAM Staging CA",
            "-addext",
            "basicConstraints=critical,CA:TRUE,pathlen:0",
            "-addext",
            "keyUsage=critical,keyCertSign,cRLSign",
            "-out",
            str(certificate),
        )
    if openssl("pkey", "-in", str(key), "-pubout") != openssl(
        "x509", "-in", str(certificate), "-noout", "-pubkey"
    ):
        raise ValueError("CA key and certificate do not match")
    openssl("x509", "-in", str(certificate), "-checkend", "2592000", "-noout")
    key.chmod(0o600)
    certificate.chmod(0o644)


def leaf(name: str, names: list[str], renew: bool) -> None:
    directory = SHARED / ".pki"
    key = directory / f"{name}.key"
    certificate = directory / f"{name}.crt"
    if certificate.exists() and key.exists() and not renew:
        if openssl("pkey", "-in", str(key), "-pubout") != openssl(
            "x509", "-in", str(certificate), "-noout", "-pubkey"
        ):
            raise ValueError("Server key and certificate do not match")
        key.chmod(0o444)
        openssl(
            "verify", "-CAfile", str(directory / "ca.crt"), str(certificate)
        )
        openssl(
            "x509", "-in", str(certificate), "-checkend", "604800", "-noout"
        )
        for entry in names:
            kind, value = entry.split(":", 1)
            openssl(
                "verify",
                "-CAfile",
                str(directory / "ca.crt"),
                "-verify_ip" if kind == "IP" else "-verify_hostname",
                value,
                str(certificate),
            )
        return
    csr = directory / f"{name}.csr"
    extensions = directory / f"{name}.ext"
    temporary_key = directory / f"{name}.new.key"
    temporary_certificate = directory / f"{name}.new.crt"
    openssl(
        "req",
        "-new",
        "-newkey",
        "rsa:3072",
        "-nodes",
        "-sha256",
        "-keyout",
        str(temporary_key),
        "-out",
        str(csr),
        "-subj",
        f"/CN={name}",
    )
    extensions.write_text(
        "basicConstraints=critical,CA:FALSE\n"
        "keyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        "subjectKeyIdentifier=hash\nauthorityKeyIdentifier=keyid,issuer\n"
        "subjectAltName="
        + ",".join(names)
        + "\n",
        encoding="utf-8",
    )
    openssl(
        "x509",
        "-req",
        "-in",
        str(csr),
        "-CA",
        str(directory / "ca.crt"),
        "-CAkey",
        str(directory / "ca.key"),
        "-set_serial",
        "0x" + secrets.token_hex(16),
        "-days",
        "365",
        "-sha256",
        "-extfile",
        str(extensions),
        "-out",
        str(temporary_certificate),
    )
    save(key, temporary_key.read_bytes())
    save(certificate, temporary_certificate.read_bytes(), 0o644)
    for file in (csr, extensions, temporary_key, temporary_certificate):
        file.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--supabase-ca", type=Path)
    parser.add_argument("--renew-certificates", action="store_true")
    arguments = parser.parse_args()
    os.umask(0o077)
    try:
        if os.name != "posix":
            raise ValueError("Run this preparation inside Ubuntu")
        configuration = {}
        for directory in (SHARED, AUTH):
            current = {}
            for line in (directory / ".env").read_text().splitlines():
                if line.strip() and not line.lstrip().startswith("#"):
                    name, value = line.split("=", 1)
                    current[name] = value.strip()
            if current.get("APP_ENV") != "staging":
                raise ValueError("Each configuration requires APP_ENV=staging")
            configuration.update(current)
        if configuration.get("APP_ENV") != "staging":
            raise ValueError("This deployment expects APP_ENV=staging")
        origin = configuration["SUPABASE_URL"].rstrip("/")
        if not re.fullmatch(r"https://[a-z0-9-]+\.supabase\.co", origin):
            raise ValueError("Configure the Supabase Cloud project URL")
        if "project-id" in origin:
            raise ValueError("Replace the public configuration template")
        if configuration["SUPABASE_JWKS_URL"] != (
            origin + "/auth/v1/.well-known/jwks.json"
        ):
            raise ValueError("Supabase JWKS and project must match")
        addresses = [
            str(ipaddress.ip_address(value.strip()))
            for value in configuration["TLS_IPS"].split(",")
        ]
        for directory in (SHARED / ".secrets", SHARED / ".pki", AUTH / ".secrets", AUTH / ".certificates"):
            private_directory(directory)
        ca_path = AUTH / ".certificates" / "supabase-ca.crt"
        if arguments.supabase_ca is not None:
            content = arguments.supabase_ca.read_bytes()
            if b"PRIVATE KEY" in content:
                raise ValueError("Provide only the public Supabase CA")
            openssl("x509", "-in", str(arguments.supabase_ca), "-noout")
            save(ca_path, content, 0o644)
        openssl("x509", "-in", str(ca_path), "-noout")
        save(
            AUTH / ".certificates" / "supabase-trust.pem",
            ca_path.read_bytes().rstrip()
            + b"\n"
            + Path("/etc/ssl/certs/ca-certificates.crt").read_bytes(),
            0o644,
        )
        secret(
            AUTH, "auth_supabase_publishable_key",
            prompt="Supabase publishable key: ",
        )
        database = secret(
            AUTH, "auth_outbox_database_url",
            prompt="Dedicated outbox PostgreSQL URL: ",
        )
        parsed = urlsplit(database)
        if parsed.scheme not in {"postgres", "postgresql"}:
            raise ValueError("Outbox URL must be PostgreSQL")
        if set(parse_qs(parsed.query, keep_blank_values=True)) & {
            "sslmode",
            "sslrootcert",
            "sslcert",
            "sslkey",
        }:
            raise ValueError("Configure outbox TLS through the mounted CA")
        prepare_definitions()
        prepare_ca()
        renew = arguments.renew_certificates
        leaf(
            "https",
            ["DNS:clusterjam.test", "DNS:localhost"]
            + ["IP:" + value for value in addresses],
            renew,
        )
        leaf("rabbitmq", ["DNS:rabbitmq", "DNS:clusterjam-rabbitmq"], renew)
        leaf(
            "personalization-grpc",
            ["DNS:personalization-grpc", "DNS:clusterjam-personalization-grpc"],
            renew,
        )
        if renew:
            save(SHARED / ".pki" / "recreate-required", b"renewed\n", 0o600)
    except (OSError, ValueError, KeyError):
        print(
            "Deployment preparation failed. Check public configuration, "
            "certificates and required secrets; no secret values were logged."
        )
        return 1
    except (KeyboardInterrupt, EOFError):
        return 130
    print("Deployment configuration, secrets and certificates are ready.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
