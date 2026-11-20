package com.clusterjam.catalog.application.photos;

import java.time.Instant;
import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.application.ports.PhotoStorage;
import com.clusterjam.catalog.application.ports.PhotoStore;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Objects;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Photo;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Pixels;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Slot;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PhotoTransactions {

    private final PhotoStore store;
    private final PhotoStorage storage;

    public PhotoTransactions(PhotoStore store, PhotoStorage storage) {
        this.store = store;
        this.storage = storage;
    }

    @Transactional
    public Objects prepare() {
        Objects objects = Objects.fresh(storage.bucket());
        store.queue(objects, Instant.now().plusSeconds(3600));
        return objects;
    }

    @Transactional(readOnly = true)
    public Photo get(Slot slot) {
        return store.photo(slot).orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND));
    }

    @Transactional
    public Photo replace(UUID actor, Slot slot, String match, boolean create, Objects objects, Pixels pixels) {
        store.lockTask(objects.id()).orElseThrow(() -> new ResponseStatusException(HttpStatus.CONFLICT));
        store.lockProduct(slot);
        Optional<Photo> previous = store.photo(slot);
        check(previous, match, create);

        storage.upload(objects.bucket(), objects.original(), pixels.original());
        storage.upload(objects.bucket(), objects.thumbnail(), pixels.thumbnail());
        Photo saved = store.save(slot, objects);
        previous.ifPresent(old -> queueOld(old));
        store.audit(actor, saved, "PHOTO_REPLACE");
        store.removeTask(objects.id());
        return saved;
    }

    @Transactional
    public Photo retire(UUID actor, Slot slot, String match) {
        store.lockProduct(slot);
        Photo previous = get(slot);
        check(Optional.of(previous), match, false);
        Photo retired = store.retire(slot);
        store.audit(actor, retired, "PHOTO_RETIRE");
        queueOld(previous);
        return retired;
    }

    private void queueOld(Photo photo) {
        store.queue(new Objects(UUID.randomUUID(), photo.bucket(), photo.original(), photo.thumbnail()),
            Instant.now().plusSeconds(300));
    }

    private void check(Optional<Photo> previous, String match, boolean create) {
        if (create) {
            if (previous.isPresent()) {
                throw new ResponseStatusException(HttpStatus.PRECONDITION_FAILED);
            }
        } else if (previous.isEmpty() || !previous.get().etag().equals(match)) {
            throw new ResponseStatusException(HttpStatus.PRECONDITION_FAILED);
        }
    }
}
