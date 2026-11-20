package com.clusterjam.catalog.application.photos;

import java.time.Instant;
import java.util.List;
import java.util.UUID;

import com.clusterjam.catalog.application.ports.PhotoStorage;
import com.clusterjam.catalog.application.ports.PhotoStore;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PhotoCleanup {

    private final PhotoStore store;
    private final PhotoStorage storage;

    public PhotoCleanup(PhotoStore store, PhotoStorage storage) {
        this.store = store;
        this.storage = storage;
    }

    @Transactional(readOnly = true)
    public List<UUID> due() {
        return store.dueTasks(Instant.now());
    }

    @Transactional
    public void clean(UUID id) {
        var task = store.lockTask(id);
        if (task.isEmpty() || !store.isDue(id, Instant.now()) || store.referenced(task.get())) {
            return;
        }
        var objects = task.get();
        storage.delete(objects.bucket(), objects.original());
        storage.delete(objects.bucket(), objects.thumbnail());
        store.removeTask(id);
    }
}
