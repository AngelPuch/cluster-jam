package com.clusterjam.catalog.infrastructure.database.models;

import java.util.UUID;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(schema = "app", name = "inventario")
public class CatalogInventoryEntity {

    @Id
    @Column(name = "variante_id")
    private UUID variantId;

    @Column(name = "stock_fisico", insertable = false, updatable = false, nullable = false)
    private int physical;

    @Column(name = "stock_reservado", insertable = false, updatable = false, nullable = false)
    private int reserved;

    protected CatalogInventoryEntity() {
    }

    public CatalogInventoryEntity(UUID variantId) {
        this.variantId = variantId;
    }
}
