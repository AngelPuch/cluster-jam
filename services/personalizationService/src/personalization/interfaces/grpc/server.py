"""Serve the administrative protobuf contract over TLS only."""

import logging
import signal
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from threading import Event
from types import FrameType

import grpc
from opentelemetry.sdk.trace import TracerProvider
from pydantic import ValidationError

from personalization.application.designs.draft_service import DraftService
from personalization.infrastructure.config.settings import Settings
from personalization.infrastructure.database.design_repository import (
    SqlAlchemyDesignRepository,
)
from personalization.infrastructure.database.engine import (
    create_database_engine,
)
from personalization.infrastructure.database.template_repository import (
    SqlAlchemyTemplateRepository,
)
from personalization.infrastructure.observability.logging_config import (
    configure_logging,
)
from personalization.infrastructure.security.grpc_tls import (
    TlsConfigurationError,
    TlsMaterial,
    load_tls,
)
from personalization.infrastructure.security.supabase_jwt_verifier import (
    SupabaseJwtVerifier,
)
from personalization.interfaces.grpc.draft_servicer import (
    SERVICE_NAME,
    DraftServicer,
)
from personalization.interfaces.grpc.generated import personalization_pb2 as pb


@dataclass
class BoundServer:
    server: grpc.Server = field(repr=False)
    executor: ThreadPoolExecutor = field(repr=False)
    port: int

    def close(self) -> None:
        self.server.stop(5).wait(10)
        self.executor.shutdown(wait=True, cancel_futures=True)


def create_server(
    servicer: DraftServicer, tls: TlsMaterial, address: str
) -> BoundServer:
    executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="grpc")
    server = grpc.server(
        executor,
        maximum_concurrent_rpcs=16,
        options=[
            ("grpc.max_receive_message_length", 65_536),
            ("grpc.max_send_message_length", 65_536),
            ("grpc.max_metadata_size", 16_384),
            ("grpc.so_reuseport", 0),
        ],
    )
    handler = grpc.unary_unary_rpc_method_handler(
        servicer.get_design_draft,
        request_deserializer=pb.GetDesignDraftRequest.FromString,
        response_serializer=pb.GetDesignDraftResponse.SerializeToString,
    )
    server.add_generic_rpc_handlers(
        (
            grpc.method_handlers_generic_handler(
                SERVICE_NAME, {"GetDesignDraft": handler}
            ),
        )
    )
    try:
        port = server.add_secure_port(address, tls.credentials())
        if not port:
            raise TlsConfigurationError
        server.start()
        return BoundServer(server, executor, port)
    except Exception:
        server.stop(0).wait(5)
        executor.shutdown(wait=True, cancel_futures=True)
        raise


def main() -> int:
    try:
        settings = Settings()
        tls = load_tls(
            settings.grpc_tls_certificate_file, settings.grpc_tls_key_file
        )
    except (ValidationError, TlsConfigurationError) as error:
        configure_logging(environment="unknown", log_level="ERROR")
        logging.getLogger("personalization.grpc").error(
            "gRPC configuration is invalid",
            extra={
                "event": "grpc.configuration.invalid",
                "code": "CONFIGURATION_INVALID"
                if isinstance(error, ValidationError)
                else "TLS_CONFIGURATION_INVALID",
            },
        )
        return 2
    configure_logging(
        environment=settings.app_env, log_level=settings.log_level
    )
    logger = logging.getLogger("personalization.grpc")
    engine = create_database_engine(settings)
    provider = TracerProvider()
    stop = Event()

    def request_stop(signum: int, frame: FrameType | None) -> None:
        stop.set()

    previous = {
        signum: signal.signal(signum, request_stop)
        for signum in (signal.SIGINT, signal.SIGTERM)
    }
    bound: BoundServer | None = None
    try:
        bound = create_server(
            DraftServicer(
                DraftService(
                    SqlAlchemyDesignRepository(
                        engine, settings.storage_bucket
                    ),
                    SqlAlchemyTemplateRepository(engine),
                ),
                SupabaseJwtVerifier(
                    str(settings.supabase_issuer),
                    str(settings.supabase_jwks_url),
                ),
                provider.get_tracer("personalization.grpc"),
            ),
            tls,
            f"{settings.grpc_host}:{settings.grpc_port}",
        )
        logger.info("gRPC server started", extra={"event": "grpc.started"})
        stop.wait()
        return 0
    except Exception:
        logger.error(
            "gRPC server cannot start",
            extra={"event": "grpc.failed", "code": "GRPC_START_FAILED"},
        )
        return 1
    finally:
        if bound is not None:
            bound.close()
        engine.dispose()
        provider.shutdown()
        for signum, previous_handler in previous.items():
            signal.signal(signum, previous_handler)
        logger.info("gRPC server stopped", extra={"event": "grpc.stopped"})


if __name__ == "__main__":
    raise SystemExit(main())
