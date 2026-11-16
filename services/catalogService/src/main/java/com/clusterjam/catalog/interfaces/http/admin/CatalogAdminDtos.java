package com.clusterjam.catalog.interfaces.http.admin;

import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.products.CatalogProducts.NewVariant;
import com.clusterjam.catalog.application.products.CatalogProducts.Product;
import com.clusterjam.catalog.application.products.CatalogProducts.ProductFields;
import com.clusterjam.catalog.application.products.CatalogProducts.Status;
import com.clusterjam.catalog.application.products.CatalogProducts.Variant;
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public final class CatalogAdminDtos {

    private static final int MAX_REFERENCE_ID = 32767;
    private static final long MAX_PRICE_CENTS = 10_000_000;
    private static final String NAME = "[^\\x00-\\x1F\\x7F-\\x9F]+";
    private static final String DESCRIPTION = "[^\\x00-\\x08\\x0B\\x0C\\x0E-\\x1F\\x7F-\\x9F]*";

    private CatalogAdminDtos() {
    }

    @Schema(additionalProperties = Schema.AdditionalPropertiesValue.FALSE)
    public record CreateProduct(
        @NotNull @Positive @Max(MAX_REFERENCE_ID) Integer typeId,
        @NotBlank @Size(max = 120) @Pattern(regexp = NAME) String name,
        @Schema(types = {"string", "null"})
        @Size(max = 2000) @Pattern(regexp = DESCRIPTION) String description
    ) {
        ProductFields fields() {
            return new ProductFields(typeId, name.strip(), description);
        }
    }

    @Schema(additionalProperties = Schema.AdditionalPropertiesValue.FALSE)
    public record EditProduct(
        @NotNull @Positive @Max(MAX_REFERENCE_ID) Integer typeId,
        @NotBlank @Size(max = 120) @Pattern(regexp = NAME) String name,
        @Schema(types = {"string", "null"})
        @Size(max = 2000) @Pattern(regexp = DESCRIPTION) String description,
        @NotNull Status status
    ) {
        ProductFields fields() {
            return new ProductFields(typeId, name.strip(), description);
        }
    }

    @Schema(additionalProperties = Schema.AdditionalPropertiesValue.FALSE)
    public record CreateVariant(
        @NotNull @Positive @Max(MAX_REFERENCE_ID) Integer sizeId,
        @NotNull @Positive @Max(MAX_REFERENCE_ID) Integer colorId,
        @NotBlank @Pattern(regexp = "^[A-Z0-9][A-Z0-9_.-]{0,59}$") String sku,
        @NotNull @Positive @Max(MAX_PRICE_CENTS) Long basePriceCents
    ) {
        NewVariant fields() {
            return new NewVariant(sizeId, colorId, sku, basePriceCents);
        }
    }

    @Schema(additionalProperties = Schema.AdditionalPropertiesValue.FALSE)
    public record EditVariant(
        @NotNull @Positive @Max(MAX_PRICE_CENTS) Long basePriceCents,
        @NotNull Status status
    ) {
    }

    public record ProductView(
        UUID id, int typeId, String name, @Schema(types = {"string", "null"}) String description, Status status
    ) {

        static ProductView from(Product product) {
            return new ProductView(product.id(), product.typeId(), product.name(), product.description(),
                product.status());
        }
    }

    public record VariantView(
        UUID id, UUID productId, int sizeId, int colorId, String sku,
        long basePriceCents, @Schema(allowableValues = "MXN") String currency, Status status
    ) {

        static VariantView from(Variant variant) {
            return new VariantView(variant.id(), variant.productId(), variant.sizeId(), variant.colorId(),
                variant.sku(), variant.basePriceCents(), "MXN", variant.status());
        }
    }

    public record PageView<T>(List<T> items, @Schema(types = {"string", "null"}, format = "uuid") UUID nextCursor) {
    }
}
