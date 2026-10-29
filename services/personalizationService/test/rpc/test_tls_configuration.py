"""Verify fail-closed TLS configuration and deterministic codegen."""

import json
from datetime import datetime, timedelta, tzinfo
from pathlib import Path

import pytest

from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.security import grpc_tls
from personalization.infrastructure.security.development_tls import (
    create_development_tls,
)
from personalization.infrastructure.security.grpc_tls import (
    TlsConfigurationError,
    load_tls,
    validate_tls,
)
from personalization.interfaces.grpc import server as entrypoint
from test.e2e.conftest import http_settings as http_settings
from test.rpc.conftest import RpcData


def test_tls_bytes_and_paths_are_validated_without_secret_reprs(
    tmp_path: Path,
) -> None:
    tls = create_development_tls()
    assert "PRIVATE KEY" not in repr(tls)
    assert "CERTIFICATE" not in repr(tls)
    certificate = tmp_path / "server.pem"
    key = tmp_path / "server.key"
    certificate.write_bytes(tls.server.certificate)
    key.write_bytes(tls.server.private_key)
    assert load_tls(certificate, key) == tls.server
    assert tls.server.credentials() is not None
    with pytest.raises(TlsConfigurationError):
        load_tls(None, None)
    with pytest.raises(TlsConfigurationError):
        load_tls(tmp_path / "missing", key)
    wrong_key = create_development_tls().server.private_key
    with pytest.raises(TlsConfigurationError):
        validate_tls(tls.server.certificate, wrong_key)


@pytest.mark.parametrize(
    "certificate,key",
    [
        (b"", b""),
        (b"private-data", b"secret"),
        (b"x" * 65_537, b"key"),
        (b"cert", b"x" * 16_385),
    ],
    ids=["empty", "malformed", "oversized-cert", "oversized-key"],
)
def test_invalid_or_oversized_tls_is_sanitized(
    certificate: bytes, key: bytes
) -> None:
    with pytest.raises(TlsConfigurationError) as error:
        validate_tls(certificate, key)
    assert str(error.value) == "TLS_CONFIGURATION_INVALID"


def test_expired_chain_is_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    tls = create_development_tls()

    class FutureTime:
        @staticmethod
        def now(zone: tzinfo | None = None) -> datetime:
            return datetime.now(zone) + timedelta(days=32)

    monkeypatch.setattr(grpc_tls, "datetime", FutureTime)
    with pytest.raises(TlsConfigurationError):
        validate_tls(tls.server.certificate, tls.server.private_key)


@pytest.mark.parametrize("bad_settings", [True, False])
def test_entrypoint_rejects_bad_settings_or_absent_tls_before_binding(
    http_settings: Settings,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    bad_settings: bool,
) -> None:
    def settings() -> Settings:
        return (
            Settings.model_validate({"APP_ENV": "private-input"})
            if bad_settings
            else http_settings
        )

    def unexpected(*args: object, **kwargs: object) -> None:
        raise AssertionError("A misconfigured server cannot bind a port")

    monkeypatch.setattr(entrypoint, "Settings", settings)
    monkeypatch.setattr(entrypoint, "create_server", unexpected)
    assert entrypoint.main() == 2
    output = capsys.readouterr()
    event = json.loads(output.out)
    assert event["code"] == (
        "CONFIGURATION_INVALID"
        if bad_settings
        else "TLS_CONFIGURATION_INVALID"
    )
    assert "private-input" not in output.out + output.err


def test_health_probe_verifies_full_tls_chain_and_h2(
    rpc: RpcData,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from personalization.interfaces.grpc import health

    ca = tmp_path / "ca.crt"
    ca.write_bytes(rpc.tls.root_certificate)
    monkeypatch.setenv("GRPC_HEALTH_CA_FILE", str(ca))
    monkeypatch.setenv("GRPC_PORT", str(rpc.port))
    assert health.main() == 0
    ca.write_bytes(create_development_tls().root_certificate)
    assert health.main() == 1
