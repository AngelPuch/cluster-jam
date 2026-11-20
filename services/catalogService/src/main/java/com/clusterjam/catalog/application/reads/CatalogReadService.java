package com.clusterjam.catalog.application.reads;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.photos.CatalogPhotos.Links;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Slot;
import com.clusterjam.catalog.application.ports.CatalogReadCursors;
import com.clusterjam.catalog.application.ports.CatalogReadStore;
import com.clusterjam.catalog.application.ports.PhotoStorage;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Card;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Compatibility;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Detail;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Filter;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Page;
import com.clusterjam.catalog.application.reads.CatalogReadModels.ProductSize;
import com.clusterjam.catalog.application.reads.CatalogReadModels.References;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Variant;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Isolation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;
import tools.jackson.databind.json.JsonMapper;

@Service
@Transactional(readOnly = true, isolation = Isolation.REPEATABLE_READ)
public class CatalogReadService {

    private final CatalogReadStore store;
    private final CatalogReadCursors cursors;
    private final PhotoStorage storage;
    private final JsonMapper json;

    public CatalogReadService(
        CatalogReadStore store, CatalogReadCursors cursors, PhotoStorage storage, JsonMapper json
    ) {
        this.store = store;
        this.cursors = cursors;
        this.storage = storage;
        this.json = json;
    }

    public Page<Card> search(Filter filter, int limit, String cursor) {
        if (filter.minPrice() != null && filter.maxPrice() != null && filter.minPrice() > filter.maxPrice()) {
            throw new ResponseStatusException(HttpStatus.UNPROCESSABLE_CONTENT);
        }
        String scope = "products:" + limit + ":" + json.writeValueAsString(filter);
        var rows = store.search(filter, cursors.decode(cursor, scope), limit + 1);
        if (rows.size() <= limit) {
            return new Page<>(rows, null);
        }
        return new Page<>(rows.subList(0, limit), cursors.encode(rows.get(limit - 1).id(), scope));
    }

    public Detail detail(UUID productId, int limit, String cursor) {
        var product = store.publishedProduct(productId)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        String scope = "variants:" + productId + ":" + limit;
        var rows = store.publishedVariants(productId, cursors.decode(cursor, scope), limit + 1);
        Page<Variant> page;
        if (rows.size() <= limit) {
            page = new Page<>(rows, null);
        } else {
            page = new Page<>(rows.subList(0, limit), cursors.encode(rows.get(limit - 1).id(), scope));
        }
        List<Integer> colors = page.items().stream().map(Variant::colorId).distinct().toList();
        return new Detail(product.id(), product.typeId(), product.name(), product.description(),
            page, store.photos(productId, colors));
    }

    public Links links(Slot slot) {
        var photo = store.publishedPhoto(slot).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        Instant expires = Instant.now().plusSeconds(60);
        return new Links(storage.sign(photo.bucket(), photo.original(), 60),
            storage.sign(photo.bucket(), photo.thumbnail(), 60), expires);
    }

    public Compatibility compatibility(UUID id, boolean commerce) {
        return store.compatibility(id, commerce).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    public ProductSize productSize(UUID productId, int sizeId) {
        return store.productSize(productId, sizeId)
            .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    public References references() {
        return store.references();
    }
}
