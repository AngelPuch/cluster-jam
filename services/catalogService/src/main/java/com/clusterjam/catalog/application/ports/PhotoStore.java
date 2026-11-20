package com.clusterjam.catalog.application.ports;

import java.time.Instant;
import java.util.List;
import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.application.photos.CatalogPhotos.Objects;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Photo;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Slot;

public interface PhotoStore {

    void lockProduct(Slot slot);

    Optional<Photo> photo(Slot slot);

    Photo save(Slot slot, Objects objects);

    Photo retire(Slot slot);

    void audit(UUID actor, Photo photo, String action);

    void queue(Objects objects, Instant after);

    Optional<Objects> lockTask(UUID id);

    boolean isDue(UUID id, Instant now);

    List<UUID> dueTasks(Instant now);

    boolean referenced(Objects objects);

    void removeTask(UUID id);
}
