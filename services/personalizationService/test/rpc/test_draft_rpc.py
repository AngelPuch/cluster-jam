"""Exercise protobuf, TLS, JWT ownership, limits and safe RPC errors."""

from collections.abc import Callable
from dataclasses import replace
from uuid import uuid4

import grpc
import pytest

from personalization.application.errors.design_error import DesignFailure
from personalization.infrastructure.security.development_tls import (
    create_development_tls,
)
from personalization.interfaces.grpc.draft_servicer import RPC_METHOD
from personalization.interfaces.grpc.generated import personalization_pb2 as pb
from personalization.interfaces.http.design_drafts.preconditions import (
    draft_etag,
)
from test.rpc.conftest import RpcData


def error_metadata(error: grpc.RpcError) -> dict[str, str | bytes]:
    return {item.key: item.value for item in error.trailing_metadata()}


def admin_token(sign: Callable[..., str], claims: dict[str, object]) -> str:
    return sign({**claims, "app_metadata": {"app_role": "administrador"}})


def test_own_snapshot_etag_source_oneof_and_local_jwks_cache(
    rpc: RpcData,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: object,
) -> None:
    token = admin_token(sign_token, claims)
    trace_id = "4bf92f3577b34da6a3ce929d0e0e4736"
    headers = (
        ("authorization", "Bearer " + token),
        ("traceparent", f"00-{trace_id}-00f067aa0ba902b7-01"),
    )
    response, transport = rpc.call.with_call(
        pb.GetDesignDraftRequest(design_id=str(rpc.draft.id)),
        metadata=headers,
        timeout=5,
    )
    assert response.design.id == str(rpc.draft.id)
    assert response.design.owner_id == str(rpc.draft.owner_id)
    assert response.etag == draft_etag(rpc.draft)
    assert response.catalog_validation == pb.CATALOG_VALIDATION_PENDING
    assert response.checkout_readiness == pb.CHECKOUT_BLOCKED
    assert response.diagnostic_only is True
    assert not response.design.HasField("front_preview_id")
    assert {
        app.WhichOneof("source") for app in response.design.applications
    } == {"file_id", "print_version_id"}
    assert dict(transport.trailing_metadata())["trace-id"] == trace_id
    assert dict(transport.trailing_metadata())["error-code"] == "OK"
    changed = replace(
        rpc.draft, front_preview_id=uuid4(), back_preview_id=uuid4()
    )
    rpc.repository.records[changed.id] = changed
    second = rpc.call(
        pb.GetDesignDraftRequest(design_id=str(changed.id)),
        metadata=headers,
        timeout=5,
    )
    assert second.etag != response.etag and second.design.version == 1
    assert second.design.front_preview_id == str(changed.front_preview_id)
    from test.security.conftest import JwksTransport

    assert (
        isinstance(jwks_transport, JwksTransport) and jwks_transport.calls == 1
    )
    assert len(rpc.repository.audit) == 1


@pytest.mark.parametrize(
    "kind,status,code",
    [
        ("missing", grpc.StatusCode.UNAUTHENTICATED, "INVALID_ACCESS_TOKEN"),
        ("duplicate", grpc.StatusCode.UNAUTHENTICATED, "INVALID_ACCESS_TOKEN"),
        ("malformed", grpc.StatusCode.UNAUTHENTICATED, "INVALID_ACCESS_TOKEN"),
        ("expired", grpc.StatusCode.UNAUTHENTICATED, "INVALID_ACCESS_TOKEN"),
        ("client", grpc.StatusCode.PERMISSION_DENIED, "FORBIDDEN"),
        ("role", grpc.StatusCode.PERMISSION_DENIED, "INVALID_APP_ROLE"),
    ],
)
def test_security_precedes_database_access(
    rpc: RpcData,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    kind: str,
    status: grpc.StatusCode,
    code: str,
) -> None:
    token = admin_token(sign_token, claims)
    if kind == "expired":
        token = sign_token(
            {**claims, "exp": 1, "app_metadata": {"app_role": "administrador"}}
        )
    elif kind == "role":
        token = sign_token({**claims, "app_metadata": {"app_role": "unknown"}})
    elif kind == "client":
        token = sign_token()
    elif kind == "malformed":
        token = "private-token-detail"
    headers = (
        () if kind == "missing" else (("authorization", "Bearer " + token),)
    )
    if kind == "duplicate":
        headers = (*headers, *headers)
    initial = rpc.repository.calls
    with pytest.raises(grpc.RpcError) as error:
        rpc.call(
            pb.GetDesignDraftRequest(design_id=str(rpc.draft.id)),
            metadata=headers,
            timeout=5,
        )
    assert error.value.code() == status
    assert error_metadata(error.value)["error-code"] == code
    assert rpc.repository.calls == initial


@pytest.mark.parametrize(
    "kind,status,code",
    [
        ("other", grpc.StatusCode.PERMISSION_DENIED, "FORBIDDEN"),
        ("unknown", grpc.StatusCode.NOT_FOUND, "DESIGN_NOT_FOUND"),
        ("uuid", grpc.StatusCode.INVALID_ARGUMENT, "INVALID_DESIGN_ID"),
        (
            "no-deadline",
            grpc.StatusCode.INVALID_ARGUMENT,
            "INVALID_RPC_DEADLINE",
        ),
        (
            "long-deadline",
            grpc.StatusCode.INVALID_ARGUMENT,
            "INVALID_RPC_DEADLINE",
        ),
        (
            "database",
            grpc.StatusCode.UNAVAILABLE,
            "DESIGN_DATABASE_UNAVAILABLE",
        ),
    ],
)
def test_domain_failures_and_deadlines_are_sanitized(
    rpc: RpcData,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    kind: str,
    status: grpc.StatusCode,
    code: str,
) -> None:
    payload = {**claims, "app_metadata": {"app_role": "administrador"}}
    if kind == "other":
        payload["sub"] = str(uuid4())
    identifier = (
        str(uuid4())
        if kind == "unknown"
        else "bad"
        if kind == "uuid"
        else str(rpc.draft.id)
    )
    if kind == "database":
        rpc.repository.failure = DesignFailure.DESIGN_DATABASE_UNAVAILABLE
    timeout = (
        None if kind == "no-deadline" else 15 if kind == "long-deadline" else 5
    )
    with pytest.raises(grpc.RpcError) as error:
        rpc.call(
            pb.GetDesignDraftRequest(design_id=identifier),
            timeout=timeout,
            metadata=(("authorization", "Bearer " + sign_token(payload)),),
        )
    assert error.value.code() == status
    assert error_metadata(error.value)["error-code"] == code
    assert len(rpc.repository.audit) == 1


@pytest.mark.parametrize("kind", ["untrusted", "plaintext", "hostname"])
def test_tls_rejects_untrusted_plaintext_or_wrong_hostname(
    rpc: RpcData,
    kind: str,
) -> None:
    initial = rpc.repository.calls
    target = f"127.0.0.1:{rpc.port}"
    if kind == "plaintext":
        channel = grpc.insecure_channel(target)
    else:
        root = (
            create_development_tls().root_certificate
            if kind == "untrusted"
            else rpc.tls.root_certificate
        )
        channel = grpc.secure_channel(
            target,
            grpc.ssl_channel_credentials(root),
            options=[("grpc.ssl_target_name_override", "wrong.invalid")]
            if kind == "hostname"
            else None,
        )
    try:
        call = channel.unary_unary(
            "/" + RPC_METHOD,
            request_serializer=pb.GetDesignDraftRequest.SerializeToString,
            response_deserializer=pb.GetDesignDraftResponse.FromString,
        )
        with pytest.raises(grpc.RpcError) as error:
            call(
                pb.GetDesignDraftRequest(design_id=str(rpc.draft.id)),
                timeout=1,
            )
        assert error.value.code() in {
            grpc.StatusCode.UNAVAILABLE,
            grpc.StatusCode.DEADLINE_EXCEEDED,
        }
        assert rpc.repository.calls == initial
    finally:
        channel.close()


def test_message_limit_and_checkout_method_is_absent(rpc: RpcData) -> None:
    with pytest.raises(grpc.RpcError) as too_large:
        rpc.call(pb.GetDesignDraftRequest(design_id="x" * 70_000), timeout=2)
    assert too_large.value.code() == grpc.StatusCode.RESOURCE_EXHAUSTED
    assert set(
        pb.DESCRIPTOR.services_by_name["PersonalizationDrafts"].methods_by_name
    ) == {"GetDesignDraft"}
    unknown: grpc.UnaryUnaryMultiCallable[bytes, bytes] = (
        rpc.channel.unary_unary(
            "/clusterjam.personalization.v1.PersonalizationDrafts/FreezeDesign"
        )
    )
    with pytest.raises(grpc.RpcError) as unimplemented:
        unknown(b"", timeout=2)
    assert unimplemented.value.code() == grpc.StatusCode.UNIMPLEMENTED


def test_unexpected_error_does_not_log_tokens_or_private_details(
    rpc: RpcData,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import json
    from uuid import UUID

    from personalization.application.designs.draft_record import DraftRecord
    from personalization.infrastructure.observability.logging_config import (
        configure_logging,
    )

    configure_logging(environment="test", log_level="INFO")
    token = admin_token(sign_token, claims)

    def broken(owner_id: UUID, design_id: UUID) -> DraftRecord:
        raise RuntimeError("private-database-detail")

    monkeypatch.setattr(rpc.repository, "get", broken)
    with pytest.raises(grpc.RpcError) as error:
        rpc.call(
            pb.GetDesignDraftRequest(design_id=str(rpc.draft.id)),
            timeout=5,
            metadata=(("authorization", "Bearer " + token),),
        )
    assert error.value.code() == grpc.StatusCode.INTERNAL
    output = capsys.readouterr()
    assert token not in output.out + output.err
    assert "private-database-detail" not in output.out + output.err
    event = json.loads(output.out)
    assert event["event"] == "grpc.request.completed"
    assert (
        event["rpc_status"] == "INTERNAL" and event["code"] == "INTERNAL_ERROR"
    )
    assert event["trace_id"] and event["span_id"]
