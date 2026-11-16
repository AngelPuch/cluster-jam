package com.clusterjam.catalog.infrastructure.database;

import java.sql.SQLException;
import java.util.List;
import java.util.Optional;
import java.util.UUID;
import java.util.function.Supplier;

import com.clusterjam.catalog.application.ports.CatalogProductStore;
import com.clusterjam.catalog.application.products.CatalogProductException;
import com.clusterjam.catalog.application.products.CatalogProductException.Reason;
import com.clusterjam.catalog.application.products.CatalogProducts.Change;
import com.clusterjam.catalog.application.products.CatalogProducts.NewVariant;
import com.clusterjam.catalog.application.products.CatalogProducts.Product;
import com.clusterjam.catalog.application.products.CatalogProducts.ProductFields;
import com.clusterjam.catalog.application.products.CatalogProducts.Status;
import com.clusterjam.catalog.application.products.CatalogProducts.Variant;
import com.clusterjam.catalog.infrastructure.database.models.CatalogAuditEntity;
import com.clusterjam.catalog.infrastructure.database.models.CatalogInventoryEntity;
import com.clusterjam.catalog.infrastructure.database.models.CatalogProductEntity;
import com.clusterjam.catalog.infrastructure.database.models.CatalogVariantEntity;
import com.clusterjam.catalog.infrastructure.database.repositories.CatalogProductJpaRepository;
import com.clusterjam.catalog.infrastructure.database.repositories.CatalogVariantJpaRepository;
import jakarta.persistence.EntityManager;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.data.domain.Limit;
import org.springframework.stereotype.Repository;

@Repository
public class CatalogProductJpaStore implements CatalogProductStore {

    private final CatalogProductJpaRepository products;
    private final CatalogVariantJpaRepository variants;
    private final EntityManager entities;

    public CatalogProductJpaStore(
        CatalogProductJpaRepository products,
        CatalogVariantJpaRepository variants,
        EntityManager entities
    ) {
        this.products = products;
        this.variants = variants;
        this.entities = entities;
    }

    @Override
    public List<Product> products(UUID after, int limit) {
        Limit bound = Limit.of(limit);
        var rows = after == null ? products.findAllByOrderByIdAsc(bound)
            : products.findByIdGreaterThanOrderByIdAsc(after, bound);
        return rows.stream().map(CatalogProductEntity::toProduct).toList();
    }

    @Override
    public Optional<Product> product(UUID id) {
        return products.findById(id).map(CatalogProductEntity::toProduct);
    }

    @Override
    public Product insertProduct(ProductFields fields) {
        return write(() -> products.saveAndFlush(new CatalogProductEntity(fields))).toProduct();
    }

    @Override
    public Product updateProduct(UUID id, ProductFields fields, Status status) {
        var product = products.findById(id).orElseThrow(() -> new CatalogProductException(Reason.MISSING));
        product.edit(fields, status);
        return write(() -> products.saveAndFlush(product)).toProduct();
    }

    @Override
    public List<Variant> variants(UUID productId, UUID after, int limit) {
        Limit bound = Limit.of(limit);
        var rows = after == null ? variants.findByProductIdOrderByIdAsc(productId, bound)
            : variants.findByProductIdAndIdGreaterThanOrderByIdAsc(productId, after, bound);
        return rows.stream().map(CatalogVariantEntity::toVariant).toList();
    }

    @Override
    public Optional<Variant> variant(UUID productId, UUID id) {
        return variants.findByProductIdAndId(productId, id).map(CatalogVariantEntity::toVariant);
    }

    @Override
    public Variant insertVariant(UUID productId, NewVariant input) {
        return write(() -> variants.saveAndFlush(new CatalogVariantEntity(productId, input))).toVariant();
    }

    @Override
    public Variant updateVariant(UUID productId, UUID id, long price, Status status) {
        var variant = variants.findByProductIdAndId(productId, id)
            .orElseThrow(() -> new CatalogProductException(Reason.MISSING));
        variant.edit(price, status);
        return write(() -> variants.saveAndFlush(variant)).toVariant();
    }

    @Override
    public void initializeInventory(UUID variantId) {
        entities.persist(new CatalogInventoryEntity(variantId));
    }

    @Override
    public void record(Change change) {
        entities.persist(new CatalogAuditEntity(change));
    }

    private <T> T write(Supplier<T> statement) {
        try {
            return statement.get();
        } catch (DataIntegrityViolationException exception) {
            if (exception.getMostSpecificCause() instanceof SQLException cause) {
                switch (cause.getSQLState()) {
                    case "23503" -> throw new CatalogProductException(Reason.INVALID_REFERENCE);
                    case "23505" -> throw new CatalogProductException(Reason.DUPLICATE);
                    default -> throw exception;
                }
            }
            throw exception;
        }
    }
}
