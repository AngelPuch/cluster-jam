package com.clusterjam.catalog.application.products;

import java.util.List;
import java.util.UUID;
import java.util.function.Function;

import com.clusterjam.catalog.application.ports.CatalogProductStore;
import com.clusterjam.catalog.application.products.CatalogProductException.Reason;
import com.clusterjam.catalog.application.products.CatalogProducts.Change;
import com.clusterjam.catalog.application.products.CatalogProducts.NewVariant;
import com.clusterjam.catalog.application.products.CatalogProducts.Page;
import com.clusterjam.catalog.application.products.CatalogProducts.Product;
import com.clusterjam.catalog.application.products.CatalogProducts.ProductFields;
import com.clusterjam.catalog.application.products.CatalogProducts.Resource;
import com.clusterjam.catalog.application.products.CatalogProducts.Status;
import com.clusterjam.catalog.application.products.CatalogProducts.Variant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class CatalogProductService {

    private final CatalogProductStore store;

    public CatalogProductService(CatalogProductStore store) {
        this.store = store;
    }

    public Page<Product> products(UUID after, int limit) {
        return page(store.products(after, limit + 1), limit, Product::id);
    }

    public Product product(UUID id) {
        return store.product(id).orElseThrow(() -> new CatalogProductException(Reason.MISSING));
    }

    public Page<Variant> variants(UUID productId, UUID after, int limit) {
        product(productId);
        return page(store.variants(productId, after, limit + 1), limit, Variant::id);
    }

    public Variant variant(UUID productId, UUID id) {
        return store.variant(productId, id).orElseThrow(() -> new CatalogProductException(Reason.MISSING));
    }

    @Transactional
    public Product createProduct(UUID actor, ProductFields fields) {
        Product created = store.insertProduct(fields);
        store.record(new Change(actor, Resource.PRODUCT, created.id(), null,
            created.status(), null, null, created.version()));
        return created;
    }

    @Transactional
    public Product editProduct(UUID actor, UUID id, int version, ProductFields fields, Status status) {
        Product before = product(id);
        validateEdit(before.version(), version, before.status(), status);
        Product updated = store.updateProduct(id, fields, status);
        store.record(new Change(actor, Resource.PRODUCT, id, before.status(),
            updated.status(), null, null, updated.version()));
        return updated;
    }

    @Transactional
    public Variant createVariant(UUID actor, UUID productId, NewVariant fields) {
        product(productId);
        Variant created = store.insertVariant(productId, fields);
        store.initializeInventory(created.id());
        store.record(new Change(actor, Resource.VARIANT, created.id(), null,
            created.status(), null, created.basePriceCents(), created.version()));
        return created;
    }

    @Transactional
    public Variant editVariant(UUID actor, UUID productId, UUID id, int version, long price, Status status) {
        Variant before = variant(productId, id);
        validateEdit(before.version(), version, before.status(), status);
        Variant updated = store.updateVariant(productId, id, price, status);
        store.record(new Change(actor, Resource.VARIANT, id, before.status(),
            updated.status(), before.basePriceCents(), updated.basePriceCents(), updated.version()));
        return updated;
    }

    private void validateEdit(int currentVersion, int version, Status currentStatus, Status status) {
        if (currentVersion != version) {
            throw new CatalogProductException(Reason.STALE);
        }
        if (currentStatus != Status.DRAFT && status == Status.DRAFT) {
            throw new CatalogProductException(Reason.INVALID_TRANSITION);
        }
    }

    private <T> Page<T> page(List<T> rows, int limit, Function<T, UUID> id) {
        if (rows.size() <= limit) {
            return new Page<>(rows, null);
        }
        return new Page<>(rows.subList(0, limit), id.apply(rows.get(limit - 1)));
    }
}
