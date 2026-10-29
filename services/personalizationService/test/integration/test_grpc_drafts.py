"""Read PostgreSQL snapshots through protobuf over a real TLS socket."""

import os
from collections.abc import Callable

import grpc
import pytest
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy import Engine, func, select
from sqlalchemy.orm import Session

from personalization.application.designs.draft_service import DraftService
from personalization.infrastructure.database.design_repository import (
    SqlAlchemyDesignRepository,
)
from personalization.infrastructure.database.models.application import (
    ApplicationModel,
)
from personalization.infrastructure.database.models.audit_entry import (
    AuditEntryModel,
)
from personalization.infrastructure.database.models.design import DesignModel
from personalization.infrastructure.database.template_repository import (
    SqlAlchemyTemplateRepository,
)
from personalization.infrastructure.security.development_tls import (
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
from personalization.interfaces.http.design_drafts.preconditions import (
    draft_etag,
)
from test.files.fakes import BUCKET
from test.integration.test_design_drafts import DraftSeed
from test.integration.test_design_drafts import draft_seed as draft_seed
from test.integration.test_print_versioning import seed as seed
from test.integration.test_templates import series as series
from test.security.conftest import claims as claims
from test.security.conftest import jwks_transport as jwks_transport
from test.security.conftest import sign_token as sign_token
from test.security.conftest import signing_keys as signing_keys

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(
        os.environ.get("PERSONALIZATION_DATABASE_INTEGRATION") != "1",
        reason="Requires the disposable PostgreSQL integration database",
    ),
]


def row_counts(engine: Engine) -> tuple[int, ...]:
    with Session(engine) as session:
        return tuple(
            session.scalar(select(func.count()).select_from(model)) or 0
            for model in (DesignModel, ApplicationModel, AuditEntryModel)
        )


def test_grpc_reads_owned_snapshot_and_preserves_all_rows(
    engine: Engine,
    draft_seed: DraftSeed,
    sign_token: Callable[..., str],
    claims: dict[str, object],
    jwks_transport: object,
) -> None:
    repository = SqlAlchemyDesignRepository(engine, BUCKET)
    draft = repository.create(draft_seed.owner_id, draft_seed.content)
    before = row_counts(engine)
    provider = TracerProvider()
    tls = create_development_tls()
    bound = create_server(
        DraftServicer(
            DraftService(repository, SqlAlchemyTemplateRepository(engine)),
            SupabaseJwtVerifier(
                "https://supabase.example.test/auth/v1",
                "https://supabase.example.test/auth/v1/.well-known/jwks.json",
            ),
            provider.get_tracer("test.grpc.postgres"),
        ),
        tls.server,
        "127.0.0.1:0",
    )
    channel = grpc.secure_channel(
        f"localhost:{bound.port}",
        grpc.ssl_channel_credentials(tls.root_certificate),
    )

    def serialize(request: pb.GetDesignDraftRequest) -> bytes:
        return request.SerializeToString()

    call = channel.unary_unary(
        "/" + RPC_METHOD,
        request_serializer=serialize,
        response_deserializer=pb.GetDesignDraftResponse.FromString,
    )
    admin = sign_token(
        {
            **claims,
            "sub": str(draft.owner_id),
            "app_metadata": {"app_role": "administrador"},
        }
    )
    try:
        response = call(
            pb.GetDesignDraftRequest(design_id=str(draft.id)),
            metadata=(("authorization", "Bearer " + admin),),
            timeout=5,
        )
        assert response.design.id == str(
            draft.id
        ) and response.etag == draft_etag(draft)
        assert response.design.applications[0].print_version_id == str(
            draft.content.applications[0].print_version_id
        )
        assert response.checkout_readiness == pb.CHECKOUT_BLOCKED
        with pytest.raises(grpc.RpcError) as denied:
            call(
                pb.GetDesignDraftRequest(design_id=str(draft.id)),
                metadata=(("authorization", "Bearer " + sign_token()),),
                timeout=5,
            )
        assert denied.value.code() == grpc.StatusCode.PERMISSION_DENIED
        assert row_counts(engine) == before
        assert repository.get(draft.owner_id, draft.id) == draft
    finally:
        channel.close()
        bound.close()
        provider.shutdown()
