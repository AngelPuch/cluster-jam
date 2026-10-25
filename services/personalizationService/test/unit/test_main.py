"""Verify safe failure before binding a misconfigured HTTP server."""

import json

import pytest
import uvicorn

import personalization.main as entrypoint
from personalization.infrastructure.config.settings import Settings


def test_invalid_configuration_stops_before_server_start(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    def invalid_settings() -> Settings:
        return Settings.model_validate({"APP_ENV": "private-config-input"})

    def unexpected_server_call(*args: object, **kwargs: object) -> None:
        raise AssertionError("A misconfigured process must not start a server")

    monkeypatch.setenv("APP_ENV", "private-environment")
    monkeypatch.setattr(entrypoint, "Settings", invalid_settings)
    monkeypatch.setattr(uvicorn, "run", unexpected_server_call)
    with pytest.raises(SystemExit) as stopped:
        entrypoint.main()
    assert stopped.value.code == 2
    captured = capsys.readouterr()
    event = json.loads(captured.out)
    assert event["code"] == "CONFIGURATION_INVALID"
    assert event["environment"] == "unknown"
    assert "private" not in captured.out + captured.err
    assert captured.err == ""
