package com.clusterjam.catalog.interfaces.http.openapi;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import tools.jackson.databind.json.JsonMapper;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {"springdoc.api-docs.enabled=true", "springdoc.swagger-ui.enabled=false"}
)
class CatalogOpenApiContractTest {

    private static final Path CONTRACT = Path.of("../../contracts/openapi/catalog/v1/openapi.json");

    @LocalServerPort
    private int port;

    @Test
    void contractMatchesOrWritesSnapshot() throws IOException, InterruptedException {
        HttpRequest request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + "/openapi.json"))
            .timeout(Duration.ofSeconds(10))
            .GET()
            .build();
        var response = HttpClient.newHttpClient().send(request, HttpResponse.BodyHandlers.ofString());
        assertEquals(200, response.statusCode());
        var json = new JsonMapper().readTree(response.body());
        assertTrue(json.at("/paths/~1health~1live/get/responses/200").isObject());
        assertTrue(json.at("/paths/~1health~1ready/get/responses/503/content/application~1problem+json").isObject());
        assertTrue(json.at("/components/schemas/ProblemDetails").isObject());

        assertEquals("bearer", json.at("/components/securitySchemes/supabaseBearer/scheme").stringValue());
        assertEquals("bearer", json.at("/components/securitySchemes/serviceBearer/scheme").stringValue());
        assertTrue(json.at("/paths/~1health~1live/get/security").isMissingNode());

        String generated = response.body().replace("\r\n", "\n").stripTrailing() + "\n";
        if (Boolean.getBoolean("catalog.openapi.write")) {
            Files.createDirectories(CONTRACT.getParent());
            Files.writeString(CONTRACT, generated);
            return;
        }
        assertTrue(Files.isRegularFile(CONTRACT), "Generate the OpenAPI snapshot in write mode first.");
        assertEquals(Files.readString(CONTRACT).replace("\r\n", "\n"), generated, "OpenAPI snapshot changed.");
    }
}
