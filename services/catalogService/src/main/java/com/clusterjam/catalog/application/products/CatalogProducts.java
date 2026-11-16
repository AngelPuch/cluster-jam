package com.clusterjam.catalog.application.products;

import java.util.List;
import java.util.UUID;

public final class CatalogProducts {

    private CatalogProducts() {
    }

    public enum Status {
        DRAFT, PUBLISHED, RETIRED
    }

    public enum Resource {
        PRODUCT, VARIANT
    }

    public record Product(
        UUID id, int typeId, String name, String description, Status status, int version
    ) {
    }

    public record Variant(
        UUID id, UUID productId, int sizeId, int colorId, String sku,
        long basePriceCents, Status status, int version
    ) {
    }

    public record ProductFields(int typeId, String name, String description) {
    }

    public record NewVariant(int sizeId, int colorId, String sku, long basePriceCents) {
    }

    public record Page<T>(List<T> items, UUID nextCursor) {
    }

    public record Change(
        UUID actor, Resource resource, UUID resourceId, Status previousStatus, Status status,
        Long previousPrice, Long price, int version
    ) {
    }
}
