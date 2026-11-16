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

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import tools.jackson.databind.json.JsonMapper;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.datasource.url=jdbc:postgresql://127.0.0.1:1/catalogo_db"
)
class HealthHttpTest {

    private final JsonMapper json = new JsonMapper();
    private final HttpClient client = HttpClient.newHttpClient();

    @LocalServerPort
    private int port;

    @Test
    void liveStaysOkWhileDatabaseIsUnreachable() throws IOException, InterruptedException {
        HttpResponse<String> response = get("/health/live");
        assertEquals(200, response.statusCode());
        assertEquals(Optional.of("application/json"), response.headers().firstValue("Content-Type"));
        assertEquals(Optional.of("no-store"), response.headers().firstValue("Cache-Control"));
        assertEquals("{\"status\":\"ok\"}", response.body());
    }

    @Test
    void readyReturnsSanitizedServiceUnavailable() throws IOException, InterruptedException {
        HttpResponse<String> response = get("/health/ready");
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

    private HttpResponse<String> get(String path) throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
            .timeout(Duration.ofSeconds(5))
            .header("Accept", "application/json, application/problem+json")
            .GET()
            .build();
        return client.send(request, HttpResponse.BodyHandlers.ofString());
    }
}
