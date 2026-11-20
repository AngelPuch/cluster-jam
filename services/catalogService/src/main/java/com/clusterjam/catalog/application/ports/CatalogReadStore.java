package com.clusterjam.catalog.application.ports;

import java.util.List;
import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.application.photos.CatalogPhotos.Photo;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Slot;
import com.clusterjam.catalog.application.products.CatalogProducts.Product;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Card;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Compatibility;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Filter;
import com.clusterjam.catalog.application.reads.CatalogReadModels.PhotoRef;
import com.clusterjam.catalog.application.reads.CatalogReadModels.ProductSize;
import com.clusterjam.catalog.application.reads.CatalogReadModels.References;
import com.clusterjam.catalog.application.reads.CatalogReadModels.Variant;

public interface CatalogReadStore {

    List<Card> search(Filter filter, UUID after, int limit);

    Optional<Product> publishedProduct(UUID id);

    List<Variant> publishedVariants(UUID productId, UUID after, int limit);

    List<PhotoRef> photos(UUID productId, List<Integer> colors);

    Optional<Photo> publishedPhoto(Slot slot);

    Optional<Compatibility> compatibility(UUID variantId, boolean commerce);

    Optional<ProductSize> productSize(UUID productId, int sizeId);

    References references();
}
