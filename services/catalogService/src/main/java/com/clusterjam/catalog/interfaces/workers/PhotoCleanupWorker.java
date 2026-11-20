package com.clusterjam.catalog.interfaces.workers;

import com.clusterjam.catalog.application.photos.PhotoCleanup;
import com.clusterjam.catalog.application.photos.PhotoFailure;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Component;
import org.springframework.transaction.TransactionException;

@Component
public class PhotoCleanupWorker {

    private static final Logger LOG = LoggerFactory.getLogger(PhotoCleanupWorker.class);
    private final PhotoCleanup cleanup;

    public PhotoCleanupWorker(PhotoCleanup cleanup) {
        this.cleanup = cleanup;
    }

    @Scheduled(fixedDelayString = "${catalog.photos.cleanup-delay-ms:60000}")
    public void run() {
        try {
            for (var id : cleanup.due()) {
                try {
                    cleanup.clean(id);
                } catch (PhotoFailure | DataAccessException | TransactionException failure) {
                    LOG.warn("Photo cleanup deferred for task {}", id);
                }
            }
        } catch (DataAccessException | TransactionException unavailable) {
            LOG.warn("Photo cleanup is waiting for PostgreSQL");
        }
    }
}
