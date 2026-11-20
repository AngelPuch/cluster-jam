package com.clusterjam.catalog.interfaces.http.catalog;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.ServerSocket;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.DriverManager;
import java.time.Duration;
import java.time.Instant;
import java.util.Base64;
import java.util.Date;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.TimeUnit;

import com.clusterjam.catalog.application.photos.PhotoFailure;
import com.clusterjam.catalog.application.photos.PhotoFailure.Reason;
import com.clusterjam.catalog.application.ports.PhotoStorage;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.TestInstance;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.context.bean.override.convention.TestBean;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

@EnabledIfEnvironmentVariable(named = "CATALOG_VERIFY_POSTGRES", matches = "true")
@TestInstance(TestInstance.Lifecycle.PER_CLASS)
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {"catalog.environment=test", "spring.jpa.hibernate.ddl-auto=validate"}
)
class CatalogReadsHttpTest {

    private static final Keys KEYS = new Keys();
    private static final UUID PRODUCT = UUID.randomUUID();
    private static final UUID OTHER = UUID.randomUUID();
    private static final UUID DRAFT = UUID.randomUUID();
    private static final UUID FIRST = UUID.randomUUID();
    private static final UUID SECOND = UUID.randomUUID();
    private static final UUID RETIRED = UUID.randomUUID();
    private static final String TERM = "R7-" + UUID.randomUUID();

    @LocalServerPort
    private int port;

    private int gatewayPort;
    private Process nginx;
    private Path gatewayDirectory;
    private final HttpClient client = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(3)).build();
    private final JsonMapper json = new JsonMapper();

    @TestBean(methodName = "unavailableStorage", enforceOverride = true)
    private PhotoStorage photoStorage;

    static PhotoStorage unavailableStorage() {
        return new PhotoStorage() {
            public String bucket() {
                return "catalog-photos";
            }

            public void upload(String bucket, String key, byte[] bytes) {
                throw new PhotoFailure(Reason.STORAGE_UNAVAILABLE);
            }

            public void delete(String bucket, String key) {
                throw new PhotoFailure(Reason.STORAGE_UNAVAILABLE);
            }

            public String sign(String bucket, String key, int seconds) {
                throw new PhotoFailure(Reason.STORAGE_UNAVAILABLE);
            }
        };
    }

    @DynamicPropertySource
    static void settings(DynamicPropertyRegistry values) {
        values.add("catalog.security.supabase-url", KEYS::origin);
        values.add("catalog.security.service-jwt-issuer", () -> KEYS.origin() + "/machine");
        values.add("catalog.reads.cursor-key", () -> Base64.getEncoder().encodeToString(new byte[32]));
    }

    @BeforeAll
    void seedAndStartGateway() throws Exception {
        try (var connection = DriverManager.getConnection(System.getenv("CATALOG_DB_URL"),
            "migrator_catalogo", System.getenv("CATALOG_MIGRATION_PASSWORD"));
             var statement = connection.createStatement()) {
            statement.executeUpdate("""
                INSERT INTO app.producto(id,tipo_prenda_id,nombre,estado) VALUES
                ('%s',1,'%s A','PUBLICADO'),('%s',1,'%s B','PUBLICADO'),('%s',1,'%s C','BORRADOR');
                INSERT INTO app.variante(id,producto_id,talla_id,color_id,sku,precio_base_centavos,estado) VALUES
                ('%s','%s',1,1,'%s',100,'PUBLICADO'),
                ('%s','%s',2,2,'%s',200,'PUBLICADO'),
                ('%s','%s',4,1,'%s',400,'RETIRADO');
                INSERT INTO app.variante(producto_id,talla_id,color_id,sku,precio_base_centavos,estado)
                VALUES ('%s',1,2,'%s',300,'PUBLICADO');
                INSERT INTO app.inventario(variante_id,stock_fisico,stock_reservado)
                SELECT id,CASE WHEN id='%s' THEN 7 ELSE 0 END,CASE WHEN id='%s' THEN 2 ELSE 0 END
                FROM app.variante WHERE producto_id IN ('%s','%s');
                INSERT INTO app.foto_producto(producto_id,color_id,cara,bucket,objeto_clave,miniatura_objeto_clave)
                VALUES ('%s',1,'FRENTE','catalog-photos','example.png','example-thumb.png');
                """.formatted(PRODUCT, TERM, OTHER, TERM, DRAFT, TERM,
                FIRST, PRODUCT, FIRST.toString().toUpperCase(java.util.Locale.ROOT),
                SECOND, PRODUCT, SECOND.toString().toUpperCase(java.util.Locale.ROOT),
                RETIRED, PRODUCT, RETIRED.toString().toUpperCase(java.util.Locale.ROOT),
                OTHER, UUID.randomUUID().toString().toUpperCase(java.util.Locale.ROOT),
                FIRST, FIRST, PRODUCT, OTHER, PRODUCT));
        }
        String executable = System.getenv("CATALOG_NGINX_EXE");
        if (executable == null || executable.isBlank()) {
            return;
        }
        try (var socket = new ServerSocket(0)) {
            gatewayPort = socket.getLocalPort();
        }
        gatewayDirectory = Files.createTempDirectory(Path.of("target"), "read-gateway-").toAbsolutePath();
        Files.createDirectories(gatewayDirectory.resolve(".local"));
        String configuration = Files.readString(Path.of("../../infra/catalog/nginx.local.conf"))
            .replace("127.0.0.1:8083", "127.0.0.1:" + port)
            .replace("127.0.0.1:8084", "127.0.0.1:" + gatewayPort);
        Files.writeString(gatewayDirectory.resolve("nginx.conf"), configuration);
        nginx = new ProcessBuilder(executable, "-p", gatewayDirectory + "/", "-c", "nginx.conf",
            "-e", "stderr", "-g", "daemon off;")
            .redirectErrorStream(true).redirectOutput(gatewayDirectory.resolve("process.log").toFile()).start();
        for (int attempt = 0; attempt < 50; attempt++) {
            try {
                client.send(HttpRequest.newBuilder(URI.create(base() + "/")).GET().build(),
                    HttpResponse.BodyHandlers.discarding());
                return;
            } catch (IOException waiting) {
                Thread.sleep(100);
            }
        }
        throw new IllegalStateException("Local Nginx did not start");
    }

    @AfterAll
    void close() throws Exception {
        KEYS.server.stop(0);
        if (nginx != null) {
            new ProcessBuilder(System.getenv("CATALOG_NGINX_EXE"), "-p", gatewayDirectory + "/",
                "-c", "nginx.conf", "-e", "stderr", "-s", "quit").start().waitFor(5, TimeUnit.SECONDS);
            if (!nginx.waitFor(5, TimeUnit.SECONDS)) {
                nginx.destroyForcibly();
            }
        }
    }

    @Test
    void readsOnlyPublishedRowsAndKeepsVariantFiltersTogether() throws Exception {
        String user = token(false, "cliente", null);
        String query = "/api/v1/products?name=" + TERM;
        assertEquals(401, get(query, null).statusCode());
        var filtered = body(get(query + "&sizeId=1&colorId=2&maxPriceCents=350", user), 200);
        assertEquals(1, filtered.get("items").size());
        assertEquals(OTHER.toString(), filtered.get("items").get(0).get("id").asString());
        assertFalse(filtered.get("items").get(0).get("available").asBoolean());
        assertEquals(0, body(get(query + "&sizeId=1&colorId=2&minPriceCents=350", user), 200).get("items").size());

        var first = body(get(query + "&limit=1", user), 200);
        String cursor = first.get("nextCursor").asString();
        var next = body(get(query + "&limit=1&cursor=" + cursor, user), 200);
        assertEquals(1, next.get("items").size());
        assertFalse(first.get("items").get(0).get("id").asString()
            .equals(next.get("items").get(0).get("id").asString()));
        assertEquals(422, get(query + "X&limit=1&cursor=" + cursor, user).statusCode());

        String productPath = "/api/v1/products/" + PRODUCT;
        var detail = body(get(productPath, user), 200);
        assertEquals(2, detail.get("variants").get("items").size());
        assertEquals(1, detail.get("photos").size());
        assertFalse(detail.toString().contains("catalog-photos"));
        String link = detail.get("photos").get(0).get("linksPath").asString();
        assertEquals(503, get(link, user).statusCode());
        assertEquals(200, get(productPath, user).statusCode());
        assertEquals(404, get("/api/v1/products/" + DRAFT, user).statusCode());
        assertEquals(3, body(get("/api/v1/catalog/references", user), 200).get("types").size());
    }

    @Test
    void exposesRealCompatibilityWithSeparateHumanAndServicePermissions() throws Exception {
        String path = "/api/v1/internal/variants/" + FIRST;
        String personalization = token(true, "personalization", "catalog:compatibility");
        var value = body(get(path, personalization), 200);
        assertEquals(PRODUCT.toString(), value.get("productId").asString());
        assertEquals(1, value.get("sizeId").asInt());
        assertTrue(value.get("published").asBoolean());
        assertTrue(value.get("commerce").isNull());
        var order = body(get(path, token(true, "orders", "catalog:read")), 200);
        assertEquals(5, order.get("commerce").get("availableQuantity").asInt());
        assertFalse(body(get("/api/v1/internal/variants/" + RETIRED, personalization), 200)
            .get("published").asBoolean());

        String sizes = "/api/v1/internal/products/" + PRODUCT + "/sizes/";
        assertTrue(body(get(sizes + "1", personalization), 200).get("compatible").asBoolean());
        assertFalse(body(get(sizes + "4", personalization), 200).get("compatible").asBoolean());
        assertEquals(404, get(sizes + "32767", personalization).statusCode());
        assertEquals(401, get(path, token(false, "administrador", null)).statusCode());
        assertEquals(403, get(path, token(true, "orders", "catalog:reserve")).statusCode());
    }

    private String base() {
        return "http://127.0.0.1:" + (gatewayPort == 0 ? port : gatewayPort);
    }

    private HttpResponse<String> get(String path, String token) throws Exception {
        var request = HttpRequest.newBuilder(URI.create(base() + path)).timeout(Duration.ofSeconds(15)).GET();
        if (token != null) {
            request.header("Authorization", "Bearer " + token);
        }
        var response = client.send(request.build(), HttpResponse.BodyHandlers.ofString());
        if (gatewayPort != 0) {
            assertEquals("local", response.headers().firstValue("X-Catalog-Gateway").orElseThrow());
        }
        return response;
    }

    private JsonNode body(HttpResponse<String> response, int status) {
        assertEquals(status, response.statusCode(), response.body());
        return json.readTree(response.body());
    }

    private String token(boolean service, String subject, String scope) throws Exception {
        Instant now = Instant.now();
        var claims = new JWTClaimsSet.Builder().issuer(KEYS.origin() + (service ? "/machine" : "/auth/v1"))
            .audience(service ? "catalog-service" : "authenticated")
            .subject(service ? subject : UUID.randomUUID().toString())
            .issueTime(Date.from(now)).expirationTime(Date.from(now.plusSeconds(180)));
        if (service) {
            claims.claim("scope", scope);
        } else {
            claims.claim("role", "authenticated").claim("app_metadata", Map.of("app_role", subject));
        }
        var signed = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).keyID("read-test").build(),
            claims.build());
        signed.sign(new RSASSASigner(KEYS.key));
        return signed.serialize();
    }

    private static final class Keys {

        private final HttpServer server;
        private final RSAKey key;

        private Keys() {
            try {
                key = new RSAKeyGenerator(2048).keyID("read-test").generate();
                server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
                byte[] bytes = new JWKSet(key.toPublicJWK()).toString().getBytes(StandardCharsets.UTF_8);
                for (String path : new String[]{"/auth/v1/.well-known/jwks.json", "/machine/.well-known/jwks.json"}) {
                    server.createContext(path, exchange -> {
                        try (exchange) {
                            exchange.getResponseHeaders().set("Content-Type", "application/json");
                            exchange.sendResponseHeaders(200, bytes.length);
                            exchange.getResponseBody().write(bytes);
                        }
                    });
                }
                server.start();
            } catch (Exception failure) {
                throw new IllegalStateException(failure);
            }
        }

        private String origin() {
            return "http://127.0.0.1:" + server.getAddress().getPort();
        }
    }
}
