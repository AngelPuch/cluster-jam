package com.clusterjam.catalog.infrastructure.database;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.application.photos.CatalogPhotos.Objects;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Photo;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Side;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Slot;
import com.clusterjam.catalog.application.ports.PhotoStore;
import com.clusterjam.catalog.infrastructure.database.models.CatalogAuditEntity;
import com.clusterjam.catalog.infrastructure.database.models.CatalogPhotoEntity;
import com.clusterjam.catalog.infrastructure.database.models.CatalogPhotoTaskEntity;
import com.clusterjam.catalog.infrastructure.database.repositories.CatalogPhotoJpaRepository;
import com.clusterjam.catalog.infrastructure.database.repositories.CatalogPhotoTaskJpaRepository;
import com.clusterjam.catalog.infrastructure.database.repositories.CatalogProductJpaRepository;
import com.clusterjam.catalog.infrastructure.database.repositories.CatalogVariantJpaRepository;
import jakarta.persistence.EntityManager;
import org.springframework.data.domain.Limit;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Repository;
import org.springframework.web.server.ResponseStatusException;

@Repository
public class CatalogPhotoJpaStore implements PhotoStore {

    private final CatalogPhotoJpaRepository photos;
    private final CatalogPhotoTaskJpaRepository tasks;
    private final CatalogProductJpaRepository products;
    private final CatalogVariantJpaRepository variants;
    private final EntityManager entities;

    public CatalogPhotoJpaStore(
        CatalogPhotoJpaRepository photos, CatalogPhotoTaskJpaRepository tasks,
        CatalogProductJpaRepository products, CatalogVariantJpaRepository variants, EntityManager entities
    ) {
        this.photos = photos;
        this.tasks = tasks;
        this.products = products;
        this.variants = variants;
        this.entities = entities;
    }

    @Override
    public void lockProduct(Slot slot) {
        products.findLockedById(slot.productId()).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        if (!variants.existsByProductIdAndColorId(slot.productId(), (short) slot.colorId())) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
    }

    private Optional<CatalogPhotoEntity> entity(Slot slot) {
        return photos.findByProductIdAndColorIdAndSide(slot.productId(), (short) slot.colorId(),
            slot.side() == Side.FRONT ? "FRENTE" : "ESPALDA");
    }

    @Override
    public Optional<Photo> photo(Slot slot) {
        return entity(slot).map(CatalogPhotoEntity::toPhoto);
    }

    @Override
    public Photo save(Slot slot, Objects objects) {
        var photo = entity(slot).orElseGet(() -> new CatalogPhotoEntity(slot, objects));
        photo.replace(objects);
        return photos.saveAndFlush(photo).toPhoto();
    }

    @Override
    public Photo retire(Slot slot) {
        var photo = entity(slot).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
        photo.retire();
        return photos.saveAndFlush(photo).toPhoto();
    }

    @Override
    public void audit(UUID actor, Photo photo, String action) {
        entities.persist(new CatalogAuditEntity(actor, photo.id(), action, photo.version(), photo.active()));
    }

    @Override
    public void queue(Objects objects, Instant after) {
        entities.persist(new CatalogPhotoTaskEntity(objects, after));
        entities.flush();
    }

    @Override
    public Optional<Objects> lockTask(UUID id) {
        return tasks.findLockedById(id).map(CatalogPhotoTaskEntity::objects);
    }

    @Override
    public boolean isDue(UUID id, Instant now) {
        return tasks.findById(id).map(row -> row.due(now)).orElse(false);
    }

    @Override
    public List<UUID> dueTasks(Instant now) {
        return tasks.findByCleanupAfterLessThanEqualOrderByCleanupAfterAsc(now, Limit.of(10))
            .stream().map(row -> row.objects().id()).toList();
    }

    @Override
    public boolean referenced(Objects objects) {
        return photos.referenced(objects.bucket(), objects.original(), objects.thumbnail());
    }

    @Override
    public void removeTask(UUID id) {
        tasks.deleteById(id);
    }
}
