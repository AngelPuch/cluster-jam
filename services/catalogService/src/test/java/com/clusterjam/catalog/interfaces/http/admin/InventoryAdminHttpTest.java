package com.clusterjam.catalog.interfaces.http.admin;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.sql.DriverManager;
import java.time.Duration;
import java.time.Instant;
import java.util.List;
import java.util.Map;
import java.util.UUID;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.security.oauth2.jwt.BadJwtException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.convention.TestBean;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

@EnabledIfEnvironmentVariable(named = "CATALOG_VERIFY_POSTGRES", matches = "true")
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = "spring.jpa.hibernate.ddl-auto=validate")
class InventoryAdminHttpTest {

    private static final UUID ACTOR = UUID.fromString("c83913d8-29f8-4c1b-bb2d-d93565a9436b");
    private static final UUID OTHER = UUID.fromString("d225329e-5b03-4b6a-b17b-c5c4eeed83cf");
    private final HttpClient client = HttpClient.newHttpClient();
    private final JsonMapper json = new JsonMapper();

    @LocalServerPort
    private int port;

    @TestBean(name = "humanJwtDecoder", methodName = "testDecoder", enforceOverride = true)
    private JwtDecoder humanJwtDecoder;

    static JwtDecoder testDecoder() {
        return token -> {
            String role = switch (token) {
                case "inventory-admin", "inventory-other" -> "administrador";
                case "inventory-client" -> "cliente";
                default -> throw new BadJwtException("Invalid fixture token");
            };
            Instant now = Instant.now();
            return Jwt.withTokenValue(token).header("alg", "RS256")
                .subject((token.equals("inventory-other") ? OTHER : ACTOR).toString())
                .issuedAt(now).expiresAt(now.plusSeconds(60))
                .claim("app_metadata", Map.of("app_role", role)).build();
        };
    }

    @Test
    void persistsOneHistoricalResultAndScopesKeysToTheVerifiedActor() throws Exception {
        UUID variant = fixture(0, 0);
        UUID key = UUID.randomUUID();
        var first = send("POST", path(variant) + "/adjustments", "inventory-admin", key, body(10));
        var original = content(first, 201);
        assertEquals("false", first.headers().firstValue("Idempotency-Replayed").orElseThrow());
        assertEquals(ACTOR.toString(), original.get("actorRef").asString());
        content(send("POST", path(variant) + "/adjustments", "inventory-admin", UUID.randomUUID(), body(2)), 201);
        var replay = send("POST", path(variant) + "/adjustments", "inventory-admin", key,
            "{\"reason\":\"  Conteo físico  \",\"quantityDelta\":10}");
        assertEquals(original, content(replay, 201));
        assertEquals("true", replay.headers().firstValue("Idempotency-Replayed").orElseThrow());
        assertEquals(first.headers().firstValue("Location"), replay.headers().firstValue("Location"));
        assertEquals(409, send("POST", path(variant) + "/adjustments", "inventory-admin", key, body(11)).statusCode());
        UUID another = fixture(0, 0);
        assertEquals(409, send("POST", path(another) + "/adjustments", "inventory-admin", key, body(10)).statusCode());
        var other = content(send("POST", path(variant) + "/adjustments", "inventory-other", key, body(1)), 201);
        assertNotEquals(original.get("id"), other.get("id"));
        assertEquals(13, balance(variant).get("physicalQuantity").asInt());
        var page = content(send("GET", path(variant) + "/movements?limit=1", "inventory-admin", null, null), 200);
        assertEquals(original, page.get("items").get(0));
        assertEquals(1, page.get("nextAfterVersion").asInt());
        var next = content(send("GET", path(variant) + "/movements?limit=1&afterVersion=1",
            "inventory-admin", null, null), 200);
        assertEquals(2, next.get("items").get(0).get("inventoryVersion").asInt());
        String location = first.headers().firstValue("Location").orElseThrow();
        assertEquals(original, content(send("GET", location, "inventory-admin", null, null), 200));
        assertEquals(404, send("GET", path(another) + "/movements/" + original.get("id").asString(),
            "inventory-admin", null, null).statusCode());
        assertRows(variant, 3, 3);
    }

    @Test
    void serializesDuplicateKeysAndCompetingWithdrawals() throws Exception {
        UUID variant = fixture(0, 0);
        UUID key = UUID.randomUUID();
        HttpRequest request = request("POST", path(variant) + "/adjustments", "inventory-admin", key, body(5));
        var left = client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
        var right = client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
        var first = left.get();
        var second = right.get();
        assertEquals(content(first, 201), content(second, 201));
        assertEquals(List.of("false", "true"), List.of(
            first.headers().firstValue("Idempotency-Replayed").orElseThrow(),
            second.headers().firstValue("Idempotency-Replayed").orElseThrow()).stream().sorted().toList());
        assertRows(variant, 1, 1);
        var a = client.sendAsync(request("POST", path(variant) + "/adjustments", "inventory-admin",
            UUID.randomUUID(), body(-4)), HttpResponse.BodyHandlers.ofString());
        var b = client.sendAsync(request("POST", path(variant) + "/adjustments", "inventory-admin",
            UUID.randomUUID(), body(-4)), HttpResponse.BodyHandlers.ofString());
        var one = a.get();
        var two = b.get();
        assertEquals(List.of(201, 409), List.of(one.statusCode(), two.statusCode()).stream().sorted().toList(),
            one.body() + " / " + two.body());
        assertEquals(1, balance(variant).get("physicalQuantity").asInt());
        assertRows(variant, 2, 2);
    }

    @Test
    void rejectsUnauthorizedOrInvalidWritesAndPreservesReservedStock() throws Exception {
        UUID variant = fixture(10, 4);
        String endpoint = path(variant) + "/adjustments";
        assertEquals(401, send("POST", endpoint, null, UUID.randomUUID(), body(1)).statusCode());
        assertEquals(403, send("POST", endpoint, "inventory-client", UUID.randomUUID(), body(1)).statusCode());
        assertEquals(401, send("POST", endpoint, "invalid", UUID.randomUUID(), body(1)).statusCode());
        assertEquals(403, send("GET", path(variant) + "/movements", "inventory-client", null, null).statusCode());
        assertEquals(422, send("POST", endpoint, "inventory-admin", null, body(1)).statusCode());
        assertEquals(422, send("POST", endpoint, "inventory-admin", UUID.randomUUID(), body(0)).statusCode());
        assertEquals(422, send("POST", endpoint, "inventory-admin", UUID.randomUUID(),
            "{\"quantityDelta\":1,\"reason\":\"Conteo\",\"actorRef\":\"forged\"}").statusCode());
        assertEquals(422, send("POST", endpoint, "inventory-admin", UUID.randomUUID(),
            "{\"quantityDelta\":1,\"reason\":\"Conteo\\nforjado\"}").statusCode());
        assertEquals(400, send("POST", endpoint, "inventory-admin", UUID.randomUUID(),
            "{\"quantityDelta\":\"1\",\"reason\":\"Conteo\"}").statusCode());
        UUID rejected = UUID.randomUUID();
        var conflict = send("POST", endpoint, "inventory-admin", rejected, body(-7));
        assertEquals(409, conflict.statusCode(), conflict.body());
        assertTrue(conflict.headers().firstValue("Content-Type").orElseThrow().startsWith("application/problem+json"));
        assertEquals(10, balance(variant).get("physicalQuantity").asInt());
        assertRows(variant, 0, 0);
        content(send("POST", endpoint, "inventory-admin", rejected, body(-6)), 201);
        var balance = balance(variant);
        assertEquals(4, balance.get("physicalQuantity").asInt());
        assertEquals(4, balance.get("reservedQuantity").asInt());
        assertEquals(0, balance.get("availableQuantity").asInt());
        assertRows(variant, 1, 1);
    }

    private UUID fixture(int physical, int reserved) throws Exception {
        UUID product = UUID.randomUUID();
        UUID variant = UUID.randomUUID();
        try (var connection = DriverManager.getConnection(System.getenv("CATALOG_DB_URL"),
            "migrator_catalogo", System.getenv("CATALOG_MIGRATION_PASSWORD"))) {
            connection.setAutoCommit(false);
            try (var p = connection.prepareStatement(
                "INSERT INTO app.producto(id,tipo_prenda_id,nombre) VALUES (?,1,'Inventory test')");
                 var v = connection.prepareStatement("""
                    INSERT INTO app.variante(id,producto_id,talla_id,color_id,sku,precio_base_centavos)
                    VALUES (?,?,1,1,?,19900)
                    """);
                 var i = connection.prepareStatement(
                     "INSERT INTO app.inventario(variante_id,stock_fisico,stock_reservado) VALUES (?,?,?)")) {
                p.setObject(1, product);
                p.executeUpdate();
                v.setObject(1, variant);
                v.setObject(2, product);
                v.setString(3, variant.toString().toUpperCase(java.util.Locale.ROOT));
                v.executeUpdate();
                i.setObject(1, variant);
                i.setInt(2, physical);
                i.setInt(3, reserved);
                i.executeUpdate();
            }
            connection.commit();
        }
        return variant;
    }

    private void assertRows(UUID variant, int movements, int keys) throws Exception {
        try (var connection = DriverManager.getConnection(System.getenv("CATALOG_DB_URL"),
            "migrator_catalogo", System.getenv("CATALOG_MIGRATION_PASSWORD"));
             var query = connection.prepareStatement("""
                SELECT count(*) AS movements, count(k.movimiento_id) AS keys
                FROM app.movimiento_inventario m LEFT JOIN app.idempotencia_ajuste k ON k.movimiento_id = m.id
                WHERE m.variante_id = ?
                """)) {
            query.setObject(1, variant);
            try (var rows = query.executeQuery()) {
                assertTrue(rows.next());
                assertEquals(movements, rows.getInt("movements"));
                assertEquals(keys, rows.getInt("keys"));
            }
        }
    }

    private JsonNode balance(UUID variant) throws Exception {
        return content(send("GET", path(variant), "inventory-admin", null, null), 200);
    }

    private String path(UUID variant) {
        return "/api/v1/admin/variants/" + variant + "/inventory";
    }

    private String body(int delta) {
        return "{\"quantityDelta\":%d,\"reason\":\"Conteo físico\"}".formatted(delta);
    }

    private JsonNode content(HttpResponse<String> response, int status) {
        assertEquals(status, response.statusCode(), response.body());
        return json.readTree(response.body());
    }

    private HttpResponse<String> send(String method, String path, String token, UUID key, String body)
        throws Exception {
        return client.send(request(method, path, token, key, body), HttpResponse.BodyHandlers.ofString());
    }

    private HttpRequest request(String method, String path, String token, UUID key, String body) {
        var request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
            .timeout(Duration.ofSeconds(10)).method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofString(body));
        if (token != null) {
            request.header("Authorization", "Bearer " + token);
        }
        if (key != null) {
            request.header("Idempotency-Key", key.toString());
        }
        if (body != null) {
            request.header("Content-Type", "application/json");
        }
        return request.build();
    }
}
