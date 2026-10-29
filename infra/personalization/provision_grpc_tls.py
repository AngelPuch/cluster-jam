"""Provision development TLS without replacing existing certificates."""

import os
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes

from personalization.infrastructure.security.development_tls import (
    create_development_tls,
)
from personalization.infrastructure.security.grpc_tls import load_tls


def provision_tls(directory: Path) -> None:
    if directory.is_symlink():
        raise ValueError("The secret directory must not be a symlink")
    directory.mkdir(mode=0o700, parents=True, exist_ok=True)
    names = ("grpc_server_cert.pem", "grpc_server_key.pem", "grpc_ca.crt")
    paths = [directory / name for name in names]
    if any(
        path.is_symlink() or (path.exists() and not path.is_file())
        for path in paths
    ):
        raise ValueError("TLS files must be regular files")
    if any(path.exists() for path in paths):
        if not all(path.exists() for path in paths):
            raise ValueError("Existing development TLS bundle is incomplete")
        load_tls(paths[0], paths[1])
        with paths[2].open("rb") as stream:
            root_bytes = stream.read(65_537)
        if not 1 <= len(root_bytes) <= 65_536:
            raise ValueError("The existing development CA is invalid")
        root = x509.load_pem_x509_certificate(root_bytes)
        chain = x509.load_pem_x509_certificates(paths[0].read_bytes())
        if root.fingerprint(hashes.SHA256()) != chain[-1].fingerprint(
            hashes.SHA256()
        ):
            raise ValueError("The development CA does not match the chain")
        return
    bundle = create_development_tls()
    values = (
        bundle.server.certificate,
        bundle.server.private_key,
        bundle.root_certificate,
    )
    for path, value in zip(paths, values, strict=True):
        with path.open("xb") as stream:
            stream.write(value)
        if os.name == "posix":
            path.chmod(0o444)


if __name__ == "__main__":
    if os.environ.get("APP_ENV") == "production":
        raise SystemExit(
            "Development certificates cannot be provisioned for production"
        )
    provision_tls(Path(__file__).resolve().parent / ".secrets")
    print("Development TLS ready; files preserved. CA: .secrets/grpc_ca.crt")
