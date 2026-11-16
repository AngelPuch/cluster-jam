package com.clusterjam.catalog.interfaces.http.common.security;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.time.Instant;
import java.util.Date;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.atomic.AtomicBoolean;

import com.clusterjam.catalog.CatalogApplication;
import com.nimbusds.jose.JOSEException;
import com.nimbusds.jose.JWSAlgorithm;
import com.nimbusds.jose.JWSHeader;
import com.nimbusds.jose.crypto.ECDSASigner;
import com.nimbusds.jose.crypto.RSASSASigner;
import com.nimbusds.jose.jwk.Curve;
import com.nimbusds.jose.jwk.ECKey;
import com.nimbusds.jose.jwk.JWK;
import com.nimbusds.jose.jwk.JWKSet;
import com.nimbusds.jose.jwk.RSAKey;
import com.nimbusds.jose.jwk.gen.ECKeyGenerator;
import com.nimbusds.jose.jwk.gen.RSAKeyGenerator;
import com.nimbusds.jwt.JWTClaimsSet;
import com.nimbusds.jwt.SignedJWT;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.context.TestComponent;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RestController;
import tools.jackson.databind.json.JsonMapper;

@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    classes = {CatalogApplication.class, CatalogSecurityHttpTest.TestEndpoints.class},
    properties = {
        "catalog.environment=test",
        "catalog.security.writes-per-minute=3",
        "catalog.security.max-json-bytes=1024"
    }
)
class CatalogSecurityHttpTest {

    private static final String PRODUCTS = "/api/v1/products";
    private static final String ADMIN_PRODUCTS = "/api/v1/admin/products";
    private static final String VARIANT = "/api/v1/internal/variants/demo";
    private static final String RESERVATIONS = "/api/v1/internal/stock-reservations";
    private static final LocalJwks KEYS = new LocalJwks();

    private final HttpClient client = HttpClient.newHttpClient();
    private final JsonMapper json = new JsonMapper();

    @LocalServerPort
    private int port;

    @DynamicPropertySource
    static void configure(DynamicPropertyRegistry registry) {
        registry.add("catalog.security.supabase-url", KEYS::origin);
        registry.add("catalog.security.service-jwt-issuer", () -> KEYS.origin() + "/machine");
    }

    @AfterAll
    static void stopJwks() {
        KEYS.server.stop(0);
    }

    @Test
    void acceptsOnlyValidHumanTokensAndTrustedRoles() throws Exception {
        var missing = send("GET", PRODUCTS, null, null);
        problem(missing, 401, "UNAUTHORIZED");
        assertEquals("Bearer", missing.headers().firstValue("WWW-Authenticate").orElseThrow());
        problem(send("GET", PRODUCTS, "not-a-jwt", null), 401, "UNAUTHORIZED");
        problem(send("GET", PRODUCTS, human("cliente", Instant.now().minusSeconds(180)), null),
            401, "UNAUTHORIZED");

        String clientToken = human("cliente", Instant.now().plusSeconds(180));
        assertEquals(200, send("GET", PRODUCTS, clientToken, null).statusCode());
        problem(send("POST", ADMIN_PRODUCTS, clientToken, "{\"name\":\"Polo\"}"), 403, "FORBIDDEN");
        String admin = human("administrador", Instant.now().plusSeconds(180));
        assertEquals(200, send("POST", ADMIN_PRODUCTS, admin, "{\"name\":\"Polo\"}").statusCode());
        problem(send("GET", VARIANT, admin, null), 401, "UNAUTHORIZED");
    }

    @Test
    void requiresServiceIssuerAndPermissionPerOperation() throws Exception {
        String orders = service("orders", "catalog:read catalog:reserve", KEYS.serviceKey);
        String readOnly = service("orders", "catalog:read", KEYS.serviceKey);
        String personalization = service("personalization", "catalog:compatibility catalog:reserve", KEYS.serviceKey);

        assertEquals(200, send("GET", VARIANT, readOnly, null).statusCode());
        problem(send("POST", RESERVATIONS, readOnly, "{}"), 403, "FORBIDDEN");
        assertEquals(200, send("POST", RESERVATIONS, orders, "{}").statusCode());
        assertEquals(200, send("GET", VARIANT, personalization, null).statusCode());
        problem(send("POST", RESERVATIONS, personalization, "{}"), 403, "FORBIDDEN");
        problem(send("GET", PRODUCTS, orders, null), 401, "UNAUTHORIZED");
    }

    @Test
    void distinguishesJwksOutageFromInvalidCredentials() throws Exception {
        RSAKey fresh = new RSAKeyGenerator(2048).keyID("other-test-key").generate();
        String token = service("orders", "catalog:read", fresh);
        KEYS.failMachineKeys.set(true);
        try {
            problem(send("GET", VARIANT, token, null), 503, "SERVICE_UNAVAILABLE");
        } finally {
            KEYS.failMachineKeys.set(false);
        }
    }

    @Test
    void validatesWriteSizeSchemaAndQuota() throws Exception {
        String admin = human("administrador", Instant.now().plusSeconds(180));
        problem(send("POST", ADMIN_PRODUCTS, admin, "{\"name\":\"" + "a".repeat(2048) + "\"}"),
            413, "PAYLOAD_TOO_LARGE");
        problem(send("POST", ADMIN_PRODUCTS, admin, "{\"name\":\"Polo\",\"unexpected\":true}"),
            422, "UNPROCESSABLE_ENTITY");
        assertEquals(200, send("POST", ADMIN_PRODUCTS, admin, "{\"name\":\"Polo\"}").statusCode());
        assertEquals(200, send("POST", ADMIN_PRODUCTS, admin, "{\"name\":\"Polo\"}").statusCode());
        var limited = send("POST", ADMIN_PRODUCTS, admin, "{\"name\":\"Polo\"}");
        problem(limited, 429, "TOO_MANY_REQUESTS");
        assertTrue(Integer.parseInt(limited.headers().firstValue("Retry-After").orElseThrow()) > 0);
    }

    private void problem(HttpResponse<String> response, int status, String code) {
        assertEquals(status, response.statusCode());
        assertEquals("application/problem+json", response.headers().firstValue("Content-Type").orElseThrow());
        assertEquals("nosniff", response.headers().firstValue("X-Content-Type-Options").orElseThrow());
        assertFalse(response.headers().firstValue("Set-Cookie").isPresent());
        var problem = json.readTree(response.body());
        assertEquals(code, problem.get("code").stringValue());
        assertEquals(response.headers().firstValue("X-Trace-Id").orElseThrow(), problem.get("traceId").stringValue());
    }

    private String human(String role, Instant expires) throws JOSEException {
        var claims = new JWTClaimsSet.Builder()
            .issuer(KEYS.origin() + "/auth/v1")
            .audience("authenticated")
            .subject(UUID.randomUUID().toString())
            .expirationTime(Date.from(expires))
            .claim("role", "authenticated")
            .claim("app_metadata", Map.of("app_role", role))
            .claim("user_metadata", Map.of("app_role", "administrador"))
            .build();
        var token = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.ES256).keyID("human-test").build(), claims);
        token.sign(new ECDSASigner(KEYS.humanKey));
        return token.serialize();
    }

    private String service(String subject, String scopes, RSAKey key) throws JOSEException {
        var claims = new JWTClaimsSet.Builder()
            .issuer(KEYS.origin() + "/machine")
            .audience("catalog-service")
            .subject(subject)
            .issueTime(new Date())
            .expirationTime(Date.from(Instant.now().plusSeconds(180)))
            .claim("scope", scopes)
            .build();
        var token = new SignedJWT(new JWSHeader.Builder(JWSAlgorithm.RS256).keyID(key.getKeyID()).build(), claims);
        token.sign(new RSASSASigner(key));
        return token.serialize();
    }

    private HttpResponse<String> send(
        String method,
        String path,
        String token,
        String body
    ) throws IOException, InterruptedException {
        var request = HttpRequest.newBuilder(URI.create("http://127.0.0.1:" + port + path))
            .timeout(Duration.ofSeconds(10))
            .method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofString(body));
        if (token != null) {
            request.header("Authorization", "Bearer " + token);
        }
        if (body != null) {
            request.header("Content-Type", "application/json");
        }
        return client.send(request.build(), HttpResponse.BodyHandlers.ofString());
    }

    @TestComponent
    @RestController
    static class TestEndpoints {

        @GetMapping("/products")
        List<String> products() {
            return List.of("Polo");
        }

        @PostMapping("/admin/products")
        String product(@RequestBody ProductInput body) {
            return body.name();
        }

        @GetMapping("/internal/variants/{id}")
        String variant() {
            return "variant";
        }

        @PostMapping("/internal/stock-reservations")
        String reserve() {
            return "reservation";
        }
    }

    record ProductInput(String name) {
    }

    private static final class LocalJwks {

        private final HttpServer server;
        private final ECKey humanKey;
        private final RSAKey serviceKey;
        private final AtomicBoolean failMachineKeys = new AtomicBoolean();

        private LocalJwks() {
            try {
                humanKey = new ECKeyGenerator(Curve.P_256).keyID("human-test").generate();
                serviceKey = new RSAKeyGenerator(2048).keyID("machine-test").generate();
                server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
                serve("/auth/v1/.well-known/jwks.json", humanKey.toPublicJWK(), new AtomicBoolean());
                serve("/machine/.well-known/jwks.json", serviceKey.toPublicJWK(), failMachineKeys);
                server.start();
            } catch (IOException | JOSEException error) {
                throw new IllegalStateException("Unable to start local test JWKS.", error);
            }
        }

        private String origin() {
            return "http://127.0.0.1:" + server.getAddress().getPort();
        }

        private void serve(String path, JWK publicKey, AtomicBoolean fail) {
            byte[] body = new JWKSet(publicKey).toString().getBytes(StandardCharsets.UTF_8);
            server.createContext(path, exchange -> {
                try (exchange) {
                    if (fail.get()) {
                        exchange.sendResponseHeaders(503, -1);
                    } else {
                        exchange.getResponseHeaders().set("Content-Type", "application/json");
                        exchange.sendResponseHeaders(200, body.length);
                        exchange.getResponseBody().write(body);
                    }
                }
            });
        }
    }
}
