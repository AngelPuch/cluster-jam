package com.clusterjam.catalog.infrastructure.database.models;

import java.util.UUID;

import com.clusterjam.catalog.application.products.CatalogProducts.NewVariant;
import com.clusterjam.catalog.application.products.CatalogProducts.Status;
import com.clusterjam.catalog.application.products.CatalogProducts.Variant;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(schema = "app", name = "variante")
public class CatalogVariantEntity extends CatalogVersionedEntity {

    @Column(name = "producto_id", nullable = false, updatable = false)
    private UUID productId;

    @Column(name = "talla_id", nullable = false, updatable = false)
    private short sizeId;

    @Column(name = "color_id", nullable = false, updatable = false)
    private short colorId;

    @Column(nullable = false, updatable = false, length = 60)
    private String sku;

    @Column(name = "precio_base_centavos", nullable = false)
    private long basePriceCents;

    protected CatalogVariantEntity() {
    }

    public CatalogVariantEntity(UUID productId, NewVariant fields) {
        this.productId = productId;
        sizeId = (short) fields.sizeId();
        colorId = (short) fields.colorId();
        sku = fields.sku();
        basePriceCents = fields.basePriceCents();
    }

    public void edit(long price, Status status) {
        basePriceCents = price;
        markEdited(status);
    }

    public Variant toVariant() {
        return new Variant(id, productId, sizeId, colorId, sku, basePriceCents, status, version);
    }
}
