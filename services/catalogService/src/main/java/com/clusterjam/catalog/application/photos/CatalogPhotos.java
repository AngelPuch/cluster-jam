package com.clusterjam.catalog.application.photos;

import java.time.Instant;
import java.util.UUID;

public final class CatalogPhotos {

    private CatalogPhotos() {
    }

    public enum Side {
        FRONT, BACK
    }

    public record Slot(UUID productId, int colorId, Side side) {
    }

    public record Photo(
        UUID id, Slot slot, String bucket, String original, String thumbnail, boolean active, int version
    ) {
        public String etag() {
            return "\"photo-" + id + "-" + version + "\"";
        }
    }

    public record Objects(UUID id, String bucket, String original, String thumbnail) {

        public static Objects fresh(String bucket) {
            UUID id = UUID.randomUUID();
            return new Objects(id, bucket, id + ".png", id + "-thumb.png");
        }
    }

    public record Pixels(byte[] original, byte[] thumbnail) {
    }

    public record Links(String imageUrl, String thumbnailUrl, Instant expiresAt) {
    }
}
