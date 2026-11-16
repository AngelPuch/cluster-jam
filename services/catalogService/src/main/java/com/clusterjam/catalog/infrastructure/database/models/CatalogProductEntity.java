package com.clusterjam.catalog.infrastructure.database.models;

import com.clusterjam.catalog.application.products.CatalogProducts.Product;
import com.clusterjam.catalog.application.products.CatalogProducts.ProductFields;
import com.clusterjam.catalog.application.products.CatalogProducts.Status;
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Table;

@Entity
@Table(schema = "app", name = "producto")
public class CatalogProductEntity extends CatalogVersionedEntity {

    @Column(name = "tipo_prenda_id", nullable = false)
    private short typeId;

    @Column(name = "nombre", nullable = false, length = 120)
    private String name;

    @Column(name = "descripcion", columnDefinition = "text")
    private String description;

    protected CatalogProductEntity() {
    }

    public CatalogProductEntity(ProductFields fields) {
        setFields(fields);
    }

    public void edit(ProductFields fields, Status status) {
        setFields(fields);
        markEdited(status);
    }

    public Product toProduct() {
        return new Product(id, typeId, name, description, status, version);
    }

    private void setFields(ProductFields fields) {
        typeId = (short) fields.typeId();
        name = fields.name();
        description = fields.description();
    }
}
