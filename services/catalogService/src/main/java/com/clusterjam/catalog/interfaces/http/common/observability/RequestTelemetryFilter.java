package com.clusterjam.catalog.interfaces.http.common.observability;

import java.io.IOException;
import java.util.Collections;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import io.opentelemetry.api.trace.Span;
import io.opentelemetry.api.trace.SpanKind;
import io.opentelemetry.api.trace.StatusCode;
import io.opentelemetry.api.trace.Tracer;
import io.opentelemetry.api.trace.propagation.W3CTraceContextPropagator;
import io.opentelemetry.context.Context;
import io.opentelemetry.context.Scope;
import io.opentelemetry.context.propagation.TextMapGetter;
import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.slf4j.spi.LoggingEventBuilder;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;
import org.springframework.web.servlet.HandlerMapping;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 10)
public class RequestTelemetryFilter extends OncePerRequestFilter {

    public static final String TRACE_ID_ATTRIBUTE = RequestTelemetryFilter.class.getName() + ".traceId";
    public static final String TRACE_ID_HEADER = "X-Trace-Id";
    public static final String REQUEST_ID_HEADER = "X-Request-Id";

    private static final Logger LOG = LoggerFactory.getLogger(RequestTelemetryFilter.class);
    private static final TextMapGetter<HttpServletRequest> TRACE_HEADERS = new TextMapGetter<>() {
        @Override
        public Iterable<String> keys(HttpServletRequest request) {
            return Collections.list(request.getHeaderNames());
        }

        @Override
        public String get(HttpServletRequest request, String key) {
            var values = request.getHeaders(key);
            if (!values.hasMoreElements()) {
                return null;
            }
            String value = values.nextElement();
            return !values.hasMoreElements() && value.length() <= 512 ? value : null;
        }
    };

    private final Tracer tracer;

    public RequestTelemetryFilter(Tracer tracer) {
        this.tracer = tracer;
    }

    @Override
    protected void doFilterInternal(
        HttpServletRequest request,
        HttpServletResponse response,
        FilterChain chain
    ) throws ServletException, IOException {
        long start = System.nanoTime();
        String requestId = UUID.randomUUID().toString();
        Context parent = W3CTraceContextPropagator.getInstance().extract(Context.root(), request, TRACE_HEADERS);
        Span span = tracer.spanBuilder("HTTP request").setSpanKind(SpanKind.SERVER).setParent(parent).startSpan();
        String traceId = span.getSpanContext().getTraceId();
        request.setAttribute(TRACE_ID_ATTRIBUTE, traceId);
        response.setHeader(TRACE_ID_HEADER, traceId);
        response.setHeader(REQUEST_ID_HEADER, requestId);

        boolean failed = true;
        try (Scope scope = span.makeCurrent()) {
            chain.doFilter(request, response);
            failed = false;
        } finally {
            try {
                int status = failed ? 500 : response.getStatus();
                complete(request, span, requestId, status, start);
            } finally {
                span.end();
            }
        }
    }

    private void complete(HttpServletRequest request, Span span, String requestId, int status, long start) {
        String method = safeMethod(request.getMethod());
        String route = routeTemplate(request);
        span.updateName(method + " " + route);
        span.setAttribute("http.request.method", method);
        span.setAttribute("http.route", route);
        span.setAttribute("http.response.status_code", status);
        if (status >= 500) {
            span.setStatus(StatusCode.ERROR);
        }
        if (status < 400 && ("/health/live".equals(route) || "/health/ready".equals(route))) {
            return;
        }

        LoggingEventBuilder entry = status >= 500 && status != 503 ? LOG.atError()
            : status >= 400 ? LOG.atWarn() : LOG.atInfo();
        entry.addKeyValue("event", "http.request.completed")
            .addKeyValue("trace_id", span.getSpanContext().getTraceId())
            .addKeyValue("span_id", span.getSpanContext().getSpanId())
            .addKeyValue("request_id", requestId)
            .addKeyValue("http_method", method)
            .addKeyValue("http_route", route)
            .addKeyValue("status_code", status)
            .addKeyValue("duration_ms", TimeUnit.NANOSECONDS.toMillis(System.nanoTime() - start));
        if (status >= 500) {
            entry.addKeyValue("error_type", status == 503 ? "ServiceUnavailable" : "ServerError");
        }
        entry.log("HTTP request completed");
    }

    private String routeTemplate(HttpServletRequest request) {
        Object pattern = request.getAttribute(HandlerMapping.BEST_MATCHING_PATTERN_ATTRIBUTE);
        if (pattern instanceof String route && !"/**".equals(route)) {
            return route;
        }
        return "unmatched";
    }

    private String safeMethod(String method) {
        return switch (method) {
            case "GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS" -> method;
            default -> "OTHER";
        };
    }
}
