package com.clusterjam.catalog.infrastructure.storage;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.ByteBuffer;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.Flow;

import com.clusterjam.catalog.application.photos.PhotoFailure;
import com.clusterjam.catalog.application.photos.PhotoFailure.Reason;
import com.clusterjam.catalog.application.ports.PhotoStorage;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Component;
import tools.jackson.databind.JsonNode;
import tools.jackson.databind.json.JsonMapper;

@Component
public class SupabasePhotoStorage implements PhotoStorage {

    private final Environment environment;
    private final JsonMapper json;
    private final HttpClient client = HttpClient.newBuilder()
        .connectTimeout(Duration.ofSeconds(3)).followRedirects(HttpClient.Redirect.NEVER).build();

    public SupabasePhotoStorage(Environment environment, JsonMapper json) {
        this.environment = environment;
        this.json = json;
    }

    @Override
    public String bucket() {
        String name = environment.getProperty("catalog.photos.bucket", "catalog-photos");
        if (!name.matches("[a-z0-9][a-z0-9-]{0,62}")) {
            throw unavailable();
        }
        return name;
    }

    private URI base() {
        String value = environment.getProperty("catalog.security.supabase-url", "");
        URI origin;
        try {
            origin = URI.create(value);
        } catch (IllegalArgumentException error) {
            throw unavailable();
        }
        if (!"https".equals(origin.getScheme()) || origin.getHost() == null
            || !origin.getHost().endsWith(".supabase.co") || origin.getRawUserInfo() != null
            || origin.getPort() != -1 || origin.getRawQuery() != null || origin.getRawFragment() != null
            || !(origin.getPath().isEmpty() || origin.getPath().equals("/"))) {
            throw unavailable();
        }
        return URI.create("https://" + origin.getHost() + "/storage/v1/");
    }

    private void verifyBucket(String name) {
        if (!bucket().equals(name)) {
            throw unavailable();
        }
        JsonNode details = request("GET", "bucket/" + name, null, null);
        JsonNode types = details.path("allowed_mime_types");
        if (!name.equals(details.path("id").asString()) || !details.path("public").isBoolean()
            || details.path("public").asBoolean() || details.path("file_size_limit").asLong() != 10_000_000
            || !types.isArray() || types.size() != 1 || !"image/png".equals(types.get(0).asString())) {
            throw unavailable();
        }
    }

    private String path(String name, String key) {
        if (!name.equals(bucket()) || !key.matches("[0-9a-f-]{36}(-thumb)?\\.png")) {
            throw unavailable();
        }
        return name + "/" + key;
    }

    @Override
    public void upload(String name, String key, byte[] content) {
        verifyBucket(name);
        String path = path(name, key);
        JsonNode result = request("POST", "object/" + path, content, "image/png");
        if (!path.equals(result.path("Key").asString())) {
            throw unavailable();
        }
    }

    @Override
    public void delete(String name, String key) {
        path(name, key);
        request("DELETE", "object/" + name, json.writeValueAsBytes(Map.of("prefixes", List.of(key))),
            "application/json");
    }

    @Override
    public String sign(String name, String key, int seconds) {
        verifyBucket(name);
        String path = "/object/sign/" + path(name, key);
        JsonNode result = request("POST", path.substring(1),
            json.writeValueAsBytes(Map.of("expiresIn", seconds)), "application/json");
        String signed = result.path("signedURL").asString("");
        URI relative;
        try {
            relative = URI.create(signed);
        } catch (IllegalArgumentException error) {
            throw unavailable();
        }
        if (relative.isAbsolute() || relative.getRawAuthority() != null || !path.equals(relative.getRawPath())
            || relative.getRawFragment() != null || relative.getRawQuery() == null
            || !relative.getRawQuery().matches("token=[A-Za-z0-9_.~-]+") || signed.length() > 8192) {
            throw unavailable();
        }
        return base().toString().replaceAll("/$", "") + signed;
    }

    private JsonNode request(String method, String route, byte[] body, String type) {
        String key = environment.getProperty("catalog.photos.key", "");
        if (key.isBlank()) {
            throw unavailable();
        }
        var builder = HttpRequest.newBuilder(base().resolve(route)).timeout(Duration.ofSeconds(15))
            .header("apikey", key).header("Accept", "application/json");
        if (key.startsWith("eyJ")) {
            builder.header("Authorization", "Bearer " + key);
        }
        if (type != null) {
            builder.header("Content-Type", type);
        }
        builder.header("x-upsert", "false").header("Cache-Control", "private, no-store")
            .method(method, body == null ? HttpRequest.BodyPublishers.noBody()
                : HttpRequest.BodyPublishers.ofByteArray(body));
        try {
            var response = client.send(builder.build(), info -> new LimitedBody());
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                throw unavailable();
            }
            return json.readTree(response.body());
        } catch (IOException | RuntimeException failure) {
            throw unavailable();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw unavailable();
        }
    }

    private PhotoFailure unavailable() {
        return new PhotoFailure(Reason.STORAGE_UNAVAILABLE);
    }

    private static final class LimitedBody implements HttpResponse.BodySubscriber<byte[]> {

        private final HttpResponse.BodySubscriber<byte[]> delegate = HttpResponse.BodySubscribers.ofByteArray();
        private Flow.Subscription subscription;
        private int received;

        @Override
        public CompletionStage<byte[]> getBody() {
            return delegate.getBody();
        }

        @Override
        public void onSubscribe(Flow.Subscription value) {
            subscription = value;
            delegate.onSubscribe(value);
        }

        @Override
        public void onNext(List<ByteBuffer> buffers) {
            for (var buffer : buffers) {
                received += buffer.remaining();
                if (received > 8192) {
                    subscription.cancel();
                    delegate.onError(new IOException("Storage response exceeds limit"));
                    return;
                }
            }
            delegate.onNext(buffers);
        }

        @Override
        public void onError(Throwable error) {
            delegate.onError(error);
        }

        @Override
        public void onComplete() {
            delegate.onComplete();
        }
    }
}
