package com.clusterjam.catalog.application.ports;

import java.util.Optional;
import java.util.UUID;

import com.clusterjam.catalog.application.outbox.OutboxEvent;

public interface OutboxStore {

    Optional<OutboxEvent> nextPending();

    void markPublished(UUID messageId);
}
