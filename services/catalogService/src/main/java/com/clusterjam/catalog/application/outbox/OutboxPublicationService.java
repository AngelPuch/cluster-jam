package com.clusterjam.catalog.application.outbox;

import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.application.ports.CatalogEventPublisher;
import com.clusterjam.catalog.application.ports.OutboxStore;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OutboxPublicationService {

    private final OutboxStore store;
    private final CatalogEventPublisher publisher;

    public OutboxPublicationService(OutboxStore store, CatalogEventPublisher publisher) {
        this.store = store;
        this.publisher = publisher;
    }

    @Transactional
    public Optional<UUID> publishNext() {
        var pending = store.nextPending();
        if (pending.isEmpty()) {
            return Optional.empty();
        }
        OutboxEvent event = pending.orElseThrow();
        publisher.publish(event);
        try {
            store.markPublished(event.messageId());
        } catch (RuntimeException databaseFailure) {
            throw new OutboxPublicationFailure(event.messageId(), "OUTBOX_WRITE_FAILED");
        }
        return Optional.of(event.messageId());
    }
}
