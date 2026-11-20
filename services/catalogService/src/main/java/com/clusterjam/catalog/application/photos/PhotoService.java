package com.clusterjam.catalog.application.photos;

import java.time.Instant;
import java.util.UUID;
import java.util.concurrent.Semaphore;

import com.clusterjam.catalog.application.ports.PhotoImages;
import com.clusterjam.catalog.application.ports.PhotoStorage;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Links;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Photo;
import com.clusterjam.catalog.application.photos.CatalogPhotos.Slot;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PhotoService {

    private final PhotoTransactions transactions;
    private final PhotoImages images;
    private final PhotoStorage storage;
    private final Semaphore uploads = new Semaphore(2);

    public PhotoService(PhotoTransactions transactions, PhotoImages images, PhotoStorage storage) {
        this.transactions = transactions;
        this.images = images;
        this.storage = storage;
    }

    public Photo replace(UUID actor, Slot slot, String match, boolean create, byte[] bytes) {
        if (!uploads.tryAcquire()) {
            throw new PhotoFailure(PhotoFailure.Reason.BUSY);
        }
        try {
            var pixels = images.normalize(bytes);
            var objects = transactions.prepare();
            return transactions.replace(actor, slot, match, create, objects, pixels);
        } finally {
            uploads.release();
        }
    }

    public Photo get(Slot slot) {
        return transactions.get(slot);
    }

    public Photo retire(UUID actor, Slot slot, String match) {
        return transactions.retire(actor, slot, match);
    }

    public Links links(Slot slot) {
        Photo photo = get(slot);
        if (!photo.active()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND);
        }
        Instant expires = Instant.now().plusSeconds(60);
        String original = storage.sign(photo.bucket(), photo.original(), 60);
        String thumbnail = storage.sign(photo.bucket(), photo.thumbnail(), 60);
        return new Links(original, thumbnail, expires);
    }
}
