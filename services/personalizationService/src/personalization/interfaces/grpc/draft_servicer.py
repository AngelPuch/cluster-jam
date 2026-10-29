"""Map bounded RPC requests to the existing owned-draft use case."""

import logging
from dataclasses import dataclass
from time import perf_counter
from uuid import UUID

import grpc
from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)

from personalization.application.designs.draft_record import DraftRecord
from personalization.application.designs.draft_service import DraftService
from personalization.application.errors.design_error import (
    DesignError,
    DesignFailure,
)
from personalization.application.errors.security_error import (
    SecurityError,
    SecurityFailure,
)
from personalization.application.ports.access_token_verifier_port import (
    AccessTokenVerifierPort,
)
from personalization.application.prints.print_service import (
    require_administrator,
)
from personalization.interfaces.grpc.generated import personalization_pb2 as pb
from personalization.interfaces.http.design_drafts.preconditions import (
    draft_etag,
)

SERVICE_NAME = "clusterjam.personalization.v1.PersonalizationDrafts"
RPC_METHOD = SERVICE_NAME + "/GetDesignDraft"
MAX_DEADLINE_SECONDS = 10


@dataclass(frozen=True)
class RpcRequestError(Exception):
    status: grpc.StatusCode
    code: str
    detail: str


def response_for(draft: DraftRecord) -> pb.GetDesignDraftResponse:
    design = pb.DesignDraft(
        id=str(draft.id),
        owner_id=str(draft.owner_id),
        variant_id=str(draft.variant_id),
        template_id=str(draft.template_id),
        state=draft.state.value,
        version=draft.version,
    )
    if draft.front_preview_id is not None:
        design.front_preview_id = str(draft.front_preview_id)
    if draft.back_preview_id is not None:
        design.back_preview_id = str(draft.back_preview_id)
    for saved in draft.applications:
        item = saved.selection
        application = design.applications.add(
            id=str(saved.id),
            zone_id=str(item.zone_id),
            zone_size_id=str(item.zone_size_id),
        )
        if item.print_version_id is not None:
            application.print_version_id = str(item.print_version_id)
        elif item.file_id is not None:
            application.file_id = str(item.file_id)
    return pb.GetDesignDraftResponse(
        design=design,
        etag=draft_etag(draft),
        catalog_validation=pb.CATALOG_VALIDATION_PENDING,
        checkout_readiness=pb.CHECKOUT_BLOCKED,
        diagnostic_only=True,
    )


class DraftServicer:
    def __init__(
        self,
        drafts: DraftService,
        verifier: AccessTokenVerifierPort,
        tracer: Tracer,
    ) -> None:
        self._drafts = drafts
        self._verifier = verifier
        self._tracer = tracer
        self._logger = logging.getLogger("personalization.grpc")

    def get_design_draft(
        self, request: pb.GetDesignDraftRequest, context: grpc.ServicerContext
    ) -> pb.GetDesignDraftResponse:
        metadata = tuple(context.invocation_metadata())
        trace_headers = [
            value for key, value in metadata if key == "traceparent"
        ]
        carrier: dict[str, str] = {}
        if len(trace_headers) == 1 and isinstance(trace_headers[0], str):
            if len(trace_headers[0]) <= 128:
                carrier["traceparent"] = trace_headers[0]
        parent = TraceContextTextMapPropagator().extract(carrier)
        with self._tracer.start_as_current_span(
            RPC_METHOD,
            context=parent,
            kind=SpanKind.SERVER,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            started = perf_counter()
            failure: RpcRequestError | None = None
            result: pb.GetDesignDraftResponse | None = None
            try:
                tokens = [
                    value for key, value in metadata if key == "authorization"
                ]
                if (
                    len(metadata) > 32
                    or len(tokens) != 1
                    or not isinstance(tokens[0], str)
                ):
                    raise SecurityError(SecurityFailure.INVALID_ACCESS_TOKEN)
                authorization = tokens[0]
                scheme, separator, token = authorization.partition(" ")
                if (
                    scheme.lower() != "bearer"
                    or not separator
                    or not token
                    or len(token) > 8192
                    or any(char.isspace() for char in token)
                ):
                    raise SecurityError(SecurityFailure.INVALID_ACCESS_TOKEN)
                identity = self._verifier.verify(token)
                require_administrator(identity)
                remaining = context.time_remaining()
                if remaining is None or remaining > MAX_DEADLINE_SECONDS:
                    raise RpcRequestError(
                        grpc.StatusCode.INVALID_ARGUMENT,
                        "INVALID_RPC_DEADLINE",
                        "Set a deadline of at most 10 seconds.",
                    )
                if not context.is_active() or remaining <= 0:
                    raise RpcRequestError(
                        grpc.StatusCode.CANCELLED,
                        "RPC_CANCELLED",
                        "The request is no longer active.",
                    )
                if len(request.design_id) != 36:
                    raise ValueError
                design_id = UUID(request.design_id)
                if str(design_id) != request.design_id.lower():
                    raise ValueError
                result = response_for(self._drafts.get(identity, design_id))
            except SecurityError as error:
                status = (
                    grpc.StatusCode.UNAUTHENTICATED
                    if error.failure is SecurityFailure.INVALID_ACCESS_TOKEN
                    else grpc.StatusCode.UNAVAILABLE
                    if error.failure is SecurityFailure.KEYS_UNAVAILABLE
                    else grpc.StatusCode.PERMISSION_DENIED
                )
                failure = RpcRequestError(
                    status,
                    error.failure.value,
                    "User authentication or authorization failed.",
                )
            except DesignError as error:
                status = (
                    grpc.StatusCode.NOT_FOUND
                    if error.failure is DesignFailure.DESIGN_NOT_FOUND
                    else grpc.StatusCode.UNAVAILABLE
                )
                failure = RpcRequestError(
                    status,
                    error.failure.value,
                    "The draft is missing or its database is unavailable.",
                )
            except ValueError:
                failure = RpcRequestError(
                    grpc.StatusCode.INVALID_ARGUMENT,
                    "INVALID_DESIGN_ID",
                    "designId must be a UUID.",
                )
            except RpcRequestError as error:
                failure = error
            except Exception:
                failure = RpcRequestError(
                    grpc.StatusCode.INTERNAL,
                    "INTERNAL_ERROR",
                    "The RPC could not be completed.",
                )
            trace_id = f"{span.get_span_context().trace_id:032x}"
            code = failure.code if failure else "OK"
            context.set_trailing_metadata(
                (("error-code", code), ("trace-id", trace_id))
            )
            if failure is not None:
                span.set_status(Status(StatusCode.ERROR))
            self._logger.info(
                "gRPC request completed",
                extra={
                    "event": "grpc.request.completed",
                    "rpc_method": RPC_METHOD,
                    "rpc_status": failure.status.name if failure else "OK",
                    "code": code,
                    "duration_ms": round((perf_counter() - started) * 1000, 3),
                },
            )
            if failure is not None:
                context.abort(failure.status, failure.detail)
            assert result is not None
            return result
