package com.clusterjam.catalog.interfaces.http.admin;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.DriverManager;
import java.sql.SQLException;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.http.HttpHeaders;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.convention.TestBean;
import tools.jackson.databind.json.JsonMapper;

@EnabledIfEnvironmentVariable(named = "CATALOG_VERIFY_POSTGRES", matches = "true")
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.jpa.hibernate.ddl-auto=validate"
)
class CatalogAdminHttpTest {

    private static final String PRODUCTS = "/api/v1/admin/products";
    private static final UUID ACTOR = UUID.fromString("757d8aac-cc98-4dc1-babf-11cdbb54fd8d");

    private final HttpClient client = HttpClient.newHttpClient();
    private final JsonMapper json = new JsonMapper();

    @LocalServerPort
    private int port;

    @TestBean(name = "humanJwtDecoder", methodName = "testDecoder", enforceOverride = true)
    private JwtDecoder humanJwtDecoder;

    static JwtDecoder testDecoder() {
        return token -> {
            String role = switch (token) {
                case "test-admin" -> "administrador";
                case "test-client" -> "cliente";
                default -> throw new BadJwtException("Unknown test token");
            };
            Instant now = Instant.now();
            return Jwt.withTokenValue(token).header("alg", "RS256")
                .subject(ACTOR.toString()).issuedAt(now).expiresAt(now.plusSeconds(60))
                .claim("app_metadata", Map.of("app_role", role))
                .build();
        };
    }

    @Test
    void writesVersionsInventoryAndAuditOnTheRealApi() throws Exception {
        assertEquals(200, send("GET", "/health/ready", "test-admin", null, null).statusCode());
        var product = createProduct();
        String productPath = location(product);
        String productTag = etag(product);
        assertTrue(productPath.startsWith(PRODUCTS + "/"));
        assertEquals("DRAFT", json.readTree(product.body()).get("status").stringValue());

        UUID variantId = UUID.randomUUID();
        var variant = createVariant(productPath, 2, sku(variantId));
        String variantPath = location(variant);
        String originalTag = etag(variant);
        assertEquals("MXN", json.readTree(variant.body()).get("currency").stringValue());

        String productUpdate = """
            {"typeId":1,"name":"Playera de integración","description":null,"status":"PUBLISHED"}
            """;
        var publishedProduct = send("PATCH", productPath, "test-admin", productTag, productUpdate);
        assertEquals(200, publishedProduct.statusCode(), publishedProduct.body());
        assertEquals("PUBLISHED", json.readTree(publishedProduct.body()).get("status").stringValue());

        String publish = """
            {"basePriceCents":24900,"status":"PUBLISHED"}
            """;
        problem(send("PATCH", variantPath, "test-admin", null, publish), 428, "PRECONDITION_REQUIRED");
        HttpRequest edit = request("PATCH", variantPath, "test-admin", originalTag, publish);
        var left = client.sendAsync(edit, HttpResponse.BodyHandlers.ofString());
        var right = client.sendAsync(edit, HttpResponse.BodyHandlers.ofString());
        var first = left.get();
        var second = right.get();
        assertEquals(List.of(200, 412), List.of(first.statusCode(), second.statusCode()).stream().sorted().toList(),
            first.body() + " / " + second.body());
        var published = first.statusCode() == 200 ? first : second;
        problem(send("PATCH", variantPath, "test-admin", originalTag, publish), 412, "PRECONDITION_FAILED");

        var retired = send("PATCH", variantPath, "test-admin", etag(published),
            "{\"basePriceCents\":24900,\"status\":\"RETIRED\"}");
        assertEquals(200, retired.statusCode(), retired.body());
        UUID storedId = UUID.fromString(json.readTree(retired.body()).get("id").stringValue());
        assertEquals("RETIRED", json.readTree(retired.body()).get("status").stringValue());
        assertEquals(etag(retired), etag(send("GET", variantPath, "test-admin", null, null)));
        checkPersistence(storedId);
    }

    @Test
    void enforcesRoleScopeUniquenessAndStrictInput() throws Exception {
        problem(send("GET", PRODUCTS, "test-client", null, null), 403, "FORBIDDEN");
        problem(send("POST", PRODUCTS, "test-admin", null, "{\"typeId\":32767,\"name\":\"Referencia inválida\"}"),
            422, "UNPROCESSABLE_ENTITY");
        String first = location(createProduct());
        String other = location(createProduct());
        String unique = sku(UUID.randomUUID());
        String variantPath = location(createVariant(first, 2, unique));

        problem(send("GET", other + variantPath.substring(first.length()), "test-admin", null, null),
            404, "NOT_FOUND");
        problem(send("POST", first + "/variants", "test-admin", null, variantBody(3, unique)),
            409, "CONFLICT");
        problem(send("POST", first + "/variants", "test-admin", null, variantBody(2, sku(UUID.randomUUID()))),
            409, "CONFLICT");

        String body = variantBody(3, sku(UUID.randomUUID()));
        problem(send("POST", first + "/variants", "test-admin", null,
                body.replace("\"basePriceCents\":19900", "\"basePriceCents\":\"19900\"")),
            400, "BAD_REQUEST");
        problem(send("POST", first + "/variants", "test-admin", null,
                body.replace("\"basePriceCents\":19900", "\"basePriceCents\":19900,\"stockFisico\":10")),
            422, "UNPROCESSABLE_ENTITY");

        String secondPath = location(createVariant(first, 3, sku(UUID.randomUUID())));
        var page = send("GET", first + "/variants?limit=1", "test-admin", null, null);
        assertEquals(200, page.statusCode(), page.body());
        var content = json.readTree(page.body());
        assertEquals(1, content.get("items").size());
        String after = content.get("nextCursor").stringValue();
        var following = send("GET", first + "/variants?limit=1&after=" + after, "test-admin", null, null);
        assertEquals(200, following.statusCode(), following.body());
        var next = json.readTree(following.body());
        assertEquals(1, next.get("items").size());
        String last = next.get("items").get(0).get("id").stringValue();
        assertTrue(!after.equals(last) && (variantPath.endsWith(last) || secondPath.endsWith(last)));
    }

    private void checkPersistence(UUID id) throws SQLException {
        String url = System.getenv().getOrDefault("CATALOG_DB_URL", "jdbc:postgresql://127.0.0.1:5436/catalogo_db");
        try (var connection = DriverManager.getConnection(url,
            "migrator_catalogo", System.getenv("CATALOG_MIGRATION_PASSWORD"));
             var inventory = connection.prepareStatement("""
                SELECT stock_fisico, stock_reservado FROM app.inventario WHERE variante_id = ?
                """);
             var audit = connection.prepareStatement("""
                SELECT accion, actor_ref, detalle->>'previousStatus' AS previous_status,
                    detalle->>'status' AS status, detalle->>'basePriceCents' AS cents
                FROM app.auditoria_local WHERE recurso = 'VARIANT' AND recurso_id = ?
                ORDER BY (detalle->>'version')::integer
                """)) {
            inventory.setObject(1, id);
            audit.setObject(1, id);
            try (var rows = inventory.executeQuery(); var events = audit.executeQuery()) {
                assertTrue(rows.next());
                assertEquals(0, rows.getInt("stock_fisico"));
                assertEquals(0, rows.getInt("stock_reservado"));

                assertTrue(events.next());
                assertEquals("CREATE", events.getString("accion"));
                assertEquals(ACTOR, events.getObject("actor_ref", UUID.class));
                assertEquals("19900", events.getString("cents"));
                assertTrue(events.next());
                assertEquals("DRAFT", events.getString("previous_status"));
                assertEquals("PUBLISHED", events.getString("status"));
                assertEquals("24900", events.getString("cents"));
                assertTrue(events.next());
                assertEquals("RETIRED", events.getString("status"));
                assertTrue(!events.next());
            }
        }
    }

    private HttpResponse<String> createProduct() throws IOException, InterruptedException {
        var response = send("POST", PRODUCTS, "test-admin", null,
            "{\"typeId\":1,\"name\":\"Playera de integración\"}");
        assertEquals(201, response.statusCode(), response.body());
        return response;
    }

    private HttpResponse<String> createVariant(String productPath, int size, String code)
        throws IOException, InterruptedException {
        var response = send("POST", productPath + "/variants", "test-admin", null, variantBody(size, code));
        assertEquals(201, response.statusCode(), response.body());
        return response;
    }

    private String variantBody(int size, String code) {
        return "{\"sizeId\":%d,\"colorId\":1,\"sku\":\"%s\",\"basePriceCents\":19900}".formatted(size, code);
    }

    private String sku(UUID id) {
        return "IT-" + id.toString().toUpperCase(java.util.Locale.ROOT);
    }

    private String location(HttpResponse<String> response) {
        return response.headers().firstValue(HttpHeaders.LOCATION).orElseThrow();
    }

    private String etag(HttpResponse<String> response) {
        return response.headers().firstValue(HttpHeaders.ETAG).orElseThrow();
    }

    private void problem(HttpResponse<String> response, int status, String code) {
        assertEquals(status, response.statusCode(), response.body());
        assertEquals("application/problem+json", response.headers().firstValue(HttpHeaders.CONTENT_TYPE).orElseThrow());
        assertEquals(code, json.readTree(response.body()).get("code").stringValue());
    }

    private HttpResponse<String> send(String method, String path, String token, String tag, String body)
        throws IOException, InterruptedException {
        return client.send(request(method, path, token, tag, body), HttpResponse.BodyHandlers.ofString());
    }

    private HttpRequest request(String method, String path, String token, String tag, String body) {
        var request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
            .timeout(Duration.ofSeconds(10))
            .header(HttpHeaders.AUTHORIZATION, "Bearer " + token)
            .method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofString(body));
        if (tag != null) {
            request.header(HttpHeaders.IF_MATCH, tag);
        }
        if (body != null) {
            request.header(HttpHeaders.CONTENT_TYPE, "application/json");
        }
        return request.build();
    }
}
