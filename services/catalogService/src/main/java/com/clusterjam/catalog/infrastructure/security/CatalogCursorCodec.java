package com.clusterjam.catalog.infrastructure.security;

import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.Base64;
import java.util.UUID;

import com.clusterjam.catalog.application.ports.CatalogReadCursors;
import javax.crypto.Mac;
import javax.crypto.spec.SecretKeySpec;
import org.springframework.core.env.Environment;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

@Component
public class CatalogCursorCodec implements CatalogReadCursors {

    private final Environment environment;

    public CatalogCursorCodec(Environment environment) {
        this.environment = environment;
    }

    @Override
    public UUID decode(String cursor, String scope) {
        if (cursor == null) {
            return null;
        }
        if (cursor.length() > 512 || !cursor.matches("[A-Za-z0-9_-]+\\.[A-Za-z0-9_-]+")) {
            throw invalid();
        }
        try {
            String[] parts = cursor.split("\\.");
            byte[] body = Base64.getUrlDecoder().decode(parts[0]);
            byte[] signature = Base64.getUrlDecoder().decode(parts[1]);
            if (!MessageDigest.isEqual(sign(body), signature)) {
                throw invalid();
            }
            String[] fields = new String(body, StandardCharsets.UTF_8).split("\\|");
            if (fields.length != 3 || !"1".equals(fields[0]) || !hash(scope).equals(fields[2])) {
                throw invalid();
            }
            UUID id = UUID.fromString(fields[1]);
            if (!id.toString().equals(fields[1])) {
                throw invalid();
            }
            return id;
        } catch (IllegalArgumentException malformed) {
            throw invalid();
        }
    }

    @Override
    public String encode(UUID last, String scope) {
        byte[] bytes = ("1|" + last + "|" + hash(scope)).getBytes(StandardCharsets.UTF_8);
        return Base64.getUrlEncoder().withoutPadding().encodeToString(bytes) + "."
            + Base64.getUrlEncoder().withoutPadding().encodeToString(sign(bytes));
    }

    private byte[] sign(byte[] data) {
        try {
            byte[] key = Base64.getDecoder().decode(environment.getProperty("catalog.reads.cursor-key", ""));
            if (key.length < 32) {
                throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE);
            }
            Mac mac = Mac.getInstance("HmacSHA256");
            mac.init(new SecretKeySpec(key, "HmacSHA256"));
            return mac.doFinal(data);
        } catch (java.security.GeneralSecurityException | IllegalArgumentException error) {
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE);
        }
    }

    private String hash(String scope) {
        try {
            return Base64.getUrlEncoder().withoutPadding()
                .encodeToString(MessageDigest.getInstance("SHA-256").digest(scope.getBytes(StandardCharsets.UTF_8)));
        } catch (NoSuchAlgorithmException error) {
            throw new IllegalStateException(error);
        }
    }

    private ResponseStatusException invalid() {
        return new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT);
    }
}
