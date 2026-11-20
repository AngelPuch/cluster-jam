package com.clusterjam.catalog.interfaces.http.admin;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

import java.awt.image.BufferedImage;
import java.io.ByteArrayOutputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.sql.DriverManager;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import java.util.concurrent.ConcurrentHashMap;

import com.clusterjam.catalog.application.photos.PhotoCleanup;
import com.clusterjam.catalog.application.photos.PhotoFailure;
import com.clusterjam.catalog.application.photos.PhotoFailure.Reason;
import com.clusterjam.catalog.application.ports.PhotoStorage;
import javax.imageio.ImageIO;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.server.LocalServerPort;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.test.context.bean.override.convention.TestBean;
import tools.jackson.databind.json.JsonMapper;

@EnabledIfEnvironmentVariable(named = "CATALOG_VERIFY_POSTGRES", matches = "true")
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT,
    properties = {"spring.jpa.hibernate.ddl-auto=validate", "catalog.photos.cleanup-delay-ms=3600000"}
)
class CatalogPhotoHttpTest {

    private static final UUID ACTOR = UUID.fromString("53dd6221-264b-44bf-951f-90b02c344bb6");

    @LocalServerPort
    private int port;

    @TestBean(name = "humanJwtDecoder", methodName = "decoder", enforceOverride = true)
    private JwtDecoder humanJwtDecoder;

    @TestBean(methodName = "storage", enforceOverride = true)
    private PhotoStorage photoStorage;

    @Autowired
    private PhotoCleanup cleanup;

    private final HttpClient client = HttpClient.newHttpClient();
    private final JsonMapper json = new JsonMapper();

    static JwtDecoder decoder() {
        return token -> Jwt.withTokenValue(token).header("alg", "RS256").subject(ACTOR.toString())
            .claim("app_metadata", Map.of("app_role", token.equals("client") ? "cliente" : "administrador")).build();
    }

    static PhotoStorage storage() {
        return new FakeStorage();
    }

    @Test
    void replacesConcurrentlyRetiresAndCleansOldObjects() throws Exception {
        String path = slot();
        byte[] pixels = picture("png");
        var created = upload(path, null, "*", pixels);
        assertEquals(201, created.statusCode(), created.body());
        String originalTag = etag(created);
        assertEquals(412, upload(path, null, "*", pixels).statusCode());

        var request = uploadRequest(path, originalTag, null, pixels);
        var left = client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
        var right = client.sendAsync(request, HttpResponse.BodyHandlers.ofString());
        var first = left.get();
        var second = right.get();
        assertEquals(List.of(200, 412), List.of(first.statusCode(), second.statusCode()).stream().sorted().toList(),
            first.body() + second.body());
        var current = first.statusCode() == 200 ? first : second;

        var links = send("POST", path + "/links", null, null);
        assertEquals(200, links.statusCode(), links.body());
        assertTrue(json.readTree(links.body()).get("imageUrl").asString().startsWith("https://test.invalid/"));
        var retired = send("DELETE", path, etag(current), null);
        assertEquals(200, retired.statusCode(), retired.body());
        assertFalse(json.readTree(retired.body()).get("active").asBoolean());
        assertEquals(404, send("POST", path + "/links", null, null).statusCode());
        expireAndClean();
    }

    @Test
    void rejectsBadImagesAndKeepsThePreviousPhotoAfterPartialStorageFailure() throws Exception {
        String path = slot();
        var original = upload(path, null, "*", picture("jpeg"));
        assertEquals(201, original.statusCode(), original.body());
        String tag = etag(original);
        assertEquals(422, upload(path, tag, null, "fake image".getBytes(StandardCharsets.UTF_8)).statusCode());
        assertEquals(413, upload(path, tag, null, new byte[10_000_001]).statusCode());
        var fake = (FakeStorage) photoStorage;
        fake.failThumbnail = true;
        try {
            assertEquals(503, upload(path, tag, null, picture("png")).statusCode());
        } finally {
            fake.failThumbnail = false;
        }
        var unchanged = send("GET", path, null, null);
        assertEquals(tag, etag(unchanged));
        assertEquals(200, send("POST", path + "/links", null, null).statusCode());
        expireAndClean();
        assertEquals(200, send("POST", path + "/links", null, null).statusCode());

        var clientRequest = HttpRequest.newBuilder(URI.create(base() + path))
            .header("Authorization", "Bearer client").GET().build();
        assertEquals(403, client.send(clientRequest, HttpResponse.BodyHandlers.ofString()).statusCode());
    }

    private void expireAndClean() throws Exception {
        try (var connection = DriverManager.getConnection(System.getenv("CATALOG_DB_URL"),
            "migrator_catalogo", System.getenv("CATALOG_MIGRATION_PASSWORD"));
             var statement = connection.createStatement()) {
            statement.executeUpdate("UPDATE app.foto_limpieza SET limpiar_despues = now() - interval '1 second'");
        }
        for (UUID id : cleanup.due()) {
            cleanup.clean(id);
        }
    }

    private String slot() throws Exception {
        var product = send("POST", "/api/v1/admin/products", null, "{\"typeId\":1,\"name\":\"Foto prueba\"}");
        assertEquals(201, product.statusCode(), product.body());
        String path = product.headers().firstValue("Location").orElseThrow();
        var variant = send("POST", path + "/variants", null,
            "{\"sizeId\":2,\"colorId\":1,\"sku\":\"PHOTO-" + UUID.randomUUID().toString().toUpperCase()
                + "\",\"basePriceCents\":19900}");
        assertEquals(201, variant.statusCode(), variant.body());
        return path + "/colors/1/photos/FRONT";
    }

    private byte[] picture(String format) throws Exception {
        var output = new ByteArrayOutputStream();
        ImageIO.write(new BufferedImage(80, 60, BufferedImage.TYPE_INT_RGB), format, output);
        return output.toByteArray();
    }

    private HttpRequest uploadRequest(String path, String tag, String none, byte[] data) {
        String boundary = "catalogBoundary";
        byte[] prefix = ("--" + boundary
            + "\r\nContent-Disposition: form-data; name=\"file\"; filename=\"photo.bin\""
            + "\r\nContent-Type: application/octet-stream\r\n\r\n").getBytes(StandardCharsets.US_ASCII);
        byte[] suffix = ("\r\n--" + boundary + "--\r\n").getBytes(StandardCharsets.US_ASCII);
        var builder = HttpRequest.newBuilder(URI.create(base() + path))
            .header("Authorization", "Bearer admin")
            .header("Content-Type", "multipart/form-data; boundary=" + boundary);
        if (tag != null) {
            builder.header("If-Match", tag);
        }
        if (none != null) {
            builder.header("If-None-Match", none);
        }
        return builder.PUT(HttpRequest.BodyPublishers.concat(HttpRequest.BodyPublishers.ofByteArray(prefix),
            HttpRequest.BodyPublishers.ofByteArray(data), HttpRequest.BodyPublishers.ofByteArray(suffix))).build();
    }

    private HttpResponse<String> upload(String path, String tag, String none, byte[] data) throws Exception {
        return client.send(uploadRequest(path, tag, none, data), HttpResponse.BodyHandlers.ofString());
    }

    private String etag(HttpResponse<String> response) {
        return response.headers().firstValue("ETag").orElseThrow();
    }

    private String base() {
        return "http://127.0.0.1:" + port;
    }

    private HttpResponse<String> send(String method, String path, String tag, String body) throws Exception {
        var builder = HttpRequest.newBuilder(URI.create(base() + path)).header("Authorization", "Bearer admin");
        if (tag != null) {
            builder.header("If-Match", tag);
        }
        if (body != null) {
            builder.header("Content-Type", "application/json");
        }
        return client.send(builder.method(method, body == null ? HttpRequest.BodyPublishers.noBody()
            : HttpRequest.BodyPublishers.ofString(body)).build(), HttpResponse.BodyHandlers.ofString());
    }

    static class FakeStorage implements PhotoStorage {

        private final Map<String, byte[]> contents = new ConcurrentHashMap<>();
        private volatile boolean failThumbnail;

        @Override
        public String bucket() {
            return "catalog-photos";
        }

        @Override
        public void upload(String bucket, String key, byte[] content) {
            if (failThumbnail && key.endsWith("-thumb.png")) {
                throw new PhotoFailure(Reason.STORAGE_UNAVAILABLE);
            }
            if (contents.putIfAbsent(key, content) != null) {
                throw new PhotoFailure(Reason.STORAGE_UNAVAILABLE);
            }
        }

        @Override
        public void delete(String bucket, String key) {
            contents.remove(key);
        }

        @Override
        public String sign(String bucket, String key, int seconds) {
            if (!contents.containsKey(key)) {
                throw new PhotoFailure(Reason.STORAGE_UNAVAILABLE);
            }
            return "https://test.invalid/" + key + "?token=example";
        }
    }
}
