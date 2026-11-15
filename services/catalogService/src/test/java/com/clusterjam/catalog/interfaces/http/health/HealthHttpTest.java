package com.clusterjam.catalog.interfaces.http.health;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Optional;

import org.junit.jupiter.api.Nested;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.TestPropertySource;
import tools.jackson.databind.json.JsonMapper;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@TestPropertySource(properties = "catalog.readiness-available=true")
class HealthHttpTest {

    private final JsonMapper json = new JsonMapper();
    private final HttpClient client = HttpClient.newHttpClient();

    @LocalServerPort
    private int port;

    @Test
    void liveAndReadyReturnOk() throws IOException, InterruptedException {
        assertHealth(port, "/health/live", 200, "ok");
        assertHealth(port, "/health/ready", 200, "ok");
    }

    @Nested
    @TestPropertySource(properties = "catalog.readiness-available=false")
    class WithUnavailableReadinessProbe {

        @LocalServerPort
        private int unavailablePort;

        @Test
        void liveStaysOkWhileReadyReturnsServiceUnavailable() throws IOException, InterruptedException {
            assertHealth(unavailablePort, "/health/live", 200, "ok");
            HttpResponse<String> response = get(unavailablePort, "/health/ready");
            var problem = json.readTree(response.body());
            assertEquals(503, response.statusCode());
            assertEquals(Optional.of("application/problem+json"), response.headers().firstValue("Content-Type"));
            assertEquals(Optional.of("no-store"), response.headers().firstValue("Cache-Control"));
            assertEquals(503, problem.get("status").intValue());
            assertEquals("SERVICE_UNAVAILABLE", problem.get("code").stringValue());
            assertEquals("/health/ready", problem.get("instance").stringValue());
            String traceId = problem.get("traceId").stringValue();
            assertTrue(traceId.matches("[0-9a-f]{32}"));
            assertEquals(Optional.of(traceId), response.headers().firstValue("X-Trace-Id"));
        }
    }

    private void assertHealth(int serverPort, String path, int expectedCode, String expectedStatus)
        throws IOException, InterruptedException {
        HttpResponse<String> response = get(serverPort, path);
        assertEquals(expectedCode, response.statusCode());
        assertEquals(Optional.of("application/json"), response.headers().firstValue("Content-Type"));
        assertEquals(Optional.of("no-store"), response.headers().firstValue("Cache-Control"));
        assertEquals("{\"status\":\"" + expectedStatus + "\"}", response.body());
    }

    private HttpResponse<String> get(int serverPort, String path) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + serverPort + path))
            .timeout(Duration.ofSeconds(5))
            .header("Accept", "application/json, application/problem+json")
            .GET()
            .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
