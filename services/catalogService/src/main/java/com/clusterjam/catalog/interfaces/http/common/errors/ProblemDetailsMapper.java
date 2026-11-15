package com.clusterjam.catalog.interfaces.http.common.errors;

import java.net.URI;
import java.util.List;
import java.util.regex.Pattern;

import com.clusterjam.catalog.interfaces.http.common.observability.RequestTelemetryFilter;
import io.opentelemetry.api.trace.Span;
import jakarta.servlet.RequestDispatcher;
import jakarta.servlet.http.HttpServletRequest;
import org.springframework.http.CacheControl;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;

@Component
public class ProblemDetailsMapper {

    private static final Pattern SAFE_PATH = Pattern.compile("/[A-Za-z0-9/_.~-]{0,511}");

    public ResponseEntity<ProblemDetail> response(
        ProblemCode code,
        HttpServletRequest request
    ) {
        return response(HttpStatusCode.valueOf(code.status()), code, HttpHeaders.EMPTY, request, List.of());
    }

    public ResponseEntity<ProblemDetail> response(
        HttpStatusCode status,
        HttpHeaders originalHeaders,
        HttpServletRequest request,
        List<String> errors
    ) {
        return response(status, ProblemCode.forStatus(status.value()), originalHeaders, request, errors);
    }

    private ResponseEntity<ProblemDetail> response(
        HttpStatusCode status,
        ProblemCode code,
        HttpHeaders originalHeaders,
        HttpServletRequest request,
        List<String> errors
    ) {
        ProblemDetail body = ProblemDetail.forStatusAndDetail(status, code.detail());
        HttpStatus standardStatus = HttpStatus.resolve(status.value());
        body.setTitle(standardStatus != null ? standardStatus.getReasonPhrase() : "HTTP error");
        body.setInstance(instance(request));
        body.setProperty("code", code.name());
        String traceId = traceId(request);
        if (traceId != null) {
            body.setProperty("traceId", traceId);
        }
        if (!errors.isEmpty()) {
            body.setProperty("errors", errors);
        }

        HttpHeaders headers = new HttpHeaders();
        headers.putAll(originalHeaders);
        headers.remove(HttpHeaders.CONTENT_LENGTH);
        headers.setContentType(MediaType.APPLICATION_PROBLEM_JSON);
        headers.setCacheControl(CacheControl.noStore());
        if (status.value() == 401 && !headers.containsHeader(HttpHeaders.WWW_AUTHENTICATE)) {
            headers.set(HttpHeaders.WWW_AUTHENTICATE, "Bearer");
        }
        return ResponseEntity.status(status).headers(headers).body(body);
    }

    private URI instance(HttpServletRequest request) {
        Object original = request.getAttribute(RequestDispatcher.ERROR_REQUEST_URI);
        String path = original instanceof String errorPath ? errorPath : request.getRequestURI();
        if (path != null && !path.startsWith("//") && SAFE_PATH.matcher(path).matches()) {
            return URI.create(path);
        }
        return URI.create("/");
    }

    private String traceId(HttpServletRequest request) {
        if (request.getAttribute(RequestTelemetryFilter.TRACE_ID_ATTRIBUTE) instanceof String traceId) {
            return traceId;
        }
        var context = Span.current().getSpanContext();
        return context.isValid() ? context.getTraceId() : null;
    }
}
