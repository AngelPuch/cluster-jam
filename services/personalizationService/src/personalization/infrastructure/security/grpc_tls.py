"""Load bounded server TLS files without retaining secrets in repr."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import grpc
from cryptography import x509
from cryptography.exceptions import UnsupportedAlgorithm
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec, rsa
from cryptography.x509.oid import ExtendedKeyUsageOID


class TlsConfigurationError(Exception):
    def __init__(self) -> None:
        super().__init__("TLS_CONFIGURATION_INVALID")


@dataclass(frozen=True)
class TlsMaterial:
    certificate: bytes = field(repr=False)
    private_key: bytes = field(repr=False)

    def credentials(self) -> grpc.ServerCredentials:
        return grpc.ssl_server_credentials(
            [(self.private_key, self.certificate)]
        )


def validate_tls(certificate: bytes, private_key: bytes) -> TlsMaterial:
    try:
        if (
            not 1 <= len(certificate) <= 65_536
            or not 1 <= len(private_key) <= 16_384
        ):
            raise ValueError
        chain = x509.load_pem_x509_certificates(certificate)
        if not chain:
            raise ValueError
        now = datetime.now(UTC)
        if any(
            not item.not_valid_before_utc <= now < item.not_valid_after_utc
            for item in chain
        ):
            raise ValueError
        leaf = chain[0]
        leaf.extensions.get_extension_for_class(x509.AuthorityKeyIdentifier)
        for item in chain[1:]:
            item.extensions.get_extension_for_class(x509.SubjectKeyIdentifier)
        if leaf.extensions.get_extension_for_class(
            x509.BasicConstraints
        ).value.ca:
            raise ValueError
        if (
            ExtendedKeyUsageOID.SERVER_AUTH
            not in leaf.extensions.get_extension_for_class(
                x509.ExtendedKeyUsage
            ).value
        ):
            raise ValueError
        if not leaf.extensions.get_extension_for_class(
            x509.SubjectAlternativeName
        ).value:
            raise ValueError
        key = serialization.load_pem_private_key(private_key, password=None)
        if not isinstance(
            key, (ec.EllipticCurvePrivateKey, rsa.RSAPrivateKey)
        ):
            raise ValueError
        encoding = serialization.Encoding.DER
        kind = serialization.PublicFormat.SubjectPublicKeyInfo
        if key.public_key().public_bytes(
            encoding, kind
        ) != leaf.public_key().public_bytes(encoding, kind):
            raise ValueError
        return TlsMaterial(certificate, private_key)
    except ValueError, TypeError, UnsupportedAlgorithm, x509.ExtensionNotFound:
        raise TlsConfigurationError from None


def load_tls(
    certificate_file: Path | None, key_file: Path | None
) -> TlsMaterial:
    if certificate_file is None or key_file is None:
        raise TlsConfigurationError
    try:
        with certificate_file.open("rb") as stream:
            certificate = stream.read(65_537)
        with key_file.open("rb") as stream:
            key = stream.read(16_385)
        return validate_tls(certificate, key)
    except OSError:
        raise TlsConfigurationError from None
