"""Correlate HTTP responses, logs, and safe error details."""

import logging
from time import perf_counter
from uuid import uuid4

from opentelemetry.trace import SpanKind, Status, StatusCode, Tracer
from opentelemetry.trace.propagation.tracecontext import (
    TraceContextTextMapPropagator,
)
from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from personalization.interfaces.http.errors.problem_handlers import (
    unexpected_problem,
)

HEALTH_PATHS = {"/health/live", "/health/ready"}


class RequestContextMiddleware:
    """Create an OpenTelemetry server span for each request."""

    def __init__(self, app: ASGIApp, tracer: Tracer) -> None:
        self._app = app
        self._tracer = tracer
        self._propagator = TraceContextTextMapPropagator()
        self._logger = logging.getLogger("personalization.http")

    async def __call__(
        self, scope: Scope, receive: Receive, send: Send
    ) -> None:
        """Emit one completion event and never copy bodies into logs."""
        if scope["type"] != "http":
            await self._app(scope, receive, send)
            return
        headers = Headers(scope=scope)
        carrier: dict[str, str] = {}
        if len(headers.getlist("traceparent")) == 1:
            carrier["traceparent"] = headers["traceparent"]
            if len(headers.getlist("tracestate")) == 1:
                carrier["tracestate"] = headers["tracestate"]
        parent = self._propagator.extract(carrier)
        method = str(scope.get("method", "UNKNOWN"))[:16]
        with self._tracer.start_as_current_span(
            method,
            context=parent,
            kind=SpanKind.SERVER,
            record_exception=False,
            set_status_on_exception=False,
        ) as span:
            span_context = span.get_span_context()
            state = scope.setdefault("state", {})
            state["trace_id"] = f"{span_context.trace_id:032x}"
            state["span_id"] = f"{span_context.span_id:016x}"
            state["request_id"] = uuid4().hex
            outgoing: dict[str, str] = {}
            self._propagator.inject(outgoing)
            started = perf_counter()
            status_code = 500
            response_started = False
            error_type: str | None = None

            async def correlated_send(message: Message) -> None:
                nonlocal status_code, response_started
                if message["type"] == "http.response.start":
                    status_code = message["status"]
                    response_started = True
                    response_headers = MutableHeaders(scope=message)
                    response_headers["traceparent"] = outgoing["traceparent"]
                    response_headers["X-Request-ID"] = state["request_id"]
                    response_headers["X-Content-Type-Options"] = "nosniff"
                    response_headers["Referrer-Policy"] = "no-referrer"
                await send(message)

            try:
                await self._app(scope, receive, correlated_send)
            except Exception as exception:
                error_type = type(exception).__name__
                if response_started:
                    raise
                response = unexpected_problem(Request(scope))
                await response(scope, receive, correlated_send)
            finally:
                route = getattr(scope.get("route"), "path", None)
                if isinstance(route, str):
                    route_name = route
                elif scope.get("path") in {"/docs", "/openapi.json"}:
                    route_name = str(scope["path"])
                else:
                    route_name = "unmatched"
                span.update_name(f"{method} {route_name}")
                span.set_attribute("http.request.method", method)
                span.set_attribute("http.route", route_name)
                span.set_attribute("http.response.status_code", status_code)
                if status_code >= 500 or error_type:
                    span.set_status(Status(StatusCode.ERROR))
                healthy_probe = (
                    scope.get("path") in HEALTH_PATHS and status_code == 200
                )
                if not healthy_probe:
                    fields: dict[str, object] = {
                        "event": "http.request.failed"
                        if error_type
                        else "http.request.completed",
                        "http_method": method,
                        "http_route": route_name,
                        "status_code": status_code,
                        "duration_ms": round(
                            (perf_counter() - started) * 1000, 3
                        ),
                        "request_id": state["request_id"],
                    }
                    if error_type:
                        fields["error_type"] = error_type
                    level = logging.INFO
                    if status_code == 503 and not error_type:
                        level = logging.WARNING
                    elif status_code >= 500 or error_type:
                        level = logging.ERROR
                    self._logger.log(
                        level,
                        "HTTP request completed"
                        if not error_type
                        else "HTTP request failed",
                        extra=fields,
                    )
