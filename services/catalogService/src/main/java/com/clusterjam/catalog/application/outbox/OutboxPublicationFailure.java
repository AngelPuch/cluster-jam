package com.clusterjam.catalog.application.outbox;

import java.util.UUID;

public final class OutboxPublicationFailure extends RuntimeException {

    private final UUID messageId;

    public OutboxPublicationFailure(UUID messageId, String code) {
        super(code);
        this.messageId = messageId;
    }

    public UUID messageId() {
        return messageId;
    }
}
