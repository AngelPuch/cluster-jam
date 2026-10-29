"""Run a real TLS gRPC socket with fake data ports and signed JWTs."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from uuid import UUID, uuid4

import grpc
import pytest
from opentelemetry.sdk.trace import TracerProvider

from personalization.application.designs.draft_record import (
    DraftContent,
    DraftRecord,
)
from personalization.application.designs.draft_service import DraftService
from personalization.infrastructure.security.development_tls import (
    DevelopmentTls,
    create_development_tls,
)
from personalization.infrastructure.security.supabase_jwt_verifier import (
    SupabaseJwtVerifier,
)
from personalization.interfaces.grpc.draft_servicer import (
    RPC_METHOD,
    DraftServicer,
)
from personalization.interfaces.grpc.generated import personalization_pb2 as pb
from personalization.interfaces.grpc.server import create_server
from test.designs.draft_fakes import MemoryDesignRepository
from test.designs.fakes import analysis_data
from test.security.conftest import claims as claims
from test.security.conftest import jwks_transport as jwks_transport
from test.security.conftest import sign_token as sign_token
from test.security.conftest import signing_keys as signing_keys


@dataclass
class RpcData:
    channel: grpc.Channel
    call: grpc.UnaryUnaryMultiCallable[
        pb.GetDesignDraftRequest, pb.GetDesignDraftResponse
    ]
    draft: DraftRecord
    repository: MemoryDesignRepository
    tls: DevelopmentTls
    port: int


@pytest.fixture
def rpc(jwks_transport: object) -> Iterator[RpcData]:
    source = analysis_data()
    repository = MemoryDesignRepository()
    draft = repository.create(
        UUID("11111111-1111-4111-8111-111111111111"),
        DraftContent(uuid4(), source.template.header.id, source.selections),
    )
    provider = TracerProvider()
    tls = create_development_tls()
    bound = create_server(
        DraftServicer(
            DraftService(repository, source.templates),
            SupabaseJwtVerifier(
                "https://supabase.example.test/auth/v1",
                "https://supabase.example.test/auth/v1/.well-known/jwks.json",
            ),
            provider.get_tracer("test.grpc"),
        ),
        tls.server,
        "127.0.0.1:0",
    )
    channel = grpc.secure_channel(
        f"localhost:{bound.port}",
        grpc.ssl_channel_credentials(root_certificates=tls.root_certificate),
    )

    def serialize(request: pb.GetDesignDraftRequest) -> bytes:
        return request.SerializeToString()

    call = channel.unary_unary(
        "/" + RPC_METHOD,
        request_serializer=serialize,
        response_deserializer=pb.GetDesignDraftResponse.FromString,
    )
    try:
        grpc.channel_ready_future(channel).result(timeout=5)
        yield RpcData(channel, call, draft, repository, tls, bound.port)
    finally:
        channel.close()
        bound.close()
        provider.shutdown()
