package com.clusterjam.catalog.application.ports;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.application.products.CatalogProducts.Change;
import com.clusterjam.catalog.application.products.CatalogProducts.NewVariant;
import com.clusterjam.catalog.application.products.CatalogProducts.Product;
import com.clusterjam.catalog.application.products.CatalogProducts.ProductFields;
import com.clusterjam.catalog.application.products.CatalogProducts.Status;
import com.clusterjam.catalog.application.products.CatalogProducts.Variant;

public interface CatalogProductStore {

    List<Product> products(UUID after, int limit);

    Optional<Product> product(UUID id);

    Product insertProduct(ProductFields fields);

    Product updateProduct(UUID id, ProductFields fields, Status status);

    List<Variant> variants(UUID productId, UUID after, int limit);

    Optional<Variant> variant(UUID productId, UUID id);

    Variant insertVariant(UUID productId, NewVariant input);

    Variant updateVariant(UUID productId, UUID id, long price, Status status);

    void initializeInventory(UUID variantId);

    void record(Change change);
}
