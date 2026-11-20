package com.clusterjam.catalog.application.reads;

import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.photos.CatalogPhotos.Side;
import com.clusterjam.catalog.application.products.CatalogProducts.Status;

public final class CatalogReadModels {

    private CatalogReadModels() {
    }

    public record Filter(String name, Integer typeId, Integer sizeId, Integer colorId, Long minPrice, Long maxPrice) {
    }

    public record Page<T>(List<T> items, String nextCursor) {
    }

    public record PhotoRef(int colorId, Side side, String linksPath) {
    }

    public record Card(
        UUID id, int typeId, String name, long basePriceFromCents, String currency,
        boolean available, PhotoRef cover
    ) {
    }

    public record Variant(
        UUID id, UUID productId, int sizeId, int colorId, String sku, long basePriceCents,
        String currency, int availableQuantity
    ) {
    }

    public record Detail(
        UUID id, int typeId, String name, String description, Page<Variant> variants, List<PhotoRef> photos
    ) {
    }

    public record Commerce(long basePriceCents, String currency, int availableQuantity) {
    }

    public record Compatibility(
        UUID variantId, UUID productId, int sizeId, int colorId, Status productStatus,
        Status variantStatus, boolean published, Commerce commerce
    ) {
    }

    public record ProductSize(
        UUID productId, int sizeId, Status productStatus, boolean hasPublishedVariants, boolean compatible
    ) {
    }

    public record Type(int id, String name) {
    }

    public record Size(int id, String code, int order) {
    }

    public record Color(int id, String name, String hex) {
    }

    public record References(List<Type> types, List<Size> sizes, List<Color> colors) {
    }
}
