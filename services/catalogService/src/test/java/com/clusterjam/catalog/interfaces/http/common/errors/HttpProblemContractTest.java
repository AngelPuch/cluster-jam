package com.clusterjam.catalog.interfaces.http.common.errors;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import tools.jackson.databind.json.JsonMapper;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "springdoc.api-docs.enabled=false"
)
class HttpProblemContractTest {

    private static final String TRACE_ID = "4bf92f3577b34da6a3ce929d0e0e4736";
    private static final String TRACE_PARENT = "00-" + TRACE_ID + "-00f067aa0ba902b7-01";

    private final HttpClient client = HttpClient.newHttpClient();
    private final JsonMapper json = new JsonMapper();

    @LocalServerPort
    private int port;

    @Test
    void missingRouteUsesProblemDetailsAndContinuesTrace() throws IOException, InterruptedException {
        var response = send("GET", "/api/v1/missing?debug=private-value");
        var problem = json.readTree(response.body());

        assertEquals(404, response.statusCode());
        assertEquals("application/problem+json", response.headers().firstValue("Content-Type").orElseThrow());
        assertEquals("no-store", response.headers().firstValue("Cache-Control").orElseThrow());
        assertEquals("NOT_FOUND", problem.get("code").stringValue());
        assertEquals("/api/v1/missing", problem.get("instance").stringValue());
        assertEquals(TRACE_ID, problem.get("traceId").stringValue());
        assertEquals(TRACE_ID, response.headers().firstValue("X-Trace-Id").orElseThrow());
        UUID.fromString(response.headers().firstValue("X-Request-Id").orElseThrow());
        assertFalse(response.body().contains("private-value"));
    }

    @Test
    void unsupportedMethodKeepsAllowHeader() throws IOException, InterruptedException {
        var response = send("POST", "/health/live");
        assertEquals(405, response.statusCode());
        assertEquals("METHOD_NOT_ALLOWED", json.readTree(response.body()).get("code").stringValue());
        assertTrue(response.headers().firstValue("Allow").orElseThrow().contains("GET"));
    }

    private HttpResponse<String> send(String method, String path) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
            .timeout(Duration.ofSeconds(5))
            .header("traceparent", TRACE_PARENT)
            .method(method, HttpRequest.BodyPublishers.noBody())
            .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
